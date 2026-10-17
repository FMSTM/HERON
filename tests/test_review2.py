"""Вторая проверка исправлений: каждый сценарий — наблюдаемым поведением.

Все чужие и «секретные» файлы создаются только во временных папках.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from PIL import Image

from heron.core import build as pipeline
from heron.core import media, output, watch
from heron.core.errors import HeronError
from heron.scaffold import create
from tests.nginx_server import needs_nginx, serve

ROOT = Path(__file__).resolve().parents[1]
PAGE = "---\ntitle: {t}\nh1: {t} page\ndescription: D\n{extra}---\n\nText {t}.\n"
SECRET = "чужое-содержимое"


def make(tmp_path: Path, langs=("en",), name="site") -> Path:
    root = tmp_path / name
    root.mkdir()
    create(root, name="demo", languages=list(langs))
    return root


def write(root: Path, rel: str, text: str) -> None:
    path = root / "content" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def site_yaml(root: Path, change) -> None:
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def codes(result) -> list[str]:
    return [e.code for e in result.collector.errors]


def snapshot(dist: Path) -> dict[str, bytes]:
    return {p.relative_to(dist).as_posix(): p.read_bytes() for p in dist.rglob("*") if p.is_file()}


# --- 1. кэш не выходит за свои пределы -----------------------------------------


def test_sweep_does_not_follow_a_symlinked_version_folder(tmp_path):
    cache = tmp_path / "cache"
    outside = tmp_path / "outside"
    (outside / "entry").mkdir(parents=True)
    (outside / "entry" / "keep.txt").write_text(SECRET, encoding="utf-8")
    (cache / media.SLICES).mkdir(parents=True)
    os.symlink(outside, cache / media.SLICES / "v1-old")  # «старая версия» — ссылка наружу
    entry_link = media.store(cache)
    entry_link.mkdir(parents=True)
    os.symlink(outside / "entry", entry_link / ("0" * 64))
    media.sweep(cache, now=time.time() + 400 * 86400)
    assert (outside / "entry" / "keep.txt").read_text(encoding="utf-8") == SECRET


def test_cache_entry_symlink_out_is_e024_and_writes_nothing_outside(tmp_path):
    root = make(tmp_path)
    (root / "media").mkdir(exist_ok=True)
    Image.new("RGB", (900, 900), (10, 20, 30)).save(root / "media" / "p.png")
    write(root, "en/a.md", PAGE.format(t="A", extra="image: media/p.png\nimage_alt: x\n"))
    outside = tmp_path / "outside"
    outside.mkdir()
    store = media.store(root / ".heron-cache")
    store.mkdir(parents=True)
    os.symlink(outside, store / media.digest(root / "media" / "p.png"))
    with pytest.raises(HeronError) as error:
        pipeline.run(root)
    assert error.value.code == "E024"
    assert list(outside.iterdir()) == []


def test_legacy_cache_link_is_removed_not_followed(tmp_path):
    cache = tmp_path / "site" / ".heron-cache"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text(SECRET, encoding="utf-8")
    cache.mkdir(parents=True)
    os.symlink(outside, cache / "media")  # прежний формат кэша — ссылкой
    media._forget_legacy(cache)
    assert (outside / "keep.txt").read_text(encoding="utf-8") == SECRET


# --- 2. сами папки static, assets, i18n ------------------------------------------


@pytest.mark.parametrize("folder", ["static", "theme/assets"])
def test_folder_itself_symlinked_out_is_e024(tmp_path, folder):
    root = make(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "leak.txt").write_text(SECRET, encoding="utf-8")
    target = root / folder
    if target.exists():
        shutil.rmtree(target)
    os.symlink(foreign, target)
    with pytest.raises(HeronError) as error:
        pipeline.run(root)
    assert error.value.code == "E024"
    if (root / "dist").exists():
        assert not any(
            SECRET.encode() in p.read_bytes() for p in (root / "dist").rglob("*") if p.is_file()
        )


def test_i18n_file_symlinked_out_is_e024(tmp_path):
    root = make(tmp_path)
    foreign = tmp_path / "en.yaml"
    foreign.write_text(f"read_more: {SECRET}\n", encoding="utf-8")
    strings = root / "theme" / "i18n" / "en.yaml"
    strings.unlink()
    os.symlink(foreign, strings)
    with pytest.raises(HeronError) as error:
        pipeline.run(root)
    assert error.value.code == "E024"


# --- 3, 14. scripts/site.sh -----------------------------------------------------


def site_sh(tmp_path: Path, engine_exit: int) -> tuple[Path, Path, dict]:
    """Копия site.sh во временной папке и docker-заглушка, имитирующая движок."""
    heron = tmp_path / "heron"
    (heron / "scripts").mkdir(parents=True, exist_ok=True)
    (heron / "env").mkdir(exist_ok=True)
    shutil.copy(ROOT / "scripts/site.sh", heron / "scripts/site.sh")
    site = tmp_path / "content-site"
    site.mkdir(exist_ok=True)
    (site / "site.yaml").write_text("site: {}\n", encoding="utf-8")
    (heron / "env/.env.demo.dev").write_text(
        f"SITE_PATH={site}\nSITE_ENV=dev\nENGINE=ghcr.io/fmstm/heron:prod\n", encoding="utf-8"
    )
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "docker").write_text(
        f'#!/bin/sh\ncase "$1" in buildx|image|pull|inspect) exit 0 ;; esac\nexit {engine_exit}\n',
        encoding="utf-8",
    )
    (stub / "docker").chmod(0o755)
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"}
    return heron, heron / "out" / "demo-dev", env


def test_failed_rebuild_keeps_the_previous_site(tmp_path):
    heron, out, env = site_sh(tmp_path, engine_exit=1)
    out.mkdir(parents=True)
    (out / "index.html").write_text("previous good site", encoding="utf-8")
    done = subprocess.run(
        ["bash", str(heron / "scripts/site.sh"), "demo", "build", "dev"],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert done.returncode != 0
    assert (out / "index.html").read_text(encoding="utf-8") == "previous good site"


def test_site_sh_without_a_terminal_under_strict_bash(tmp_path):
    """Пустой массив tty под set -u: в bash 3.2 (macOS) — unbound variable.

    Новые bash этого не видят, поэтому проверяется сама запись раскрытия:
    ни одного голого "${массив[@]}" в скрипте.
    """
    text = (ROOT / "scripts/site.sh").read_text(encoding="utf-8")
    import re

    bare = [m for m in re.findall(r'"\$\{(\w+)\[@\]\}"', text)]
    guarded = re.findall(r'\$\{(\w+)\[@\]\+"\$\{\1\[@\]\}"\}', text)
    assert set(bare) <= set(guarded), bare
    heron, out, env = site_sh(tmp_path, engine_exit=0)
    done = subprocess.run(
        ["bash", str(heron / "scripts/site.sh"), "demo", "check", "dev"],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert "unbound variable" not in done.stderr
    assert done.returncode == 0, done.stderr


# --- 4, 12. чужие файлы и прерванная запись ---------------------------------------


def test_foreign_file_on_a_needed_path_is_e026_before_any_change(tmp_path):
    root = make(tmp_path)
    write(root, "en/a.md", PAGE.format(t="A", extra=""))
    pipeline.run(root)
    before = snapshot(root / "dist")
    write(root, "en/b.md", PAGE.format(t="B", extra=""))
    (root / "dist/b").mkdir()
    (root / "dist/b/index.html").write_text(SECRET, encoding="utf-8")  # положил не движок
    with pytest.raises(HeronError) as error:
        pipeline.run(root)
    assert error.value.code == "E026"
    after = snapshot(root / "dist")
    assert after.pop("b/index.html") == SECRET.encode()
    assert after == before


def test_interrupted_commit_is_cleaned_up_by_the_next_build(tmp_path, monkeypatch):
    root = make(tmp_path)
    write(root, "en/a.md", PAGE.format(t="A", extra=""))
    pipeline.run(root)
    (root / "dist/keep.txt").write_text("foreign", encoding="utf-8")
    write(root, "en/b.md", PAGE.format(t="B", extra=""))
    write(root, "en/c.md", PAGE.format(t="C", extra=""))

    real = output.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        if str(dst).endswith("c/index.html"):
            raise OSError("диск кончился")
        calls["n"] += 1
        return real(src, dst)

    monkeypatch.setattr(output.os, "replace", flaky)
    with pytest.raises(OSError):
        pipeline.run(root)
    monkeypatch.setattr(output.os, "replace", real)
    assert (root / "dist/b/index.html").is_file()  # успел лечь до обрыва

    (root / "content/en/b.md").unlink()  # входы изменились
    (root / "content/en/c.md").unlink()
    result = pipeline.run(root)
    assert not result.failed
    assert not (root / "dist/b").exists()  # своё лишнее убрано
    assert (root / "dist/keep.txt").read_text(encoding="utf-8") == "foreign"
    assert output.previous(root / "dist") == set(result.written)


def test_legacy_dist_without_manifest_is_adopted(tmp_path):
    """Сборка прошлой версии движка (без манифеста) — не «чужие файлы»."""
    root = make(tmp_path)
    write(root, "en/a.md", PAGE.format(t="A", extra=""))
    pipeline.run(root)
    (root / "dist" / output.MANIFEST).unlink()
    (root / "dist/a/index.html").write_text("old engine", encoding="utf-8")
    result = pipeline.run(root)
    assert not result.failed


# --- 5. подменённый nginx-конфиг --------------------------------------------------


@needs_nginx
def test_overridden_nginx_config_is_what_nginx_t_checks(tmp_path):
    root = make(tmp_path)
    (root / "static").mkdir(exist_ok=True)
    (root / "static" / ".heron-nginx.conf").write_text("server { this is broken", "utf-8")
    site_yaml(root, lambda d: d.setdefault("build", {}).update(overrides=[".heron-nginx.conf"]))
    result = pipeline.run(root, strict=True)
    assert result.report.nginx_test is not None and result.report.nginx_test[0] is False
    assert result.failed and not (root / "dist").exists()


# --- 6, 7. плагины ----------------------------------------------------------------


PLUGIN = """
def register(hooks):
    hooks.on("on_page_rendered", lambda page, html: html.replace("</body>", "<i>one</i></body>"))
    hooks.on("on_page_rendered", lambda page, html: html.replace("</body>", "<i>two</i></body>"))
    def boom(site, config, dist):
        raise RuntimeError("уведомление не ушло")
    hooks.on("on_build_finished", boom)
"""


def plugin_site(tmp_path: Path) -> Path:
    root = make(tmp_path)
    folder = root / "plugins" / "chain"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text(PLUGIN, encoding="utf-8")
    site_yaml(root, lambda d: d.update(plugins=["chain"]))
    return root


def test_rendered_hooks_are_chained(tmp_path):
    root = plugin_site(tmp_path)
    pipeline.run(root)
    html = (root / "dist/index.html").read_text(encoding="utf-8")
    assert "<i>one</i><i>two</i></body>" in html


def test_finishing_step_failure_is_a_separate_status(tmp_path):
    from click.testing import CliRunner

    from heron.cli import main

    root = plugin_site(tmp_path)
    result = pipeline.run(root)
    assert not result.failed  # сайт собран и записан
    assert (root / "dist/index.html").is_file()
    assert any("уведомление не ушло" in e for e in result.finish_errors)
    cli = CliRunner().invoke(main, ["build", str(root)])
    assert cli.exit_code == 3
    assert "Сайт записан и цел" in cli.output or "site is written" in cli.output


# --- 8. внутренние ссылки каталогов -----------------------------------------------


def test_internal_folder_links_keep_their_paths_and_cycles_stop(tmp_path):
    root = make(tmp_path)
    static = root / "static"
    (static / "v2").mkdir(parents=True)
    (static / "v2" / "guide.txt").write_text("guide", encoding="utf-8")
    os.symlink(static / "v2", static / "latest")  # второй, законный путь
    os.symlink(static, static / "v2" / "loop")  # петля
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (root / "dist/v2/guide.txt").read_text(encoding="utf-8") == "guide"
    assert (root / "dist/latest/guide.txt").read_text(encoding="utf-8") == "guide"


# --- 9. нечитаемые исходники ------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root читает всё; права не проверить")
def test_unreadable_source_folder_is_e030(tmp_path):
    root = make(tmp_path)
    write(root, "en/hidden/a.md", PAGE.format(t="A", extra=""))
    folder = root / "content/en/hidden"
    folder.chmod(0)
    try:
        with pytest.raises(HeronError) as error:
            pipeline.run(root)
        assert error.value.code == "E030"
    finally:
        folder.chmod(0o755)


def test_unreadable_source_folder_is_e030_even_for_root(tmp_path, monkeypatch):
    """Права root не ограничивают — отказ чтения имитируется."""
    root = make(tmp_path)
    write(root, "en/hidden/a.md", PAGE.format(t="A", extra=""))
    real = os.scandir

    def deny(path="."):
        if str(path).endswith("hidden"):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", deny)
    with pytest.raises(HeronError) as error:
        pipeline.run(root)
    assert error.value.code == "E030"
    assert not (root / "dist").exists()


# --- 10. наблюдатель ----------------------------------------------------------------


def test_watcher_sees_local_plugin_sources(tmp_path):
    root = plugin_site(tmp_path)
    before = watch.snapshot(root)
    (root / "plugins/chain/__init__.py").write_text(PLUGIN + "\n# правка\n", encoding="utf-8")
    assert "plugins/chain/__init__.py" in watch.changed(before, watch.snapshot(root))


# --- 11. граница префикса 410 ----------------------------------------------------


@needs_nginx
def test_raw_prefix_keeps_its_boundary(tmp_path):
    root = make(tmp_path)
    site_yaml(root, lambda d: d.update(gone=["/%D0/*"]))
    write(root, "en/a.md", PAGE.format(t="A", extra=""))
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:
        assert get("/%D0/anything/")[0] == 410
        assert get("/%D0extra/")[0] == 404
        assert get("/a/")[0] == 200


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


@pytest.mark.skipif(not _docker_ready(), reason="нет докера для bash 3.2")
def test_site_sh_runs_under_real_bash_3_2(tmp_path):
    """macOS по умолчанию — bash 3.2: там пустой массив под set -u — ошибка."""
    work = tmp_path / "w"
    (work / "heron/scripts").mkdir(parents=True)
    (work / "heron/env").mkdir()
    (work / "site").mkdir()
    (work / "bin").mkdir()
    shutil.copy(ROOT / "scripts/site.sh", work / "heron/scripts/site.sh")
    (work / "site/site.yaml").write_text("site: {}\n", encoding="utf-8")
    (work / "heron/env/.env.demo.dev").write_text(
        "SITE_PATH=/w/site\nSITE_ENV=dev\nENGINE=ghcr.io/fmstm/heron:prod\n", encoding="utf-8"
    )
    (work / "bin/docker").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (work / "bin/docker").chmod(0o755)
    image = os.environ.get("HERON_BASH32_IMAGE", "bash:3.2")
    done = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{work}:/w",
            "-e",
            "PATH=/w/bin:/usr/local/bin:/usr/bin:/bin",
            image,
            "bash",
            "/w/heron/scripts/site.sh",
            "demo",
            "check",
            "dev",
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert "unbound variable" not in done.stderr, done.stderr
    assert done.returncode == 0, done.stderr
