"""Остатки ревью e15-fix (E15.S1.T13): один поиск --notes, E011 вместо «engine bug»,
склонение en, конфигуратор с языком запуска.

Источник: reports/qa/E15.fix.review.report.yaml, раздел not_blocking_beta.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from heron import cli
from heron.cli import main
from heron.core.errors import HeronError
from heron.messages import say
from heron.scaffold import create

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
RU_THEME = "# Что тема ждёт от site.yaml"
EN_THEME = "# What the theme expects from site.yaml"
STARTER = "site:\n  name: Example\n  languages: [en]\ntheme:\n  source: starter\n"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.delenv("HERON_CHANNEL", raising=False)


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="Demo", languages=["en"], notes="en", agents="false")
    return root


def run(*args: str, env: dict[str, str] | None = None, input: str | None = None):
    return CliRunner().invoke(main, list(args), env=env, input=input)


def tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- конфигуратор через браузер: язык запуска доходит до apply (server.py:133) ---------


def _serve_in_context(root: Path, notes: str, port: int, ready: threading.Event, box: dict) -> None:
    """Сервер в потоке, где идёт «команда click с --notes»: как `heron setup --notes ru`."""
    from heron.setup import server

    def on_ready(token: str) -> None:
        box["token"] = token
        ready.set()

    with click.Context(click.Command("setup"), info_name="setup") as ctx:
        ctx.params["notes"] = notes
        server.run(root, "127.0.0.1", port, on_ready=on_ready)


@pytest.mark.parametrize("notes, want", [("ru", RU_THEME), ("en", EN_THEME)])
def test_browser_form_installs_the_starter_in_the_launch_language(tmp_path, notes, want):
    from tests.test_setup_access import _call, _free_port, _stop

    other = "en" if notes == "ru" else "ru"
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="Demo", languages=["en"], notes=other, agents="false")
    port, ready, box = _free_port(), threading.Event(), {}
    thread = threading.Thread(
        target=_serve_in_context, args=(root, notes, port, ready, box), daemon=True
    )
    thread.start()
    assert ready.wait(10)
    token = box["token"]
    try:
        answers = {"site": {"name": "Example", "languages": ["en"]}, "theme": {"source": "starter"}}
        status, body = _call(
            f"http://127.0.0.1:{port}/api/save", data={"answers": answers}, token=token
        )
        assert status == 200, body
    finally:
        _stop(port, token, thread)
    theme = (root / "theme" / "theme.yaml").read_text(encoding="utf-8")
    assert want in theme  # язык запуска (--notes), а не build.notes сайта


# --- один поиск --notes в контексте click ---------------------------------------


def _nested(group_notes: str | None, command_notes: str | None):
    group = click.Context(click.Group("heron"), info_name="heron")
    group.params["notes"] = group_notes
    command = click.Context(click.Command("theme"), parent=group, info_name="theme")
    command.params["notes"] = command_notes
    return group, command


@pytest.mark.parametrize(
    "group_notes, command_notes, want",
    [("ru", None, "ru"), (None, "ru", "ru"), ("en", "ru", "ru"), (None, None, None)],
)
def test_one_function_finds_notes_for_every_consumer(site: Path, group_notes, command_notes, want):
    from heron.scaffold import ctx_notes
    from heron.setup.reasons import run_lang
    from heron.themes import _site_notes

    group, command = _nested(group_notes, command_notes)
    with group, command:
        assert ctx_notes() == want
        expected = want or "en"  # сайт en: без флага - build.notes
        assert run_lang(site) == expected
        assert _site_notes(site) == expected


def test_group_flag_reaches_run_lang_and_site_notes_in_a_real_command(site: Path):
    """`heron --notes ru theme get starter`: флаг у группы, команда ставит ru-тему."""
    result = run("--notes", "ru", "theme", "get", "starter", str(site))
    assert result.exit_code == 0, result.output
    assert RU_THEME in (site / "theme" / "theme.yaml").read_text(encoding="utf-8")


def test_theme_get_passes_its_language_to_install(site: Path, monkeypatch):
    """Язык вычислен в theme_get один раз и передан явно, install не ищет его заново."""
    from heron import themes

    def boom(_root):
        raise AssertionError("install искал язык заново")

    monkeypatch.setattr(themes, "_site_notes", boom)
    result = run("theme", "get", "starter", str(site), "--notes", "ru")
    assert result.exit_code == 0, result.output
    assert RU_THEME in (site / "theme" / "theme.yaml").read_text(encoding="utf-8")
    assert CYRILLIC.search(result.output)  # сообщения тоже ru


# --- E011 вместо рамки «engine bug» ----------------------------------------------


def _frame(output: str) -> bool:
    return "unexpected error" in output or "engine bug" in output or "Traceback" in output


def _set(root: Path, text: str | bytes) -> None:
    path = root / "site.yaml"
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def _first_block(root: Path) -> str:
    return (root / "site.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("value", ["de", "xx"])
def test_init_with_a_wrong_build_notes_is_e011(site: Path, value: str):
    text = _first_block(site).replace("notes: en", f"notes: {value}")
    assert f"notes: {value}" in text
    _set(site, text)
    before = tree(site)
    result = run("init", str(site))
    assert result.exit_code == 1, result.output
    assert "E011" in result.output and not _frame(result.output)
    assert f"'{value}'" in result.output and "ru and en" in result.output
    assert "build.notes" in result.output
    assert tree(site) == before  # ничего не записано


def test_init_with_a_wrong_notes_variable_names_the_variable(site: Path):
    before = tree(site)
    result = run("init", str(site), env={"HERON_NOTES": "de"})
    assert result.exit_code == 1, result.output
    assert "E011" in result.output and not _frame(result.output)
    assert "HERON_NOTES" in result.output and "site.yaml is not valid" not in result.output
    assert tree(site) == before


def test_init_with_languages_not_a_list_is_e011(site: Path):
    text = re.sub(r"(?m)^(\s+)languages:.*$", r"\1languages: 5", _first_block(site), count=1)
    assert "languages: 5" in text
    _set(site, text)
    before = tree(site)
    result = run("init", str(site))
    assert result.exit_code == 1, result.output
    assert "E011" in result.output and not _frame(result.output)
    assert "site.languages: 5" in result.output and "not a list" in result.output
    assert tree(site) == before


def test_init_agents_with_languages_not_a_list_is_e011_too(site: Path):
    _set(site, re.sub(r"(?m)^(\s+)languages:.*$", r"\1languages: 5", _first_block(site), count=1))
    result = run("init", str(site), "--agents")
    assert result.exit_code == 1 and "E011" in result.output and not _frame(result.output)


@pytest.mark.parametrize("body", ["- 1\n- 2\n", "just text\n", "42\n"])
def test_init_with_a_root_that_is_not_a_block_is_e011(site: Path, body: str):
    _set(site, body)
    result = run("init", str(site))
    assert result.exit_code == 1, result.output
    assert "E011" in result.output and not _frame(result.output)
    assert "not a block of keys" in result.output
    assert (site / "site.yaml").read_text(encoding="utf-8") == body


def test_empty_and_raw_site_yaml_are_still_completed_by_init(site: Path):
    """Сырой конфиг - повод для init, а не для отказа: пустой файл и опечатки допустимы."""
    _set(site, "")
    assert run("init", str(site)).exit_code == 0
    _set(site, "site:\n  name: X\n  languages: [en]\n  typo_key: 1\n")
    assert run("init", str(site)).exit_code == 0


@pytest.mark.parametrize("notes, word", [("ru", "не в кодировке UTF-8"), ("en", "not UTF-8")])
def test_binary_site_yaml_is_e011_in_init_and_theme_get(site: Path, notes: str, word: str):
    _set(site, b"\xff\xfe\x00binary\x80\x81")
    for args in (
        ("init", str(site), "--notes", notes),
        ("init", str(site), "--agents", "--notes", notes),
        ("theme", "get", "starter", str(site), "--notes", notes),
    ):
        result = run(*args)
        assert result.exit_code == 1, (args, result.output)
        assert "E011" in result.output and not _frame(result.output), args
        assert word in result.output, (args, result.output)
        assert bool(CYRILLIC.search(result.output)) is (notes == "ru"), (args, result.output)
    assert (site / "site.yaml").read_bytes() == b"\xff\xfe\x00binary\x80\x81"
    assert not (site / "theme" / "theme.yaml.bak").exists()


def test_binary_site_yaml_is_e011_in_check_and_build(site: Path):
    _set(site, b"\xff\xfe\x00binary\x80\x81")
    for args in (("check", str(site)), ("build", str(site)), ("check", str(site), "--json")):
        result = run(*args)
        assert result.exit_code != 0, (args, result.output)
        assert "E011" in result.output and not _frame(result.output), (args, result.output)
        assert "UTF-8" in result.output


def test_check_json_on_a_binary_site_yaml_says_the_error_in_json(site: Path):
    _set(site, b"\xff\xfe\x00binary\x80\x81")
    result = CliRunner().invoke(main, ["check", str(site), "--json"])
    assert result.exit_code != 0
    data = json.loads(result.stdout)  # в stdout JSON, а не рамка ошибки
    assert data["ok"] is False
    assert [e["code"] for e in data["errors"]] == ["E011"]
    assert "UTF-8" in data["errors"][0]["message"]


def test_read_yaml_names_the_encoding(tmp_path: Path):
    from heron.contracts.loader import read_yaml

    path = tmp_path / "x.yaml"
    path.write_bytes(b"a: \xff\xfe\n")
    with pytest.raises(HeronError) as raised:
        read_yaml(path)
    assert raised.value.code == "E011"
    assert "UTF-8" in raised.value.message and raised.value.path == str(path)
    with pytest.raises(HeronError) as theme:
        read_yaml(path, code="E008")
    assert theme.value.code == "E008"


@pytest.mark.parametrize("notes, word", [("ru", "не удалось записать"), ("en", "could not write")])
def test_build_agents_write_failure_speaks_the_notes_language(
    tmp_path: Path, monkeypatch, notes: str, word: str
):
    from heron.core import yamlsafe
    from heron.scaffold import set_build_agents

    (tmp_path / "site.yaml").write_text("site:\n  name: X\n", encoding="utf-8")
    monkeypatch.setattr(yamlsafe, "load", lambda _text, **_: {"build": {"agents": "bogus"}})
    with pytest.raises(HeronError) as raised:
        set_build_agents(tmp_path, "false", notes)
    assert raised.value.code == "E011"
    assert word in raised.value.message
    assert bool(CYRILLIC.search(raised.value.message + raised.value.hint)) is (notes == "ru")
    assert "agents: false" in raised.value.hint


# --- --version не читает site.yaml, предел справки 64 КБ -------------------------


def test_help_limit_is_64_kb():
    assert cli.HELP_SITE_LIMIT == 64 * 1024


@pytest.mark.parametrize("args", [["--version"], ["-V"], ["--notes", "ru", "--version"]])
def test_version_never_reads_site_yaml(site: Path, monkeypatch, args):
    import heron.scaffold

    monkeypatch.chdir(site)
    read: list[Path] = []

    def spy(path):
        read.append(path)
        return None

    monkeypatch.setattr(heron.scaffold, "_declared", spy)
    monkeypatch.setattr(heron.scaffold, "notes_in_text", spy)
    result = run(*args)
    assert result.exit_code == 0 and result.output.startswith("heron, version ")
    assert read == []


def test_help_still_reads_a_small_site_yaml_and_skips_a_big_one(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "site.yaml").write_text("build:\n  notes: ru\n", encoding="utf-8")
    assert cli._help_lang(["--help"]) == "ru"
    assert cli._help_lang(["--help", "--version"]) == "ru"  # справка рядом - язык нужен
    padding = "# " + "x" * 100 + "\n"
    big = "build:\n  notes: ru\n" + padding * 700  # около 70 КБ
    (tmp_path / "site.yaml").write_text(big, encoding="utf-8")
    assert (tmp_path / "site.yaml").stat().st_size > cli.HELP_SITE_LIMIT
    assert cli._help_lang(["--help"]) == "en"


# --- склонение en ----------------------------------------------------------------


@pytest.mark.parametrize(
    "count, fix, files",
    [(1, "Fix it", "1 file"), (2, "Fix them", "2 files"), (21, "Fix them", "21 files")],
)
def test_english_counts_are_inflected(count: int, fix: str, files: str):
    assert f"{count} error" in say("en", "build_failed", count=count)
    assert fix + " and build again" in say("en", "build_failed", count=count)
    assert fix not in say("en", "check_failed", count=count)  # у check своя фраза
    assert say("en", "kit_created", code="en", n=count).endswith(files)
    assert say("en", "kit_fallback", want="ru", have="en", n=count).endswith(files)
    assert say("en", "docs_exported", target="d", n=count).endswith(files)


def test_russian_texts_do_not_change():
    assert say("ru", "docs_exported", target="d", n=1).endswith("файлов 1")
    assert "Исправьте и соберите снова" in say("ru", "build_failed", count=1)
