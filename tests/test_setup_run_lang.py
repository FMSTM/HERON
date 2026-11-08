"""Анкета и каталог тем говорят на языке запуска (F19, F22, F28)."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron import setup, themes
from heron.cli import main
from heron.setup import server

PAGE = Path(setup.__file__).parent / "page.js"  # скрипт конфигуратора (ST8)
CYR = re.compile("[А-Яа-яЁё]")


def _site(root: Path) -> Path:
    (root / "content" / "ru").mkdir(parents=True)
    (root / "site.yaml").write_text(
        "site:\n  name: Before\n  domain: example.test\n  languages: [ru]\n  default_lang: ru\n"
        "build:\n  notes: ru\ntheme:\n  name: theme\n",
        encoding="utf-8",
    )
    return root


def test_state_lang_overrides_site_notes(tmp_path):
    root = _site(tmp_path)
    assert setup.state(root, lang="en")["notes"] == "en"
    assert setup.state(root)["notes"] == "ru"


def test_server_started_with_en_serves_en_on_ru_site(tmp_path, monkeypatch):
    from tests.test_setup_access import _call, _free_port, _stop  # noqa: PLC0415

    monkeypatch.setenv("HERON_NOTES", "en")
    root = _site(tmp_path)
    port = _free_port()
    ready = threading.Event()
    box: dict[str, str] = {}

    def on_ready(token: str) -> None:
        box["token"] = token
        ready.set()

    thread = threading.Thread(
        target=server.run, args=(root, "127.0.0.1", port), kwargs={"on_ready": on_ready}
    )
    thread.daemon = True
    thread.start()
    assert ready.wait(10)
    try:
        status, body = _call(f"http://127.0.0.1:{port}/api/state", token=box["token"])
        assert status == 200
        assert json.loads(body)["notes"] == "en"
    finally:
        _stop(port, box["token"], thread)


def test_page_placeholders_have_no_cyrillic():
    text = PAGE.read_text("utf-8")
    block = re.search(r"const PLACEHOLDER = \{.*?\};", text, re.S)
    assert block
    assert not CYR.search(block.group(0))


def test_starter_has_both_descriptions():
    starter = themes._catalog("file:///nonexistent", 0.1)[0]
    assert starter["name"] == themes.STARTER
    assert not CYR.search(starter["description"])
    assert CYR.search(starter["description_ru"])
    assert "—" not in starter["description_ru"] and "–" not in starter["description_ru"]


@pytest.mark.parametrize(("lang", "key"), [("ru", "description_ru"), ("en", "description")])
def test_theme_list_follows_notes(lang, key, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    starter = themes._catalog("file:///nonexistent", 0.1)[0]
    monkeypatch.setattr(themes, "catalog", lambda *a, **k: [starter])
    result = CliRunner().invoke(main, ["--notes", lang, "theme", "list"])
    assert result.exit_code == 0, result.output
    assert starter[key] in result.output
