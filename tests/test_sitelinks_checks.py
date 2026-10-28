"""Предупреждения E16.S2.T6: пустая навигация, меню не в HTML, дубли title."""

import re
from types import SimpleNamespace

import pytest

from heron.core import build as pipeline
from heron.core import report
from heron.scaffold import create

PAGE = "---\ntitle: {title}\nh1: {title}\ndescription: Опис\n{extra}---\n\nТекст.\n"


def _write(root, name, title, extra=""):
    (root / "content" / "uk" / name).write_text(
        PAGE.format(title=title, extra=extra), encoding="utf-8"
    )


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    _write(root, "index.md", "Головна")
    _write(root, "bio.md", "Біо")
    _write(root, "404.md", "Нема", 'type: "404"\nnoindex: true\n')
    return root


def _seo(result):
    return [w.message for w in result.collector.warnings if w.kind == "seo"]


def _set_nav(root, main):
    """Заменить блок nav в site.yaml (или дописать его)."""
    path = root / "site.yaml"
    text = re.sub(r"(?m)^nav:\n(?:[ #].*\n|\n)*", "", path.read_text(encoding="utf-8"))
    path.write_text(text.rstrip("\n") + f"\nnav:\n  main: {main}\n", encoding="utf-8")


def _nav_warnings(messages):
    return [m for m in messages if "nav.main" in m]


def test_empty_nav_warns_in_check(site):
    _set_nav(site, "[]")
    assert _nav_warnings(_seo(pipeline.check(site)))


def test_filled_nav_does_not_warn(site):
    _set_nav(site, "[bio]")
    assert not _nav_warnings(_seo(pipeline.check(site)))


def test_duplicate_titles_listed(site):
    _write(site, "a.md", "Одинаковый")
    _write(site, "b.md", "Одинаковый")
    dup = [m for m in _seo(pipeline.check(site)) if "a.md" in m]
    assert len(dup) == 1
    assert "b.md" in dup[0] and "2" in dup[0] and "uk" in dup[0]


def test_noindex_duplicate_ignored(site):
    _write(site, "a.md", "Одинаковый")
    _write(site, "b.md", "Одинаковый", "noindex: true\n")
    assert not [m for m in _seo(pipeline.check(site)) if "a.md" in m]


def test_distinct_titles_no_warning(site):
    assert not [m for m in _seo(pipeline.check(site)) if "bio.md" in m]


def _cfg(notes="en", suffix="", i18n=None):
    return SimpleNamespace(
        site=SimpleNamespace(default_lang="uk", languages=["uk", "en"]),
        build=SimpleNamespace(notes=notes),
        seo=SimpleNamespace(title_suffix=suffix, i18n=i18n or {}),
        nav=SimpleNamespace(main=["bio"]),
    )


def _nav_site():
    return SimpleNamespace(
        nav={
            "uk": {"main": [SimpleNamespace(url="/bio/")]},
            "en": {"main": [SimpleNamespace(url="/en/bio/")]},
        }
    )


def test_nav_in_html_script_menu_warns():
    html = '<nav id="menu"></nav><script>menu.innerHTML = "<a href=/bio/>"</script>'
    found = report.nav_in_html({"index.html": html}, _nav_site(), _cfg())
    assert len(found) == 1
    assert found[0].kind == "seo" and found[0].path == "index.html"
    assert "(uk)" in found[0].message


def test_nav_in_html_normalizes_href():
    out = {
        "index.html": '<a class="x" href="https://example.org/bio">b</a>',
        "en/index.html": "<a href='/en/bio/#top'>b</a>",
    }
    assert report.nav_in_html(out, _nav_site(), _cfg()) == []


def test_nav_in_html_second_language_home():
    out = {"index.html": '<a href="/bio/">b</a>', "en/index.html": "<p>no menu</p>"}
    found = report.nav_in_html(out, _nav_site(), _cfg(notes="ru"))
    assert [w.path for w in found] == ["en/index.html"]
    assert found[0].message.startswith("ссылок навигации нет в HTML главной (en)")


def test_title_suffix_per_language_makes_titles_differ():
    pages = {
        "uk": [SimpleNamespace(title="A", source="uk/a.md", meta=SimpleNamespace(noindex=False))],
        "en": [
            SimpleNamespace(title="A", source="en/a.md", meta=SimpleNamespace(noindex=False)),
            SimpleNamespace(title="A", source="en/b.md", meta=SimpleNamespace(noindex=False)),
        ],
    }
    site = SimpleNamespace(of_lang=lambda lang: pages[lang])
    cfg = _cfg(suffix=" | X", i18n={"title_suffix": {"en": " | Y"}})
    found = report.duplicate_titles(site, cfg)
    assert len(found) == 1
    assert "(en)" in found[0].message and "en/a.md, en/b.md" in found[0].message


def test_build_catches_script_menu(site, tmp_path):
    _set_nav(site, "[bio]")
    base = site / "theme" / "templates" / "base.html"
    if base.is_file():
        text = base.read_text(encoding="utf-8")
        # убираем ссылки меню из разметки: навигация как будто строится скриптом
        base.write_text(re.sub(r"<nav\b.*?</nav>", "<nav></nav>", text, flags=re.S), "utf-8")
    result = pipeline.run(site, dist=tmp_path / "dist", with_media=False)
    html_has_bio = "/bio" in (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    warned = [m for m in _seo(result) if "home page HTML" in m or "HTML главной" in m]
    assert bool(warned) != html_has_bio


def test_build_with_plain_menu_does_not_warn(site, tmp_path):
    _set_nav(site, "[bio]")
    result = pipeline.run(site, dist=tmp_path / "dist", with_media=False)
    assert not result.failed
    warned = [m for m in _seo(result) if "home page HTML" in m or "HTML главной" in m]
    assert warned == []


def test_build_skips_non_utf8_static_index(site, tmp_path):
    """static/old/index.html в cp1251 - не главная: проверка его не читает, сборка не падает."""
    _set_nav(site, "[bio]")
    old = site / "static" / "old"
    old.mkdir(parents=True, exist_ok=True)
    (old / "index.html").write_bytes("<p>Старий сайт</p>".encode("cp1251"))
    result = pipeline.run(site, dist=tmp_path / "dist", with_media=False)
    assert not result.failed, [e.code for e in result.collector.errors]
    assert not [e for e in result.collector.errors if e.code == "E034"]
    assert (tmp_path / "dist" / "old" / "index.html").read_bytes() == "<p>Старий сайт</p>".encode(
        "cp1251"
    )
