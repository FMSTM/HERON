"""Тексты проверки разметки schema.org (E17.S2.T2): ключи есть на ru и en и форматируются."""

import pytest

from heron.messages import TEXT, say, title

FIELDS = {
    "value": "Physican",
    "release": "29.3",
    "suggest": "Physician",
    "types": "IndividualPhysician",
    "prop": "worksFor",
    "domain": "Person",
    "enum": "MedicalSpecialty",
    "members": "Cardiovascular, Dermatology",
    "got": "Text",
    "expected": "URL",
    "replacement": "practicesAt",
    "url": "/media/x.jpg",
    "nodes": 40,
    "n": 3,
    "errors": 1,
    "warnings": 2,
    "finding": "SCH002:site.yaml:schema.entity.worksFor",
    "reason": "переход на practicesAt",
    "until": "2026-12-31",
    "source": "site.yaml",
    "props": "practicesAt, isAcceptingNewPatients",
}

KEYS = [f"sch00{n}_{part}" for n in range(1, 7) for part in ("detail", "hint")] + [
    "schema_head",
    "schema_key",
    "schema_exceptions_head",
    "schema_exception_site",
    "schema_exception_flag",
    "schema_unused",
    "schema_expired",
    "schema_pending",
    "schema_reason_missing",
    "schema_exception_twice",
    "schema_key_bad",
]


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("key", KEYS)
def test_key_formats(lang: str, key: str) -> None:
    assert key in TEXT[lang], (lang, key)
    text = say(lang, key, **FIELDS)
    assert text.strip() and "{" not in text


def test_detail_uses_repr() -> None:
    assert say("en", "sch002_detail", types="Person", prop="worksFor") == (
        "type Person has no property 'worksFor'"
    )
    assert say("ru", "sch006_detail", prop="image", url="/a.jpg") == "image: /a.jpg - файла нет в сборке"


@pytest.mark.parametrize(
    ("errors", "warnings", "expected"),
    [
        (1, 2, "(1 ошибка, 2 предупреждения)"),
        (3, 5, "(3 ошибки, 5 предупреждений)"),
        (11, 21, "(11 ошибок, 21 предупреждение)"),
    ],
)
def test_schema_head_plural_ru(errors: int, warnings: int, expected: str) -> None:
    line = say("ru", "schema_head", release="29.3", nodes=7, n=errors + warnings, errors=errors, warnings=warnings)
    assert line.startswith("Разметка schema.org (словарь 29.3): узлов 7")
    assert line.endswith(expected)


def test_schema_head_plural_en() -> None:
    assert say("en", "schema_head", release="29.3", nodes=7, n=3, errors=1, warnings=2) == (
        "schema.org markup (vocabulary 29.3): 7 nodes, 3 findings (1 error, 2 warnings)"
    )


@pytest.mark.parametrize("code", [f"SCH00{n}" for n in range(1, 7)])
def test_titles_both_languages(code: str) -> None:
    ru, en = title("ru", code), title("en", code)
    assert ru != code and en != code and ru != en


def test_missing_field_is_an_error() -> None:
    with pytest.raises(KeyError):
        say("en", "sch001_detail", value="X")
