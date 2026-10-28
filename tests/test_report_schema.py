"""Раздел отчёта «разметка schema.org»: строки по готовой секции, ru и en."""

from __future__ import annotations

from datetime import date

from heron.core.report import schema_lines
from heron.messages import say
from heron.schemaorg.policy import Entry, SchemaSection
from heron.schemaorg.validate import Finding

KEY = "SCH002:site.yaml:schema.entity.worksFor"
FLAG = "SCH004:content/uk/bio.md:schema.ProfilePage.about"
STALE = "SCH001:site.yaml:schema.entity"


def _entry(key: str, **over) -> Entry:
    code, file, path = key.split(":", 2)
    finding = Finding(code=code, path=path, value="x", fields={})
    return Entry(key, code, file, path, "x", finding, **over)


def _section(n: int = 1, prod: bool = True) -> SchemaSection:
    return SchemaSection(
        release="29.3",
        nodes=42,
        env_prod=prod,
        findings=[_entry(f"SCH002:site.yaml:schema.entity.p{i}") for i in range(n)],
        excepted=[
            _entry(KEY, reason="пока так", until=date(2026, 12, 31), source="site"),
            _entry(FLAG, source="flag"),
        ],
        unused=[STALE],
        expired=[_entry(KEY, until=date(2026, 10, 1), source="site")],
        pending=["practicesAt"],
    )


def test_empty_section_prints_nothing():
    assert schema_lines(SchemaSection(), "ru") == []


def test_lines_follow_contract_ru():
    lines = schema_lines(_section(), "ru")
    assert lines == [
        say("ru", "schema_head", release="29.3", nodes=42, n=1, errors=1, warnings=0),
        say("ru", "schema_exceptions_head", n=2),
        say(
            "ru",
            "schema_exception_site",
            finding=KEY,
            reason="пока так",
            until="2026-12-31",
            source="site.yaml",
        ),
        "  " + say("ru", "schema_exception_flag", finding=FLAG),
        say("ru", "schema_unused", finding=STALE),
        say("ru", "schema_expired", finding=KEY, until=date(2026, 10, 1)),
        say("ru", "schema_pending", props="practicesAt"),
    ]
    text = "\n".join(lines)
    assert "Исключения разметки: 2" in text and "«пока так»" in text
    assert "Лишнее исключение" in text and "Исключение просрочено" in text


def test_lines_follow_contract_en():
    text = "\n".join(schema_lines(_section(prod=False), "en"))
    assert "schema.org markup (vocabulary 29.3): 42 nodes, 1 findings" in text
    assert "0 errors, 1 warning)" in text
    assert "Markup exceptions: 2" in text and "--allow-schema" in text
    assert "Unused exception" in text and "Expired exception" in text


def test_plural_ru():
    one = schema_lines(_section(1), "ru")[0]
    few = schema_lines(_section(2), "ru")[0]
    many = schema_lines(_section(5), "ru")[0]
    assert "1 ошибка" in one and "2 ошибки" in few and "5 ошибок" in many
    assert "0 предупреждений" in one


def test_plural_en_dev():
    one = schema_lines(_section(1, prod=False), "en")[0]
    many = schema_lines(_section(5, prod=False), "en")[0]
    assert "1 warning)" in one and "5 warnings)" in many
