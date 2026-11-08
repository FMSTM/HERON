"""Третья приёмка 0.3.0 (STUDIO.FIX3).

- `E043` больше не отвергает то, что пишет обычный редактор: `url(#id)` в стилях,
  `href="#id"`, растр `data:image/png` в `<image>`, ссылки `http(s):`/`mailto:` в `<a>`;
  экранирование CSS (`u\\72l(`, `@\\69mport`) и комментарии больше не прячут `url(`.
- SVG из `static/` проверяется так же, как из `media/` и темы; кэш годных SVG - в
  `.heron-cache` сайта, в нём только проверенные годными файлы.
- `--json` остаётся JSON, даже если в тексте есть DEL и C1.
- Новая копия языка не наследует `redirect_from` и `updated` основного (было `E009`).
- Раздел на месте папки 0.2 без перевода не прячет молча переведённые страницы внутри.
- Общие поля страницы - один список у редактора и `check` (в нём `published`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron import studio
from heron.cli import main
from heron.core import build as pipeline
from heron.core import svg
from heron.core.environment import BuildEnv
from heron.core.errors import HeronError
from heron.edit import console
from heron.edit import entity as ops
from heron.scaffold import create
from heron.setup import server

FIXTURES = Path(__file__).parent / "fixtures"
EDITORS = sorted((FIXTURES / "svg").glob("*.svg"))
NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'


def wrap(inner: str) -> bytes:
    return f"<svg {NS}>{inner}</svg>".encode()


def run(*args, input=None):
    return CliRunner().invoke(main, [str(a) for a in args], input=input)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=["ru", "en"], notes="ru", demo=True)
    return root


# --- 1. E043: что пишет редактор, проходит --------------------------------------------------


EDITOR_SNIPPETS = [
    # Illustrator: класс с градиентом в <style>
    '<style type="text/css">.st0{fill:url(#SVGID_1_);}</style>'
    '<linearGradient id="SVGID_1_"><stop offset="0"/></linearGradient><rect class="st0"/>',
    # Inkscape: градиент в атрибуте style и ссылка градиента на градиент
    '<defs><linearGradient id="a"/><linearGradient id="g" xlink:href="#a"/></defs>'
    '<rect style="fill:url(#g);stroke:none"/>',
    '<rect fill="url(#g)" filter="url( \'#f\' )" clip-path="url(&quot;#c&quot;)"/>',
    '<use href="#a"/><use xlink:href="#a"/>',
    '<image href="data:image/png;base64,iVBORw0KGgo=" width="1" height="1"/>',
    '<image xlink:href="data:image/jpeg;base64,/9j/4AAQ" width="1" height="1"/>',
    '<image href="data:image/webp;base64,UklGRg==" width="1" height="1"/>',
    '<a href="https://example.org/"><text>x</text></a>',
    '<a xlink:href="http://example.org/"><text>x</text></a>',
    '<a href="mailto:hello@example.org"><text>x</text></a>',
    "<style>@font-face{font-family:x;src:local(x)}</style>",
]


@pytest.mark.parametrize("path", EDITORS, ids=lambda p: p.name)
def test_files_saved_by_inkscape_and_illustrator_pass(path, tmp_path):
    data = path.read_bytes()
    assert svg.problem(data) is None
    assert studio.upload(tmp_path, path.name, data)["path"] == f"media/{path.name}"


@pytest.mark.parametrize("inner", EDITOR_SNIPPETS)
def test_what_editors_write_is_not_refused(inner):
    assert svg.problem(wrap(inner)) is None


STILL_BAD = [
    "<script>alert(1)</script>",
    '<rect onload="x()"/>',
    '<a href="javascript:alert(1)"><text>x</text></a>',
    '<a href="&#106;avascript:alert(1)"><text>x</text></a>',
    '<a href="vbscript:x"/>',
    '<a href="blob:https://example.org/1"/>',
    '<a href="ftp://example.org/"/>',
    '<a href="data:text/html,x"/>',
    # внешнее в CSS
    "<style>rect{fill:url(https://example.org/x.png)}</style>",
    '<rect style="fill:url(https://example.org/x.svg#g)"/>',
    '<rect filter="url(https://example.org/f.svg#a)"/>',
    '<rect fill="url(other.svg#g)"/>',
    '<style>@import "https://example.org/x.css";</style>',
    "<style><![CDATA[@import url(x.css);]]></style>",
    '<style>a{background:image-set("x.png" 1x)}</style>',
    # экранирование CSS и комментарии не прячут url( и @import
    "<style>rect{fill:u\\72l(https://example.org/x.png)}</style>",
    '<style>@\\69mport "https://example.org/x.css";</style>',
    '<style>@\\000069mport "x.css";</style>',
    "<style>rect{fill:\\75 rl(https://example.org/x.png)}</style>",
    "<style>\\/* url(https://example.org/x.png) */</style>",
    '<style>a{content:"/*"} b{fill:url(https://example.org/)} c{content:"*/"}</style>',
    '<rect style="fill:u\\72l(https://example.org/x.png)"/>',
    # <use> - только на #id своего файла
    '<use href="https://example.org/a.svg#x"/>',
    '<use href="//example.org/a.svg#x"/>',
    '<use href="other.svg#x"/>',
    '<use href="data:image/svg+xml;base64,PHN2Zz4="/>',
    # картинка внутри файла - только растр
    '<image href="data:image/svg+xml;base64,PHN2Zz4="/>',
    '<image href="https://example.org/x.png"/>',
    "<foreignObject><div/></foreignObject>",
    '<h:meta xmlns:h="http://www.w3.org/1999/xhtml" http-equiv="refresh" content="0;url=x"/>',
    '<a xml:base="javascript:alert(1)//" href="x"><text>x</text></a>',
    '<set attributeName="href" to="javascript:alert(1)"/>',
]


@pytest.mark.parametrize("inner", STILL_BAD)
def test_executable_and_external_svg_is_still_refused(inner):
    assert svg.problem(wrap(inner)) is not None


@pytest.mark.parametrize(
    "data",
    [
        b'<?xml-stylesheet type="text/xsl" href="x.xsl"?>' + wrap(""),
        b'<!DOCTYPE svg [<!ENTITY x "y">]>' + wrap("&x;"),
        wrap('<x:template xmlns:x="http://www.w3.org/1999/XSL/Transform"/>'),
        wrap("<?php echo 1 ?>"),
    ],
)
def test_processing_instructions_doctype_and_xslt_are_still_refused(data):
    assert svg.problem(data) is not None


# --- 6. static/ проверяется так же ----------------------------------------------------------

BAD_SVG = wrap("<script>alert(1)</script>")


def test_check_finds_an_unsafe_svg_in_static(site):
    (site / "static" / "icons").mkdir(parents=True, exist_ok=True)
    (site / "static" / "icons" / "bad.svg").write_bytes(BAD_SVG)
    (site / "static" / "fine.svg").write_bytes((FIXTURES / "svg" / "inkscape.svg").read_bytes())
    result = pipeline.check(site, notes_lang="en")
    found = [e.path for e in result.collector.errors if e.code == "E043"]
    assert found == ["static/icons/bad.svg"], found


def test_prod_build_stops_and_dev_build_warns_on_static_svg(site, tmp_path):
    (site / "static" / "bad.svg").write_bytes(BAD_SVG)
    prod = pipeline.run(site, dist=tmp_path / "p", env=BuildEnv.resolve("prod"))
    assert [e.path for e in prod.collector.errors if e.code == "E043"] == ["static/bad.svg"]
    assert not (tmp_path / "p" / "index.html").exists()
    dev = pipeline.run(site, dist=tmp_path / "d")
    assert not [e for e in dev.collector.errors if e.code == "E043"]
    assert [w.path for w in dev.collector.warnings if "SVG" in w.message.text("en")] == [
        "static/bad.svg"
    ]


# --- кэш SVG: только годные, в .heron-cache сайта -------------------------------------------


def _store(site: Path) -> Path:
    return site / ".heron-cache" / "svg-safe.json"


def test_svg_cache_lives_in_the_site_cache_whatever_out_is(site, tmp_path):
    (site / "media" / "bad.svg").write_bytes(BAD_SVG)
    pipeline.run(site, dist=tmp_path / "elsewhere" / "out")
    assert not (tmp_path / "elsewhere" / ".heron-cache" / "svg-safe.json").exists()
    data = json.loads(_store(site).read_text("utf-8"))
    assert data["rules"] == svg.RULES
    assert hashlib.sha256(BAD_SVG).hexdigest() not in data["safe"]
    assert all(re.fullmatch(r"[0-9a-f]{64}", item) for item in data["safe"])


@pytest.mark.parametrize(
    "stored",
    [
        "{not json",
        '["x"]',
        '{"rules": 0, "safe": ["DIGEST"]}',  # другая версия правил
        '{"DIGEST": null}',  # вид прежней версии: «null» значило «годен»
        '{"rules": RULES, "safe": "DIGEST"}',
    ],
)
def test_a_cache_of_another_form_is_a_miss(site, tmp_path, monkeypatch, stored):
    (site / "media" / "bad.svg").write_bytes(BAD_SVG)
    digest = hashlib.sha256(BAD_SVG).hexdigest()
    _store(site).parent.mkdir(parents=True, exist_ok=True)
    text = stored.replace("DIGEST", digest).replace("RULES", str(svg.RULES))
    _store(site).write_text(text, encoding="utf-8")
    result = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.resolve("prod"))
    assert [e.path for e in result.collector.errors if e.code == "E043"] == ["media/bad.svg"]


def test_a_malformed_entry_is_ignored(site, tmp_path):
    (site / "media" / "bad.svg").write_bytes(BAD_SVG)
    digest = hashlib.sha256(BAD_SVG).hexdigest()
    _store(site).parent.mkdir(parents=True, exist_ok=True)
    body = {"rules": svg.RULES, "safe": [digest.upper(), digest + "0", 7, None]}
    _store(site).write_text(json.dumps(body), encoding="utf-8")
    result = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.resolve("prod"))
    assert [e.path for e in result.collector.errors if e.code == "E043"] == ["media/bad.svg"]


def test_a_symlinked_site_cache_is_not_used(site, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, site / ".heron-cache")
    pipeline.run(site, dist=tmp_path / "out" / "dist")
    assert not (outside / "svg-safe.json").exists()


# --- 2. --json остаётся JSON ----------------------------------------------------------------

DIRTY = "Блоки\\x9B31m\\x7F\\x85"  # так в YAML: DEL и C1 экранированы


def _dirty_site(root: Path, check: bool = False) -> None:
    page = root / "content" / "ru" / "blocks.md"
    text = page.read_text(encoding="utf-8")
    for name in ("title", "h1", "nav_title"):
        line = f'{name}: "{DIRTY}"'
        text = re.sub(rf"^{name}: .*$", lambda _m, line=line: line, text, count=1, flags=re.M)
    # неизвестный тип: сообщение `check` повторяет его имя
    text = text.replace("\nh1:", f'\ntype: "zz{DIRTY}"\nh1:', 1) if check else text
    page.write_text(text, encoding="utf-8")
    theme = root / "theme" / "theme.yaml"
    body = theme.read_text(encoding="utf-8")
    body = re.sub(
        r"^(\s*hint_ru:) .*$", lambda m: f'{m.group(1)} "{DIRTY}"', body, count=1, flags=re.M
    )
    theme.write_text(body, encoding="utf-8")


@pytest.mark.parametrize(
    "args",
    [["page", "list", "--json"], ["describe", "home", "--json"], ["check", "--json"]],
    ids=["page-list", "describe", "check"],
)
def test_json_output_stays_json_with_del_and_c1(site, args):
    _dirty_site(site, check=args[0] == "check")
    result = run(*args, site)
    data = json.loads(result.output)
    assert "\x9b" not in result.output
    assert "\x9b31m\x7f\x85" in json.dumps(data, ensure_ascii=False)


def test_the_json_helper_escapes_every_control_character():
    from heron import term

    text = "a\x00\x1b\x7f\x9b\x85 " + term.MARK + "b\n"
    out = term.dumps({"t": text}, indent=2)
    assert json.loads(out) == {"t": text}
    assert term.clean(out) == out and term.MARK not in out


# --- 5. новая копия языка не наследует redirect_from и updated ------------------------------


def test_a_new_language_copy_starts_without_redirects_and_updated(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "old"
    shutil.copytree(FIXTURES / "site-0.2", root)
    about = root / "content" / "ru" / "about.md"
    text = about.read_text(encoding="utf-8").replace(
        "# redirect_from:", "redirect_from:\n  - /staroe-o-nas/\nupdated: 2024-01-02\n# x:", 1
    )
    about.write_text(text, encoding="utf-8")
    answers = tmp_path / "de.yaml"
    answers.write_text("de:\n  title: Über uns\n  h1: Wer wir sind\n", encoding="utf-8")
    result = run("page", "add", "about", root, "--answers", answers)
    assert result.exit_code == 0, result.output
    head = (root / "content" / "de" / "about.md").read_text(encoding="utf-8").split("---")[1]
    assert "staroe-o-nas" not in head and not re.search(r"^updated:", head, re.M)
    checked = pipeline.check(root, notes_lang="en")
    assert not [e for e in checked.collector.errors if e.code == "E009"]


def test_dump_shows_redirects_and_updated_of_other_languages(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "old"
    shutil.copytree(FIXTURES / "site-0.2", root)
    result = run("page", "add", "about", root, "--dump")
    import yaml

    data = yaml.safe_load(result.output)
    for lang in ("en", "de"):
        assert "redirect_from" in data[lang] and "updated" in data[lang]
        assert list(data[lang])[-1] == "translation"


# --- общие поля: один список ----------------------------------------------------------------


def test_shared_fields_are_one_list_for_the_editor_and_check(tmp_path, monkeypatch):
    from heron.contracts.fields import SERVICE, SHARED

    assert "published" in SHARED and "type" in SHARED
    assert pipeline.SHARED_FIELDS is SHARED
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=["ru", "en"], notes="ru", demo=True)
    entity = ops.open_entity(ops.context(root, "en"), "blocks")
    service = {spec.name for spec in SERVICE if spec.where == "frontmatter"}
    editor = {f.name for f in ops.fields_of(entity, "ru") if ops.shared(f) and f.name in service}
    assert editor == set(SHARED) - {"children_type"}  # children_type - только у категории


def test_check_warns_when_published_differs_between_languages(site):
    page = site / "content" / "en" / "blocks.md"
    text = page.read_text(encoding="utf-8")
    page.write_text(
        re.sub(r"^published: .*$", "published: false", text, count=1, flags=re.M), "utf-8"
    )
    result = pipeline.check(site, notes_lang="en")
    texts = [
        w.message.text("en")
        for w in result.collector.warnings
        if w.path == page.relative_to(site / "content").as_posix()
    ]
    assert any("published" in t for t in texts), texts


# --- 4. раздел на месте папки 0.2 -----------------------------------------------------------


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    """Сайт 0.2: services/ без _index.md, services/roofing переведён на en."""
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "old"
    shutil.copytree(FIXTURES / "site-0.2", root)
    ru = root / "content" / "ru" / "services" / "roofing.md"
    en = root / "content" / "en" / "services" / "roofing.md"
    en.parent.mkdir(parents=True)
    en.write_text(
        ru.read_text(encoding="utf-8").replace('title: "', 'title: "EN ', 1), encoding="utf-8"
    )
    return root


def files(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted((root / "content").rglob("*"))
        if p.is_file()
    }


ROOFING = "content/en/services/roofing.md"


def test_drops_lists_translated_pages_of_an_implicit_folder(legacy):
    entity = ops.open_entity(ops.context(legacy, "en"), "services", category=True)
    for lang in ("en", "de"):
        ops.mark(entity, lang, True)
    assert ops.drops(entity) == {"services": {"en": [ROOFING]}}


def test_yes_refuses_to_hide_translated_pages(legacy):
    before = files(legacy)
    result = run("category", "add", "services", legacy, "-y", "--notes", "en")
    assert result.exit_code != 0
    assert "E039" in result.output and ROOFING in result.output
    assert "will drop out of prod" in result.output
    assert files(legacy) == before


def test_answers_pending_is_consent_and_still_warns(legacy, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text("en: pending\n", encoding="utf-8")
    result = run("category", "add", "services", legacy, "--answers", answers, "--notes", "en")
    assert result.exit_code == 0, result.output
    assert "will drop out of prod" in result.output and ROOFING in result.output
    assert (legacy / "content" / "en" / "services" / "_index.md").is_file()


def test_answers_without_the_language_are_refused(legacy, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text("ru:\n  title: Услуги\n", encoding="utf-8")
    before = files(legacy)
    result = run("category", "add", "services", legacy, "--answers", answers)
    assert result.exit_code != 0 and "E039" in result.output
    assert files(legacy) == before


def test_translated_section_keeps_the_pages_in_prod(legacy, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text(
        "ru:\n  title: Услуги\n  h1: Наши услуги\n  description: Что мы делаем.\n"
        "  sections.intro.text: Кровля и окна.\n"
        "en:\n  title: Services\n  h1: Our services\n  description: What we do.\n"
        "  sections.intro.text: Roofs and windows.\n",
        encoding="utf-8",
    )
    result = run("category", "add", "services", legacy, "--answers", answers, "--notes", "en")
    assert result.exit_code == 0, result.output
    assert "drop out of prod" not in result.output
    built = pipeline.run(legacy, dist=tmp_path / "dist", env=BuildEnv.resolve("prod"))
    assert not built.collector.errors, [str(e) for e in built.collector.errors]
    assert (tmp_path / "dist" / "en" / "services" / "roofing" / "index.html").is_file()
    # de - раздел с пометкой: E040 его заготовка в проде не даёт, страница не публикуется
    assert not (tmp_path / "dist" / "de" / "services" / "index.html").exists()


def test_a_pending_stub_index_does_not_fail_prod_with_e040(legacy, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text(
        "ru:\n  title: Услуги\n  h1: Наши услуги\n  description: Что мы делаем.\n"
        "  sections.intro.text: Кровля и окна.\nen: pending\n",
        encoding="utf-8",
    )
    assert run("category", "add", "services", legacy, "--answers", answers).exit_code == 0
    built = pipeline.run(legacy, dist=tmp_path / "dist", env=BuildEnv.resolve("prod"))
    assert not [e for e in built.collector.errors if e.code == "E040"]


def test_a_new_page_into_the_implicit_folder_is_refused_with_the_way_out(legacy):
    before = files(legacy)
    result = run("page", "add", "services/painting", legacy, "-y", "--notes", "en")
    assert result.exit_code != 0 and "E039" in result.output
    assert "heron category add services" in result.output
    assert files(legacy) == before


def _io(answers: list[str]):
    out: list[str] = []
    feed = iter(answers)
    return console.Io(
        lambda prompt: (out.append(prompt), next(feed, ""))[1],
        lambda *a, **k: out.append(str(a[0]) if a else ""),
    ), out


def test_console_warns_and_asks_before_hiding(legacy):
    entity = ops.open_entity(ops.context(legacy, "en"), "services", category=True)
    io, out = _io([])
    session = console.Console(entity, io, "en")
    session.run()
    shown = "\n".join(out)
    assert "prod stops showing the translated pages" in shown and ROOFING in shown
    # Enter на вопросе «спрятать?» - нет: ничего не пишется
    io, out = _io([])
    session.io = io
    assert session.confirm() is False
    assert any("Write the section without a translation" in line for line in out)
    # да - запись идёт, согласие записано
    io, out = _io(["y", ""])
    session.io = io
    assert session.confirm() is True
    assert session.agreed == {("services", "en")}


def test_studio_asks_before_hiding(legacy):
    request = {"target": {"kind": "category", "key": "services"}}
    first = studio.save(legacy, request, "en")
    assert "confirm" in first and first["confirm"]["drops"] == {"services": {"en": [ROOFING]}}
    assert ROOFING in first["confirm"]["message"]
    assert not (legacy / "content" / "en" / "services" / "_index.md").exists()
    done = studio.save(legacy, {**request, "confirm_pending": True}, "en")
    assert "content/en/services/_index.md" in done["saved"]["created"]


def test_check_warning_names_the_main_language_and_the_consequence(legacy):
    (legacy / "content" / "de" / "services").mkdir()
    shutil.copy(legacy / ROOFING, legacy / "content" / "de" / "services" / "roofing.md")
    result = pipeline.check(legacy, notes_lang="en")
    found = [w for w in result.collector.warnings if "no _index.md" in w.message.text("en")]
    assert [w.path for w in found] == ["ru/services/"]
    assert "does not publish the pages inside" in found[0].message.text("en")


def test_refuse_drops_names_the_category_command(legacy):
    entity = ops.open_entity(ops.context(legacy, "en"), "services", category=True)
    ops.mark(entity, "en", True)
    with pytest.raises(HeronError) as error:
        ops.refuse_drops(entity, ops.drops(entity), set())
    assert error.value.code == "E039"


# --- мелочи ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "after"),
    [
        (b"<!-- <head> --><!doctype html><html><head><title>t</title>", b"<head>"),
        (b'<!doctype html><html lang="ru"><head data-x="1">', b'<head data-x="1">'),
        (b"<html><body><script>var s = '<head>'</script>", b"<html>"),
        (b"\xef\xbb\xbf<!DOCTYPE html>\n<html>\n<head>\n<title>", b"<head>\n"),
    ],
)
def test_preview_script_goes_into_the_real_head(html, after):
    tag = b'<script src="/_studio/preview.js"></script>'
    out = server.with_preview_script(html)
    assert out.count(tag) == 1
    assert out.index(tag) == html.rindex(after) + len(after)


def test_one_language_run_shows_skip_for_a_language_without_a_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "old"
    shutil.copytree(FIXTURES / "site-0.2", root)
    entity = ops.open_entity(ops.context(root, "en"), "services/roofing")
    io, out = _io([])
    console.Console(entity, io, "en").run(only="de")
    prompts = [line for line in out if line.strip().startswith("›")]
    assert prompts and all("[skip]" in p for p in prompts if "[" in p), prompts
    assert not (root / "content" / "de" / "services" / "roofing.md").exists()


def test_a_cover_on_the_main_language_warns_about_image_alt_elsewhere(site):
    shutil.copy(next((site / "media").rglob("*.png")), site / "media" / "cover-x.png")
    entity = ops.open_entity(ops.context(site, "en"), "blocks")
    item = next(f for f in ops.fields_of(entity, "ru") if f.path == "image")
    io, out = _io(["media/cover-x.png"])
    console.Console(entity, io, "en").field("ru", item)
    assert any(line.strip().startswith("en: image_alt") for line in out), out
