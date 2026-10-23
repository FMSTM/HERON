"""Анкета, тема и init не пишут, не резервируют и не удаляют вне папки сайта.

Каждый сценарий подменяет часть папки сайта ссылкой наружу, выполняет
команду и проверяет: отказ E024, а снаружи не изменилось ни байта.
Отдельно — уникальные резервные копии и путь архива у `theme get`.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron import setup
from heron.cli import main
from heron.core.errors import HeronError
from heron.scaffold import adopt, create
from heron.setup import files as files_module
from heron.setup.answers import read
from heron.themes import install, pack

MARK = "outside-MARKER"


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="S", languages=["en"], demo=True)
    return root


def _outside(tmp_path: Path) -> Path:
    out = tmp_path / "outside"
    out.mkdir()
    (out / "keep.txt").write_text(MARK, encoding="utf-8")
    return out


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def _answers(root: Path, **publish):
    answers = read(setup.raw_config(root))
    data = answers.model_dump()
    data["site"]["name"] = "Changed"
    data["publish"].update(publish)
    return setup.Answers.model_validate(data)


def _refused(call) -> None:
    with pytest.raises(HeronError) as error:
        call()
    assert error.value.code == "E024"


def test_symlinked_site_yaml(tmp_path):
    root = _site(tmp_path)
    out = _outside(tmp_path)
    external = out / "site.yaml"
    external.write_bytes((root / "site.yaml").read_bytes())
    (root / "site.yaml").unlink()
    (root / "site.yaml").symlink_to(external)
    before = _snapshot(out)
    _refused(lambda: setup.apply(root, _answers(root)))
    assert _snapshot(out) == before


def test_symlinked_content_on_a_new_language(tmp_path):
    root = _site(tmp_path)
    out = _outside(tmp_path)
    (root / "content").rename(out / "content")
    (root / "content").symlink_to(out / "content")
    before = _snapshot(out)
    answers = _answers(root)
    data = answers.model_dump()
    data["site"]["languages"] = ["en", "de"]
    _refused(lambda: setup.apply(root, setup.Answers.model_validate(data)))
    assert _snapshot(out) == before
    assert "Changed" not in (root / "site.yaml").read_text("utf-8")  # отказ до записи


def test_symlinked_helpers_folder(tmp_path):
    root = _site(tmp_path)
    out = _outside(tmp_path)
    (out / "scripts").mkdir()
    # чужой файл с отметкой анкеты: удаление прежних помощников его бы стёрло
    (out / "scripts" / "build.sh").write_text(f"# {files_module.MARK}\n", encoding="utf-8")
    import shutil

    shutil.rmtree(root / ".heron", ignore_errors=True)
    (root / ".heron").symlink_to(out)
    before = _snapshot(out)
    _refused(lambda: setup.apply(root, _answers(root, helpers={"build": False})))
    _refused(lambda: setup.apply(root, _answers(root)))
    assert _snapshot(out) == before


def test_symlinked_intermediate_folder_of_backups(tmp_path):
    root = _site(tmp_path)
    out = _outside(tmp_path)
    (root / ".heron-cache").mkdir(exist_ok=True)
    (root / ".heron-cache" / "setup").symlink_to(out)
    before = _snapshot(out)
    _refused(lambda: setup.apply(root, _answers(root)))
    _refused(lambda: install(root, "starter", languages=["en"]))
    assert _snapshot(out) == before


def test_symlinked_theme_and_content_on_theme_install(tmp_path):
    root = _site(tmp_path)
    out = _outside(tmp_path)
    import shutil

    shutil.move(str(root / "theme"), str(out / "theme"))
    (root / "theme").symlink_to(out / "theme")
    before = _snapshot(out)
    _refused(lambda: install(root, "starter", languages=["en"]))
    assert _snapshot(out) == before


def test_symlinked_content_on_init(tmp_path):
    root = _site(tmp_path)
    out = _outside(tmp_path)
    for path in (root / "content" / "en").glob("*.md"):
        path.unlink()
    (root / "content" / "en").rmdir()
    (root / "content" / "en").symlink_to(out)
    before = _snapshot(out)
    _refused(lambda: adopt(root, notes="en"))
    assert _snapshot(out) == before


def test_link_inside_the_site_is_allowed(tmp_path):
    root = _site(tmp_path)
    (root / "shared").mkdir()
    (root / ".heron").mkdir(exist_ok=True)
    import shutil

    shutil.rmtree(root / ".heron")
    (root / ".heron").symlink_to(root / "shared")
    setup.apply(root, _answers(root))
    assert (root / "shared" / "scripts" / "build.sh").is_file()


# --- уникальные резервные копии -------------------------------------------------


def test_two_site_yaml_backups_in_one_second_do_not_overwrite(tmp_path, monkeypatch):
    root = _site(tmp_path)
    monkeypatch.setattr(time, "strftime", lambda *_: "20990101-000000")
    first = setup.backup(root, "site.yaml", b"one")
    second = setup.backup(root, "site.yaml", b"two")
    assert first != second
    assert first.read_bytes() == b"one" and second.read_bytes() == b"two"


def test_two_saves_in_one_second_keep_both_versions(tmp_path, monkeypatch):
    root = _site(tmp_path)
    monkeypatch.setattr(time, "strftime", lambda *_: "20990101-000000")
    original = (root / "site.yaml").read_text("utf-8")
    one = setup.apply(root, _answers(root))
    data = _answers(root).model_dump()
    data["site"]["name"] = "Changed again"
    two = setup.apply(root, setup.Answers.model_validate(data))
    assert one.backup and two.backup and one.backup != two.backup
    assert (root / one.backup).read_text("utf-8") == original
    assert "Changed" in (root / two.backup).read_text("utf-8")


def test_two_theme_backups_in_one_second(tmp_path, monkeypatch):
    root = _site(tmp_path)
    monkeypatch.setattr(time, "strftime", lambda *_: "20990101-000000")
    (root / "theme" / "first.txt").write_text("1", encoding="utf-8")
    one = install(root, "starter", languages=["en"])
    (root / "theme" / "second.txt").write_text("2", encoding="utf-8")
    two = install(root, "starter", languages=["en"])
    assert one.backup != two.backup
    assert (root / one.backup / "first.txt").is_file()
    assert (root / two.backup / "second.txt").is_file()
    assert not (root / two.backup / "theme").exists()  # не вложилась в чужую копию


# --- theme get: путь архива ----------------------------------------------------


@pytest.mark.parametrize("where", ["site", "cwd", "absolute"])
def test_theme_get_archive_path(tmp_path, monkeypatch, where):
    root = _site(tmp_path)
    archive = pack(root, root / "mine.tar.gz")
    monkeypatch.chdir(tmp_path)
    if where == "site":
        source = "mine.tar.gz"
    elif where == "cwd":
        (tmp_path / "cwd.tar.gz").write_bytes(Path(archive).read_bytes())
        source = "cwd.tar.gz"
    else:
        source = str(Path(archive).resolve())
    result = CliRunner().invoke(main, ["theme", "get", source, "site"])
    assert result.exit_code == 0, result.output
