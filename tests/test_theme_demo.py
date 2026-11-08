"""Демо темы обязательно, справка темы из контракта и демо (STUDIO ST3).

Спецификация: docs/ru/spec/21-engine.md, §7 «Демо темы и справка», §10 «heron theme».
"""

from __future__ import annotations

import re
import tarfile
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron import scaffold
from heron.cli import main
from heron.core import build as pipeline
from heron.core import demo
from heron.core.errors import Collector, HeronError
from heron.core.render import themeref
from heron.scaffold import create
from heron.themes import check_demo, install, pack

OLD_THEME = """\
name: old
version: "0.1"
modules: [prose, list, checklist, steps, table, facts, faq, timeline, callout, gallery, tabs,
  breadcrumbs, children]
types:
  home: {uses: [intro, "*"]}
  page: {uses: [intro, "*"]}
  "404": {uses: [intro]}
"""


def _run(*args: str):
    return CliRunner().invoke(main, list(args))


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="Demo", languages=["ru", "en"], demo=True, notes="ru")
    return root


def _found(root: Path) -> tuple[demo.Shown, object]:
    collector = Collector()
    config, theme, theme_dir, hooks = pipeline.prepare(root.resolve(), collector)
    site = pipeline.content(root.resolve(), config, theme, theme_dir, hooks, collector, False)
    assert not collector.errors, collector.errors
    return demo.render(theme_dir, site, config, theme, hooks), theme


def _gaps(root: Path) -> list[str]:
    found, theme = _found(root)
    return [m.text("en") for m in demo.gaps(theme, found)]


def _drop_section(path: Path, anchor: str) -> None:
    """Убрать из файла секцию «## … {#anchor…}» до следующего заголовка ##."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\n## [^\n]*\{#" + re.escape(anchor) + r"[ }][^\n]*\n.*?(?=\n## |\Z)", re.S
    )
    new, count = pattern.subn("\n", text)
    assert count == 1, anchor
    path.write_text(new, encoding="utf-8")


# --- демо стартовой темы полное ------------------------------------------------


@pytest.mark.parametrize("lang", scaffold.DEMO_LANGS)
def test_starter_demo_shows_everything_in_every_demo_language(tmp_path: Path, lang: str):
    """Демо на каждом языке текстов (uk, ru, en) само по себе полное: тип, блок, вид."""
    root = tmp_path / lang
    create(root, name="Demo", languages=[lang], demo=True)
    found, theme = _found(root)
    assert demo.gaps(theme, found) == []
    assert found.types() == set(theme.types)
    assert set(found.modules) == set(theme.module_specs)
    views = {view for spec in theme.types.values() if spec.views for view in spec.views.options}
    assert {view for _, view in found.views} == views


def test_starter_demo_passes_check_theme_and_pack(site: Path, tmp_path: Path):
    done = _run("check", str(site), "--theme")
    assert done.exit_code == 0, done.output
    assert "E037" not in done.output
    archive = pack(site, tmp_path / "t.tar.gz")
    with tarfile.open(archive) as packed:
        names = packed.getnames()
    for rel in ("demo/content/ru/404.md", "demo/content/en/structure/_index.md"):
        assert rel in names


def test_demo_pages_cover_page_modules_and_views(site: Path):
    found, _ = _found(site)
    crumbs = {str(page.source) for page, section in found.modules["breadcrumbs"]}
    assert "ru/blocks.md" in crumbs and all(s is None for _, s in found.modules["breadcrumbs"])
    assert [p.source for p in found.views[("view", "list")]][:1] == ["ru/structure/_index.md"]
    assert "ru/index.md" in [p.source for p in found.views[("view", "cards")]]
    # секционные модули записаны с id секции: галерея - секция gallery страницы «Блоки»
    assert ("ru/blocks.md", "gallery") in [(p.source, s) for p, s in found.modules["gallery"]]


def test_category_page_carries_the_view_line_with_a_hint(site: Path):
    head = (site / "content" / "ru" / "structure" / "_index.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(head.split("---", 2)[1])
    assert meta["view"] == "list"
    assert "view: list\n# ↑ " in head


# --- пропуски демо: E037 -------------------------------------------------------


def test_missing_type_page_stops_pack_and_check_theme(site: Path, tmp_path: Path):
    for lang in ("ru", "en"):
        (site / "content" / lang / "404.md").unlink()
    assert _gaps(site) == ["type 404: no demo page at all"]
    with pytest.raises(HeronError) as raised:
        pack(site, tmp_path / "t.tar.gz")
    assert raised.value.code == "E037"
    assert "404" in raised.value.message
    assert not (tmp_path / "t.tar.gz").exists()
    done = _run("check", str(site), "--theme", "--notes", "en")
    assert done.exit_code == 1, done.output
    assert "E037" in done.output and "type 404" in done.output
    done = _run("theme", "pack", str(site), "--out", str(tmp_path / "t.tar.gz"))
    assert done.exit_code != 0 and "E037" in done.output


def test_missing_block_and_view_are_named(site: Path):
    for lang in ("ru", "en"):
        _drop_section(site / "content" / lang / "blocks.md", "gallery")
        (site / "content" / lang / "structure" / "_index.md").unlink()
    gaps = _gaps(site)
    assert any(g.startswith("block gallery (gallery)") for g in gaps), gaps
    assert any(g.startswith("section view list") and "view: list" in g for g in gaps), gaps
    assert len(gaps) == 2


def test_missing_page_module_is_named(site: Path):
    """Без вложенных страниц крошкам нечего рисовать - модуль страницы назван."""
    for lang in ("ru", "en"):
        folder = site / "content" / lang
        for name in ("blocks", "themes", "docs"):
            (folder / f"{name}.md").unlink()
        for path in sorted((folder / "structure").glob("*.md")):
            path.unlink()
    gaps = _gaps(site)
    assert "page module breadcrumbs: drew nothing on any demo page" in gaps
    assert any(g.startswith("type page") for g in gaps)


def test_plain_check_does_not_require_a_demo(tmp_path: Path):
    root = tmp_path / "plain"
    create(root, name="Plain", languages=["en"])  # главная и 404, без демо
    done = _run("check", str(root))
    assert done.exit_code == 0, done.output
    assert "E037" not in done.output
    done = _run("check", str(root), "--theme")
    assert done.exit_code == 1 and "E037" in done.output


def test_check_theme_json_reports_e037(site: Path):
    for lang in ("ru", "en"):
        (site / "content" / lang / "404.md").unlink()
    done = _run("check", str(site), "--theme", "--json")
    assert done.exit_code == 1
    assert '"E037"' in done.output


def test_old_theme_without_fields_only_warns(tmp_path: Path):
    root = tmp_path / "old"
    create(root, name="Old", languages=["en"])
    (root / "theme" / "theme.yaml").write_text(OLD_THEME, encoding="utf-8")
    notices: list = []
    archive = pack(root, tmp_path / "old.tar.gz", notices)
    assert archive.is_file()
    assert len(notices) == 1 and "E037" in notices[0].text("en")
    assert "type page" in notices[0].text("en")
    done = _run("theme", "pack", str(root), "--out", str(tmp_path / "o2.tar.gz"), "--notes", "en")
    assert done.exit_code == 0, done.output
    assert "warning:" in done.output
    done = _run("check", str(root), "--theme")
    assert done.exit_code == 0, done.output
    # справка собирается и для старой темы: модули без полей, без примеров - с пометкой
    done = _run("build", str(root), "--out", str(tmp_path / "old-dist"), "--notes", "en")
    assert done.exit_code == 0, done.output
    page = (tmp_path / "old-dist" / "_heron" / "theme" / "index.html").read_text("utf-8")
    assert "the demo does not show this block" in page


def test_pack_without_site_yaml_is_e037(site: Path, tmp_path: Path):
    (site / "site.yaml").unlink()
    with pytest.raises(HeronError) as raised:
        check_demo(site)
    assert raised.value.code == "E037"
    assert "site.yaml" in raised.value.message


# --- theme get раскладывает тему и демо и перечисляет разложенное ---------------


def test_theme_get_archive_places_demo_and_lists_it(site: Path, tmp_path: Path):
    archive = pack(site, tmp_path / "t.tar.gz")
    other = tmp_path / "other"
    create(other, name="Other", languages=["en"])
    mine = (other / "content" / "en" / "index.md").read_bytes()
    done = _run("theme", "get", str(archive), str(other), "--notes", "en")
    assert done.exit_code == 0, done.output
    for rel in ("content/en/blocks.md", "content/en/structure/_index.md", "media/demo/light.svg"):
        assert (other / rel).is_file(), rel
        assert f"    {rel}\n" in done.output
    # своя главная и 404 не тронуты и названы числом
    assert (other / "content" / "en" / "index.md").read_bytes() == mine
    assert "content/en/index.md" not in done.output
    assert "kept as they are" in done.output
    assert _run("check", str(other), "--theme").exit_code == 0


def test_theme_get_starter_brings_404_and_section(tmp_path: Path):
    root = tmp_path / "bare"
    create(root, name="Bare", languages=["de"])
    (root / "content" / "de" / "404.md").unlink()
    result = install(root, "starter", languages=["de"])
    assert "content/de/404.md" in result.created
    assert "content/de/structure/one-intent.md" in result.created
    assert "content/de/index.md" in result.kept
    assert (root / "content" / "de" / "structure" / "_index.md").is_file()


# --- справка темы ---------------------------------------------------------------


def _reference(root: Path, lang: str) -> dict:
    return themeref.load(root, lang)


def test_reference_has_an_example_of_every_block_and_view(site: Path):
    data = _reference(site, "ru")
    for item in data["contract"]["modules"]:
        assert item["demo"], item["name"]
        for example in item["demo"]:
            assert example["lang"] == "ru"
            if item["scope"] == "section":
                assert example["markdown"].startswith("## "), item["name"]
    lists = next(m for m in data["contract"]["modules"] if m["name"] == "list")
    assert [e["kind"] for e in lists["demo"]] == ["list", "alert-list"]
    for item in data["contract"]["types"]:
        assert item["demo"], item["name"]
        for option in (item["views"] or {}).get("options", []):
            assert option["demo"], (item["name"], option["name"])
    assert {"where": "modules.faq", "schemaorg": "FAQPage"} in data["schema"]
    assert any(t["name"] == "--accent" and t["color"] for t in data["styles"]["tokens"])
    assert any(row["key"] == "read_more" for row in data["strings"])


def test_docs_theme_ref_prints_contract_and_demo_markdown(site: Path):
    done = _run("docs", "theme-ref", str(site), "--lang", "ru")
    assert done.exit_code == 0, done.output
    out = done.output
    for name in ("prose", "gallery", "tabs", "breadcrumbs", "children", "404", "home"):
        assert f"  {name} " in out, name
    assert "## Шкала {#timeline .timeline}" in out
    assert "ru/blocks.md (/blocks/)" in out
    assert "view: list" in out and "FAQPage" in out and "--accent" in out
    assert "/_heron/theme/" in out
    en = _run("docs", "theme-ref", str(site), "--lang", "en")
    assert en.exit_code == 0 and "Section views" in en.output
    assert "en/blocks.md (/en/blocks/)" in en.output


def test_docs_theme_ref_needs_a_site(tmp_path: Path):
    done = _run("docs", "theme-ref", str(tmp_path))
    assert done.exit_code != 0


def test_reference_follows_the_contract(site: Path):
    """Справку не пишут руками: поменялась подсказка в theme.yaml - поменялась справка."""
    path = site / "theme" / "theme.yaml"
    text = path.read_text(encoding="utf-8")
    old = "Обычный текст - абзацы, ссылки, выделения, код"
    assert old in text
    path.write_text(text.replace(old, "Свой текст подсказки модуля"), encoding="utf-8")
    done = _run("docs", "theme-ref", str(site), "--lang", "ru")
    assert "Свой текст подсказки модуля" in done.output and old not in done.output


def test_draft_build_writes_the_reference_page(site: Path, tmp_path: Path):
    out = tmp_path / "dist"
    done = _run("build", str(site), "--out", str(out), "--strict")
    assert done.exit_code == 0, done.output
    page = (out / "_heron" / "theme" / "index.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex, nofollow">' in page
    assert '<link rel="stylesheet" href="/assets/site.css">' in page
    # живой пример модуля и его markdown рядом
    assert '<section id="gallery" class="block gallery">' in page
    assert "## Галерея {#gallery .gallery}" in page
    assert 'class="rows"' in page and 'class="cards"' in page  # оба вида раздела живьём
    assert '<html lang="ru">' in page
    second = (out / "_heron" / "theme" / "en" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in second and "## Gallery {#gallery .gallery}" in second
    assert "How it looks" in second or "how it looks" in second
    for name in ("sitemap.xml", "sitemap-ru.xml", "llms.txt", "llms-ru.txt"):
        if (out / name).is_file():
            assert "_heron" not in (out / name).read_text(encoding="utf-8"), name


def test_prod_build_has_no_reference_page(site: Path, tmp_path: Path):
    out = tmp_path / "prod"
    done = _run("build", str(site), "--out", str(out), "--env", "prod")
    assert done.exit_code == 0, done.output
    assert not (out / "_heron").exists()


def test_reference_page_escapes_demo_text(site: Path, tmp_path: Path):
    path = site / "content" / "ru" / "blocks.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("## Просто текст {#text}", "## Текст 1 < 2 {#text}"), "utf-8")
    out = tmp_path / "dist"
    done = _run("build", str(site), "--out", str(out))
    assert done.exit_code == 0, done.output
    page = (out / "_heron" / "theme" / "index.html").read_text(encoding="utf-8")
    assert "## Текст 1 &lt; 2 {#text}" in page


def test_theme_get_from_catalog_places_demo_and_lists_it(site: Path, tmp_path: Path, monkeypatch):
    """Тема из каталога ставится тем же путём, что архив: тема и демо, список в выводе."""
    import hashlib

    from heron import themes

    blob = pack(site, tmp_path / "t.tar.gz").read_bytes()
    entry = {"name": "mine", "url": "https://example.com/mine.tar.gz"}
    entry["sha256"] = hashlib.sha256(blob).hexdigest()
    monkeypatch.setattr(themes, "_entry", lambda name: entry)
    monkeypatch.setattr(themes, "_download", lambda url: blob)
    other = tmp_path / "cat"
    create(other, name="Cat", languages=["en"])
    done = _run("theme", "get", "mine", str(other), "--notes", "en")
    assert done.exit_code == 0, done.output
    assert "    content/en/structure/categories.md\n" in done.output
    assert (other / "content" / "en" / "structure" / "categories.md").is_file()
