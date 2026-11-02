"""Строки интерфейса en: без длинного и короткого тире (AGENTS.md, «Типографика»)."""

from __future__ import annotations

import pytest

from heron import messages

DASHES = ("—", "–")
TABLES = [name for name in ("TEXT", "TITLES", "KINDS") if "en" in getattr(messages, name, {})]


def _bad_keys(table: dict[str, str]) -> list[str]:
    return [key for key, value in table.items() if any(d in value for d in DASHES)]


def test_tables_are_discovered():
    assert "TEXT" in TABLES and "TITLES" in TABLES


@pytest.mark.parametrize("name", TABLES)
def test_en_values_have_no_long_or_short_dash(name):
    bad = _bad_keys(getattr(messages, name)["en"])
    assert not bad, f"{name}['en']: тире в ключах {bad}"


def test_report_pages_en_uses_hyphen():
    out = messages.say("en", "report_pages", count=3, by_lang="en: 3")
    assert " - " in out and not any(d in out for d in DASHES)


def test_plan_notes_en_uses_hyphen_and_ru_keeps_dash():
    out = messages.say("en", "plan_notes", count=2)
    assert " - " in out and not any(d in out for d in DASHES)
    assert "—" in messages.say("ru", "plan_notes", count=2)
    assert "—" in messages.say("ru", "report_pages", count=3, by_lang="en: 3")


@pytest.mark.parametrize("dash", DASHES)
def test_mutation_dash_in_en_value_fails_the_check(monkeypatch, dash):
    monkeypatch.setitem(messages.TEXT["en"], "report_pages", f"Pages {dash} {{count}}")
    with pytest.raises(AssertionError, match=r"TEXT\['en'\].*report_pages"):
        test_en_values_have_no_long_or_short_dash("TEXT")
