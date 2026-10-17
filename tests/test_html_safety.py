"""Данные сайта не становятся сценарием на странице.

Две дыры: строка с `</script>` в разметке schema.org закрывала тег JSON-LD,
и атрибуты заголовка принимали `onclick=…` даже при запрещённом сыром HTML.
Проверяется итоговая структура HTML и — если есть Playwright — браузер.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.core.parser import markdown
from heron.scaffold import create

PAYLOAD = "</script><script>window.__pwned = 1</script><!--"


class Scripts(HTMLParser):
    """Все <script> страницы: атрибуты и текст — как их видит разборщик HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[dict, str]] = []
        self._open: dict | None = None
        self._text: list[str] = []
        self.handlers: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key.startswith("on"):
                self.handlers.append((tag, key))
        if tag == "script":
            self._open, self._text = dict(attrs), []

    def handle_data(self, data):
        if self._open is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._open is not None:
            self.found.append((self._open, "".join(self._text)))
            self._open = None


def site(tmp_path: Path, front: str = "", body: str = "Text.\n") -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    (root / "content" / "en" / "a.md").write_text(
        f"---\ntitle: A\nh1: A\ndescription: D\n{front}---\n\n{body}", encoding="utf-8"
    )
    return root


def scripts(root: Path) -> Scripts:
    parser = Scripts()
    parser.feed((root / "dist" / "a" / "index.html").read_text(encoding="utf-8"))
    return parser


def test_closing_script_tag_stays_inside_json_ld(tmp_path):
    root = site(tmp_path, f"schema:\n  Article:\n    headline: {json.dumps(PAYLOAD)}\n")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    parsed = scripts(root)
    # ни одного сценария, кроме разметки, который принёс бы текст поля
    assert not any(
        "__pwned" in text
        for attrs, text in parsed.found
        if attrs.get("type") != "application/ld+json"
    )
    blocks = [text for attrs, text in parsed.found if attrs.get("type") == "application/ld+json"]
    assert blocks
    nodes = []
    for text in blocks:
        data = json.loads(text)  # каждый блок — целый JSON
        nodes += data.get("@graph", [data])
    article = next(n for n in nodes if n.get("@type") == "Article")
    assert article["headline"] == PAYLOAD  # данные те же, буква в букву


def test_event_handler_in_heading_is_e025(tmp_path):
    root = site(tmp_path, body="### Title {#t onclick=alert(1)}\n\nText.\n")
    result = pipeline.run(root)
    assert "E025" in [e.code for e in result.collector.errors]


def test_section_heading_with_handler_is_e025(tmp_path):
    root = site(tmp_path, body="## Title {#t onmouseover=alert(1)}\n\nText.\n")
    result = pipeline.run(root)
    assert "E025" in [e.code for e in result.collector.errors]


def test_allowed_attributes_render_and_handlers_never_do():
    md = markdown.make(allow_raw_html=False)
    html = md.render('### Title {#t .wide lang=en data-step=2 onclick="alert(1)"}\n')
    parser = Scripts()
    parser.feed(html)
    assert parser.handlers == []
    assert 'id="t"' in html and 'class="wide"' in html
    assert 'lang="en"' in html and 'data-step="2"' in html


def test_heading_in_code_block_is_just_code(tmp_path):
    body = "Text.\n\n```md\n### Title {#t onclick=alert(1)}\n```\n"
    root = site(tmp_path, body=body)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]


def test_forbidden_attrs_reports_the_line():
    md = markdown.make()
    with pytest.raises(HeronError) as error:
        markdown.forbidden_attrs(md, "Text.\n\n## A {#a style=color:red}\n", "x.md", offset=4)
    assert error.value.code == "E025"
    assert error.value.line == 7


def test_browser_runs_no_injected_script(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    root = site(tmp_path, f"schema:\n  Article:\n    headline: {json.dumps(PAYLOAD)}\n")
    result = pipeline.run(root)
    assert not result.failed
    page_file = root / "dist" / "a" / "index.html"
    with sync_api.sync_playwright() as play:
        browser = play.chromium.launch()
        try:
            page = browser.new_page()
            dialogs: list[str] = []
            page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
            page.goto(page_file.as_uri())
            assert page.evaluate("typeof window.__pwned") == "undefined"
            data = page.evaluate(
                "[...document.querySelectorAll('script[type=\"application/ld+json\"]')]"
                ".map(s => JSON.parse(s.textContent))"
            )
            assert dialogs == []
        finally:
            browser.close()
    nodes = [n for d in data for n in d.get("@graph", [d])]
    assert any(n.get("headline") == PAYLOAD for n in nodes)
