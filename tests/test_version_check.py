"""check_version: семантика требований как в pip и текст E012."""

import pytest

from heron.contracts import check_version
from heron.contracts import version as v
from heron.core.errors import HeronError


@pytest.mark.parametrize(
    ("actual", "spec", "expected"),
    [
        ("0.4.3", "~=0.4.1", True),
        ("0.4.0", "~=0.4.1", False),
        ("0.5.0", "~=0.4.1", False),
        ("0.9.0", "~=0.4", True),
        ("1.0.0", "~=0.4", False),
        ("0.4.7", "==0.4.*", True),
        ("0.5.0", "==0.4.*", False),
        ("0.5.0", "!=0.4.*", True),
        ("0.4.2", "!=0.4.*", False),
        ("0.4.2", " >=0.4 , <0.5 ", True),
    ],
)
def test_pip_semantics(actual, spec, expected):
    assert v.satisfies(actual, spec) is expected


@pytest.mark.parametrize("spec", ["~=1", ">=0.4.*", ",", "0.4", "=>0.4"])
def test_bad_spec_is_e011(spec):
    with pytest.raises(HeronError) as exc:
        check_version(spec, "0.4.0")
    assert exc.value.code == "E011"


def test_e012_names_both_versions_and_tag():
    with pytest.raises(HeronError) as exc:
        check_version(">=0.9,<0.10", "0.4.2", site_yaml="/srv/site/site.yaml")
    err = exc.value
    assert err.code == "E012"
    assert err.path == "/srv/site/site.yaml"
    assert "0.4.2" in err.message and ">=0.9,<0.10" in err.message
    assert "heron:0.9" in err.hint and "heron:0.4" in err.hint


def test_e012_without_lower_bound_still_hints():
    with pytest.raises(HeronError) as exc:
        check_version("<0.3", "0.4.0")
    assert exc.value.code == "E012"
    assert "heron:0.4" in exc.value.hint


def test_compatible_returns_none():
    assert check_version("~=0.4.0", "0.4.5") is None


def test_old_name_is_same_function():
    assert v.check is v.check_version is check_version
