"""Сообщения разметки на ключах texts/markup.py: ru прежний, en без кириллицы."""

import re

from heron.messages import Msg, say
from heron.schemaorg.validate import validate

CYR = re.compile("[а-яА-ЯёЁ]")


def _by_code(result, code):
    return next(f for f in result.findings if f.code == code)


def test_validate_got_is_msg_with_both_languages():
    result = validate({"@type": "Person", "birthDate": 5})
    got = _by_code(result, "SCH004").fields["got"]
    assert isinstance(got, Msg)
    assert got == "число"
    assert got.text("en") == "number"


def test_validate_string_got():
    result = validate({"@type": "Event", "maximumAttendeeCapacity": "many"})
    got = [f.fields["got"] for f in result.findings if f.code == "SCH004"]
    assert got
    for item in got:
        assert isinstance(item, Msg)
        assert item.text("ru") == "строка"
        assert item.text("en") == "string"


def test_validate_enum_member_hint():
    result = validate({"@type": "Monday"})
    hint = _by_code(result, "SCH001").fields["hint"]
    assert isinstance(hint, Msg)
    assert hint.text("ru").startswith("это значение перечисления ")
    assert not CYR.search(hint.text("en"))
    assert hint.text("en").endswith(", not a type")


def test_no_replacement_msg():
    msg = Msg("markup_no_replacement")
    assert msg.text("ru") == "нет замены, уберите"
    assert msg.text("en") == "no replacement, remove it"


def test_texts_keys_have_ru_and_en_without_dashes():
    keys = [
        "markup_json_unparsable",
        "markup_theme_expects",
        "markup_theme_expects_hint",
        "markup_no_entity",
        "markup_entity_empty",
        "markup_entity_empty_hint",
        "markup_money",
        "markup_money_hint",
    ]
    fields = {"error": "boom", "want": "FAQPage", "fields": "price"}
    for key in keys:
        en = say("en", key, **fields)
        assert not CYR.search(en), key
        assert "—" not in en and "–" not in en, key
        assert CYR.search(say("ru", key, **fields)), key
    assert say("ru", "markup_money", fields="price") == "в разметке есть поля про деньги: price"
    assert say("en", "markup_money", fields="price") == "the markup has money fields: price"
