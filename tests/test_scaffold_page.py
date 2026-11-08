"""`heron page`: заготовка страницы целиком на языке пояснений сайта (E15.S1.T4: F03).

Тело заготовки — подсказки автору, как и SEO-блок над ним, поэтому оба на
языке `build.notes` (или HERON_NOTES), а не на языке страницы: страница
`content/en/` русскоязычного автора получает русские подсказки, которые он
заменит английским текстом.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.modules import nginx
from heron.scaffold import create
from heron.scaffold.page import BODY
from tests.edit_corpus import write_page

CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")
# латиница в русской заготовке — только токены: TODO, имена ключей и типов
RU_TOKENS = {"TODO", "title", "h1", "description", "nav_title", "slug", "type", "about"}


def _site(tmp_path, notes, languages=("en",)):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=list(languages), notes=notes)
    return root


def _body(text):
    return text.split("---", 2)[2]


def test_body_tables_have_the_same_keys():
    assert set(BODY["ru"]) == set(BODY["en"])
    for words in BODY.values():
        assert words["heading"].startswith("TODO") and words["content"].startswith("TODO")


def test_english_site_gets_no_cyrillic(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site(tmp_path, "en")
    text = write_page(root, "page", "about").read_text(encoding="utf-8")
    assert not CYRILLIC.search(text), [line for line in text.splitlines() if CYRILLIC.search(line)]
    assert BODY["en"]["intro"] in text
    assert BODY["en"]["heading"] in text or "## " not in _body(text)


def test_russian_site_body_is_russian(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site(tmp_path, "ru")
    text = write_page(root, "page", "about").read_text(encoding="utf-8")
    body = _body(text)
    assert BODY["ru"]["intro"] in body
    for line in body.splitlines():
        plain = re.sub(r"\{#[\w-]+\}", " ", line)
        stray = [w for w in re.findall(r"[A-Za-z]{2,}", plain) if w not in RU_TOKENS]
        assert not stray, (line, stray)
    head = yaml.safe_load(text.split("---", 2)[1])
    assert head["description"] == BODY["ru"]["description"]


def test_page_of_another_language_keeps_the_notes_language(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site(tmp_path, "ru", languages=("ru", "en"))
    text = write_page(root, "page", "about", lang="en").read_text(encoding="utf-8")
    assert BODY["ru"]["intro"] in text
    assert BODY["en"]["intro"] not in text


@pytest.mark.parametrize("notes", ["ru", "en"])
def test_env_switches_the_body_with_the_seo_block(tmp_path, monkeypatch, notes):
    other = "en" if notes == "ru" else "ru"
    root = _site(tmp_path, other)
    monkeypatch.setenv("HERON_NOTES", notes)
    text = write_page(root, "page", "about").read_text(encoding="utf-8")
    assert BODY[notes]["intro"] in text
    assert BODY[other]["intro"] not in text
    assert bool(CYRILLIC.search(text)) is (notes == "ru")


def test_cli_page_in_english_site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(main, ["new", "site", "--notes", "en", "-y"]).exit_code == 0
    result = runner.invoke(main, ["page", "add", "about", "site"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "site" / "content" / "en" / "about.md").read_text(encoding="utf-8")
    assert "Вводный" not in text and not CYRILLIC.search(text)


# --- заготовка без инлайн-скриптов, CSP по включённым счётчикам (E15.S1.T20) -----

COUNTERS = {"ga4": "G-TEST000001", "gtm": "GTM-TEST001", "metrika": 10000001}
GOOGLE = ("googletagmanager.com", "google-analytics.com")
YANDEX = ("mc.yandex.ru",)
DIRECTIVES = ("script-src", "connect-src", "img-src")


class _Tags(HTMLParser):
    """Теги <script> и обработчики событий в разметке, как их видит разборщик HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts: list[dict[str, str | None]] = []
        self.handlers: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append(dict(attrs))
        self.handlers += [name for name, _ in attrs if name.startswith("on")]


def _built(tmp_path, analytics=None):
    root = tmp_path / "built"
    create(root, name="demo", languages=["en"], demo=True)
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    if analytics:
        data["analytics"] = analytics
    (root / "site.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, [e.message for e in result.collector.errors]
    return root / "dist"


def _tags(page: Path) -> _Tags:
    tags = _Tags()
    tags.feed(page.read_text(encoding="utf-8"))
    return tags


def _csp(dist: Path) -> dict[str, list[str]]:
    conf = (dist / nginx.NAME).read_text(encoding="utf-8")
    found = set(re.findall(r'add_header Content-Security-Policy "([^"]+)"', conf))
    assert len(found) == 1, found  # одна политика во всех location
    return {p.split()[0]: p.split()[1:] for p in found.pop().split(";") if p.strip()}


@pytest.mark.parametrize("analytics", [None, COUNTERS], ids=["plain", "counters"])
def test_built_pages_have_no_inline_scripts(tmp_path, analytics):
    dist = _built(tmp_path, analytics)
    pages = list(dist.rglob("*.html"))
    assert pages
    for page in pages:
        tags = _tags(page)
        assert not tags.handlers, page
        inline = [
            s for s in tags.scripts if "src" not in s and s.get("type") != "application/ld+json"
        ]
        assert not inline, (page, inline)


def test_page_loads_site_js_in_head_before_paint(tmp_path):
    dist = _built(tmp_path)
    assert (dist / "assets" / "site.js").is_file()
    html = (dist / "index.html").read_text(encoding="utf-8")
    head = html.split("</head>", 1)[0]
    match = re.search(r'<script src="/assets/site\.js"([^>]*)>', head)
    assert match, head
    # без defer и async: ранняя установка темы выполняется до отрисовки
    assert "defer" not in match.group(1) and "async" not in match.group(1)
    assert head.index("/assets/site.js") < head.index("/assets/site.css")


def test_counter_ids_reach_site_js_as_data_attributes(tmp_path):
    dist = _built(tmp_path, COUNTERS)
    tags = _tags(dist / "index.html")
    script = next(s for s in tags.scripts if s.get("src") == "/assets/site.js")
    assert script["data-ga4"] == "G-TEST000001"
    assert script["data-gtm"] == "GTM-TEST001"
    assert script["data-metrika"] == "10000001"
    assert "[data-consent]" in (dist / "assets" / "site.js").read_text(encoding="utf-8")


def test_counter_ids_stay_out_of_pages_when_the_build_forbids_analytics(tmp_path):
    root = tmp_path / "dev"
    create(root, name="demo", languages=["en"], demo=True)
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["analytics"] = COUNTERS
    (root / "site.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert not pipeline.run(root, env=BuildEnv.named("dev")).failed
    tags = _tags(root / "dist" / "index.html")
    script = next(s for s in tags.scripts if s.get("src") == "/assets/site.js")
    assert not [name for name in script if name.startswith("data-")]


def test_csp_without_analytics_has_no_foreign_domains(tmp_path):
    csp = _csp(_built(tmp_path))
    assert csp["script-src"] == ["'self'"]
    assert "connect-src" not in csp
    assert csp["img-src"] == ["'self'", "data:"]


@pytest.mark.parametrize(
    "analytics, allowed, denied",
    [
        ({"ga4": "G-TEST000001"}, GOOGLE, YANDEX),
        ({"gtm": "GTM-TEST001"}, GOOGLE, YANDEX),
        ({"metrika": 10000001}, YANDEX, GOOGLE),
    ],
    ids=["ga4", "gtm", "metrika"],
)
def test_csp_lists_only_enabled_counters(tmp_path, analytics, allowed, denied):
    csp = _csp(_built(tmp_path, analytics))
    for directive in DIRECTIVES:
        values = " ".join(csp[directive])
        assert "'self'" in csp[directive]
        assert all(domain in values for domain in allowed), (directive, values)
        assert not any(domain in values for domain in denied), (directive, values)
    assert "unsafe-inline" not in " ".join(csp["script-src"])
