"""Тесты API Vocab на настоящем индексе schema.org 29.3."""

from __future__ import annotations

from heron.schemaorg import short, vocab

V = vocab()


def test_is_type() -> None:
    assert V.is_type("IndividualPhysician")
    assert V.is_type("https://schema.org/Hospital")
    assert V.is_type("schema:Hospital")
    assert not V.is_type("MusicSchool")
    assert V.is_type("Physiotherapy") and V.is_member("MedicalSpecialty", "Physiotherapy")
    assert V.is_datatype("Text") and V.is_type("URL")


def test_subtype() -> None:
    assert V.is_subtype("IndividualPhysician", "LocalBusiness")
    assert V.is_subtype("Hospital", "MedicalOrganization")
    assert not V.is_subtype("DiagnosticLab", "LocalBusiness")
    assert V.ancestors("Nope") == frozenset()


def test_allows() -> None:
    assert V.allows("IndividualPhysician", "practicesAt")
    assert V.allows("IndividualPhysician", "openingHours")
    assert not V.allows("IndividualPhysician", "worksFor")
    assert not V.allows("Museum", "email")
    assert V.allows(["Museum", "Organization"], "email")
    assert V.allows("Person", "worksFor")
    assert not V.allows("Person", "noSuchProp")
    assert "practicesAt" in V.properties_of("IndividualPhysician")


def test_ranges() -> None:
    assert V.ranges("practicesAt") == ["MedicalOrganization"]
    assert V.ranges("nope") == []


def test_enums() -> None:
    assert V.is_enum("MedicalSpecialty")
    assert len(V.members("MedicalSpecialty")) == 42
    assert V.is_member("MedicalSpecialty", "https://schema.org/Neurologic")
    assert not V.is_member("MedicalSpecialty", "Neurosurgery")
    assert V.is_member("DayOfWeek", "Monday")
    assert V.members("Nope") == []


def test_deprecated() -> None:
    prop = next(p for p, m in V.properties.items() if m["superseded_by"])
    flag, repl = V.deprecated(prop)
    assert flag is True and repl
    assert V.deprecated("name") == (False, [])
    assert V.deprecated("Nope") == (False, [])


def test_descendants() -> None:
    d = V.descendants("MedicalOrganization")
    for t in ("Hospital", "MedicalClinic", "PhysiciansOffice", "IndividualPhysician"):
        assert t in d
    assert "MedicalOrganization" not in d
    assert d == sorted(d)


def test_suggest() -> None:
    assert V.suggest("Hopsital", "type")[0] == "Hospital"
    assert "practicesAt" in V.suggest("practiceAt", "property")
    assert V.suggest("hospital", "type")[0] == "Hospital"
    assert V.suggest("neurologic", "member", enum="MedicalSpecialty")[0] == "Neurologic"


def test_short_and_ext() -> None:
    assert short("schema:Text") == "Text"
    assert short(" http://schema.org/Text ") == "Text"
    assert V.ext("Hospital") != ""
    assert V.ext("Nope") == ""


def test_cache() -> None:
    assert vocab() is vocab()
