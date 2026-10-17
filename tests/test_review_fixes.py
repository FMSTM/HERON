"""Находки независимой проверки исправлений — каждая наблюдаемым поведением."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from heron.core import build as pipeline
from heron.core import media, watch
from heron.scaffold import create
from tests.nginx_server import needs_nginx, serve

PAGE = "---\ntitle: {t}\nh1: {t} page\ndescription: D\n{extra}---\n\nText.\n"


def make(tmp_path: Path, gone=None, langs=("en", "ru")) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=list(langs))
    if gone:
        data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
        data["gone"] = gone
        (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), "utf-8")
    return root


def write(root: Path, rel: str, text: str) -> None:
    path = root / "content" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def codes(result) -> list[str]:
    return [e.code for e in result.collector.errors]


# --- 301/410: один адрес со слешем и без ---------------------------------------


def test_gone_and_redirect_on_the_same_file_path_with_and_without_slash(tmp_path):
    root = make(tmp_path, gone=["/a.html"])
    write(root, "en/x.md", PAGE.format(t="X", extra="redirect_from: [/a.html/]\n"))
    assert "E022" in codes(pipeline.run(root))


def test_two_redirects_that_differ_only_by_the_slash(tmp_path):
    root = make(tmp_path)
    write(root, "en/x.md", PAGE.format(t="X", extra="redirect_from: [/a.html, /a.html/]\n"))
    assert "E009" in codes(pipeline.run(root))


@pytest.mark.parametrize("entry", ["/404.html/", "/ru/404/index.html/", "/ru/404/index.html"])
def test_gone_on_service_pages_with_any_slash_is_e022(tmp_path, entry):
    root = make(tmp_path, gone=[entry])
    assert "E022" in codes(pipeline.run(root))


@pytest.mark.parametrize("bad", ["/a%0Ab/", "/a%00b/"])
def test_control_characters_in_old_addresses(tmp_path, bad):
    root = make(tmp_path, gone=[bad])
    assert "E022" in codes(pipeline.run(root))
    root2 = tmp_path / "two"
    root2.mkdir()
    create(root2, name="demo", languages=["en"])
    (root2 / "content/en/x.md").write_text(
        PAGE.format(t="X", extra=f"redirect_from: ['{bad}']\n"), encoding="utf-8"
    )
    assert "E009" in codes(pipeline.run(root2))


# --- сегменты адреса из папок -------------------------------------------------------


@pytest.mark.parametrize("folder", ["a$b", "with space", ".hidden", "Upper", "папка"])
def test_folder_names_are_checked_like_file_names(tmp_path, folder):
    root = make(tmp_path)
    write(root, f"en/{folder}/x.md", PAGE.format(t="X", extra="redirect_from: [/old-x/]\n"))
    result = pipeline.run(root)
    assert "E005" in codes(result)


def test_folder_slug_rescues_a_folder_name(tmp_path):
    root = make(tmp_path)
    write(root, "en/Upper/_index.md", PAGE.format(t="Sec", extra="slug: upper\n"))
    write(root, "en/Upper/x.md", PAGE.format(t="X", extra=""))
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (root / "dist/upper/x/index.html").is_file()


# --- запись результата не выходит из dist -----------------------------------------


def test_stale_cleanup_never_follows_a_symlinked_folder(tmp_path):
    root = make(tmp_path, langs=("en",))
    write(root, "en/docs/a.md", PAGE.format(t="A", extra=""))
    pipeline.run(root)
    outside = tmp_path / "outside"
    (outside / "docs/a").mkdir(parents=True)
    (outside / "docs/a/index.html").write_text("foreign", encoding="utf-8")
    outside.chmod(0o700)
    import shutil

    shutil.rmtree(root / "dist/docs")
    os.symlink(outside / "docs", root / "dist/docs")
    (root / "content/en/docs/a.md").unlink()
    pipeline.run(root)
    assert (outside / "docs/a/index.html").read_text(encoding="utf-8") == "foreign"
    assert outside.stat().st_mode & 0o777 == 0o700  # чужую папку не открыли


@pytest.mark.parametrize("name", [".heron-manifest.json", ".heron-staging/a.txt"])
def test_static_cannot_take_the_ledger_names(tmp_path, name):
    root = make(tmp_path, langs=("en",))
    target = root / "static" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")
    assert "E026" in codes(pipeline.run(root))


def test_theme_template_symlink_out_is_e024(tmp_path):
    root = make(tmp_path, langs=("en",))
    secret = tmp_path / "secret.html"
    secret.write_text("SECRET-OUTSIDE", encoding="utf-8")
    partials = root / "theme" / "partials"
    partials.mkdir(exist_ok=True)
    os.symlink(secret, partials / "leak.html")
    page = root / "theme/templates/page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</h1>", '</h1>{% include "partials/leak.html" %}', 1
        ),
        encoding="utf-8",
    )
    write(root, "en/a.md", PAGE.format(t="A", extra=""))
    result = pipeline.run(root)
    assert "E024" in codes(result)
    if (root / "dist").exists():
        assert not any(
            b"SECRET-OUTSIDE" in p.read_bytes() for p in (root / "dist").rglob("*") if p.is_file()
        )


# --- кэш: уборка не мешает живой сборке ------------------------------------------


def test_sweep_waits_while_a_build_uses_the_cache(tmp_path):
    import time

    cache = tmp_path / "cache"
    entry = media.store(cache) / ("0" * 64)
    entry.mkdir(parents=True)
    (entry / "crop-1x1-400.webp").write_bytes(b"x")
    later = time.time() + 400 * 86400
    with media.using(cache):
        assert media.sweep(cache, now=later) == []  # занято — не убирает
        assert entry.exists()
    assert media.sweep(cache, now=later) == [entry]


# --- наблюдатель -------------------------------------------------------------------


def test_snapshot_survives_a_file_vanishing_mid_walk(tmp_path, monkeypatch):
    root = make(tmp_path, langs=("en",))
    gone = root / "content/en/tmp.md"
    gone.write_text("x", encoding="utf-8")
    original = Path.stat

    def flaky(self, *a, **k):
        if self == gone:
            raise FileNotFoundError(self)
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "stat", flaky)
    found = watch.snapshot(root)
    assert "content/en/tmp.md" not in found


@needs_nginx
def test_language_404_stays_404_with_gone_entries(tmp_path):
    root = make(tmp_path, gone=["/old/"])
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:
        assert get("/ru/missing/")[0] == 404
        assert get("/old/")[0] == 410
