"""Страница анкеты heron/setup/page.html: виджеты enum, subtype, bool, hours (разбор файла как текста)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from heron.setup import answers

PAGE = (Path(answers.__file__).parent / "page.html").read_text(encoding="utf-8")
NEW_KEYS = ["not_set", "filter", "add_rule", "remove", "hours_preview", "hours_order", "not_in_vocab", "remove_value"]


def _block(lang: str) -> str:
    start = PAGE.index(f"\n  {lang}: {{")
    end = PAGE.index("\n  },", start) if "\n  }," in PAGE[start:] else PAGE.index("\n};", start)
    return PAGE[start:end]


@pytest.mark.parametrize("kind", ["enum", "subtype", "bool", "hours"])
def test_page_handles_kind(kind: str):
    assert f'kind === "{kind}"' in PAGE


@pytest.mark.parametrize("fn", ["enumBox", "subtypeSelect", "boolButtons", "hoursBuilder"])
def test_page_has_widget(fn: str):
    assert f"function {fn}(" in PAGE


def test_hours_re_matches_contract():
    m = re.search(r"const HOURS_RE = new RegExp\(String\.raw`([^`]+)`\)", PAGE)
    assert m, "HOURS_RE не найден"
    assert m.group(1) == answers.HOURS_RE.pattern.replace("\\Z", "$")


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_strings_in_both_languages(lang: str, key: str):
    assert re.search(rf"\b{key}: \"", _block(lang))


def test_no_long_dashes_in_new_strings():
    new = [m.group(0) for lang in ("ru", "en") for m in re.finditer(r"\b(?:%s): \"[^\"]*\"" % "|".join(NEW_KEYS + ["day_from", "day_to", "opens", "closes", "yes", "no", "hours_bad", "delete", "hours_complex"]), _block(lang))]
    assert new
    assert not any("—" in s or "–" in s for s in new)
    widgets = PAGE[PAGE.index("function schemaList("):PAGE.index("function aboutField(")]
    assert "—" not in widgets and "–" not in widgets
