"""requires темы проверяется по каждому языку сайта."""

import pytest

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.contracts.wiring import verify
from heron.core.errors import HeronError
from tests.conftest import SITE_MIN, THEME_MIN


def _site(languages, contact):
    data = {
        **SITE_MIN,
        "site": {**SITE_MIN["site"], "languages": languages, "default_lang": languages[0]},
        "contact": contact,
    }
    return SiteConfig.model_validate(data)


def _theme():
    return ThemeConfig.model_validate({**THEME_MIN, "requires": ["contact.address"]})


def test_all_languages_have_value():
    site = _site(["ru", "uk"], {"address_ru": "Москва", "address_uk": "Київ"})
    assert verify(_theme(), site) == []


def test_missing_in_one_language():
    site = _site(["ru", "uk"], {"address_ru": "Москва"})
    with pytest.raises(HeronError) as exc:
        verify(_theme(), site)
    assert exc.value.code == "E011"
    text = str(exc.value.message)
    assert "contact.address" in text and "uk" in text


def test_missing_everywhere():
    site = _site(["ru", "uk"], {"phone": "1"})
    with pytest.raises(HeronError) as exc:
        verify(_theme(), site)
    text = str(exc.value.message)
    assert exc.value.code == "E011"
    assert "contact.address" in text and "(" not in text.split("requires")[-1].split("\n", 1)[-1]


def test_single_language_plain_key():
    site = _site(["uk"], {"address": "Київ"})
    assert verify(_theme(), site) == []
