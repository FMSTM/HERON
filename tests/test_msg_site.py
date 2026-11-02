"""Сообщения contracts/site.py и theme.py на ключах heron/texts/site.py (E15.S2.T13)."""

import re

import pytest

from heron.contracts.site import SiteConfig, load_site, parse_gone
from heron.contracts.theme import ThemeConfig
from heron.core.errors import HeronError
from heron.messages import Msg, MsgError

CYRILLIC = re.compile("[А-Яа-яЁё]")


def _site(**over):
    data = {"heron": ">=0.1", "site": {"name": "S", "domain": "example.com", "theme": "t", "languages": ["ru"], "default_lang": "ru"}}
    data["site"].update(over.pop("site", {}))
    data.update(over)
    return data


def _err(call, *args):
    with pytest.raises(MsgError) as caught:
        call(*args)
    msg = caught.value.args[0]
    assert isinstance(msg, Msg)
    assert not CYRILLIC.search(msg.text("en"))
    return msg


@pytest.mark.parametrize(
    "entry,ru,en",
    [
        ("old", "gone: 'old' - ожидается путь от корня, например /old-page/",
         "gone: 'old' - expected a path from the root, for example /old-page/"),
        ("/a#b", "gone: '/a#b' - якорь серверу не приходит, уберите #…",
         "gone: '/a#b' - the server never receives an anchor, remove the #..."),
        ("/?p", "gone: '/?p' - параметр пишется одной парой: /?p=* или /?p=12",
         "gone: '/?p' - write the parameter as a single pair: /?p=* or /?p=12"),
        ("/?p=1*", "gone: '/?p=1*' - звёздочка заменяет значение целиком: /?p=*",
         "gone: '/?p=1*' - the asterisk replaces the whole value: /?p=*"),
        ("/w*p/*", "gone: '/w*p/*' - звёздочка допустима только в конце: /wp/*",
         "gone: '/w*p/*' - the asterisk is allowed only at the end: /wp/*"),
    ],
)
def test_parse_gone_ru_is_old_text_en_has_no_cyrillic(entry, ru, en):
    msg = _err(parse_gone, entry)
    assert msg.text("ru") == ru
    assert msg.text("en") == en


def test_site_block_errors_through_describe(tmp_path):
    path = tmp_path / "site.yaml"
    path.write_text("heron: '>=0.1'\nsite:\n  name: S\n  domain: example.com\n  theme: 'bad theme'\n  languages: [ru, ru]\n")
    with pytest.raises(HeronError) as caught:
        load_site(path)
    msg = caught.value.message
    assert isinstance(msg, Msg)
    assert "имя темы - латиница, цифры, дефис и подчёркивание" in msg.text("ru")
    assert "the theme name is Latin letters, digits, hyphen and underscore" in msg.text("en")
    assert not CYRILLIC.search(msg.text("en"))


def test_load_site_without_heron_key(tmp_path):
    path = tmp_path / "site.yaml"
    path.write_text("site:\n  name: S\n")
    with pytest.raises(HeronError) as caught:
        load_site(path)
    err = caught.value
    assert err.message.text("ru") == "нет обязательного ключа `heron` с требуемой версией движка"
    assert err.hint.text("ru") == 'добавьте первой строкой, например: heron: ">=0.1,<0.2"'
    assert not CYRILLIC.search(err.message.text("en"))
    assert not CYRILLIC.search(err.hint.text("en"))


def test_default_lang_missing_and_language_code():
    with pytest.raises(Exception) as caught:
        SiteConfig.model_validate(_site(site={"languages": ["ru"], "default_lang": "en"}))
    cause = caught.value.errors()[0]["ctx"]["error"]
    assert cause.args[0].text("ru") == "default_lang 'en' отсутствует в languages ['ru']"
    assert cause.args[0].text("en") == "default_lang 'en' is missing from languages ['ru']"
    with pytest.raises(Exception) as caught:
        SiteConfig.model_validate(_site(site={"languages": ["RUS"]}))
    msg = caught.value.errors()[0]["ctx"]["error"].args[0]
    assert msg.text("ru") == "код языка 'RUS' не похож на код языка: ожидается uk, ru, en-gb"
    assert not CYRILLIC.search(msg.text("en"))


def test_plugins_and_exceptions_validators():
    with pytest.raises(Exception) as caught:
        SiteConfig.model_validate(_site(plugins=["a b"]))
    msg = caught.value.errors()[0]["ctx"]["error"].args[0]
    assert msg.text("ru") == "plugins: недопустимое имя 'a b': латиница, цифры, _ и -"
    assert not CYRILLIC.search(msg.text("en"))
    with pytest.raises(Exception) as caught:
        SiteConfig.model_validate(_site(plugins=["a", "a"]))
    msg = caught.value.errors()[0]["ctx"]["error"].args[0]
    assert msg.text("ru") == "plugins: имя плагина повторяется"
    assert msg.text("en") == "plugins: a plugin name is repeated"


def test_theme_validators():
    base = {"name": "t", "version": "1"}
    with pytest.raises(Exception) as caught:
        ThemeConfig.model_validate({**base, "name": "bad name"})
    msg = caught.value.errors()[0]["ctx"]["error"].args[0]
    assert msg.text("ru") == "имя темы - латиница, цифры, дефис и подчёркивание"
    assert msg.text("en") == "the theme name is Latin letters, digits, hyphen and underscore"
