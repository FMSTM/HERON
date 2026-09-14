"""Схема фронтматтера: жёсткое — ошибкой, мягкое — предупреждением."""

import pytest
from pydantic import ValidationError

from heron.contracts.frontmatter import PageMeta

MIN = {"title": "Заголовок под выдачу", "h1": "Заголовок на странице", "description": "Описание"}


def test_minimal_page():
    page = PageMeta.model_validate(MIN)
    assert page.published is True
    assert page.order == 999
    assert page.redirect_from == []


@pytest.mark.parametrize("field", ["title", "h1", "description"])
def test_required_fields(field):
    data = {k: v for k, v in MIN.items() if k != field}
    with pytest.raises(ValidationError):
        PageMeta.model_validate(data)


def test_blank_required_field_rejected():
    with pytest.raises(ValidationError):
        PageMeta.model_validate({**MIN, "h1": "   "})


@pytest.mark.parametrize("slug", ["Плохой", "with_underscore", "two//slashes", "ТРЕШ"])
def test_bad_slug_rejected(slug):
    with pytest.raises(ValidationError):
        PageMeta.model_validate({**MIN, "slug": slug})


def test_good_slug_accepted():
    assert PageMeta.model_validate({**MIN, "slug": "getting-started-2"}).slug == "getting-started-2"


def test_redirect_from_must_be_paths():
    with pytest.raises(ValidationError):
        PageMeta.model_validate({**MIN, "redirect_from": ["https://example.com/old/"]})
    page = PageMeta.model_validate(
        {**MIN, "redirect_from": ["/services/old/"], "gone": ["/forum/"]}
    )
    assert page.gone == ["/forum/"]


def test_unknown_fields_kept_for_theme():
    page = PageMeta.model_validate({**MIN, "related": ["onboarding"], "mentions": ["consulting"]})
    assert page.extra["related"] == ["onboarding"]


def test_long_title_is_a_warning_not_an_error():
    page = PageMeta.model_validate({**MIN, "title": "д" * 80})
    messages = [w.message for w in page.lint("content/uk/a.md")]
    assert any("title" in m for m in messages)


def test_image_without_alt_is_a_warning():
    page = PageMeta.model_validate({**MIN, "image": "img/a.png"})
    assert any("image_alt" in w.message for w in page.lint("a.md"))


def test_title_equal_h1_is_a_warning():
    page = PageMeta.model_validate({**MIN, "title": "Одно и то же", "h1": "Одно и то же"})
    assert any("title и h1" in w.message for w in page.lint("a.md"))


def test_clean_page_has_no_warnings():
    assert PageMeta.model_validate(MIN).lint("a.md") == []
