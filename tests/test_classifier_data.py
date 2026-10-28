"""Данные классификатора анкеты на настоящем индексе schema.org 29.3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from heron.schemaorg import vocab

V = vocab()
FILE = Path(__file__).resolve().parent.parent / "heron" / "setup" / "classifier.yaml"
DATA: dict[str, Any] = yaml.safe_load(FILE.read_text(encoding="utf-8"))
ITEMS: list[dict[str, Any]] = [it for d in DATA["directions"] for it in d["items"]]
BY_ID = {it["id"]: it for it in ITEMS}


def _types(it: dict[str, Any]) -> list[str]:
    t = it.get("type")
    if t is None:
        return []
    return [t] if isinstance(t, str) else list(t)


def _is_local(it: dict[str, Any]) -> bool:
    return any(V.is_subtype(t, "LocalBusiness") for t in _types(it))


def test_ids_unique() -> None:
    ids = [it["id"] for it in ITEMS]
    assert len(ids) == len(set(ids))
    assert len(ITEMS) == 198


def test_all_types_exist_and_not_enum_values() -> None:
    enum_values = {v for values in V.enums.values() for v in values}
    for it in ITEMS:
        for t in _types(it):
            assert V.is_type(t), (it["id"], t)
            assert not V.is_datatype(t), (it["id"], t)
            assert t not in enum_values, (it["id"], t)


@pytest.mark.parametrize("bad", ["MusicSchool", "TaxiService", "Physiotherapy"])
def test_bad_types_absent(bad: str) -> None:
    assert all(bad not in _types(it) for it in ITEMS)


def test_fixed_specializations() -> None:
    assert BY_ID["health-07"]["type"] == "MedicalBusiness"
    assert BY_ID["health-07"]["specialty"] == "Physiotherapy"
    assert BY_ID["education-07"]["type"] == "EducationalOrganization"
    assert BY_ID["transport-02"]["type"] == "LocalBusiness"
    assert BY_ID["health-06"]["type"] == ["DiagnosticLab", "MedicalBusiness"]
    assert BY_ID["animals-01"]["type"] == ["VeterinaryCare", "LocalBusiness"]
    for i in ("arts-01", "arts-03", "arts-05", "religion-01"):
        assert BY_ID[i]["type"][1] == "Organization"


def test_specialty_is_medical_specialty() -> None:
    found = [it for it in ITEMS if "specialty" in it]
    assert found
    for it in found:
        assert V.is_member("MedicalSpecialty", it["specialty"]), it["id"]


def test_non_local_table() -> None:
    rows = DATA["non_local"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) == 21
    computed = {it["id"] for it in ITEMS if _types(it) and not _is_local(it)}
    added = {r["id"] for r in rows if r["decision"] == "add_type"}
    assert set(ids) == computed | added
    for r in rows:
        assert r["decision"] in {"keep", "add_type", "replace"}
        assert r["reason"].strip()
        assert r["id"] in BY_ID
        assert r["type"] == BY_ID[r["id"]]["type"], r["id"]
