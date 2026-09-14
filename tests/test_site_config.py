"""Схема site.yaml: что движок проверяет, а что пропускает насквозь."""

import pytest

from heron.contracts.site import SiteConfig, load_site
from heron.core.errors import HeronError
from tests.conftest import SITE_MIN


def test_minimal_config_loads(write_yaml):
    site = load_site(write_yaml("site.yaml", SITE_MIN))
    assert site.site.domain == "example.com"
    assert site.site.languages == ["uk"]
    assert site.build.allow_raw_html is False
    assert site.seo.llms_txt is True


def test_missing_heron_key_is_e011(write_yaml):
    data = {k: v for k, v in SITE_MIN.items() if k != "heron"}
    with pytest.raises(HeronError) as exc:
        load_site(write_yaml("site.yaml", data))
    assert exc.value.code == "E011"
    assert "heron" in str(exc.value)


def test_broken_yaml_names_the_line(write_yaml):
    with pytest.raises(HeronError) as exc:
        load_site(write_yaml("site.yaml", "heron: '>=0.1'\nsite:\n  domain: a\n   theme: b\n"))
    assert exc.value.code == "E011"
    assert exc.value.line is not None


def test_domain_normalised(write_yaml):
    data = {**SITE_MIN, "site": {**SITE_MIN["site"], "domain": "https://Example.COM/"}}
    assert load_site(write_yaml("site.yaml", data)).site.domain == "example.com"


def test_default_lang_must_be_listed(write_yaml):
    data = {**SITE_MIN, "site": {**SITE_MIN["site"], "default_lang": "en"}}
    with pytest.raises(HeronError) as exc:
        load_site(write_yaml("site.yaml", data))
    assert "default_lang" in str(exc.value)


def test_typo_in_known_block_is_caught(write_yaml):
    data = {**SITE_MIN, "build": {"fail_on_warnings": True}}
    with pytest.raises(HeronError) as exc:
        load_site(write_yaml("site.yaml", data))
    assert "fail_on_warnings" in str(exc.value)


def test_unknown_top_level_blocks_pass_through(write_yaml):
    """Ядро не знает, что такое contact и organization, и не обязано знать."""
    data = {
        **SITE_MIN,
        "contact": {"phone": "+1-555-0100", "city": "Вигадане"},
        "organization": {"type": "Organization", "name": "Хтось"},
    }
    site = load_site(write_yaml("site.yaml", data))
    assert site.extras["contact"]["city"] == "Вигадане"
    assert site.get_path("organization.type") == "Organization"
    assert site.get_path("organization.missing") is None


def test_form_pointing_at_unknown_sink_fails(write_yaml):
    data = {
        **SITE_MIN,
        "forms": {"consult": {"fields": ["name", "phone"], "sinks": ["mail", "crm"]}},
        "sinks": {"mail": {"to": "a@example.com"}},
    }
    with pytest.raises(HeronError) as exc:
        load_site(write_yaml("site.yaml", data))
    assert "crm" in str(exc.value)


def test_form_with_valid_sinks_loads(write_yaml):
    data = {
        **SITE_MIN,
        "forms": {"consult": {"fields": ["name", "phone"], "sinks": ["mail"]}},
        "sinks": {"mail": {"to": "a@example.com"}},
    }
    site = load_site(write_yaml("site.yaml", data))
    assert site.forms["consult"].fields == ["name", "phone"]


def test_several_complaints_listed_at_once(write_yaml):
    data = {"heron": ">=0.1", "site": {"domain": "нет", "theme": "Демо"}}
    with pytest.raises(HeronError) as exc:
        load_site(write_yaml("site.yaml", data))
    assert str(exc.value).count("\n") >= 2


def test_missing_file_is_e011(tmp_path):
    with pytest.raises(HeronError) as exc:
        load_site(tmp_path / "site.yaml")
    assert exc.value.code == "E011"


def test_model_is_usable_directly():
    site = SiteConfig.model_validate(SITE_MIN)
    assert site.plugins == []
