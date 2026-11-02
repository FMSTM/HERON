"""Обложка страницы: `page.cover` и `cover_url` — один источник для og:image и разметки."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from heron.contracts.frontmatter import PageMeta
from heron.core import build as pipeline
from heron.core.media import Manifest, Rendition
from heron.core.models import Page, Section
from heron.core.render import env as envmod
from heron.messages import rendered
from heron.scaffold import create
from tests import sites

SEO = {"og_default_image": "media/default.png", "og_default_image_ru": "media/default-ru.png"}


@pytest.fixture
def config():
    return sites.config(
        site={
            "domain": "example.com",
            "theme": "demo",
            "default_lang": "uk",
            "languages": ["uk", "ru"],
            "name": "Сайт",
            "name_ru": "Сайт по-русски",
        },
        seo=SEO,
    )


def _page(lang: str = "uk", intro: str = "", hero: str = "", **meta) -> Page:
    page = Page(
        lang=lang,
        source=f"{lang}/x.md",
        key="x",
        meta=PageMeta(title="T", h1="H", description="D", **meta),
    )
    if intro:
        page.intro = Section(id="intro", title="", level=0, raw=intro)
    if hero:
        page.sections["hero"] = Section(id="hero", title="Hero", level=2, raw=hero)
    return page


def _rendition(src: str, ratio: str, width: int, height: int, fmts: dict) -> Rendition:
    stem = src.rsplit(".", 1)[0]
    sources = {
        fmt: [(w, f"{stem}-{ratio.replace(':', 'x')}-{w}.{ext}") for w in widths]
        for fmt, (ext, widths) in fmts.items()
    }
    return Rendition(ratio=ratio, width=width, height=height, sources=sources)


@pytest.fixture
def manifest() -> Manifest:
    """Мастер PNG 1600 px с JPEG/PNG-вариантами и мастер WEBP 1600 px без них."""
    out = Manifest()
    png = "media/og.png"
    out.add(
        png,
        {
            "1:1": _rendition(png, "1:1", 800, 800, {"origin": ("png", [400, 800])}),
            "16:9": _rendition(
                png, "16:9", 1600, 900, {"webp": ("webp", [1600]), "origin": ("png", [800, 1600])}
            ),
            "4:3": _rendition(png, "4:3", 1200, 900, {"origin": ("png", [1200])}),
        },
    )
    webp = "media/master.webp"
    out.add(
        webp,
        {"16:9": _rendition(webp, "16:9", 1600, 900, {"origin": ("webp", [800, 1200, 1600])})},
    )
    for raw in ("media/image.png", "media/intro.png", "media/hero.png"):
        out.raw.add(raw)
    out.raw.update({"media/default.png", "media/default-ru.png"})
    return out


# --- порядок выбора -------------------------------------------------------------


def test_og_image_wins_over_everything(config):
    page = _page(og_image="media/og.png", image="media/image.png", intro="![a](media/intro.png)")
    assert page.cover_source(config) == ("media/og.png", "")


def test_image_when_no_og_image(config):
    page = _page(image="./media/image.png", image_alt="Фото", intro="![a](media/intro.png)")
    assert page.cover_source(config) == ("media/image.png", "Фото")


def test_first_picture_of_intro_then_hero(config):
    page = _page(intro="Текст ![В тексте](/media/intro.png)", hero="![Герой](media/hero.png)")
    assert page.cover_source(config) == ("media/intro.png", "В тексте")
    only_hero = _page(intro="Без картинок.", hero="![Герой](media/hero.png)")
    assert only_hero.cover_source(config) == ("media/hero.png", "Герой")


def test_text_skips_non_images_and_code(config):
    page = _page(intro="[памятка](media/doc.pdf) `![x](media/code.png)` ![Да](media/intro.png)")
    assert page.cover_source(config) == ("media/intro.png", "Да")


def test_default_image_of_page_language(config):
    assert _page(lang="uk").cover_source(config) == ("media/default.png", "Сайт")
    assert _page(lang="ru").cover_source(config) == ("media/default-ru.png", "Сайт по-русски")


def test_nothing_at_all_is_none():
    bare = sites.config()
    page = _page()
    assert page.cover_source(bare) is None
    assert page.cover is None


# --- alt ----------------------------------------------------------------------


def test_og_image_alt_from_extra_then_image_alt(config):
    with_own = _page(og_image="media/og.png", og_image_alt="Карточка", image_alt="Фото")
    assert with_own.cover_source(config)[1] == "Карточка"
    fallback = _page(og_image="media/og.png", image_alt="Фото")
    assert fallback.cover_source(config)[1] == "Фото"


# --- page.cover и cover_url -----------------------------------------------------


def _resolve(page: Page, manifest: Manifest, config) -> Page:
    page.cover_of = envmod.cover_of(manifest, config)
    return page


def test_cover_takes_crawler_variant_not_narrower_than_1200(config, manifest):
    page = _resolve(_page(og_image="media/og.png", og_image_alt="Карточка"), manifest, config)
    assert page.cover == {
        "src": "media/og.png",
        "url": "https://example.com/media/og-16x9-1600.png",
        "width": 1600,
        "height": 900,
        "alt": "Карточка",
    }
    url = envmod.cover_url(manifest, config)
    assert url(page) == "https://example.com/media/og-16x9-1600.png"
    # 4:3 на 1200 тоже годится, но 16:9 ближе к карточке ссылки.
    assert url(page, min_width=800) == "https://example.com/media/og-16x9-800.png"


def test_master_without_crawler_variant_gives_master(config, manifest):
    page = _resolve(_page(og_image="media/master.webp"), manifest, config)
    assert envmod.cover_url(manifest, config)(page) == "https://example.com/media/master.webp"
    assert page.cover["url"] == "https://example.com/media/master.webp"
    assert page.cover["width"] is None and page.cover["height"] is None


def test_external_og_image_as_is(config, manifest):
    page = _resolve(_page(og_image="https://cdn.example.org/a.jpg"), manifest, config)
    assert page.cover == {
        "src": "https://cdn.example.org/a.jpg",
        "url": "https://cdn.example.org/a.jpg",
        "width": None,
        "height": None,
        "alt": "",
    }
    assert envmod.cover_url(manifest, config)(page) == "https://cdn.example.org/a.jpg"


def test_no_cover_gives_none_and_empty_url(manifest):
    bare = sites.config()
    page = _resolve(_page(), manifest, bare)
    assert page.cover is None
    assert envmod.cover_url(manifest, bare)(page) == ""


def test_master_missing_on_disk_gives_none(config, manifest):
    page = _resolve(_page(og_image="media/gone.png"), manifest, config)
    assert page.cover is None
    assert envmod.cover_url(manifest, config)(page) == ""


def test_default_image_ru_on_russian_page(config, manifest):
    page = _resolve(_page(lang="ru"), manifest, config)
    assert page.cover["src"] == "media/default-ru.png"
    assert page.cover["url"] == "https://example.com/media/default-ru.png"
    assert page.cover["alt"] == "Сайт по-русски"


# --- сборка целиком ---------------------------------------------------------------


def _png(path: Path, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (120, 80, 40)).save(path)


def _md(title: str, body: str = "Текст.", **fields) -> str:
    lines = [f"{k}: {v}" for k, v in {"title": title, "h1": title, "description": "D"}.items()]
    lines += [f"{k}: {v}" for k, v in fields.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body + "\n"


def test_build_four_pages_and_second_language(tmp_path, monkeypatch):
    root = tmp_path / "s"
    create(root, name="S", languages=["en", "ru"], demo=False)
    sites.clear_content(root)
    for name in ("og", "image", "intro", "default", "default-ru"):
        _png(root / "media" / f"{name}.png", 1600, 900)
    site_yaml = root / "site.yaml"
    site_yaml.write_text(
        site_yaml.read_text(encoding="utf-8")
        + "\nseo:\n  og_default_image: media/default.png\n"
        + "  og_default_image_ru: media/default-ru.png\n",
        encoding="utf-8",
    )
    content = root / "content"
    files = {
        "en/_index.md": _md("Home", og_image="media/og.png"),
        "en/image.md": _md("Image", image="media/image.png", image_alt="Фото"),
        "en/intro.md": _md("Intro", body="![В тексте](media/intro.png)"),
        "en/plain.md": _md("Plain"),
        "ru/_index.md": _md("Главная"),
    }
    for rel, text in files.items():
        (content / rel).parent.mkdir(parents=True, exist_ok=True)
        (content / rel).write_text(text, encoding="utf-8")

    seen: list[dict] = []
    original = envmod.context

    def spy(*args, **kwargs):
        scope = original(*args, **kwargs)
        seen.append(scope)
        return scope

    monkeypatch.setattr(envmod, "context", spy)
    result = pipeline.run(root, dist=tmp_path / "dist")
    assert not result.failed, [e.message for e in result.collector.errors]

    covers = {(s["page"].lang, Path(s["page"].source).name): s for s in seen}
    expected = {
        ("en", "_index.md"): "media/og.png",
        ("en", "image.md"): "media/image.png",
        ("en", "intro.md"): "media/intro.png",
        ("en", "plain.md"): "media/default.png",
        ("ru", "_index.md"): "media/default-ru.png",
    }
    for key, src in expected.items():
        assert key in covers, sorted(covers)
        scope = covers[key]
        cover = scope["page"].cover
        assert cover is not None and cover["src"] == src, key
        url = scope["cover_url"](scope["page"])
        assert url.startswith("https://") and url == cover["url"], key


def _site_pages(config, *pages: Page):
    from heron.core.models import Site

    site = Site()
    for page in pages:
        site.pages.append(page)
    return site


def test_report_counts_pages_without_cover():
    from heron.core import report

    cfg = sites.config(
        site={"domain": "example.com", "theme": "demo", "default_lang": "uk", "languages": ["uk"]},
        build={"notes": "ru"},
    )
    site = _site_pages(cfg, _page("uk"), _page("uk", image="media/a.png"))
    warnings = report.pages_without_cover(site, cfg)
    assert len(warnings) == 1
    assert "страниц без обложки: 1" in warnings[0].message


def test_report_silent_with_default_image(config):
    from heron.core import report

    site = _site_pages(config, _page("uk"), _page("ru"))
    assert report.pages_without_cover(site, config) == []


def test_report_ignores_non_indexable():
    from heron.core import report

    cfg = sites.config(
        site={"domain": "example.com", "theme": "demo", "default_lang": "uk", "languages": ["uk"]},
    )
    site = _site_pages(cfg, _page("uk", noindex=True))
    assert report.pages_without_cover(site, cfg) == []


def _check_site(tmp_path, default_image: bool):
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=False)
    sites.clear_content(root)
    if default_image:
        _png(root / "media" / "default.png", 1600, 900)
        site_yaml = root / "site.yaml"
        site_yaml.write_text(
            site_yaml.read_text(encoding="utf-8")
            + "\nseo:\n  og_default_image: media/default.png\n",
            encoding="utf-8",
        )
    content = root / "content" / "en"
    content.mkdir(parents=True, exist_ok=True)
    (content / "_index.md").write_text(_md("Home"), encoding="utf-8")
    (content / "plain.md").write_text(_md("Plain"), encoding="utf-8")
    (content / "hidden.md").write_text(_md("Hidden", noindex="true"), encoding="utf-8")
    return pipeline.check(root)


def test_check_warns_pages_without_cover(tmp_path):
    result = _check_site(tmp_path, default_image=False)
    messages = [rendered(w.message, "en") for w in result.collector.warnings]
    messages = [text for text in messages if "without a cover" in text]
    # noindex-страница не считается: две индексируемые без обложки
    assert messages == ["pages without a cover: 2 (no og:image and no primaryImageOfPage)"]
    assert not [e for e in result.collector.errors if "cover" in e.message]
    assert not result.failed


def test_check_silent_with_default_image(tmp_path):
    result = _check_site(tmp_path, default_image=True)
    assert not [w for w in result.collector.warnings if "without a cover" in w.message]
    assert not result.failed
