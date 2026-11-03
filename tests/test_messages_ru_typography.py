"""Строки интерфейса ru: без длинного и короткого тире (AGENTS.md, «Типографика»).

Проверяются все значения messages.TEXT["ru"], ru-значения групп heron.texts и
значения messages.CLICK_RU (переводы сообщений click: их видит человек).
"""

from __future__ import annotations

import pytest

from heron import messages
from heron.texts import groups

DASHES = ("—", "–")
TABLES = [name for name in ("TEXT", "TITLES", "KINDS") if "ru" in getattr(messages, name, {})]


def _bad_keys(table: dict[str, str]) -> list[str]:
    return [k for k, v in table.items() if any(d in v for d in DASHES)]


def test_tables_are_discovered():
    assert "TEXT" in TABLES


@pytest.mark.parametrize("name", TABLES)
def test_ru_own_values_have_no_long_or_short_dash(name):
    bad = _bad_keys(getattr(messages, name)["ru"])
    assert not bad, f"{name}['ru']: тире в ключах {bad}"


def test_click_ru_values_have_no_dash():
    bad = _bad_keys(messages.CLICK_RU)
    assert not bad, f"CLICK_RU: тире в ключах {bad}"


def test_all_group_ru_values_have_no_dash():
    bad = [
        f"{group}.{k}"
        for group, tables in groups().items()
        for k, v in tables.get("ru", {}).items()
        if any(d in v for d in DASHES)
    ]
    assert not bad, f"heron.texts ru: тире в ключах {bad}"


def test_mutation_dash_in_group_ru_value_is_detected(monkeypatch):
    group = next(iter(groups().values()))
    key = next(iter(group["ru"]))
    monkeypatch.setitem(group["ru"], key, "а — б")
    with pytest.raises(AssertionError, match=key):
        test_all_group_ru_values_have_no_dash()


def test_summary_warnings_ru_uses_hyphen():
    assert messages.say("ru", "summary_warnings", count=3) == "Предупреждений - 3:"


def test_report_pages_ru_uses_hyphen():
    out = messages.say("ru", "report_pages", count=3, by_lang="en: 3")
    assert " - " in out and not any(d in out for d in DASHES)


@pytest.mark.parametrize("dash", DASHES)
def test_mutation_dash_in_click_ru_value_fails_the_check(monkeypatch, dash):
    key = "{value!r} is not a valid UUID."
    assert key in messages.CLICK_RU
    monkeypatch.setitem(messages.CLICK_RU, key, f"{{value!r}} {dash} не UUID.")
    with pytest.raises(AssertionError, match=r"CLICK_RU.*not a valid UUID"):
        test_click_ru_values_have_no_dash()


@pytest.mark.parametrize("dash", DASHES)
def test_mutation_dash_in_ru_value_fails_the_check(monkeypatch, dash):
    monkeypatch.setitem(messages.TEXT["ru"], "report_pages", f"Страниц {dash} {{count}}")
    with pytest.raises(AssertionError, match=r"TEXT\['ru'\].*report_pages"):
        test_ru_own_values_have_no_long_or_short_dash("TEXT")
