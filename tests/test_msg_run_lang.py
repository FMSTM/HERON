"""E033 и находки schema.org идут на языке запуска, а не на build.notes (E15.S2.T30).

Язык запуска: `--notes`, затем HERON_NOTES, затем `build.notes`. Сайт строится
в tmp_path, команды идут через CliRunner.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.messages import say
from heron.scaffold import create

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
MUTATION = "{% set items = [] %}{{ items.append(1) }}"
CALL = "items.append(…)"
FINDING = "SCH002"
# Находок больше, чем сводка показывает примерами: иначе файла полного списка нет.
UNKNOWN_PROPS = [f"noSuchProp{index}" for index in range(12)]


@pytest.fixture(autouse=True)
def no_env_language(monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.delenv("SITE_ENV", raising=False)


def make_site(tmp_path: Path, notes: str) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True, notes=notes)
    return root


def with_mutation(tmp_path: Path, notes: str) -> Path:
    """Сайт, шаблон которого меняет данные: E033 и у check, и у build."""
    root = make_site(tmp_path, notes)
    page = root / "theme/templates/page.html"
    page.write_text(
        '{% extends "base.html" %}\n{% block content %}\n' + MUTATION + "\n{% endblock %}\n",
        encoding="utf-8",
    )
    return root


def with_schema_findings(tmp_path: Path, notes: str) -> Path:
    """Сайт, у разметки которого много находок SCH002 (латиницей: значения в текст попадают)."""
    root = make_site(tmp_path, notes)
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entity = {"@type": "IndividualPhysician", "@id": "#me"}
    entity.update({prop: "Clinic" for prop in UNKNOWN_PROPS})
    data["schema"] = {**(data.get("schema") or {}), "entity": entity}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return root


def run(*args: str):
    return CliRunner().invoke(main, list(args))


def e033_of(output: str) -> dict:
    data = json.JSONDecoder().raw_decode(output[output.index("{") :])[0]
    found = [item for item in data["errors"] if item["code"] == "E033"]
    assert found, output
    return found[0]


def finding_lines(output: str) -> list[str]:
    lines = [line for line in output.splitlines() if FINDING in line]
    assert lines, output
    return lines


def full_list(root: Path) -> list[tuple[str, str]]:
    """(path, message) строк полного списка с находками разметки; kind не смотрим (F25)."""
    full = root / ".heron-cache" / "warnings.txt"
    assert full.is_file()
    rows = [line.split("\t", 2) for line in full.read_text(encoding="utf-8").splitlines()]
    found = [(where, message) for _, where, message in rows if FINDING in message]
    assert found, rows
    return found


def test_check_en_on_ru_site_has_no_cyrillic(tmp_path):
    root = with_mutation(tmp_path, "ru")
    result = run("check", str(root), "--notes", "en")
    assert result.exit_code == 1, result.output
    assert "E033" in result.output
    assert not CYRILLIC.search(result.output), result.output
    assert not CYRILLIC.search(result.stderr), result.stderr


def test_check_json_en_on_ru_site_has_no_cyrillic(tmp_path):
    root = with_mutation(tmp_path, "ru")
    item = e033_of(run("check", str(root), "--json", "--notes", "en").output)
    assert item["message"] == say("en", "sandbox_mutation", call=CALL)
    assert item["hint"] == say("en", "sandbox_hint_add")
    assert not CYRILLIC.search(item["message"] + item["hint"]), item


def test_build_en_on_ru_site_e033_has_no_cyrillic(tmp_path):
    root = with_mutation(tmp_path, "ru")
    result = run("build", str(root), "--notes", "en")
    assert result.exit_code == 1, result.output
    assert "E033" in result.output
    assert not CYRILLIC.search(result.output), result.output


def test_check_json_ru_on_en_site_is_the_russian_text(tmp_path):
    root = with_mutation(tmp_path, "en")
    item = e033_of(run("check", str(root), "--json", "--notes", "ru").output)
    assert item["message"] == say("ru", "sandbox_mutation", call=CALL)
    assert item["hint"] == say("ru", "sandbox_hint_add")


def test_build_en_on_ru_site_schema_findings_have_no_cyrillic(tmp_path):
    root = with_schema_findings(tmp_path, "ru")
    result = run("build", str(root), "--notes", "en")
    assert result.exit_code == 0, result.output
    for line in finding_lines(result.output):
        assert not CYRILLIC.search(line), line
    for where, message in full_list(root):
        assert not CYRILLIC.search(where + message), message


def test_build_ru_on_en_site_schema_findings_are_russian(tmp_path):
    root = with_schema_findings(tmp_path, "en")
    result = run("build", str(root), "--notes", "ru")
    assert result.exit_code == 0, result.output
    assert any(CYRILLIC.search(line) for line in finding_lines(result.output)), result.output
    for _, message in full_list(root):
        assert CYRILLIC.search(message), message


def test_check_json_schema_findings_follow_the_run_language(tmp_path):
    root = with_schema_findings(tmp_path, "ru")
    data = run("check", str(root), "--json", "--notes", "en").output
    lines = [w for w in json.loads(data[data.index("{") :])["warnings"]]
    found = [w["message"] for w in lines if FINDING in w["message"]]
    assert found, data
    assert not CYRILLIC.search("".join(found)), found


@pytest.mark.parametrize(("notes", "russian"), [("ru", True), ("en", False)])
def test_without_flag_and_env_the_language_is_build_notes(tmp_path, notes, russian):
    root = with_mutation(tmp_path, notes)
    item = e033_of(run("check", str(root), "--json").output)
    assert item["message"] == say(notes, "sandbox_mutation", call=CALL)
    assert bool(CYRILLIC.search(item["message"])) is russian


@pytest.mark.parametrize(("notes", "russian"), [("ru", True), ("en", False)])
def test_schema_findings_without_flag_and_env_follow_build_notes(tmp_path, notes, russian):
    root = with_schema_findings(tmp_path, notes)
    result = run("build", str(root))
    assert result.exit_code == 0, result.output
    assert all(bool(CYRILLIC.search(message)) is russian for _, message in full_list(root))


def test_heron_notes_outranks_build_notes(tmp_path, monkeypatch):
    root = with_schema_findings(tmp_path / "schema", "ru")
    monkeypatch.setenv("HERON_NOTES", "en")
    result = run("build", str(root))
    assert result.exit_code == 0, result.output
    for _, message in full_list(root):
        assert not CYRILLIC.search(message), message


def test_serve_once_passes_the_run_language_to_the_build(tmp_path, monkeypatch):
    from heron.core import build as build_module
    from heron.core import watch

    root = with_schema_findings(tmp_path, "ru")
    seen: dict = {}
    real = build_module.run

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(build_module, "run", spy)
    watch.once(root, drafts=False, dist=tmp_path / "dist", lang="en")
    assert seen["notes_lang"] == "en"


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_serve_once_prod_output_follows_the_run_language(tmp_path, monkeypatch, capsys, lang):
    from heron.core import watch

    root = with_schema_findings(tmp_path, "ru")
    monkeypatch.setenv("SITE_ENV", "prod")
    watch.once(root, drafts=False, dist=tmp_path / "dist", lang=lang)
    out = capsys.readouterr().out
    assert out.strip()
    assert bool(CYRILLIC.search(out)) is (lang == "ru"), out
