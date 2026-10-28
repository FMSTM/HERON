"""robots_meta: крупные превью только индексируемым страницам прод-сборки."""

from __future__ import annotations

import re
from pathlib import Path

from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.scaffold import create
from tests import sites

LARGE = "max-image-preview:large, max-snippet:-1, max-video-preview:-1"
CLOSED = "noindex, nofollow"


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")
    sites.clear_content(root)
    lang = next(p.name for p in (root / "content").iterdir() if p.is_dir())
    sites.build(
        root,
        {
            f"{lang}/index.md": sites.page("Главная"),
            f"{lang}/open.md": sites.page("Открытая"),
            f"{lang}/secret.md": sites.page("Закрытая", noindex=True),
        },
    )
    return root


def _robots(root: Path, name: str) -> str:
    html = (root / "dist").rglob(f"{name}/index.html")
    text = next(html).read_text(encoding="utf-8")
    found = re.findall(r'<meta name="robots" content="([^"]*)">', text)
    assert len(found) == 1, found
    return found[0]


def _build(root: Path, env: BuildEnv) -> None:
    result = pipeline.run(root, env=env)
    assert not result.failed


def test_prod_page_gets_large_preview(tmp_path):
    root = _site(tmp_path)
    _build(root, BuildEnv.named("prod"))
    assert _robots(root, "open") == LARGE


def test_prod_noindex_page_stays_closed(tmp_path):
    root = _site(tmp_path)
    _build(root, BuildEnv.named("prod"))
    assert _robots(root, "secret") == CLOSED


def test_dev_closes_everything(tmp_path):
    root = _site(tmp_path)
    _build(root, BuildEnv.named("dev"))
    assert _robots(root, "open") == CLOSED
    assert _robots(root, "secret") == CLOSED


def test_prod_with_indexable_off_is_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("SITE_INDEXABLE", "0")
    root = _site(tmp_path)
    _build(root, BuildEnv.resolve("prod"))
    assert _robots(root, "open") == CLOSED


def test_theme_without_robots_meta_still_renders(tmp_path):
    root = _site(tmp_path)
    base = root / "theme" / "templates" / "base.html"
    if not base.is_file():
        base = next((root / "theme").rglob("base.html"))
    text = base.read_text(encoding="utf-8")
    text = re.sub(r'<meta name="robots"[^>]*>', "", text)
    base.write_text(text, encoding="utf-8")
    _build(root, BuildEnv.named("prod"))
    html = next((root / "dist").rglob("open/index.html")).read_text(encoding="utf-8")
    assert "robots_meta" not in html
