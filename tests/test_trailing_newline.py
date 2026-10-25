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


def test_slug_and_redirect_paths_reject_trailing_newline() -> None:
    from heron.contracts.frontmatter import PageMeta

    base = {"title": "Заголовок под выдачу", "h1": "Заголовок", "description": "Описание"}
    PageMeta.model_validate({**base, "slug": "my-page", "redirect_from": ["/old/"], "gone": ["/x"]})
    for extra in ({"slug": "my-page\n"}, {"redirect_from": ["/old\n"]}, {"gone": ["/old/\n"]}):
        with pytest.raises(ValidationError):
            PageMeta.model_validate({**base, **extra})


def test_theme_uses_rejects_trailing_newline() -> None:
    from heron.contracts.theme import TypeSpec

    TypeSpec(uses=["abc", "tabs:tabs"])
    for bad in ("abc\n", "tabs:tabs\n"):
        with pytest.raises(ValidationError):
            TypeSpec(uses=[bad])


def test_site_lang_domain_suffix_regexes() -> None:
    from heron.contracts.site import DOMAIN_RE, LANG_RE, SUFFIX_RE

    assert LANG_RE.match("ru") and LANG_RE.match("pt-br")
    assert DOMAIN_RE.match("example.com") and SUFFIX_RE.match("title_ru")
    assert not LANG_RE.match("ru\n")
    assert not DOMAIN_RE.match("example.com\n")
    assert not SUFFIX_RE.match("title_ru\n")


def test_core_identifier_regexes() -> None:
    from heron.core.media import MEDIA_FIELD
    from heron.core.parser.sections import SECTION_ID
    from heron.core.tree import SLUG as TREE_SLUG
    from heron.scaffold.page import SLUG as PAGE_SLUG

    for rx in (TREE_SLUG, PAGE_SLUG, SECTION_ID):
        assert rx.match("my-page")
        assert not rx.match("my-page\n")
    assert MEDIA_FIELD.match("media/a.png")
    assert not MEDIA_FIELD.match("media/a.png\n")


def test_setup_regexes() -> None:
    from heron.setup import answers as a

    good = {
        "REPO_RE": "you/site",
        "DOCKER_NAME_RE": "my-img",
        "BRANCH_RE": "release/v1",
        "SERVER_PATH_RE": "/var/www",
        "SERVER_RE": "me@host",
        "ENGINE_RE": "0.1.0",
        "PHONE_RE": "+7 (900) 123-45-67",
        "EMAIL_RE": "a@b.co",
        "HANDLE_RE": "@name_1",
    }
    for name, value in good.items():
        rx = getattr(a, name)
        assert rx.match(value), name
        assert not rx.match(value + "\n"), name


def test_media_walk_strips_value_before_match() -> None:
    from heron.core import media

    def walked(value: object) -> set[str]:
        found: set[str] = set()
        media.walk({"image": value}, found)
        return found

    expected = walked("media/a.png")
    assert expected == {"media/a.png"}
    assert walked("media/a.png\n") == expected
    assert walked(" media/a.png ") == expected
    assert walked("./media/a.png\n") == expected
    assert walked("media/a") == set()
    assert walked("other/a.png\n") == set()
    assert walked("https://x.io/media/a.png\n") == set()
