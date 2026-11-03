"""Сообщения version и wiring на ключах texts/version.py: ru прежний, en без кириллицы."""

import re
from types import SimpleNamespace

import pytest

from heron import __version__
from heron.contracts import version as v
from heron.contracts import wiring
from heron.core.errors import HeronError
from heron.messages import Msg
from heron.texts import version as texts

CYR = re.compile("[а-яА-ЯёЁ]")


def _en_ok(err: HeronError) -> str:
    for part in (err.message, err.hint):
        assert isinstance(part, Msg)
        assert not CYR.search(part.text("en"))
    return err.message.text("en")


def _theme(**kw):
    base = dict(name="t", heron=None, fields=[], requires=[], forms=[])
    base.update(kw)
    return SimpleNamespace(**base)


def test_keys_parity_and_en_clean():
    assert texts.TEXT["ru"].keys() == texts.TEXT["en"].keys()
    assert not any(CYR.search(x) for x in texts.TEXT["en"].values())
    assert not any("—" in x or "–" in x for x in texts.TEXT["en"].values())


def test_missing_key():
    with pytest.raises(HeronError) as ei:
        v.check_version(None, "0.4.1")
    assert "no required `heron` key" in _en_ok(ei.value)
    assert (
        ei.value.message.text("ru")
        == "в site.yaml нет обязательного ключа `heron` с требуемой версией движка"
    )
    assert ei.value.hint.text("ru") == 'добавьте первой строкой, например: heron: ">=0.1,<0.2"'


@pytest.mark.parametrize(
    "spec,ru,en",
    [
        (
            "abc",
            "не разобрать требование версии: 'abc'",
            "cannot parse the version requirement: 'abc'",
        ),
        ("==0.4.*x", "не разобрать требование версии: '==0.4.*x'", "cannot parse"),
        ("~=1", "для ~= нужна версия хотя бы из двух чисел, например ~=0.4", "~= needs a version"),
        ("<0.4.*", "шаблон `.*` допустим только с == и !=, а не с <", "wildcard is allowed only"),
        (" , ", "пустое требование версии: ' , '", "empty version requirement"),
    ],
)
def test_bad_spec(spec, ru, en):
    with pytest.raises(HeronError) as ei:
        v.check_version(spec, "0.4.1")
    assert ei.value.code == "E011"
    assert ei.value.message.text("ru") == ru
    assert en in _en_ok(ei.value)


def test_parse_error_is_valueerror_with_msg():
    with pytest.raises(ValueError) as ei:
        v.parse("x.y")
    assert isinstance(ei.value.args[0], Msg)
    assert ei.value.args[0].text("ru") == "не версия: 'x.y'"
    assert ei.value.args[0].text("en") == "not a version: 'x.y'"


def test_unsatisfied_with_and_without_tag():
    with pytest.raises(HeronError) as ei:
        v.check_version(">=0.5", "0.4.1")
    assert ei.value.code == "E012"
    assert ei.value.message.text("ru") == "движок версии 0.4.1 не удовлетворяет требованию '>=0.5'"
    assert ei.value.hint.text("ru") == (
        "нужен образ heron:0.5 (текущий даёт heron:0.4) "
        "или поднимите требование в site.yaml, проверив совместимость"
    )
    assert "image heron:0.5" in ei.value.hint.text("en")
    _en_ok(ei.value)
    with pytest.raises(HeronError) as ei:
        v.check_version("<0.4", "0.4.1")
    assert ei.value.hint.text("ru").startswith(
        "нужен образ под это требование (текущий даёт heron:0.4)"
    )
    _en_ok(ei.value)


def test_wiring_engine_too_old():
    with pytest.raises(HeronError) as ei:
        wiring.verify_engine(_theme(heron=">=99"))
    assert ei.value.code == "E012"
    assert ei.value.message.text("ru") == f"тема 't' требует движок >=99, а этот - {__version__}"
    assert "requires engine >=99" in _en_ok(ei.value)


def test_wiring_unknown_fields():
    with pytest.raises(HeronError) as ei:
        wiring.verify_engine(_theme(fields=["nope", "nah"]))
    assert ei.value.code == "E023"
    assert ei.value.message.text("ru") == (
        f"в `fields` темы 't' поля, которых движок {__version__} не знает:\n    nope\n    nah"
    )
    assert "page.meta.get('поле')" in ei.value.hint.text("ru")
    assert "page.meta.get('field')" in ei.value.hint.text("en")
    _en_ok(ei.value)


def test_wiring_site_errors_and_warning():
    site = SimpleNamespace(get_path=lambda p: None, forms={"a": 1, "b": 1})
    with pytest.raises(HeronError) as ei:
        wiring.verify(_theme(requires=["contact.phone"]), site)
    assert (
        ei.value.message.text("ru")
        == "тема 't' требует значения, которых нет в site.yaml:\n    contact.phone"
    )
    assert "missing from site.yaml" in _en_ok(ei.value)
    site = SimpleNamespace(get_path=lambda p: "x", forms={"a": 1, "b": 1})
    with pytest.raises(HeronError) as ei:
        wiring.verify(_theme(forms=["zz"]), site)
    assert ei.value.message.text("ru") == "тема 't' рисует формы, которых нет в site.yaml: zz"
    _en_ok(ei.value)
    warns = wiring.verify(_theme(forms=["a"]), site)
    assert warns[0].message.text("ru") == "формы описаны в site.yaml, но тема их не рисует: b"
    assert (
        warns[0].message.text("en")
        == "forms are described in site.yaml, but the theme does not render them: b"
    )
