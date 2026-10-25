"""Завершающий перевод строки: `$` в регэксе его пропускал, `\\Z` нет."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from heron.setup.answers import Answers, PublishAnswers
from heron.setup.files import publish_sh

BAD = ["\n", "\r", "\x00", "\t", "\x7f"]


def test_publish_sh_rejects_newline_in_dockerhub_user() -> None:
    """Раньше `u\\n` попадал в publish.sh и ломал `docker build -t`."""
    with pytest.raises(ValidationError):
        Answers(publish={"way": "dockerhub", "dockerhub_user": "u\n", "image": "i"})


def test_publish_sh_clean_values_unchanged() -> None:
    a = Answers(publish={"way": "dockerhub", "dockerhub_user": "u", "image": "i"})
    gen = publish_sh(a, "en")
    assert gen is not None
    assert 'docker build -f "$recipe" -t "u/i:$env" dist' in gen.text


@pytest.mark.parametrize("bad", BAD)
@pytest.mark.parametrize(
    "field,good",
    [
        ("repo", "you/site"),
        ("dockerhub_user", "user"),
        ("image", "img"),
        ("server", "me@host"),
        ("path", "/var/www"),
        ("branch", "main"),
        ("engine", "prod"),
    ],
)
def test_publish_fields_reject_control_chars(field: str, good: str, bad: str) -> None:
    PublishAnswers(**{field: good})
    for value in (good + bad, bad + good, good[:1] + bad + good[1:]):
        if field in ("branch", "engine") and value.strip() != value:
            continue  # эти два поля обрезаются по краям, как и раньше
        with pytest.raises(ValidationError):
            PublishAnswers(**{field: value})


def test_branch_and_engine_still_stripped() -> None:
    p = PublishAnswers(branch=" main\n", engine="beta\n")
    assert (p.branch, p.engine) == ("main", "beta")
