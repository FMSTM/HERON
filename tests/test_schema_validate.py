"""Валидатор разметки по настоящему индексу schema.org 29.3 (SCH001-SCH005)."""

from __future__ import annotations

from typing import Any

import pytest

from heron.schemaorg import vocab
from heron.schemaorg.validate import validate


def _codes(node: Any) -> list[tuple[str, str]]:
    return [(f.code, f.path) for f in validate(node).findings]


@pytest.fixture
def doctor() -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "IndividualPhysician",
        "@id": "https://example.org/#doctor",
        "name": "Иван Петров",
        "description": "Врач",
        "medicalSpecialty": [
            "https://schema.org/Neurologic",
            "https://schema.org/Surgical",
            "https://schema.org/Pediatric",
        ],
        "telephone": "+00 000 000 00 00",
        "openingHours": "Mo-Fr 09:00-18:00",
        "address": {"@type": "PostalAddress", "streetAddress": "Ул. 1", "addressLocality": "Город"},
        "geo": {"@type": "GeoCoordinates", "latitude": 55.1, "longitude": 37.2},
        "practicesAt": {
            "@type": "Hospital",
            "name": "Клиника",
            "address": {"@type": "PostalAddress", "streetAddress": "Ул. 2"},
        },
        "image": {"@type": "ImageObject", "url": "https://example.org/a.jpg"},
        "sameAs": ["https://example.org/p"],
    }


def test_reference_doctor_has_no_findings(doctor: dict[str, Any]) -> None:
    assert validate(doctor).findings == []


def test_physician_with_worksfor_gives_sch002(doctor: dict[str, Any]) -> None:
    doctor["@type"] = "Physician"
    doctor["worksFor"] = "Клиника"
    codes = _codes(doctor)
    assert ("SCH002", "worksFor") in codes
    assert ("SCH002", "practicesAt") in codes


def test_unknown_type_and_list_index() -> None:
    f = validate({"@type": "MusicSchool"}).findings
    assert [(x.code, x.path, x.value) for x in f] == [("SCH001", "@type", "MusicSchool")]
    assert _codes({"@type": ["Organization", "Nope"]}) == [("SCH001", "@type.1")]


def test_dual_and_enum_member_types() -> None:
    assert _codes({"@type": "Physiotherapy"}) == []
    f = validate({"@type": "Neurologic"}).findings
    assert [x.code for x in f] == ["SCH001"]
    assert "перечисления" in f[0].fields["hint"]
    assert f[0].fields["enum"] == "MedicalSpecialty"


def test_property_domain() -> None:
    assert _codes({"@type": "IndividualPhysician", "worksFor": "X"}) == [("SCH002", "worksFor")]
    assert _codes({"@type": "Museum", "email": "a@b.c"}) == [("SCH002", "email")]
    assert _codes({"@type": ["Museum", "Organization"], "email": "a@b.c"}) == []
    f = validate({"@type": "Museum", "email": "a@b.c"}).findings[0]
    assert f.fields["domain"] and len(f.fields["domain"].split(", ")) <= 6


def test_unknown_property_suggests() -> None:
    f = validate({"@type": "Physician", "acceptsNewPatients": True}).findings
    assert [x.code for x in f] == [("SCH002")]
    assert "isAcceptingNewPatients" in f[0].fields["suggest"]
    assert f[0].fields["domain"] == ""


def test_enum_values() -> None:
    bad = {"@type": "Physician", "medicalSpecialty": "Neurosurgery"}
    assert _codes(bad) == [("SCH003", "medicalSpecialty")]
    assert _codes({"@type": "Physician", "medicalSpecialty": ["Neurologic", "Bad"]}) == [
        ("SCH003", "medicalSpecialty.1")
    ]
    assert _codes({"@type": "Physician", "medicalSpecialty": "https://schema.org/Surgical"}) == []
    f = validate({"@type": "Physician", "medicalSpecialty": "Bad"}).findings[0]
    assert f.fields["enum"] == "MedicalSpecialty" and len(f.fields["members"].split(", ")) == 10


def test_boolean_and_number() -> None:
    base = {"@type": "Physician"}
    assert _codes({**base, "isAcceptingNewPatients": True}) == []
    assert _codes({**base, "isAcceptingNewPatients": "True"}) == []
    yes = {**base, "isAcceptingNewPatients": "yes"}
    assert _codes(yes) == [("SCH004", "isAcceptingNewPatients")]
    f = validate({**base, "isAcceptingNewPatients": 5}).findings[0]
    assert (f.code, f.fields["got"], f.fields["expected"]) == ("SCH004", "число", "Boolean")
    # Number|Text: строка допустима
    assert _codes({"@type": "GeoCoordinates", "latitude": "abc"}) == []


def test_object_values() -> None:
    base = {"@type": "IndividualPhysician"}
    assert _codes({**base, "practicesAt": {"@type": "Person"}}) == [("SCH004", "practicesAt")]
    assert _codes({**base, "practicesAt": {"@type": "Hospital"}}) == []
    assert _codes({**base, "practicesAt": "Больница"}) == []
    assert _codes({**base, "practicesAt": {"@id": "https://example.org/h"}}) == []


def test_untyped_node_uses_single_class_range() -> None:
    ok = {"@type": "Organization", "address": {"streetAddress": "Ул. 1"}}
    assert _codes(ok) == []
    bad = {"@type": "Organization", "address": {"house": "1"}}
    assert _codes(bad) == [("SCH002", "address.house")]
    assert _codes({"foo": "bar"}) == []


def test_deprecated_property() -> None:
    v = vocab()
    props = sorted(v.properties.items())
    prop = next(p for p, m in props if m.get("superseded_by") and m.get("domain"))
    dom = v.properties[prop]["domain"][0]
    f = validate({"@type": dom, prop: "x"}).findings
    sch5 = [x for x in f if x.code == "SCH005"]
    assert sch5 and sch5[0].path == prop
    assert sch5[0].fields["replacement"] == ", ".join(v.properties[prop]["superseded_by"])
    assert sch5[0].fields["release"] == v.release


def test_graph_paths() -> None:
    g = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "bogus": 1},
            {"@type": "Person", "bogus2": 1},
        ],
    }
    assert _codes(g) == [("SCH002", "@graph.0.bogus"), ("SCH002", "@graph.1.bogus2")]


def test_foreign_keys_skipped() -> None:
    node = {"@type": "Organization", "og:image": "x", "http://example.org/x": 1}
    assert _codes(node) == []


def test_pending_reported_and_deterministic(doctor: dict[str, Any]) -> None:
    res = validate(doctor)
    assert "practicesAt" in res.pending
    assert validate(doctor) == res


def test_duplicates_collapsed_and_sorted() -> None:
    res = validate({"@type": "Organization", "zzz": 1, "aaa": 2})
    assert [f.path for f in res.findings] == ["aaa", "zzz"]
    assert len({(f.code, f.path) for f in res.findings}) == len(res.findings)
