"""Модель правки страницы (STUDIO.ST6): поля, правка на месте, секции, языки, проверка."""

from __future__ import annotations

import datetime as dt

import pytest

from heron import edit
from heron.core.parser import blocks, markdown, sections
from heron.scaffold import create
from tests.edit_corpus import contract, write_page

PAGE = """---
title: "About the studio"
# ↑ the title in search
h1: About us
description: What we do and for whom.
# og_title:                  # empty - title is used
# og_image: media/og.png     # a picture for social networks
# schema:                    # refinements of the markup
#   Service:
#     serviceType: design
topics: [one, two]           # a field of the theme, the editor does not know it
---

Intro paragraph with <!-- a note to self --> a comment.

<!-- block below: keep it short -->
## Why us {#why}

- **Fast.** We answer the same day.
- **Clear.** One price,
  no surprises.
- A plain item.

> Ask us anything.

## How we work {#how}

1. **[FIRST] Call.** We talk.
2. **Plan.** We write it down.

   ```bash
   heron check .
   ```

## Raw {#raw}

<div class="hand-made">kept as is</div>

Plain | facts
"""


@pytest.fixture(scope="module")
def spec():
    return contract("en")


def _page(spec, text=PAGE, rel="content/en/about.md"):
    return edit.load(text, spec, rel=rel)


def _changed_lines(before: str, after: str) -> list[tuple[str, str]]:
    a, b = before.split("\n"), after.split("\n")
    assert len(a) == len(b), "число строк изменилось"
    return [(x, y) for x, y in zip(a, b, strict=True) if x != y]


# --- поля --------------------------------------------------------------------------


def test_fields_go_in_groups_service_first_then_sections(spec):
    page = _page(spec)
    paths = [field.path for field in edit.fields(page)]
    assert paths[:3] == ["title", "h1", "description"]
    groups = [field.group for field in edit.fields(page)]
    assert groups.index("section") > groups.index("publishing")
    assert "sections.intro.text" in paths
    assert paths.index("sections.why.heading") < paths.index("sections.how.heading")
    why = {f.name: f for f in edit.fields(page) if f.section == "why"}
    assert why["items"].value[0] == {"term": "Fast", "text": "We answer the same day."}
    assert why["items"].value[1]["text"] == "One price,\nno surprises."
    assert why["callout"].value == "Ask us anything."
    assert why["items"].hint and why["items"].fields and why["items"].md == "items"


def test_groups_have_titles_and_cover_every_field(spec):
    page = _page(spec)
    titles = {group["name"]: group["title"] for group in edit.groups(page)}
    assert all(titles.values())
    assert {field.group for field in edit.fields(page)} <= set(titles)
    assert list(titles).index("schema") < list(titles).index("section")


def test_field_has_value_default_hint_help_and_limits(spec):
    by_path = {field.path: field for field in edit.fields(_page(spec))}
    title = by_path["title"]
    assert title.value == "About the studio" and title.required
    assert title.hint and title.help and title.limits["max_length"] == 60
    assert by_path["slug"].default == "about"
    assert by_path["nav_title"].default == "About us"
    assert by_path["og_title"].value is None and by_path["og_title"].default == "About the studio"
    assert by_path["order"].default == 999 and by_path["noindex"].default is False
    assert by_path["type"].value is None and by_path["type"].default == "page"
    assert by_path["type"].limits["values"] == ["home", "page", "404"]


def test_fields_are_json_ready_and_the_same_list_for_every_consumer(spec):
    import json

    page = _page(spec)
    first = [field.to_dict() for field in edit.fields(page)]
    assert json.loads(json.dumps(first)) == first
    assert [field.to_dict() for field in edit.fields(page)] == first


def test_values_match_what_the_build_sees(spec):
    """Поля блока - те же данные, что разбор секций сборки отдаёт теме."""
    from tests.edit_corpus import corpus

    del corpus
    from heron.scaffold import DEMO

    text = (DEMO / "en" / "blocks.md").read_text(encoding="utf-8")
    page = _page(spec, text, rel="content/en/blocks.md")
    md = markdown.make()
    _intro, found = sections.split(md, markdown.strip_comments(text), "x")
    blocks.apply(md, found)
    assert [i["q"] for i in edit.get(page, "sections.faq.items")] == [
        item["q"] for item in found["faq"].data
    ]
    steps = edit.get(page, "sections.steps.items")
    assert [(s["tag"], s["title"]) for s in steps] == [
        (s["tag"], s["title"]) for s in found["steps"].data
    ]
    terms = [getattr(i, "term", "") for i in found["list"].data]
    assert [i["term"] for i in edit.get(page, "sections.list.items")] == terms
    assert [r["key"] for r in edit.get(page, "sections.facts.rows")] == [
        r["key"] for r in found["facts"].data
    ]
    assert edit.get(page, "sections.table.head") == found["table"].data["head"]
    assert [t["id"] for t in edit.get(page, "sections.tabs.tabs")] == [
        t["id"] for t in found["tabs"].data
    ]
    assert [g["title"] for g in edit.get(page, "sections.compare.groups")] == [
        g["title"] for g in found["compare"].data
    ]


# --- SEO-блок ----------------------------------------------------------------------


def test_new_key_uncomments_its_placeholder_and_keeps_the_hint(spec):
    page = edit.set(_page(spec), "og_title", "Share us")
    assert _changed_lines(PAGE, page.text) == [
        (
            "# og_title:                  # empty - title is used",
            "og_title: Share us           # empty - title is used",
        )
    ]
    back = edit.set(page, "og_title", None)
    assert back.text == PAGE


def test_placeholder_with_an_example_value_gets_the_real_one(spec):
    page = edit.set(_page(spec), "og_image", "media/share.png")
    line = next(x for x in page.text.split("\n") if x.startswith("og_image:"))
    assert line == "og_image: media/share.png    # a picture for social networks"


def test_quoting_style_is_kept_and_values_are_typed(spec):
    page = edit.set(_page(spec), "title", "New: title")
    assert 'title: "New: title"' in page.text
    page = edit.set(page, "h1", "Plain h1")
    assert "\nh1: Plain h1\n" in page.text
    page = edit.set(page, "noindex", "true")
    page = edit.set(page, "order", "5")
    page = edit.set(page, "date", "2026-03-14")
    assert edit.get(page, "noindex") is True and edit.get(page, "order") == 5
    assert edit.get(page, "date") == dt.date(2026, 3, 14)
    page = edit.set(page, "h1", "yes")
    assert edit.get(page, "h1") == "yes"  # не превратилось в true


def test_unknown_keys_and_comments_survive_an_edit(spec):
    page = edit.set(_page(spec), "description", "Something else entirely.")
    assert "topics: [one, two]           # a field of the theme" in page.text
    assert "# ↑ the title in search" in page.text
    assert len(_changed_lines(PAGE, page.text)) == 1


def test_nested_schema_fields_go_into_the_placeholder_block(spec):
    page = edit.set(_page(spec), "schema.Service.serviceType", "interior design")
    assert edit.get(page, "schema.Service") == {"serviceType": "interior design"}
    assert "schema:                      # refinements of the markup\n  Service:\n" in page.text
    page = edit.set(page, "schema.Service.areaServed", "Kyiv")
    assert edit.get(page, "schema.Service")["areaServed"] == "Kyiv"
    page = edit.set(page, "schema.Service.areaServed", None)
    page = edit.set(page, "schema.Service.serviceType", None)
    assert page.text == PAGE
    kinds = [f.path for f in edit.fields(edit.set(page, "schema.Service.x", "y"))]
    assert "schema.Service" in kinds


def test_list_values_of_the_seo_block(spec):
    page = edit.set(_page(spec), "redirect_from", ["/old/", "/older/"])
    assert edit.get(page, "redirect_from") == ["/old/", "/older/"]
    page = edit.set(page, "redirect_from.1", "/oldest/")
    assert edit.get(page, "redirect_from") == ["/old/", "/oldest/"]
    page = edit.set(page, "redirect_from", None)
    assert edit.get(page, "redirect_from") is None


def test_page_without_seo_block_gets_one(spec):
    page = edit.load("Just text.\n", spec)
    page = edit.set(page, "title", "T")
    assert page.text == "---\ntitle: T\n---\n\nJust text.\n"


def test_broken_yaml_makes_the_seo_block_read_only_but_keeps_the_body(spec):
    text = "---\ntitle: [oops\n---\n\nIntro.\n"
    page = edit.load(text, spec)
    by_path = {field.path: field for field in edit.fields(page)}
    assert not by_path["title"].editable and by_path["title"].readonly
    with pytest.raises(edit.EditError):
        edit.set(page, "title", "x")
    page = edit.set(page, "sections.intro.text", "New intro.")
    assert page.text == "---\ntitle: [oops\n---\n\nNew intro.\n"


# --- тело --------------------------------------------------------------------------


def test_list_item_edits_keep_markers_indents_and_comments(spec):
    page = edit.set(_page(spec), "sections.why.items.1.text", "One price,\nalways.")
    assert "- **Clear.** One price,\n  always.\n" in page.text
    page = edit.set(page, "sections.why.items.0.term", "Quick")
    assert "- **Quick.** We answer the same day." in page.text
    page = edit.set(page, "sections.why.items.2.term", "Plain")
    assert "- **Plain.** A plain item." in page.text
    page = edit.set(page, "sections.intro.text", "Intro with <!-- a note to self --> kept.")
    assert "<!-- block below: keep it short -->" in page.text
    assert '<div class="hand-made">kept as is</div>' in page.text


def test_steps_tag_title_and_more(spec):
    page = _page(spec)
    steps = edit.get(page, "sections.how.items")
    assert steps[0] == {"tag": "FIRST", "title": "Call", "text": "We talk.", "more": ""}
    assert steps[1]["more"] == "```bash\nheron check .\n```"
    page = edit.set(page, "sections.how.items.1.more", "```bash\nheron build .\n```")
    assert "   ```bash\n   heron build .\n   ```" in page.text
    page = edit.set(page, "sections.how.items.0.tag", "")
    assert "1. **Call.** We talk." in page.text
    page = edit.set(page, "sections.how.items.2", {"title": "Ship", "text": "Done.", "tag": "LAST"})
    assert "\n3. **[LAST] Ship.** Done.\n" in page.text


def test_whole_list_rewrite_keeps_unchanged_items_byte_for_byte(spec):
    page = _page(spec)
    items = edit.get(page, "sections.why.items")
    page = edit.set(page, "sections.why.items", [items[0], {"term": "", "text": "New."}, items[1]])
    assert (
        "- **Fast.** We answer the same day.\n- New.\n- **Clear.** One price,\n  no surprises."
        in (page.text)
    )
    page = edit.set(page, "sections.why.items.1", None)
    assert "- New." not in page.text


def test_single_line_places_refuse_line_breaks(spec):
    page = _page(spec)
    with pytest.raises(edit.EditError):
        edit.set(page, "sections.why.heading", "Two\nlines")
    with pytest.raises(edit.EditError):
        edit.set(page, "sections.why.items.0.term", "a\nb")
    with pytest.raises(edit.EditError):
        edit.set(page, "sections.why.anchor", "Bad Anchor")


def test_heading_and_anchor_are_edited_in_place(spec):
    page = edit.set(_page(spec), "sections.why.heading", "Why choose us")
    assert "## Why choose us {#why}" in page.text
    page = edit.set(page, "sections.why.anchor", "reasons")
    assert "## Why choose us {#reasons}" in page.text
    assert page.body.get("reasons") is not None


def test_add_and_remove_section(spec):
    page = edit.add_section(
        _page(spec),
        "faq",
        heading="Questions",
        kind="faq",
        values={"items": [{"q": "Why?", "a": "Because."}]},
    )
    assert page.text.endswith("## Questions {#faq}\n\n### Why?\n\nBecause.\n")
    assert edit.remove_section(page, "faq").text == PAGE
    page = edit.add_section(_page(spec), "pics", heading="Pictures", kind="gallery")
    assert "## Pictures {#pics .gallery}" in page.text
    page = edit.set(page, "sections.pics.items", [{"image": "media/a.png", "alt": "A"}])
    assert edit.get(page, "sections.pics.items") == [{"image": "media/a.png", "alt": "A"}]
    page = edit.add_section(
        _page(spec),
        "plan",
        heading="Plan",
        kind="steps",
        after="why",
        values={"items": ["One", "Two"]},
    )
    assert "> Ask us anything.\n\n## Plan {#plan}\n\n1. One\n2. Two\n\n## How we work" in page.text
    with pytest.raises(edit.EditError):
        edit.add_section(page, "plan")


def test_missing_section_from_the_type_is_created_by_setting_its_field(spec):
    text = "---\ntitle: T\nh1: H\ndescription: D\n---\n"
    page = edit.load(text, spec, rel="content/en/index.md")
    fields = {f.path: f for f in edit.fields(page)}
    assert not fields["sections.intro.lead"].present
    page = edit.set(page, "sections.intro.lead", "Lead.")
    page = edit.set(page, "sections.intro.promise", "Promise.")
    assert page.text == text + "\nLead.\n\nPromise.\n"


def test_form_the_editor_cannot_write_is_read_only_with_a_reason(spec):
    text = "---\ntitle: T\nh1: H\ndescription: D\n---\n\nSetext {#odd}\n---\n\nText.\n"
    page = edit.load(text, spec)
    heading = next(f for f in edit.fields(page) if f.path == "sections.odd.heading")
    assert not heading.editable and heading.readonly
    with pytest.raises(edit.EditError):
        edit.set(page, "sections.odd.heading", "x")
    assert edit.set(page, "sections.odd.text", "Other.").text.endswith("---\n\nOther.\n")


def test_bad_anchor_makes_the_body_read_only(spec):
    page = edit.load("---\ntitle: T\nh1: H\ndescription: D\n---\n\n## X {#Bad_Id}\n", spec)
    assert page.body.error is not None
    assert all(not f.editable for f in edit.fields(page) if f.group == "section")
    assert any(i.path == "sections" for i in edit.validate(page))


def test_theme_without_fields_shows_sections_as_free_markdown():
    from heron.contracts.theme import ThemeConfig
    from heron.core import describe

    theme = ThemeConfig.model_validate({"name": "old", "modules": ["faq"], "types": {"page": {}}})
    page = edit.load(PAGE, describe.contract(theme, None, "en"))
    why = [f for f in edit.fields(page) if f.section == "why"]
    assert [f.name for f in why] == ["heading", "anchor", "text"]
    assert why[-1].value.startswith("- **Fast.**")


def test_menu_and_category_live_outside_the_file(spec):
    page = _page(spec, rel="content/en/services/roofing.md")
    by_path = {f.path: f for f in edit.fields(page)}
    assert by_path["category"].value == "services" and not by_path["category"].editable
    with pytest.raises(edit.EditError):
        edit.set(page, "category", "other")
    page = edit.set(page, "menu", True)
    assert page.text == PAGE
    assert edit.site_changes(page) == {"nav.main": ["services/roofing"]}
    assert edit.get(page, "menu") is True


def test_category_page_has_children_type_and_view(spec):
    text = "---\ntitle: T\nh1: H\ndescription: D\n---\n"
    page = edit.load(text, spec, rel="content/en/services/_index.md")
    by_path = {f.path: f for f in edit.fields(page)}
    assert "children_type" in by_path
    assert by_path["view"].default == "cards" and by_path["view"].limits["values"] == [
        "cards",
        "list",
    ]
    assert by_path["slug"].default == "services" and by_path["category"].value is None


# --- проверка ----------------------------------------------------------------------


def test_validate_uses_the_rules_of_check(spec):
    page = edit.set(_page(spec), "title", "About us")
    page = edit.set(page, "description", "x" * 160)
    page = edit.set(page, "image", "media/cover.png")
    found = {(i.path, i.message.key) for i in edit.validate(page)}
    assert ("h1", "loader_fm_title_h1_same") in found
    assert ("description", "loader_fm_description_long") in found
    assert ("image_alt", "loader_fm_image_alt") in found
    page = edit.set(page, "slug", "Bad Slug")
    assert any(i.path == "slug" and i.level == "error" for i in edit.validate(page))
    page = edit.set(page, "title", None)
    assert ("title", "edit_required") in {(i.path, i.message.key) for i in edit.validate(page)}


def test_validate_checks_contract_limits_enum_and_schema(spec):
    page = edit.set(_page(spec), "type", "nope")
    page = edit.set(page, "sections.why.items.0.term", "x" * 70)
    page = edit.set(page, "schema.Service.serviceType", "design")
    page = edit.set(page, "schema.Service.colour", "red")
    page = edit.set(page, "schema.Nonsense.x", "y")
    keys = {(i.path, i.message.key) for i in edit.validate(page)}
    assert ("type", "edit_not_in_values") in keys
    assert ("sections.why.items.0.term", "edit_too_long") in keys
    assert ("schema.Service.colour", "edit_schema_prop") in keys
    assert ("schema.Service.serviceType", "edit_schema_prop") not in keys
    assert ("schema.Nonsense", "edit_schema_type") in keys
    message = next(i for i in edit.validate(page) if i.path == "type").to_dict("ru")["message"]
    assert "nope" in message


def test_validate_checks_pictures_on_disk(spec, tmp_path):
    from PIL import Image

    (tmp_path / "media").mkdir()
    Image.new("RGB", (800, 600)).save(tmp_path / "media" / "small.png")
    page = edit.set(_page(spec), "image", "media/small.png")
    page = edit.set(page, "image_alt", "A picture")
    page = edit.set(page, "og_image", "media/none.png")
    keys = {(i.path, i.message.key) for i in edit.validate(page, tmp_path)}
    assert ("image", "edit_image_narrow") in keys
    assert ("og_image", "edit_image_missing") in keys


def test_demo_pages_of_the_starter_theme_are_clean(spec, tmp_path):
    root = tmp_path / "site"
    create(root, name="Demo", languages=["en", "ru"], notes="en", demo=True)
    for path in sorted((root / "content").rglob("*.md")):
        if path.name == "heron-readme.md":
            continue
        rel = path.relative_to(root).as_posix()
        page = edit.open_page(root, rel, spec)
        issues = [i for i in edit.validate(page, root) if i.level == "error"]
        assert not issues, (rel, [(i.path, i.message) for i in issues])


# --- языки -------------------------------------------------------------------------


def test_files_of_a_page_on_every_language(tmp_path, monkeypatch):
    from heron.contracts.site import load_site

    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "site"
    create(root, name="Demo", languages=["ru", "en", "de"], notes="en")
    config = load_site(root / "site.yaml")
    write_page(root, "page", "about", lang="en")
    files = edit.files(root, config, "about")
    assert [(f.lang, f.rel, f.exists, f.default) for f in files] == [
        ("ru", "content/ru/about.md", False, True),
        ("en", "content/en/about.md", True, False),
        ("de", "content/de/about.md", False, False),
    ]
    assert edit.missing(root, config, "about") == ["ru", "de"]
    assert [f.exists for f in edit.files(root, config, "")] == [True, True, True]
    (root / "content" / "en" / "services").mkdir()
    (root / "content" / "en" / "services" / "_index.md").write_text(
        "---\ntitle: S\nh1: S\ndescription: D\nchildren_type: page\n---\n", encoding="utf-8"
    )
    assert edit.files(root, config, "services")[1].rel == "content/en/services/_index.md"
    assert edit.key_of("content/en/services/_index.md") == ("en", "services", True)
    assert edit.key_of("content/en/index.md") == ("en", "", False)
    assert edit.rel_for("de", "services/roofing") == "content/de/services/roofing.md"


def test_type_comes_from_the_folder_like_in_the_build(tmp_path):
    root = tmp_path
    folder = root / "content" / "en" / "docs"
    folder.mkdir(parents=True)
    (folder / "_index.md").write_text("---\nchildren_type: guide\n---\n", encoding="utf-8")
    assert edit.folder_type(root, "content/en/docs/start.md") == "guide"
    assert edit.folder_type(root, "content/en/index.md") == "home"
    assert edit.folder_type(root, "content/en/404.md") == "404"
    assert edit.folder_type(root, "content/en/about.md") == "page"
