"""Сверка версии движка с требованием из site.yaml."""

import pytest

from heron.contracts import version as v
from heron.core.errors import HeronError


@pytest.mark.parametrize(
    ("actual", "spec", "expected"),
    [
        ("0.4.0", ">=0.4,<0.5", True),
        ("0.4.9", ">=0.4,<0.5", True),
        ("0.5.0", ">=0.4,<0.5", False),
        ("0.3.9", ">=0.4,<0.5", False),
        ("1.0", ">=0.4", True),
        ("0.4", "==0.4", True),
        ("0.4.1", "==0.4", False),
    ],
)
def test_satisfies(actual, spec, expected):
    assert v.satisfies(actual, spec) is expected


def test_missing_key_is_e011():
    with pytest.raises(HeronError) as exc:
        v.check(None, "0.1.0")
    assert exc.value.code == "E011"


def test_incompatible_is_e012():
    with pytest.raises(HeronError) as exc:
        v.check(">=0.9", "0.1.0")
    assert exc.value.code == "E012"
    assert "site.yaml" in str(exc.value)


def test_compatible_passes():
    v.check(">=0.1,<0.2", "0.1.0")


def test_broken_spec_is_e011():
    with pytest.raises(HeronError) as exc:
        v.check("около 0.4", "0.1.0")
    assert exc.value.code == "E011"
