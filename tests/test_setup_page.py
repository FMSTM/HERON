"""Страница анкеты heron/setup/page.html: виджеты enum, subtype, bool, hours (разбор файла как текста)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from heron.setup import answers

PAGE = (Path(answers.__file__).parent / "page.html").read_text(encoding="utf-8")
NEW_KEYS = ["not_set", "filter", "add_rule", "remove", "hours_preview", "hours_order", "not_in_vocab", "remove_value"]


def _block(lang: str) -> str:
    start = PAGE.index(f"\n  {lang}: {{")
    end = PAGE.index("\n  },", start) if "\n  }," in PAGE[start:] else PAGE.index("\n};", start)
    return PAGE[start:end]


@pytest.mark.parametrize("kind", ["enum", "subtype", "bool", "hours"])
def test_page_handles_kind(kind: str):
    assert f'kind === "{kind}"' in PAGE


@pytest.mark.parametrize("fn", ["enumBox", "subtypeSelect", "boolButtons", "hoursBuilder"])
def test_page_has_widget(fn: str):
    assert f"function {fn}(" in PAGE


def test_hours_re_matches_contract():
    m = re.search(r"const HOURS_RE = new RegExp\(String\.raw`([^`]+)`\)", PAGE)
    assert m, "HOURS_RE не найден"
    assert m.group(1) == answers.HOURS_RE.pattern.replace("\\Z", "$")


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_strings_in_both_languages(lang: str, key: str):
    assert re.search(rf"\b{key}: \"", _block(lang))


def test_no_long_dashes_in_new_strings():
    new = [m.group(0) for lang in ("ru", "en") for m in re.finditer(r"\b(?:%s): \"[^\"]*\"" % "|".join(NEW_KEYS + ["day_from", "day_to", "opens", "closes", "yes", "no", "hours_bad", "delete", "hours_complex"]), _block(lang))]
    assert new
    assert not any("—" in s or "–" in s for s in new)
    widgets = PAGE[PAGE.index("function schemaList("):PAGE.index("function aboutField(")]
    assert "—" not in widgets and "–" not in widgets


SCH_KEYS = [
    "sch_title", "sch_fix", "sch_save_anyway", "sch_drop_q", "sch_drop", "sch_keep", "sch_reason", "sch_reason_hint",
    "sch_saved_except", "sch_banner", "sch_show", "sch_excepted", "sch_expired",
]


def test_page_handles_409_with_dialog():
    assert "r.status === 409" in PAGE
    assert "<dialog" in PAGE and "showModal()" in PAGE
    assert "function showSchemaDialog(" in PAGE and "function markBad(" in PAGE and "function schemaBanner(" in PAGE


def test_schema_dialog_flow_by_spec():
    assert "showSchemaDialog(j.schema)" in PAGE and "schema.release" in PAGE
    assert "function fixFindings(" in PAGE and "SCH_LOOSE" in PAGE
    assert 'addEventListener("cancel"' in PAGE and "e.target === e.currentTarget" in PAGE
    assert 'box.classList.remove("bad")' in PAGE and "scrollIntoView" in PAGE
    assert "go.disabled = !ta.value.trim()" in PAGE


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("key", ["sch_field", "sch_path", "sch_except_title", "sch_dropped", "sch_drop_hint"])
def test_schema_helper_strings_in_both_languages(lang: str, key: str):
    m = re.search(rf"\b{key}: \"([^\"]*)\"", _block(lang))
    assert m and "\u2014" not in m.group(1) and "\u2013" not in m.group(1)


def test_page_sends_schema_decision():
    assert 'mode: "drop"' in PAGE and 'mode: "except"' in PAGE
    assert "schema: decision" in PAGE
    assert 'data-field' in PAGE


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("key", SCH_KEYS)
def test_schema_strings_in_both_languages(lang: str, key: str):
    assert re.search(rf"\b{key}: \"", _block(lang))


def test_no_long_dashes_in_schema_strings():
    found = [m.group(0) for lang in ("ru", "en") for m in re.finditer(r"\bsch_\w+: \"[^\"]*\"", _block(lang))]
    assert len(found) >= len(SCH_KEYS) * 2
    assert not any("\u2014" in s or "\u2013" in s for s in found)
    code = PAGE[PAGE.index("// Находки schema.org"):PAGE.index("function load(state)")]
    assert "\u2014" not in code and "\u2013" not in code


def test_page_hides_fields_by_props_by_spec():
    assert "props_by_spec" in PAGE and "function fitsSpec(" in PAGE
    assert 'split(".")[0]' in PAGE
    assert "if (!fitsSpec(name))" in PAGE and "function unfitField(" in PAGE


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_not_for_spec_string_in_both_languages(lang: str):
    m = re.search(r'\bnot_for_spec: "([^"]*)"', _block(lang))
    assert m and "\u2014" not in m.group(1) and "\u2013" not in m.group(1)


def test_page_uses_person_name_of_type():
    assert "person_name" in PAGE
    assert "aboutField(name, spec, personName)" in PAGE


def test_page_groups_practices_at():
    assert 'name.startsWith("practices_at")' in PAGE
    assert '"data-group": "practices_at"' in PAGE
    assert 'h("details"' in PAGE and "workplace_other_address" in PAGE


def test_doctor_fields_follow_workplace_in_vocab_order():
    from heron.setup.answers import fields_of

    names = fields_of("IndividualPhysician")
    own = [n for n in names if n == "medical_specialty" or n.startswith("practices_at") or n in ("hospital_affiliation", "accepts_new_patients")]
    assert own[0] == "medical_specialty"
    last_work = max(i for i, n in enumerate(names) if n.startswith("practices_at"))
    assert names.index("hospital_affiliation") > last_work and names.index("accepts_new_patients") > last_work
    assert "afterWork" in PAGE and 'names.indexOf(name) > workAt ? afterWork' in PAGE


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("key", ["workplace", "workplace_other_address"])
def test_workplace_strings_without_dashes(lang: str, key: str):
    m = re.search(rf"\b{key}: \"([^\"]*)\"", _block(lang))
    assert m, f"{key} нет в {lang}"
    assert "—" not in m.group(1) and "–" not in m.group(1)


def test_subtype_select_shows_value_not_in_vocab():
    start = PAGE.index("function subtypeSelect(")
    body = PAGE[start:PAGE.index("\nfunction ", start + 1)]
    assert "not_in_vocab" in body
    assert "remove_value" in body


def test_hours_select_keeps_times_not_multiple_of_15():
    assert "function timesWith(" in PAGE
    assert 'sel(t("opens"), timesWith(r.open).map(' in PAGE
    assert 'sel(t("closes"), timesWith(r.close).map(' in PAGE
