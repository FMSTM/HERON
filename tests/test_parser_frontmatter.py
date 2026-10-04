"""Отделение фронтматтера от тела и сборка модели страницы."""

import pytest

from heron.core.errors import HeronError
from heron.core.parser import frontmatter as fm

OK = """---
title: Заголовок под выдачу
h1: Заголовок на странице
description: Описание страницы
related: [getting-started]
---

Вступление.

## Секция {#what}

Текст.
"""


def test_split_returns_meta_body_and_line():
    data, body, line = fm.split(OK, "a.md")
    assert data["title"] == "Заголовок под выдачу"
    assert body.lstrip().startswith("Вступление")
    assert line == 7


def test_body_line_lets_errors_point_at_the_real_file():
    _, _, line = fm.split(OK, "a.md")
    assert OK.splitlines()[line - 1].strip() == ""


def test_no_frontmatter_is_e001():
    with pytest.raises(HeronError) as exc:
        fm.split("# Просто заголовок\n", "a.md")
    assert exc.value.code == "E001"


def test_broken_yaml_names_the_line_in_the_file():
    text = "---\ntitle: a\n  h1: b\n---\nтекст\n"
    with pytest.raises(HeronError) as exc:
        fm.split(text, "a.md")
    assert exc.value.code == "E001"
    assert exc.value.line and exc.value.line >= 2


def test_bom_and_crlf_survive():
    data, _, _ = fm.split(
        "\ufeff---\r\ntitle: a\r\nh1: b\r\ndescription: c\r\n---\r\nтекст\r\n", "a.md"
    )
    assert data["h1"] == "b"


@pytest.mark.parametrize("field", ["title", "h1", "description"])
def test_missing_required_field_is_e002(field):
    data = {"title": "t", "h1": "h", "description": "d"}
    data.pop(field)
    with pytest.raises(HeronError) as exc:
        fm.parse_meta(data, "a.md")
    assert exc.value.code == "E002"
    assert field in str(exc.value)


def test_blank_required_field_is_e002():
    with pytest.raises(HeronError) as exc:
        fm.parse_meta({"title": "t", "h1": "   ", "description": "d"}, "a.md")
    assert exc.value.code == "E002"


def test_unknown_fields_reach_the_theme():
    meta = fm.parse_meta({"title": "t", "h1": "h", "description": "d", "related": ["a"]}, "a.md")
    assert meta.extra["related"] == ["a"]


def test_read_file(tmp_path):
    path = tmp_path / "page.md"
    path.write_text(OK, encoding="utf-8")
    meta, body, line, warnings = fm.read(path, rel="content/uk/page.md")
    assert meta.h1 == "Заголовок на странице"
    assert "## Секция" in body
    assert line == 7
    assert warnings == []


def test_lint_warnings_come_from_read(tmp_path):
    path = tmp_path / "page.md"
    path.write_text(OK.replace("Заголовок под выдачу", "д" * 90), encoding="utf-8")
    _, _, _, warnings = fm.read(path)
    assert any("title" in w.message for w in warnings)
