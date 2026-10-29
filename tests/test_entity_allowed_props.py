"""_entity не выводит свойства, недопустимые итоговому типу (SCH002)."""

from __future__ import annotations

import pytest

from heron.contracts.site import SiteConfig
from heron.modules import jsonld
from heron.schemaorg.validate import validate
from heron.setup.answers import classifier, merge, vocab
from tests.test_classifier_schema import _answers

SPECS = [(d["id"], s["id"]) for d in classifier() for s in d["items"]]
KINDS = list(vocab()["types"])


def _findings(kind: str, direction: str, spec: str) -> list[tuple[str, str]]:
    config = SiteConfig(**merge({}, _answers(kind, direction, spec), ">=0.1"))
    node = jsonld.entity(config, "en")
    assert node is not None
    return [(f.code, f.path) for f in validate(node).findings]


@pytest.mark.parametrize(("direction", "spec"), SPECS)
def test_individual_physician_pairs(direction: str, spec: str) -> None:
    assert _findings("IndividualPhysician", direction, spec) == []


@pytest.mark.parametrize("kind", [k for k in KINDS if k != "Person"])
def test_health_07_has_no_medical_specialty_on_business(kind: str) -> None:
    assert _findings(kind, "health", "health-07") == []
