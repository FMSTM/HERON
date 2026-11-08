"""Виды полей конфигуратора hours/enum/subtype/bool и списки схемы в state()."""

from __future__ import annotations

from pathlib import Path

import pytest

from heron import setup as heron_setup
from heron.setup import answers
from heron.setup.answers import _clean_value
from heron.setup.reasons import Reason, plain

HOURS = {"kind": "hours"}
ENUM = {"kind": "enum", "enum": "MedicalSpecialty", "multiple": True}
SUBTYPE = {"kind": "subtype", "of": "MedicalOrganization", "options": ["Hospital", "Dentist"]}


@pytest.mark.parametrize(
    "line", ["Mo-Fr 08:30-15:00", "Mo,We,Fr 09:00-13:00", "Mo-Fr 09:00-13:00,14:00-24:00"]
)
def test_hours_ok(line: str):
    assert _clean_value(HOURS, [line]) == [line]


@pytest.mark.parametrize("line", ["Mo-Fr 18:00-09:00", "Пн-Пт", "с 9 до 6", "Mo-Fr 25:00-26:00"])
def test_hours_bad(line: str):
    with pytest.raises(Reason) as err:
        _clean_value(HOURS, [line])
    assert err.value.key == "hours_bad"
    assert repr(line) in plain(err.value, "ru")


def test_hours_blank_lines_dropped():
    assert _clean_value(HOURS, "\nMo-Fr 08:30-15:00\n  \n") == ["Mo-Fr 08:30-15:00"]


def test_enum_member_url_and_dupes():
    got = _clean_value(ENUM, ["Neurologic", "https://schema.org/Surgical", "Neurologic"])
    assert got == ["Neurologic", "Surgical"]


def test_enum_bad():
    with pytest.raises(Reason) as err:
        _clean_value(ENUM, ["Neurosurgery"])
    assert "'Neurosurgery'" in plain(err.value, "en")


def test_enum_single():
    assert _clean_value({"kind": "enum", "enum": "MedicalSpecialty"}, "Neurologic") == "Neurologic"


def test_subtype():
    assert _clean_value(SUBTYPE, "Hospital") == "Hospital"
    with pytest.raises(Reason):
        _clean_value(SUBTYPE, "Person")


def test_bool():
    assert _clean_value({"kind": "bool"}, "true") is True
    assert _clean_value({"kind": "bool"}, "false") is False
    assert _clean_value({"kind": "bool"}, False) is False
    with pytest.raises(Reason):
        _clean_value({"kind": "bool"}, "да")


def test_state_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = {
        **answers.vocab(),
        "fields": {
            **answers.vocab()["fields"],
            "specialty": {
                "kind": "enum",
                "enum": "MedicalSpecialty",
                "to": "x.y",
                "multiple": True,
            },
        },
        "labels": {"MedicalSpecialty": {"Neurologic": {"ru": "Неврология"}}},
    }
    monkeypatch.setattr(heron_setup, "vocab", lambda: fake)
    got = heron_setup.schema_state("ru")
    assert got["release"] == "29.3"
    assert [d["value"] for d in got["days"]] == list(answers.DAYS)
    assert got["days"][0]["label"] == "Пн"
    items = {i["value"]: i["label"] for i in got["lists"]["specialty"]}
    assert items["Neurologic"] == "Неврология"
    assert items["Surgical"] == "Surgical"
