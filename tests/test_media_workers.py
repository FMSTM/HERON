"""Нарезка: сбой пула процессов не валит сборку, ошибки воркера — валят.

Спецификация: docs/spec/21-engine.md, «Сколько процессов».
"""

import errno
import shutil
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image

from heron.cli import main
from heron.contracts.theme import ImagesSpec
from heron.core import media, tree
from heron.core.errors import HeronError
from heron.scaffold import create
from tests import sites

MASTERS = ["media/a.png", "media/b.png", "media/c.png"]


class Notes:
    """Приёмник хода сборки, запоминающий замечания."""

    def __init__(self) -> None:
        self.notes: list[str] = []
        self.ticks: list[tuple[int, int, str]] = []

    def step(self, title: str) -> None: ...

    def done(self, detail: str = "", **fields: object) -> None: ...

    def tick(self, current: int, total: int, detail: str = "") -> None:
        self.ticks.append((current, total, detail))

    def note(self, key: str, **fields: object) -> None:
        self.notes.append(key)


def prepared(tmp_path: Path):
    files = {"uk/index.md": sites.page("Головна")}
    for number, src in enumerate(MASTERS):
        files[f"uk/p{number}.md"] = sites.page(f"P{number}", image=src, image_alt="Фото")
    sites.build(tmp_path, files)
    for number, src in enumerate(MASTERS):
        target = tmp_path / src
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (900, 900), (40 * number + 20, 80, 120)).save(target)
    return tree.scan(tmp_path / "content", sites.config())


def spec() -> ImagesSpec:
    return ImagesSpec.model_validate({"widths": [400, 800], "ratios": ["1:1"], "formats": ["webp"]})


def run(tmp_path: Path, site, collector, workers: int, progress=None) -> dict[str, bytes]:
    media.build(
        site,
        tmp_path,
        tmp_path / "dist",
        spec(),
        collector,
        cache_dir=tmp_path / ".heron-cache",
        workers=workers,
        progress=progress,
    )
    dist = tmp_path / "dist"
    return {p.relative_to(dist).as_posix(): p.read_bytes() for p in dist.rglob("*") if p.is_file()}


def reset(tmp_path: Path) -> None:
    shutil.rmtree(tmp_path / "dist", ignore_errors=True)
    shutil.rmtree(tmp_path / ".heron-cache", ignore_errors=True)


class Pool:
    """Пул без процессов: первые `ok` задач выполняет, остальные «умирают».

    `ok=None` — выполняет все. Исключение задачи ложится в future, как в настоящем пуле.
    """

    ok: int | None = None

    def __init__(self, max_workers=None) -> None:
        self.sent = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        future: Future = Future()
        self.sent += 1
        if type(self).ok is not None and self.sent > type(self).ok:
            future.set_exception(BrokenProcessPool("worker died"))
            return future
        try:
            future.set_result(fn(*args))
        except BaseException as error:  # noqa: BLE001 - как делает настоящий пул
            future.set_exception(error)
        return future


@pytest.fixture
def calls(monkeypatch):
    """Счётчик вызовов slice_master (и в «пуле», и в последовательной ветке)."""
    seen: list[str] = []
    real = media.slice_master

    def counting(src, source, spec_, wanted):
        seen.append(src)
        return real(src, source, spec_, wanted)

    monkeypatch.setattr(media, "slice_master", counting)
    return seen


def test_pool_cannot_be_created_encodes_sequentially_with_same_bytes(tmp_path, monkeypatch, calls):
    site, collector = prepared(tmp_path)
    reference = run(tmp_path, site, collector, workers=1)
    assert reference
    reset(tmp_path)
    calls.clear()

    def refuse(max_workers=None):
        raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(media, "ProcessPoolExecutor", refuse)
    progress = Notes()
    assert run(tmp_path, site, collector, workers=4, progress=progress) == reference
    assert len(calls) == len(MASTERS)
    assert progress.notes == ["pool_fallback"]  # предупреждение одно
    assert [t[0] for t in progress.ticks] == [1, 2, 3]


def test_broken_pool_does_not_reencode_finished_masters(tmp_path, monkeypatch, calls):
    site, collector = prepared(tmp_path)
    reference = run(tmp_path, site, collector, workers=1)
    reset(tmp_path)
    calls.clear()

    class Dying(Pool):
        ok = 1

    monkeypatch.setattr(media, "ProcessPoolExecutor", Dying)
    progress = Notes()
    assert run(tmp_path, site, collector, workers=4, progress=progress) == reference
    assert len(calls) == len(MASTERS)  # ни одного повтора: 1 в пуле + 2 после сбоя
    assert len(set(calls)) == len(MASTERS)
    assert progress.notes == ["pool_fallback"]
    assert [t[0] for t in progress.ticks] == [1, 2, 3]  # прогресс не дублируется


def test_worker_error_is_not_swallowed_and_does_not_trigger_fallback(tmp_path, monkeypatch, calls):
    site, collector = prepared(tmp_path)
    real = media.slice_master  # уже со счётчиком из фикстуры calls

    def failing(src, source, spec_, wanted):
        if src == MASTERS[1]:
            raise HeronError(code="E007", message="битая картинка")
        return real(src, source, spec_, wanted)

    monkeypatch.setattr(media, "slice_master", failing)
    monkeypatch.setattr(media, "ProcessPoolExecutor", Pool)
    progress = Notes()
    with pytest.raises(HeronError) as raised:
        run(tmp_path, site, collector, workers=4, progress=progress)
    assert raised.value.code == "E007"
    assert progress.notes == []
    assert len(calls) == len(set(calls))  # фолбэк не включался: повторов нет


@pytest.mark.parametrize(
    "error",
    [
        OSError(errno.ENOSPC, "No space left on device"),
        PermissionError(errno.EACCES, "Permission denied"),  # диск в воркере — не сбой пула
        ValueError("bad pixels"),
    ],
)
def test_worker_oserror_and_valueerror_are_not_pool_failures(tmp_path, monkeypatch, calls, error):
    site, collector = prepared(tmp_path)

    def failing(src, source, spec_, wanted):
        calls.append(src)
        raise error

    monkeypatch.setattr(media, "slice_master", failing)
    monkeypatch.setattr(media, "ProcessPoolExecutor", Pool)
    progress = Notes()
    with pytest.raises(type(error)):
        run(tmp_path, site, collector, workers=4, progress=progress)
    assert progress.notes == []
    assert len(calls) == len(MASTERS)


def test_pool_creation_error_with_foreign_errno_is_not_a_pool_failure(tmp_path, monkeypatch):
    site, collector = prepared(tmp_path)

    def broken(max_workers=None):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(media, "ProcessPoolExecutor", broken)
    with pytest.raises(OSError):
        run(tmp_path, site, collector, workers=4)


def test_workers_one_and_four_give_identical_dist(tmp_path):
    site, collector = prepared(tmp_path)
    one = run(tmp_path, site, collector, workers=1)
    reset(tmp_path)
    four = run(tmp_path, site, collector, workers=4)
    assert one.keys() == four.keys() and len(one) >= len(MASTERS)
    assert one == four


def _spy(monkeypatch) -> list[int]:
    seen: list[int] = []
    real = media.finish

    def finish(*args, **kwargs):
        seen.append(kwargs.get("workers"))
        return real(*args, **kwargs)

    monkeypatch.setattr(media, "finish", finish)
    return seen


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"])
    return root


def test_flag_and_env_choose_the_worker_count(tmp_path, monkeypatch):
    root = _site(tmp_path)
    seen = _spy(monkeypatch)
    runner = CliRunner()
    monkeypatch.delenv("HERON_WORKERS", raising=False)

    assert runner.invoke(main, ["build", str(root), "--workers", "1"]).exit_code == 0
    monkeypatch.setenv("HERON_WORKERS", "1")
    assert runner.invoke(main, ["build", str(root)]).exit_code == 0
    # флаг сильнее переменной, переменная — сильнее site.yaml
    assert runner.invoke(main, ["build", str(root), "--workers", "2"]).exit_code == 0
    monkeypatch.delenv("HERON_WORKERS")
    assert runner.invoke(main, ["build", str(root)]).exit_code == 0
    assert seen == [1, 1, 2, 0]


def test_workers_flag_out_of_range_is_a_click_error(tmp_path):
    root = _site(tmp_path)
    result = CliRunner().invoke(main, ["build", str(root), "--workers", "65"])
    assert result.exit_code == 2
    assert "65" in result.output


@pytest.mark.parametrize("value", ["65", "-1", "many", "1.5"])
def test_bad_env_value_is_a_heron_error(tmp_path, monkeypatch, value):
    root = _site(tmp_path)
    monkeypatch.setenv("HERON_WORKERS", value)
    result = CliRunner().invoke(main, ["build", str(root)])
    assert result.exit_code == 1
    assert "HERON_WORKERS" in result.output
    head = next(line for line in result.output.splitlines() if "E011" in line)
    assert "site.yaml" not in head
