"""Сырой HTML в markdown: по умолчанию запрещён."""

import pytest

from heron.core.errors import HeronError
from heron.core.parser import markdown

BODY = "## Текст {#t}\n\n<script>alert(1)</script>\n"


def test_raw_html_stops_the_build_by_default():
    with pytest.raises(HeronError) as exc:
        markdown.guard_raw_html(BODY, "a.md", allow=False)
    assert exc.value.code == "E015"
    assert exc.value.line == 3


def test_allowed_when_site_says_so():
    markdown.guard_raw_html(BODY, "a.md", allow=True)


def test_line_break_is_not_an_offence():
    markdown.guard_raw_html("текст\n<br>\nещё\n", "a.md", allow=False)


def test_escaped_when_parsed():
    md = markdown.make(allow_raw_html=False)
    assert "<script>" not in md.render("<script>alert(1)</script>")


def test_attrs_parse():
    anchor, classes, rest = markdown.parse_attrs("#quick-facts .alert .wide data=1")
    assert anchor == "quick-facts"
    assert classes == ["alert", "wide"]
    assert rest == {"data": "1"}
