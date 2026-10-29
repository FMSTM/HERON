"""CLI: --allow-schema у build и check, --env у check, раздел schema в check --json."""

import json

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main

KEY = "SCH002:site.yaml:schema.entity.worksFor"
OTHER = "SCH002:site.yaml:schema.entity.nope"
ENTITY = {"@type": "IndividualPhysician", "@id": "#me", "worksFor": "Клиника"}


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    created = CliRunner().invoke(main, ["new", "demo", "--no-agents"])
    assert created.exit_code == 0, created.output
    path = tmp_path / "demo" / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["schema"] = {**(data.get("schema") or {}), "entity": ENTITY}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return tmp_path / "demo"


def _run(*args):
    return CliRunner().invoke(main, list(args))


def test_prod_with_finding_fails(site):
    result = _run("check", "--env", "prod", str(site))
    assert result.exit_code == 1, result.output
    assert KEY in result.output


def test_allow_schema_passes_and_is_reported(site):
    result = _run("check", "--env", "prod", "--allow-schema", KEY, str(site))
    assert result.exit_code == 0, result.output
    assert any(
        KEY in line
        and ("разово (--allow-schema)" in line or "one-off (--allow-schema)" in line)
        for line in result.output.splitlines()
    ), result.output


def test_bad_key_is_usage_error(site):
    result = _run("check", "--allow-schema", "bad", str(site))
    assert result.exit_code == 2
    assert "bad" in result.output


def test_bad_key_on_build_is_usage_error(site):
    result = _run("build", "--allow-schema", "SCH999:a:b", str(site))
    assert result.exit_code == 2


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_help_shows_flags(lang):
    result = CliRunner().invoke(main, ["--notes", lang, "check", "--help"])
    assert result.exit_code == 0
    assert "--env" in result.output
    assert "--allow-schema" in result.output


def test_json_has_schema_section(site):
    result = _run("check", "--json", "--env", "prod", str(site))
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert "schema" in data
    assert any(f["key"] == KEY for f in data["schema"]["findings"])


def test_repeated_flag_and_unused_key(site):
    result = _run(
        "check", "--json", "--env", "prod", "--allow-schema", KEY, "--allow-schema", OTHER, str(site)
    )
    data = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert OTHER in data["schema"]["unused"]
    assert any(e["key"] == KEY for e in data["schema"]["excepted"])
    text = _run("check", "--env", "prod", "--allow-schema", KEY, "--allow-schema", OTHER, str(site))
    assert OTHER in text.output
    unused_line = next(line for line in text.output.splitlines() if OTHER in line)
    assert "--allow-schema" in unused_line
    assert "schema_exceptions" in unused_line
