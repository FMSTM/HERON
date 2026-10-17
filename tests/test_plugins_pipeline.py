"""Настоящий плагин сайта проходит весь конвейер — каждым заявленным хуком.

Раньше в реестре были on_page_parsed, on_page_rendered, block:<имя>,
фильтры и глобальные переменные, а конвейер их не звал; on_build_finished
шёл до записи результата; check и build применяли расширения по-разному.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heron.core import build as pipeline
from heron.scaffold import create

PLUGIN = """
import json, os
from pathlib import Path

LOG = Path(os.environ["HERON_PROBE_LOG"])


def note(event, **data):
    with LOG.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"event": event, **data}) + "\\n")


def register(hooks):
    hooks.on("on_config", lambda config, theme: note("on_config"))

    def parsed(page):
        note("on_page_parsed", page=page.source)
        if page.source == "en/a.md":
            page.meta.description = "changed by plugin"
    hooks.on("on_page_parsed", parsed)

    def tree(site):
        note("on_tree_built", pages=len(site.pages))
    hooks.on("on_tree_built", tree)

    def card(section):
        note("block:card", section=section.id)
        return {"lines": [line for line in section.raw.splitlines() if line.strip()]}
    hooks.on("block:card", card)

    hooks.filter("shout", lambda text: str(text).upper() + "!")
    hooks.add_global("plugin_name", "probe")

    def rendered(page, html):
        note("on_page_rendered", page=page.url)
        return html.replace("</body>", "<!-- rendered by probe --></body>")
    hooks.on("on_page_rendered", rendered)

    def generate(site, config):
        note("on_generate")
        return {"probe.txt": "pages: " + str(len(site.pages)) + "\\n"}
    hooks.on("on_generate", generate)

    def finished(site, config, dist):
        note("on_build_finished", written=(Path(dist) / "probe.txt").is_file())
    hooks.on("on_build_finished", finished)
"""


@pytest.fixture
def site(tmp_path, monkeypatch):
    log = tmp_path / "events.jsonl"
    monkeypatch.setenv("HERON_PROBE_LOG", str(log))
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    plugin = root / "plugins" / "probe"
    plugin.mkdir(parents=True)
    (plugin / "__init__.py").write_text(PLUGIN, encoding="utf-8")
    yaml_path = root / "site.yaml"
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8") + "\nplugins: [probe]\n", encoding="utf-8"
    )
    (root / "content/en/a.md").write_text(
        "---\ntitle: A\nh1: A page\ndescription: D\n---\n\nText.\n\n"
        "## Card {#card .card}\n\nfirst line\n\nsecond line\n",
        encoding="utf-8",
    )
    page = root / "theme/templates/page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</h1>", "</h1><b>{{ 'hi' | shout }} {{ plugin_name }}</b>", 1
        ),
        encoding="utf-8",
    )
    return root, log


def events(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def names(log: Path) -> list[str]:
    seen: list[str] = []
    for event in events(log):
        if event["event"] not in seen:
            seen.append(event["event"])
    return seen


def test_every_documented_hook_runs_in_its_stage(site):
    root, log = site
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert names(log) == [
        "on_config",
        "block:card",
        "on_page_parsed",
        "on_tree_built",
        "on_page_rendered",
        "on_generate",
        "on_build_finished",
    ]
    page = result.site.page("a", "en")
    assert page.meta.description == "changed by plugin"
    assert page.sections["card"].kind == "card"
    assert page.sections["card"].data == {"lines": ["first line", "second line"]}
    html = (root / "dist/a/index.html").read_text(encoding="utf-8")
    assert "<b>HI! probe</b>" in html  # фильтр и глобальная переменная
    assert "<!-- rendered by probe -->" in html
    assert 'content="changed by plugin"' in html
    assert (root / "dist/probe.txt").read_text(encoding="utf-8").startswith("pages: ")
    finished = [e for e in events(log) if e["event"] == "on_build_finished"]
    assert finished == [{"event": "on_build_finished", "written": True}]  # уже после записи


def test_check_applies_the_same_content_extensions(site):
    root, log = site
    result = pipeline.check(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert names(log) == ["on_config", "block:card", "on_page_parsed", "on_tree_built"]
    assert result.site.page("a", "en").sections["card"].kind == "card"


def test_each_build_runs_the_hooks_once_and_fresh(site):
    root, log = site
    pipeline.run(root)
    pipeline.run(root)
    counted = [e["event"] for e in events(log)]
    assert counted.count("on_config") == 2
    assert counted.count("on_generate") == 2
    assert counted.count("on_build_finished") == 2


def test_failed_build_does_not_reach_on_build_finished(site):
    root, log = site
    (root / "content/en/broken.md").write_text("---\ntitle: X\n---\n\nno h1\n", encoding="utf-8")
    result = pipeline.run(root)
    assert result.failed
    assert "on_build_finished" not in names(log)


def test_plugin_file_cannot_take_a_generated_path(site, tmp_path):
    root, _ = site
    init = root / "plugins/probe/__init__.py"
    init.write_text(
        init.read_text(encoding="utf-8").replace('"probe.txt"', '"robots.txt"'), encoding="utf-8"
    )
    result = pipeline.run(root)
    assert "E026" in [e.code for e in result.collector.errors]


def test_old_style_files_from_on_build_finished_are_explained(site):
    root, _ = site
    init = root / "plugins/probe/__init__.py"
    init.write_text(
        init.read_text(encoding="utf-8")
        + "\n\ndef register_old(hooks):\n    pass\n\n"
        + "_register = register\n\n"
        + "def register(hooks):\n    _register(hooks)\n"
        + "    hooks.on('on_build_finished', lambda site, config, dist: {'old.txt': 'x'})\n",
        encoding="utf-8",
    )
    result = pipeline.run(root)
    assert not result.failed
    assert not (root / "dist/old.txt").exists()
    assert any("on_generate" in notice for notice in result.notices)


def test_builtin_names_are_not_overridden_by_plugins(site):
    root, _ = site
    init = root / "plugins/probe/__init__.py"
    init.write_text(
        init.read_text(encoding="utf-8").replace(
            'hooks.add_global("plugin_name", "probe")',
            'hooks.add_global("plugin_name", "probe")\n    hooks.add_global("absolute", None)',
        ),
        encoding="utf-8",
    )
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert Path(root / "dist/index.html").is_file()
