"""Правка SEO-блока на всех формах YAML (приёмка 0.3.0, блокер 1 и баг 9).

Блочные скаляры (`|`, `|-`, `|+`, `>`, `>-`, с указателем отступа), свёрнутые,
в кавычках, многострочные простые, списки и словари в скобках, якоря и ссылки.
Правка одного поля меняет только его значение: остальные ключи, комментарии и
следующие строки - как были; YAML после правки читается.
"""

from __future__ import annotations

import itertools

import pytest
import yaml

from heron.edit import front as fronts
from heron.edit import model
from heron.edit.slots import EditError
from tests.edit_corpus import contract

# Значение поля h1 в разных записях: (текст после `h1:`, что из него читает YAML).
H1_FORMS = [
    "|-\n  Read the docs",
    "|\n  Read the docs",
    "|+\n  Read the docs\n",
    ">\n  Read the\n  docs",
    ">-\n  Read the\n  docs",
    "|2-\n    Read the docs",
    ">+2\n    Read\n    the docs\n\n",
    '"Read the docs"',
    "'Read the docs'",
    "Read the\n  docs",
    '"Read the\n  docs"',
    "Read the docs   # a comment in the line",
]

AFTER = [
    "# keep this note\n",
    "# keep: this note, with a colon\n",
    "\n# after an empty line\n",
    "description: Next key, untouched\n",
    " # a comment indented less than the text\n",
]

NEW_VALUES = ["Read them now", "Docs: read them", "two\nlines", "x # not a comment", "'quoted'"]


def _page(front: str, spec) -> model.Page:
    text = f"---\ntitle: The title of the page, long enough\n{front}---\n\nIntro.\n"
    return model.load(text, spec, rel="content/en/x.md")


def _comments(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("#")]


@pytest.fixture(scope="module")
def spec():
    return contract("en")


@pytest.mark.parametrize(
    ("form", "after", "value"), list(itertools.product(H1_FORMS, AFTER, NEW_VALUES))
)
def test_edit_any_scalar_form_keeps_next_lines(spec, form, after, value):
    page = _page(f"h1: {form}\n{after}", spec)
    before = dict(page.front.data)
    edited = model.set_field(page, "h1", value)
    data = yaml.safe_load(edited.text.split("---")[1])
    assert data["h1"] == value
    assert {k: v for k, v in data.items() if k != "h1"} == {
        k: v for k, v in before.items() if k != "h1"
    }
    # комментарии других строк на месте; комментарий в строке самого h1 - часть его значения
    kept = [c for c in _comments(page.text) if "in the line" not in c]
    assert [c for c in _comments(edited.text) if c in kept] == kept
    assert edited.text.endswith("---\n\nIntro.\n")


def test_block_scalar_reviewer_case(spec):
    page = _page("h1: |-\n  Read the docs\n# keep this note\n", spec)
    edited = model.set_field(page, "h1", "Read them now")
    assert "# keep this note" in edited.text
    assert "docs# keep" not in edited.text and "now# keep" not in edited.text
    colon = _page("h1: |-\n  Read the docs\n# keep: this note\n", spec)
    assert yaml.safe_load(model.set_field(colon, "h1", "New").text.split("---")[1])["h1"] == "New"


def test_block_scalar_keeps_its_style(spec):
    page = _page("h1: |-\n  Read the docs\n# note\n", spec)
    edited = model.set_field(page, "h1", "Read them\nnow")
    assert "h1: |-\n  Read them\n  now\n# note\n" in edited.text


@pytest.mark.parametrize(
    "front",
    [
        "redirect_from: [/a/, /b/]\n",
        "redirect_from:\n- /a/\n- /b/\n",
        "redirect_from:\n  - /a/\n  - '/b/'\n",
        "schema: {Service: {name: Roof}}\n",
        "schema:\n  Service:\n    name: Roof\n",
    ],
)
def test_flow_and_block_collections(spec, front):
    page = _page(f"h1: Head\n{front}# tail note\norder: 3\n", spec)
    if front.startswith("redirect_from"):
        edited = model.set_field(page, "redirect_from", ["/a/", "/b/", "/c/"])
        assert edited.front.data["redirect_from"] == ["/a/", "/b/", "/c/"]
    else:
        edited = model.set_field(page, "schema.Service", {"name": "Roof", "areaServed": "City"})
        assert edited.front.data["schema"]["Service"] == {"name": "Roof", "areaServed": "City"}
    assert edited.front.data["order"] == 3
    assert "# tail note" in edited.text


def test_alias_is_read_only_and_anchor_untouched(spec):
    page = _page("h1: Head\nnav_title: &short Docs\nog_title: *short\n", spec)
    by_name = {item.name: item for item in model.fields(page)}
    for name in ("og_title", "nav_title"):
        assert not by_name[name].editable
        assert by_name[name].readonly
    with pytest.raises(EditError):
        model.set_field(page, "og_title", "Other")
    with pytest.raises(EditError):
        model.set_field(page, "nav_title", "Other")
    with pytest.raises(EditError):
        model.set_field(page, "og_title", None)
    # соседнее поле правится, якорь и ссылка остаются как были
    edited = model.set_field(page, "h1", "New head")
    assert "nav_title: &short Docs\nog_title: *short\n" in edited.text
    assert edited.front.data["og_title"] == "Docs"


def test_shared_detects_alias_inside_mapping():
    text = "---\nbase: &b {name: x}\nschema:\n  Service: *b\n---\n"
    front = fronts.read(text)
    assert fronts.shared(front, ["schema", "Service"])
    assert fronts.shared(front, ["schema", "Service", "name"])
    assert fronts.shared(front, ["base"])
    assert not fronts.shared(front, ["schema"])


LIST = """redirect_from:
  # old addresses
  - /a/
  # - /commented/
  - '/b/'   # note
  - /c/  # c-note
"""


@pytest.mark.parametrize(
    "value",
    [
        ["/a/", "/b/", "/c/", "/d/"],
        ["/a/", "/c/"],
        ["/z/", "/a/", "/b/", "/c/"],
        ["/a/", "/b/"],
        ["/a/", "/B/", "/c/"],
        ["/c/"],
    ],
)
def test_block_list_keeps_comments(spec, value):
    page = _page(f"h1: Head\n{LIST}order: 1\n", spec)
    edited = model.set_field(page, "redirect_from", value)
    assert edited.front.data["redirect_from"] == value
    assert "# old addresses" in edited.text
    assert "# - /commented/" in edited.text
    if "/b/" in value:
        assert "'/b/'   # note" in edited.text
    if "/c/" in value:
        assert "/c/  # c-note" in edited.text
    assert edited.front.data["order"] == 1
