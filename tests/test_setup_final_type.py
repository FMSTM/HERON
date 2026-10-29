"""Анкета по итоговому типу (вид + специализация): поля, свойства, specialty."""

import json

import pytest
from pydantic import ValidationError

from heron.setup import schema_state
from heron.setup.answers import (
    AboutAnswers,
    Answers,
    _entity,
    entity_type,
    fields_for,
    fields_of,
    final_types,
    vocab,
)

KINDS = ["Organization", "Corporation", "LocalBusiness", "NGO", "EducationalOrganization", "Person"]


def about(kind, spec="", **fields):
    return AboutAnswers.model_construct(
        type=kind, direction="", specialization=spec, fields=fields, contacts=[]
    )


def answers(kind, spec="", fields=None, contacts=None):
    return Answers.model_validate(
        {
            "site": {"name": "X", "domain": "x.example.com", "languages": ["en"]},
            "about": {
                "type": kind,
                "specialization": spec,
                "fields": fields or {},
                "contacts": contacts or [],
            },
        }
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("spec", ["", "health-07", "arts-01", "science-01"])
def test_final_types_shape(kind, spec):
    types = final_types(about(kind, spec))
    assert types
    assert len(types) == len(set(types))
    if kind == "Person" or not spec:
        assert types == [kind]
    elif kind not in ("Organization", "LocalBusiness"):
        assert types[0] == kind


def test_final_types_replace_and_combine():
    assert final_types(about("LocalBusiness", "health-06")) == ["DiagnosticLab", "MedicalBusiness"]
    assert final_types(about("LocalBusiness", "health-07")) == ["MedicalBusiness"]
    assert final_types(about("Corporation", "health-07")) == ["Corporation", "MedicalBusiness"]


def test_fields_for_hides_invalid():
    lab = fields_for(about("LocalBusiness", "science-01"))
    assert not {"opening_hours", "latitude", "price_range"} & set(lab)
    ok = fields_for(about("LocalBusiness", "health-06"))
    assert {"opening_hours", "latitude"} <= set(ok)


def test_person_unchanged():
    assert fields_for(about("Person", "health-07")) == fields_of("Person")


def test_save_invalid_field_rejected():
    with pytest.raises(ValidationError) as err:
        AboutAnswers(
            type="LocalBusiness",
            specialization="science-01",
            fields={"opening_hours": ["Mo 09:00-10:00"]},
        )
    assert "opening_hours" in str(err.value)
    assert "fields not asked for type" in str(err.value)


def test_save_valid_field_accepted():
    AboutAnswers(
        type="LocalBusiness",
        specialization="health-06",
        fields={"opening_hours": ["Mo-Fr 09:00-18:00"], "latitude": "50.1"},
    )


def test_entity_medical_specialty():
    # изменено по решению оркестратора: словарь schema.org 29.3 не допускает
    # medicalSpecialty на MedicalBusiness (domain: Hospital, MedicalClinic,
    # MedicalOrganization, Physician)
    node = _entity(answers("LocalBusiness", "health-07"))
    assert node["@type"] == "MedicalBusiness"
    assert "medicalSpecialty" not in node
    physician = _entity(answers("IndividualPhysician", "health-07"))
    assert physician["medicalSpecialty"] == ["https://schema.org/Physiotherapy"]


def test_entity_contact_email_for_museum():
    contacts = [{"type": "email", "purpose": "", "value": "a@example.com"}]
    node = _entity(answers("LocalBusiness", "arts-01", contacts=contacts))
    assert node["email"] == "{{ contact.email }}"


def test_entity_type_scalar_and_list():
    assert entity_type(about("LocalBusiness", "health-07")) == "MedicalBusiness"
    assert entity_type(about("LocalBusiness", "health-06")) == ["DiagnosticLab", "MedicalBusiness"]
    assert entity_type(about("Person")) == "Person"


def test_props_by_spec_in_state():
    props = schema_state("en")["props_by_spec"]
    assert props
    assert len(json.dumps(props)) < 100_000
    assert "openingHours" not in props["LocalBusiness|science-01"]
    assert "openingHours" in props["Organization|health-06"]
    assert vocab()


def _science_01_labels():
    from heron.setup.answers import classifier

    for item in classifier():
        for entry in item["items"]:
            if entry["id"] == "science-01":
                return item["en"], entry["en"]
    raise AssertionError("science-01 not in classifier")


def test_read_stale_field_kept_save_rejects():
    from heron.setup.answers import _set, read

    work, spec = _science_01_labels()
    data = {
        "site": {"name": "X", "domain": "x.example.com", "languages": ["en"]},
        "schema": {"entity": {"@type": "LocalBusiness"}},
        "organization": {"field_of_work": work, "specialization": spec},
    }
    _set(data, vocab()["fields"]["opening_hours"]["to"], ["Mo 09:00-10:00"])
    got = read(data)
    assert isinstance(got, Answers)
    assert got.about.type == "LocalBusiness"
    assert got.about.specialization == "science-01"
    # поле недопустимо итоговому типу, но чтение его не теряет
    assert "opening_hours" not in fields_for(got.about)
    assert got.about.fields["opening_hours"] == ["Mo 09:00-10:00"]
    # сохранение нового ответа с тем же полем по-прежнему отклоняется
    with pytest.raises(ValidationError) as err:
        Answers.model_validate(got.model_dump())
    assert "opening_hours" in str(err.value)
    with pytest.raises(ValidationError):
        AboutAnswers(
            type="LocalBusiness",
            specialization="science-01",
            fields={"opening_hours": ["Mo 09:00-10:00"]},
        )
