"""Строки интерфейса ru: без длинного и короткого тире (AGENTS.md, «Типографика»).

Проверяются собственные значения heron.messages; ключи из групп heron/texts
правят отдельные задачи (E15.S2.T48-T50).
"""

from __future__ import annotations

import pytest

from heron import messages
from heron.texts import groups

DASHES = ("—", "–")
TABLES = [name for name in ("TEXT", "TITLES", "KINDS") if "ru" in getattr(messages, name, {})]


def _group_keys() -> set[str]:
    keys: set[str] = set()
    for tables in groups().values():
        keys.update(tables.get("ru", {}))
    return keys


def _bad_keys(table: dict[str, str], skip: set[str]) -> list[str]:
    return [k for k, v in table.items() if k not in skip and any(d in v for d in DASHES)]


def test_tables_are_discovered():
    assert "TEXT" in TABLES


@pytest.mark.parametrize("name", TABLES)
def test_ru_own_values_have_no_long_or_short_dash(name):
    skip = _group_keys() if name == "TEXT" else set()
    bad = _bad_keys(getattr(messages, name)["ru"], skip)
    assert not bad, f"{name}['ru']: тире в ключах {bad}"


def test_summary_warnings_ru_uses_hyphen():
    assert messages.say("ru", "summary_warnings", count=3) == "Предупреждений - 3:"


def test_report_pages_ru_uses_hyphen():
    out = messages.say("ru", "report_pages", count=3, by_lang="en: 3")
    assert " - " in out and not any(d in out for d in DASHES)


@pytest.mark.parametrize("dash", DASHES)
def test_mutation_dash_in_ru_value_fails_the_check(monkeypatch, dash):
    monkeypatch.setitem(messages.TEXT["ru"], "report_pages", f"Страниц {dash} {{count}}")
    with pytest.raises(AssertionError, match=r"TEXT\['ru'\].*report_pages"):
        test_ru_own_values_have_no_long_or_short_dash("TEXT")
