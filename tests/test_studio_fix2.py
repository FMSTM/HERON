"""Студия и мелочи по второй приёмке 0.3.0 (STUDIO.FIX2).

- SVG с инструкцией `<?xml-stylesheet type="text/xsl"?>` (XSLT собирает `<script>`
  уже в браузере), DOCTYPE, сущностями или пространством имён XSLT - отказ при
  загрузке; те же файлы, положенные мимо студии в `media/` или в тему, - `E043`
  в `heron check`.
- Просмотр, открытый из студии, убирает ключ `?k=` из адресной строки своим
  скриптом `/_studio/preview.js` (политика `script-src 'self'`, встроенного кода нет).
- `category add` не предлагает `home` и `404` типом страниц внутри; список нового
  языка в опроснике показывает «пропустить» - то, что делает Enter; адрес студии -
  `localhost`, как в документации; домен заготовки и домен в зарезервированной
  зоне называются по-разному.
"""

from __future__ import annotations

import json
import urllib.request

import pytest
from click.testing import CliRunner

from heron import cli, studio
from heron.cli import main
from heron.core import build as pipeline
from heron.core import svg, watch
from heron.core.errors import HeronError
from heron.edit import console
from heron.edit import entity as ops
from heron.scaffold import create, domain_note
from heron.setup import server
from tests.test_studio import _req, png, served  # noqa: F401 - served - фикстура

XSLT_PI = (
    b'<?xml version="1.0"?>\n<?xml-stylesheet type="text/xsl" href="t2.svg"?>\n'
    b'<svg xmlns="http://www.w3.org/2000/svg" '
    b'xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xsl:version="1.0" width="100" '
    b'height="100"><xsl:element name="script" namespace="http://www.w3.org/1999/xhtml">'
    b"document.title='PWNED'</xsl:element></svg>"
)
NS = b'xmlns="http://www.w3.org/2000/svg"'
BAD = [
    XSLT_PI,
    b"<svg " + NS + b"><?php echo 1 ?><rect/></svg>",
    b"<svg " + NS + b' xmlns:x="http://www.w3.org/1999/XSL/Transform"><rect/></svg>',
    b"<svg " + NS + b' xsl:version="1.0"><rect/></svg>',
    b'<!DOCTYPE svg [<!ENTITY a "b">]><svg ' + NS + b"><text>&a;</text></svg>",
]
GOOD = b'<?xml version="1.0" encoding="UTF-8"?>\n<!-- c --><svg ' + NS + b'><rect width="1"/></svg>'


@pytest.mark.parametrize("data", BAD)
def test_svg_with_processing_instructions_doctype_or_xslt_is_refused(data, tmp_path):
    assert svg.problem(data) is not None
    with pytest.raises(HeronError) as caught:
        studio.upload(tmp_path, "pic.svg", data)
    assert caught.value.code == "E039"
    assert not (tmp_path / "media").exists() or not list((tmp_path / "media").iterdir())


def test_a_plain_svg_with_the_xml_declaration_is_fine(tmp_path):
    assert svg.problem(GOOD) is None
    assert studio.upload(tmp_path, "pic.svg", GOOD)["path"] == "media/pic.svg"


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=["ru", "en"], notes="ru", demo=True)
    return root


def test_check_finds_unsafe_svg_in_media_and_in_the_theme(site):
    clean = pipeline.check(site, notes_lang="en")
    assert not [e for e in clean.collector.errors if e.code == "E043"]
    (site / "media" / "evil.svg").write_bytes(XSLT_PI)
    (site / "theme" / "assets" / "icon.svg").write_bytes(BAD[2])
    (site / "media" / "fine.svg").write_bytes(GOOD)
    result = pipeline.check(site, notes_lang="en")
    found = {e.path: e for e in result.collector.errors if e.code == "E043"}
    assert set(found) == {"media/evil.svg", "theme/assets/icon.svg"}, found
    assert "xml-stylesheet" in found["media/evil.svg"].message.text("en")


# --- ключ просмотра из адресной строки ---------------------------------------------------


def test_preview_pages_load_the_key_stripping_script(served):  # noqa: F811
    base, token, _site = served
    status, body, _ = _req(base, "/api/studio/start", data={}, token=token)
    info = json.loads(body)["preview"]
    _req(base, "/api/studio/preview", data={}, token=token)
    other = f"http://127.0.0.1:{info['port']}"
    status, page, headers = _req(other, f"/blocks/?k={info['key']}")
    assert status == 200
    head = page.split(b"</head>", 1)[0]
    assert b'<script src="/_studio/preview.js"></script>' in head
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    # сам скрипт - без ключа: в нём нет секретов, а cookie могла ещё не дойти
    status, script, headers = _req(other, "/_studio/preview.js")
    assert status == 200 and b"replaceState" in script and b'delete("k")' in script
    assert headers["Content-Type"].startswith("application/javascript")


def test_preview_script_goes_first_into_head():
    assert server.with_preview_script(b"<html><head lang=x><title>t</title></head>") == (
        b'<html><head lang=x><script src="/_studio/preview.js"></script><title>t</title></head>'
    )
    assert server.with_preview_script(b"<p>x</p>").startswith(b"<script src=")


# --- мелочи ------------------------------------------------------------------------------


def test_children_type_offers_no_home_and_no_404(site):
    ctx = ops.context(site, "ru")
    entity = ops.open_entity(ctx, "services", category=True)
    item = next(f for f in ops.fields_of(entity, "ru") if f.name == "children_type")
    values = item.limits["values"]
    assert "page" in values and "home" not in values and "404" not in values
    kind = next(f for f in ops.fields_of(entity, "ru") if f.name == "type")
    assert "home" in kind.limits["values"]  # тип самой страницы - любой тип темы


def test_a_new_languages_list_shows_skip_as_its_default(site):
    """Файла языка нет: Enter у списка - «пропустить» (текст основного языка и пометка)."""
    (site / "content" / "en" / "blocks.md").unlink()
    ctx = ops.context(site, "ru")
    entity = ops.open_entity(ctx, "blocks")
    asked: list[str] = []
    io = console.Io(lambda prompt: (asked.append(prompt), "")[1], lambda *a, **k: None)
    console.Console(entity, io, "ru").translate("en")
    lists = [p for p in asked if p.startswith("  › [")]
    assert lists and all(p == "  › [пропустить]" for p in lists), lists
    assert ops.is_pending(entity, "en")


def test_studio_and_serve_print_localhost():
    assert watch.shown_url("127.0.0.1", 8000) == "http://localhost:8000/"
    assert watch.shown_url("0.0.0.0", 8000) == "http://localhost:8000/"
    assert watch.shown_url("192.168.1.5", 8000) == "http://192.168.1.5:8000/"


def test_localhost_passes_the_host_check(tmp_path):
    (tmp_path / "content" / "en").mkdir(parents=True)
    (tmp_path / "site.yaml").write_text(
        "site:\n  name: A\n  domain: a.test\n  languages: [en]\n  default_lang: en\n",
        encoding="utf-8",
    )
    from tests.test_setup_access import _start, _stop

    port, token, thread = _start(tmp_path, "127.0.0.1")
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/", timeout=10) as response:
            assert response.status == 200
    finally:
        _stop(port, token, thread)


@pytest.mark.parametrize(
    ("domain", "name", "kind"),
    [
        ("shop.example", "Shop", "placeholder"),
        ("example.com", "Мастерская", "placeholder"),
        ("workshop.example", "Мастерская", "reserved"),
        ("my.test", "Shop", "reserved"),
        ("shop.example.org", "Shop", "reserved"),
        ("workshop.com", "Мастерская", None),
    ],
)
def test_domain_note_tells_a_placeholder_from_a_reserved_zone(domain, name, kind):
    note = domain_note(domain, name)
    assert (note[0] if note else None) == kind


def test_new_does_not_call_a_typed_domain_a_placeholder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.setattr(cli, "can_ask", lambda: True)
    answers = "ru\nМастерская\nworkshop.example\nru, en\nru\ny\n"
    result = CliRunner().invoke(main, ["new", "w"], input=answers)
    assert result.exit_code == 0, result.output
    summary = next(line for line in result.output.splitlines() if "domain: workshop" in line)
    assert "заглушка" not in summary and "зона .example зарезервирована" in summary
    assert "Домен сейчас заглушка" not in result.output
