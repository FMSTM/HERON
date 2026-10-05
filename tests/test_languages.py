"""Произвольный набор языков: три, два, один.

Сайт объявляет языки в `site.yaml`, и всё, что зависит от языков, — карта
сайта, hreflang, файлы для нейросетей, переключатель, конфиг nginx, —
следует за этим списком, а не за зашитой тройкой.

Спецификация: docs/spec/20-data-contract.md, раздел 3.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from heron.contracts.site import SiteConfig
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.scaffold import create
from tests import sites

HOME = """---
title: {title}
h1: {title}
description: Описание главной
---

Вводный абзац.
"""

PAGE = """---
title: {title}
h1: {title}
description: Описание страницы
---

Текст.
"""


def make(tmp_path: Path, languages: list[str], pages: dict[str, str] | None = None) -> Path:
    """Скелет сайта на заданных языках плюс главная и страница на каждом."""
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=languages)
    sites.clear_content(root)
    if pages is None:
        pages = {}
        for lang in languages:
            pages[f"{lang}/index.md"] = HOME.format(title=f"Главная {lang}")
            pages[f"{lang}/about.md"] = PAGE.format(title=f"О нас {lang}")
    for rel, text in pages.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def head_links(html: str) -> list[tuple[str, str]]:
    return re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', html)


# --- конфиг -----------------------------------------------------------------


def test_default_lang_must_be_listed():
    with pytest.raises(ValueError, match="default_lang"):
        SiteConfig.model_validate(
            {
                "heron": ">=0.1",
                "site": {
                    "domain": "example.com",
                    "theme": "demo",
                    "default_lang": "en",
                    "languages": ["uk", "ru"],
                },
            }
        )


# --- три фикстурных сайта ----------------------------------------------------


@pytest.mark.parametrize("languages", [["uk", "ru", "en"], ["uk", "ru"], ["ru"]])
def test_site_builds_on_any_set_of_languages(tmp_path, languages):
    root = make(tmp_path, languages)
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    default = languages[0]
    assert (dist / "index.html").is_file()
    for lang in languages[1:]:
        assert (dist / lang / "index.html").is_file()
    # языков, которых нет в списке, нет нигде
    for lang in {"uk", "ru", "en"} - set(languages):
        assert not (dist / lang).exists()
        assert not (dist / f"sitemap-{lang}.xml").exists()
    nginx = (dist / ".heron-nginx.conf").read_text(encoding="utf-8")
    assert f"location ^~ /{default}/" not in nginx
    for lang in languages[1:]:
        assert f"location ^~ /{lang}/" in nginx


def test_three_languages_sitemap_is_an_index(tmp_path):
    root = make(tmp_path, ["uk", "ru", "en"])
    pipeline.run(root)
    dist = root / "dist"
    index = (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert "<sitemapindex" in index
    for lang in ("uk", "ru", "en"):
        assert f"/sitemap-{lang}.xml" in index
        assert (dist / f"sitemap-{lang}.xml").is_file()


def test_two_languages_get_two_sitemaps_and_hreflang(tmp_path):
    root = make(tmp_path, ["uk", "ru"])
    pipeline.run(root)
    dist = root / "dist"
    assert sorted(p.name for p in dist.glob("sitemap*.xml")) == [
        "sitemap-ru.xml",
        "sitemap-uk.xml",
        "sitemap.xml",
    ]
    links = dict(head_links((dist / "ru" / "about" / "index.html").read_text(encoding="utf-8")))
    assert links == {
        "ru": "https://demo.example/ru/about/",
        "uk": "https://demo.example/about/",
        "x-default": "https://demo.example/about/",
    }
    llms = sorted(p.name for p in dist.glob("llms*.txt"))
    assert "llms-uk.txt" in llms and "llms-ru.txt" in llms


def test_one_language_has_no_hreflang_no_index_no_language_files(tmp_path):
    root = make(tmp_path, ["ru"])
    result = pipeline.run(root)
    dist = root / "dist"

    sitemap = (dist / "sitemap.xml").read_text(encoding="utf-8")
    assert "<urlset" in sitemap and "<sitemapindex" not in sitemap
    assert "https://demo.example/about/" in sitemap
    assert not list(dist.glob("sitemap-*.xml"))

    html = (dist / "about" / "index.html").read_text(encoding="utf-8")
    assert head_links(html) == []
    assert 'class="langs"' not in html

    assert sorted(p.name for p in dist.glob("llms*.txt")) == ["llms-full.txt", "llms.txt"]
    llms = (dist / "llms.txt").read_text(encoding="utf-8")
    assert "https://demo.example/about/" in llms

    assert all(not page.translations for page in result.site.pages)


def test_language_switcher_marks_missing_translation(tmp_path):
    root = make(
        tmp_path,
        ["uk", "ru"],
        {
            "uk/index.md": HOME.format(title="Головна"),
            "ru/index.md": HOME.format(title="Главная"),
            "uk/only.md": PAGE.format(title="Лише українською"),
        },
    )
    pipeline.run(root)
    html = (root / "dist" / "only" / "index.html").read_text(encoding="utf-8")
    assert '<li aria-disabled="true">ru</li>' in html
    home = (root / "dist" / "index.html").read_text(encoding="utf-8")
    assert 'href="/ru/"' in home


# --- страница только не на основном языке ------------------------------------


def test_page_only_in_second_language(tmp_path):
    root = make(
        tmp_path,
        ["uk", "ru"],
        {
            "uk/index.md": HOME.format(title="Головна"),
            "ru/index.md": HOME.format(title="Главная"),
            "ru/news.md": PAGE.format(title="Только по-русски"),
        },
    )
    result = pipeline.run(root)
    assert not result.failed
    dist = root / "dist"

    assert "https://demo.example/ru/news/" in (dist / "sitemap-ru.xml").read_text(encoding="utf-8")
    links = head_links((dist / "ru" / "news" / "index.html").read_text(encoding="utf-8"))
    assert links == [("ru", "https://demo.example/ru/news/")]

    said = [w for w in result.collector.warnings if w.kind == "переводы"]
    assert any("ru/news.md" in (w.path or "") and "'uk'" in w.message for w in said)


# --- пустой язык ------------------------------------------------------------


def _uk_empty(tmp_path: Path) -> Path:
    return make(
        tmp_path,
        ["uk", "ru"],
        {"ru/index.md": HOME.format(title="Главная"), "ru/about.md": PAGE.format(title="О нас")},
    )


def test_empty_default_language_builds_in_dev(tmp_path):
    root = _uk_empty(tmp_path)
    result = pipeline.run(root, env=BuildEnv.named("dev"))
    assert not result.failed
    assert (root / "dist" / "ru" / "about" / "index.html").is_file()
    said = [w for w in result.collector.warnings if w.kind == "языки"]
    assert any("'uk'" in w.message for w in said)
    # пока основного языка нет, страницам второго не о чем напоминать по одной
    assert not [w for w in result.collector.warnings if w.kind == "переводы"]


def test_empty_default_language_stops_prod_naming_the_language(tmp_path):
    root = _uk_empty(tmp_path)
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert result.failed
    errors = result.collector.errors
    assert [e.code for e in errors] == ["E021"]
    assert "'uk'" in str(errors[0])


def test_empty_second_language_is_only_a_warning_in_prod(tmp_path):
    root = make(
        tmp_path,
        ["uk", "ru"],
        {"uk/index.md": HOME.format(title="Головна")},
    )
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed
    assert any("'ru'" in w.message for w in result.collector.warnings if w.kind == "языки")


def test_all_languages_empty_is_e017_in_prod(tmp_path):
    root = make(tmp_path, ["uk", "ru"], {})
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert [e.code for e in result.collector.errors] == ["E017"]
