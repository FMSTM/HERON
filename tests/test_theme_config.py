"""Схема theme.yaml и стыковка темы с сайтом."""

import pytest

from heron.contracts.site import SiteConfig
from heron.contracts.theme import load_theme
from heron.contracts.wiring import verify
from heron.core.errors import HeronError
from tests.conftest import SITE_MIN, THEME_MIN


def test_minimal_theme_loads(write_yaml):
    theme = load_theme(write_yaml("theme.yaml", THEME_MIN))
    assert theme.name == "demo"
    assert theme.types == {}


def test_types_and_sections(write_yaml):
    data = {
        **THEME_MIN,
        "modules": ["prose", "faq"],
        "types": {"article": {"uses": ["intro", "faq"], "jsonld": ["Article"]}},
    }
    theme = load_theme(write_yaml("theme.yaml", data))
    assert theme.sections_of("article") == ["intro", "faq"]
    assert theme.sections_of("нет-такого") == []


def test_jsonld_lives_in_theme_not_core(write_yaml):
    """Предметные типы разметки объявляет тема — ядро в них не вникает."""
    data = {
        **THEME_MIN,
        "types": {"procedure": {"uses": ["intro"], "jsonld": ["MedicalProcedure"]}},
    }
    theme = load_theme(write_yaml("theme.yaml", data))
    assert theme.types["procedure"].jsonld == ["MedicalProcedure"]


def test_duplicate_sections_rejected(write_yaml):
    data = {**THEME_MIN, "types": {"page": {"uses": ["intro", "intro"]}}}
    with pytest.raises(HeronError):
        load_theme(write_yaml("theme.yaml", data))


def test_requires_missing_value_stops_build(write_yaml):
    theme = load_theme(write_yaml("theme.yaml", {**THEME_MIN, "requires": ["contact.phone"]}))
    with pytest.raises(HeronError) as exc:
        verify(theme, SiteConfig.model_validate(SITE_MIN))
    assert "contact.phone" in str(exc.value)


def test_requires_satisfied(write_yaml):
    theme = load_theme(write_yaml("theme.yaml", {**THEME_MIN, "requires": ["contact.phone"]}))
    site = SiteConfig.model_validate({**SITE_MIN, "contact": {"phone": "+1-555-0100"}})
    assert verify(theme, site) == []


def test_theme_form_absent_in_site_stops_build(write_yaml):
    theme = load_theme(write_yaml("theme.yaml", {**THEME_MIN, "forms": ["consult"]}))
    with pytest.raises(HeronError) as exc:
        verify(theme, SiteConfig.model_validate(SITE_MIN))
    assert "consult" in str(exc.value)


def test_site_form_nobody_draws_is_a_warning(write_yaml):
    theme = load_theme(write_yaml("theme.yaml", THEME_MIN))
    site = SiteConfig.model_validate(
        {**SITE_MIN, "forms": {"consult": {"fields": ["name"]}}, "sinks": {}}
    )
    warnings = verify(theme, site)
    assert len(warnings) == 1
    assert "consult" in warnings[0].message
