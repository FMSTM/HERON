"""Документация не расходится с движком.

Имена из 21 §7 есть в контексте шаблона, `heron docs` находит новые темы.
Спецификация: docs/ru/spec/21-engine.md §7 («Обложка и `robots_meta` в шаблоне»),
§10 («heron docs»).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from heron import docs
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.scaffold import create
from tests import sites

ROOT = Path(__file__).resolve().parents[1]
SPEC = "spec/21-engine.md"
ANCHOR = '<a id="cover-robots"></a>'

# Слово → языки, на которых оно обязано находиться (русское слово в en не ищем).
SEARCH_WORDS = {
    "обложка": ("ru",),
    "cover": ("ru", "en"),
    "alternateName": ("ru", "en"),
    "sitelinks": ("ru", "en"),
    "max-image-preview": ("ru", "en"),
    "old-urls": ("ru", "en"),
}


def section7_names(lang: str) -> list[str]:
    """Имена из списка «Кроме перечисленного, шаблон получает» (выражение для шаблона)."""
    text = (ROOT / "docs" / lang / SPEC).read_text(encoding="utf-8")
    start = text.index(ANCHOR)
    nxt = re.search(r"^#{2,3} ", text[start:], re.MULTILINE)
    block = text[start : start + nxt.start()] if nxt else text[start:]
    names = []
    for line in block.splitlines():
        match = re.match(r"- `([A-Za-z_][\w.]*)(\(?)", line)
        if match:
            names.append(match.group(1) + ("(page)" if match.group(2) else ""))
    return names


def test_section7_mentions_the_start_names():
    names = [n.split("(")[0] for n in section7_names("ru")]
    assert {"page.cover", "cover_url", "robots_meta"} <= set(names)


@pytest.mark.parametrize("lang", docs.LANGS)
def test_section7_names_are_the_same_in_both_languages(lang):
    assert section7_names(lang) == section7_names("ru")


@pytest.mark.parametrize("lang", docs.LANGS)
def test_every_name_of_section7_exists_in_template_context(tmp_path, lang):
    """Шаблон с каждым именем рендерится: StrictUndefined валит сборку на выдуманном имени."""
    names = section7_names(lang)
    assert names
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")
    sites.clear_content(root)
    content_lang = next(p.name for p in (root / "content").iterdir() if p.is_dir())
    sites.build(root, {f"{content_lang}/index.md": sites.page("Главная")})
    probe = "\n".join(f"[{name}]={{{{ {name} }}}}" for name in names) + "\n"
    templates = root / "theme" / "templates"
    for template in templates.glob("*.html"):
        template.write_text(probe, encoding="utf-8")
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, result
    html = "".join(p.read_text(encoding="utf-8") for p in (root / "dist").rglob("index.html"))
    for name in names:
        assert f"[{name}]=" in html, name
    assert "max-image-preview:large" in html


@pytest.mark.parametrize("word", SEARCH_WORDS)
def test_search_finds_every_new_word(word):
    for lang in SEARCH_WORDS[word]:
        found = docs.search(word, lang)
        assert found, f"{word!r} не найдено в docs ({lang})"


def test_seo_topic_opens_the_google_section():
    for lang in docs.LANGS:
        text = (docs.root() / "docs" / lang / "guide" / "05-seo.md").read_text(encoding="utf-8")
        assert 'id="google-images-sitelinks"' in text
        resolved = docs.resolve("seo", lang)
        assert resolved.path.endswith("guide/05-seo.md")


def test_theme_and_seo_topics_exist():
    assert docs.topic("seo") is not None
    assert docs.topic("theme") is not None
