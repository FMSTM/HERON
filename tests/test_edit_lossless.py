"""Правка страницы без потерь (STUDIO.ST6): критерий приёмки - «открыл, сохранил, байт в байт».

Корпус - все страницы, которые движок кладёт или показывает образцом (tests/edit_corpus.py).
Для каждой: чтение и запись без правок дают те же байты; запись поля его же
значением ничего не меняет; правка одного поля меняет только символы этого
поля, остальные поля и формы секций остаются прежними. То же - с `\\r\\n`,
BOM и без перевода строки в конце.
"""

from __future__ import annotations

import pytest

from heron import edit
from tests.edit_corpus import contract, corpus, unique


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    return corpus(str(tmp_path_factory.mktemp("edit-corpus")))


@pytest.fixture(scope="module")
def spec():
    return contract("en")


def _rel(name: str) -> str:
    return "content/" + name.split("/content/")[-1] if "/content/" in name else "content/en/page.md"


def test_corpus_covers_every_source(pages):
    names = [name for name, _ in pages]
    for source in ("starter-ru/demo/", "starter-en/demo/", "site-ru-True/", "site-en-False/"):
        assert any(name.startswith(source) for name in names), source
    for source in ("pack/demo/content/", "page-ru/", "docs/ru/templates/page.md", "demo-source/"):
        assert any(name.startswith(source) for name in names), source
    assert sum(name.startswith("tests/") for name in names) > 50
    assert len(unique(pages)) > 100


def test_every_page_round_trips_byte_for_byte(pages, spec):
    bad = [
        name
        for name, raw in pages
        if edit.dump(edit.load(raw, spec, rel=_rel(name))).encode() != raw
    ]
    assert not bad


@pytest.mark.parametrize(
    "variant",
    [
        lambda t: t.replace("\r\n", "\n").replace("\n", "\r\n"),
        lambda t: "﻿" + t,
        lambda t: t.rstrip("\n"),
        lambda t: t.replace("\r\n", "\n").replace("\n", "\r"),
    ],
    ids=["crlf", "bom", "no-final-newline", "cr"],
)
def test_line_endings_bom_and_missing_final_newline_round_trip(pages, spec, variant):
    for name, raw in unique(pages):
        text = variant(raw.decode("utf-8"))
        page = edit.load(text.encode("utf-8"), spec, rel=_rel(name))
        assert edit.dump(page) == text, name


def test_mixed_line_endings_round_trip(spec):
    text = "---\r\ntitle: A\nh1: B\r\ndescription: C\n---\n\nIntro\r\n\r\n## X {#x}\n\n- a\r\n- b"
    assert edit.dump(edit.load(text, spec)) == text


def test_writing_a_field_with_its_own_value_changes_nothing(pages, spec):
    bad = []
    for name, raw in unique(pages):
        page = edit.load(raw, spec, rel=_rel(name))
        for field in edit.fields(page):
            if not field.editable or not field.present or field.value in (None, "", [], {}):
                continue
            if edit.set(page, field.path, field.value).text != page.text:
                bad.append((name, field.path))
    assert not bad


def _leaves(fields):
    """Текстовые поля страницы и поля первого пункта каждого списка."""
    for field in fields:
        if not field.editable or field.type in ("schema", "flag", "number", "date", "enum", "ref"):
            continue
        if isinstance(field.value, str):
            yield field.path, field.value
        elif isinstance(field.value, list) and field.value:
            first = field.value[0]
            if isinstance(first, str):
                yield f"{field.path}.0", first
            elif isinstance(first, dict):
                for key, value in first.items():
                    if isinstance(value, str):
                        yield f"{field.path}.0.{key}", value
                    elif isinstance(value, list) and value and isinstance(value[0], str):
                        yield f"{field.path}.0.{key}.0", value[0]


def _new(path: str, value: str) -> str:
    if path.endswith((".anchor", ".id")):
        return (value + "-x") if value else "x"
    if path.endswith(".image"):
        return "zz" + value
    return ("ZZ " + value) if value else "ZZ"


def test_editing_one_field_changes_only_its_bytes(pages, spec):
    """Правка поля: вне его места текст тот же, остальные поля и формы секций - прежние."""
    bad = []
    for name, raw in unique(pages):
        page = edit.load(raw, spec, rel=_rel(name))
        fields = edit.fields(page)
        before = {field.path: field.value for field in fields}
        kinds = [(s.id, s.kind) for s in page.body.sections]
        for path, value in _leaves(fields):
            new = _new(path, value)
            changed = edit.set(page, path, new)
            where = edit.span(page, path)
            old, text = page.text, changed.text
            if where is None or not (
                text.startswith(old[: where[0]]) and text.endswith(old[where[1] :])
            ):
                bad.append((name, path, "outside its place"))
                continue
            renamed = path.endswith(".anchor")
            if not renamed and edit.get(changed, path) != new:
                bad.append((name, path, "value"))
                continue
            if not renamed and [(s.id, s.kind) for s in changed.body.sections] != kinds:
                bad.append((name, path, "section forms"))
                continue
            parts = path.split(".")
            top = ".".join(parts[:3]) if parts[0] == "sections" else parts[0]
            after = {field.path: field.value for field in edit.fields(changed)}
            derived = {"nav_title", "og_title", "og_description"}
            for other, value_before in before.items():
                if other == top or other in derived or (renamed and other.startswith(top[:-7])):
                    continue
                if after.get(other) != value_before:
                    bad.append((name, path, other))
                    break
    assert not bad, bad[:10]


def test_crlf_page_gets_crlf_in_new_lines(spec):
    text = "---\r\ntitle: A\r\nh1: B\r\ndescription: C\r\n---\r\n\r\nIntro.\r\n"
    page = edit.load(text, spec, rel="content/en/about.md")
    page = edit.set(page, "redirect_from", ["/a/", "/b/"])
    page = edit.set(page, "sections.intro.text", "One\ntwo")
    page = edit.add_section(page, "more", heading="More")
    page = edit.set(page, "sections.more.text", "Line 1\nLine 2")
    assert "\n" not in page.text.replace("\r\n", "")
    assert edit.get(page, "sections.more.text") == "Line 1\nLine 2"


def test_crlf_placeholder_is_uncommented_in_place(spec):
    text = "---\r\ntitle: A\r\nh1: B\r\ndescription: C\r\n# og_title:          # hint\r\n---\r\n"
    page = edit.set(edit.load(text, spec), "og_title", "Share")
    assert page.text == text.replace("# og_title:          #", "og_title: Share      #")
    assert edit.set(page, "og_title", None).text == text


def test_bom_stays_first_and_no_final_newline_is_kept(spec):
    text = "﻿---\ntitle: A\nh1: B\ndescription: C\n---\n\nIntro."
    page = edit.load(text.encode("utf-8"), spec, rel="content/en/about.md")
    page = edit.set(page, "og_title", "Share")
    page = edit.set(page, "sections.intro.text", "New intro.")
    assert page.text.startswith("﻿---\n")
    assert not page.text.endswith("\n")
    assert edit.get(page, "og_title") == "Share"
