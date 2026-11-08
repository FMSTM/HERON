"""heron check: E008 для страницы, у типа которой в теме нет шаблона (E15.S2.T68)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.core import build as buildmod
from heron.scaffold import create

PAGE = "---\ntitle: Odd\nh1: Other heading\n{extra}description: A test page\n---\n\nText.\n"


def site(tmp_path: Path, extra: str = "type: no-such-type\n") -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True, notes="en")
    odd = root / "content/en/odd.md"
    odd.parent.mkdir(parents=True, exist_ok=True)
    odd.write_text(PAGE.format(extra=extra), encoding="utf-8")
    return root


def run(root: Path, *args: str):
    return CliRunner().invoke(main, ["check", str(root), *args])


def test_unknown_type_gives_e008(tmp_path: Path) -> None:
    result = run(site(tmp_path), "--notes", "en")
    assert result.exit_code == 1
    assert "E008" in result.output
    assert "en/odd.md" in result.output


def test_unknown_type_json(tmp_path: Path) -> None:
    result = run(site(tmp_path), "--json", "--notes", "en")
    assert result.exit_code == 1
    found = [f for f in json.loads(result.output)["errors"] if f["code"] == "E008"]
    assert len(found) == 1
    assert found[0]["path"].endswith("en/odd.md")


def test_unknown_type_ru(tmp_path: Path) -> None:
    result = run(site(tmp_path), "--json", "--notes", "ru")
    found = [f for f in json.loads(result.output)["errors"] if f["code"] == "E008"]
    assert len(found) == 1
    assert any("а" <= ch <= "я" for ch in found[0]["message"].lower())


def test_known_type_is_green(tmp_path: Path) -> None:
    result = run(site(tmp_path, extra=""), "--json", "--notes", "en")
    assert result.exit_code == 0
    assert not [f for f in json.loads(result.output)["errors"] if f["code"] == "E008"]


def test_type_with_theme_template_is_green(tmp_path: Path) -> None:
    root = site(tmp_path)
    theme = root / "theme/theme.yaml"
    data = yaml.safe_load(theme.read_text(encoding="utf-8"))
    # подсказки на обоих языках стартовой темы: без них check ловит hint, а не шаблон
    data["types"]["no-such-type"] = {
        "template": "page.html",
        "uses": ["*"],
        "hint_ru": "Тип со своим шаблоном",
        "hint_en": "A type with its own template",
    }
    theme.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run(root, "--json", "--notes", "en")
    assert not [f for f in json.loads(result.output)["errors"] if f["code"] == "E008"]


def test_mutation_without_call_check_is_silent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(buildmod.templates_check, "missing_templates", lambda *a, **k: None)
    result = run(site(tmp_path), "--json", "--notes", "en")
    assert not [f for f in json.loads(result.output)["errors"] if f["code"] == "E008"]
