"""Контракт темы: поля модулей, секции типов, виды категорий, подсказки (STUDIO ST1).

Спецификация: docs/ru/spec/21-engine.md, «Контракт темы».
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from jsonschema import Draft202012Validator

from heron import scaffold
from heron.cli import main
from heron.contracts import fields as service
from heron.contracts import schemas
from heron.contracts.theme import (
    FIELD_TYPES,
    KINDS,
    MD_PLACES,
    ThemeConfig,
    kinds_of,
    missing_hints,
)
from heron.core import build as pipeline
from heron.core.parser import blocks, markdown, sections
from heron.messages import TEXT, say
from heron.scaffold import create

MODULES = Path(scaffold.__file__).parent / "templates" / "modules"
DEMO = Path(scaffold.__file__).parent / "demo"


def starter(notes: str = "ru") -> ThemeConfig:
    text = scaffold.theme_yaml(notes, {"theme": "starter", "theme_title": '"HERON starter"'})
    return ThemeConfig.model_validate(yaml.safe_load(text))


def walk(fields, prefix=""):
    for spec in fields or []:
        yield f"{prefix}{spec.name}", spec
        yield from walk(spec.fields, f"{prefix}{spec.name}.")


# --- стартовая тема описана полностью --------------------------------------------


@pytest.mark.parametrize("notes", ["ru", "en"])
def test_starter_theme_is_described_in_ru_and_en(notes):
    theme = starter(notes)
    assert theme.described
    assert theme.hint_langs() == ["ru", "en"]
    assert missing_hints(theme) == []
    # у всего, чему положена подсказка, есть и hint, и help на обоих языках
    # (кроме мелких полей - у них help необязателен)
    for name, spec in theme.types.items():
        for lang in ("ru", "en"):
            assert spec.text("help", lang), (name, lang)
    for name, spec in theme.module_specs.items():
        for lang in ("ru", "en"):
            assert spec.text("hint", lang) and spec.text("help", lang), (name, lang)
            if spec.scope == "section":
                assert spec.text("example", lang), (name, lang)


def test_both_notes_languages_carry_the_same_contract():
    assert starter("ru").model_dump() == starter("en").model_dump()


def test_starter_describes_every_module_file_and_every_form():
    theme = starter()
    files = {path.stem for path in MODULES.glob("*.html")}
    assert set(theme.module_specs) == files
    drawn = {kind for name, spec in theme.module_specs.items() for kind in kinds_of(name, spec)}
    assert drawn == set(KINDS)
    for name, spec in theme.module_specs.items():
        if spec.scope == "page":
            assert spec.fields == [] and kinds_of(name, spec) == [], name
        else:
            assert spec.fields, name
            assert all(field.md for _, field in walk(spec.fields)), name


@pytest.fixture
def md():
    return markdown.make()


def parse(md, body: str):
    _, found = sections.split(md, body, "a.md")
    blocks.apply(md, found)
    return found


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_module_examples_are_the_real_markdown_of_the_module(md, lang):
    """Образец каждого модуля разбирается движком в ту форму, которую модуль рисует."""
    theme = starter()
    for name, spec in theme.module_specs.items():
        if spec.scope == "page":
            continue
        found = parse(md, spec.text("example", lang))
        assert len(found) == 1, name
        section = next(iter(found.values()))
        assert section.kind in kinds_of(name, spec), (name, section.kind)
        assert theme.module_for(section.kind) == name


@pytest.mark.parametrize("lang", ["ru", "en", "uk"])
def test_every_demo_block_is_drawn_by_a_described_module(md, lang):
    theme = starter()
    pages = sorted((DEMO / lang).rglob("*.md"))
    assert any(page.parent.name == "structure" for page in pages)  # и страницы раздела
    for page in pages:
        for section in parse(md, page.read_text(encoding="utf-8")).values():
            assert theme.module_for(section.kind), (page.name, section.id, section.kind)


def test_field_names_match_the_parsed_data(md):
    """Имена полей - те же ключи, что разбор отдаёт теме: контракт не выдумывает модель."""
    theme = starter()
    data = {}
    for name in ("faq", "facts", "steps", "list", "tabs"):
        spec = theme.module_specs[name]
        section = next(iter(parse(md, spec.text("example", "en")).values()))
        data[name] = section.data
    assert set(data["faq"][0]) == {"q", "a"}
    assert {"key", "value"} == set(data["facts"][0])
    assert {"tag", "title", "text", "more"} <= set(data["steps"][0])
    assert data["list"][0].term and data["list"][0].text
    assert {"title", "id"} <= set(data["tabs"][0])
    names = {
        name: [f.name for f in theme.module_specs[name].fields[-1].fields]
        for name in ("faq", "facts", "steps")
    }
    assert names["faq"] == ["q", "a"]
    assert names["facts"] == ["key", "value"]
    assert names["steps"] == ["tag", "title", "text", "more"]


def test_starter_contract_sits_in_theme_yaml_of_a_new_site(tmp_path):
    create(tmp_path / "s", name="demo", languages=["en"], notes="en")
    text = (tmp_path / "s" / "theme" / "theme.yaml").read_text(encoding="utf-8")
    assert scaffold.CONTRACT.read_text(encoding="utf-8").rstrip("\n") in text
    data = yaml.safe_load(text)
    assert data["heron"] == ">=0.3" and data["languages"] == ["ru", "en"]
    validator = Draft202012Validator(schemas.theme_schema())
    assert not [e.message for e in validator.iter_errors(data)]


# --- старая тема и проверка ------------------------------------------------------


def _site(tmp_path: Path, edit=None) -> Path:
    root = tmp_path / "s"
    create(root, name="demo", languages=["en"], notes="en")
    if edit:
        path = root / "theme" / "theme.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        edit(data)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8")
    return root


def _old(data):
    """Тема как до 0.3: modules списком, у типов только uses."""
    data["modules"] = list(data["modules"])
    data.pop("languages")
    data["types"] = {name: {"uses": spec["uses"]} for name, spec in data["types"].items()}


def _no_fields(result) -> list:
    return [
        w
        for w in result.collector.warnings
        if getattr(w.message, "key", "") == ("build_theme_no_fields")
    ]


def test_starter_check_has_no_contract_findings(tmp_path):
    result = pipeline.check(_site(tmp_path))
    assert not result.collector.errors, [str(e) for e in result.collector.errors]
    assert not _no_fields(result)


def test_old_theme_builds_and_check_warns_once(tmp_path):
    root = _site(tmp_path, _old)
    theme = ThemeConfig.model_validate(yaml.safe_load((root / "theme/theme.yaml").read_text()))
    assert not theme.described and missing_hints(theme) == []
    result = pipeline.check(root)
    assert not result.collector.errors
    assert len(_no_fields(result)) == 1
    assert "theme.yaml" in _no_fields(result)[0].path
    built = pipeline.run(root)
    assert not built.failed, [str(e) for e in built.collector.errors]
    assert not _no_fields(built)  # предупреждение - только у check


def test_missing_hint_in_one_language_is_an_error_of_check(tmp_path):
    def drop(data):
        del data["modules"]["faq"]["fields"][0]["fields"][0]["hint_en"]
        del data["types"]["page"]["views"]["options"]["list"]["hint_ru"]

    root = _site(tmp_path, drop)
    result = pipeline.check(root)
    errors = [e for e in result.collector.errors if e.code == "E041"]
    assert len(errors) == 1
    text = errors[0].message.text("en")
    assert "modules.faq.fields.items.fields.q (en)" in text
    assert "types.page.views.options.list (ru)" in text
    out = CliRunner().invoke(main, ["check", str(root), "--notes", "en"])
    assert out.exit_code == 1 and "E041" in out.output
    assert not pipeline.run(root).failed  # сборку подсказка не останавливает


def test_hint_without_suffix_covers_every_language():
    theme = ThemeConfig.model_validate(
        {
            "name": "t",
            "languages": ["ru", "en", "de"],
            "types": {"page": {"uses": ["intro"], "hint": "Page", "hint_ru": "Страница"}},
            "modules": {"prose": {"hint_en": "Text", "fields": [{"name": "t", "type": "text"}]}},
        }
    )
    assert theme.types["page"].text("hint", "de") == "Page"
    assert theme.types["page"].text("hint", "ru") == "Страница"
    assert missing_hints(theme) == ["modules.prose (ru, de)", "modules.prose.fields.t (ru, en, de)"]


def test_languages_default_to_the_suffixes_in_use():
    theme = ThemeConfig.model_validate(
        {
            "name": "t",
            "types": {"page": {"uses": ["intro"], "hint_uk": "Сторінка"}},
            "modules": {"prose": {"hint_uk": "Текст", "hint_en": "Text", "fields": []}},
        }
    )
    assert theme.hint_langs() == ["en", "uk"]
    assert missing_hints(theme) == ["types.page (en)"]


# --- негодное описание - E041 при чтении ----------------------------------------


def _module(**field) -> dict:
    return {"name": "t", "modules": {"m": {"fields": [{"name": "f", "type": "text", **field}]}}}


@pytest.mark.parametrize(
    ("data", "key"),
    [
        (_module(md="nowhere"), "site_th_field_md"),
        (_module(type="list"), "site_th_field_list"),
        (_module(type="list", item="text", fields=[]), "site_th_field_list"),
        (_module(type="list", item="list"), "site_th_field_list_item"),
        (_module(item="text"), "site_th_field_not_list"),
        (_module(type="enum"), "site_th_field_enum"),
        (_module(values=["a"]), "site_th_field_values"),
        (_module(min_width=800), "site_th_field_image"),
        (_module(type="image", ratio="wide"), "site_th_ratio"),
        (_module(name="Bad"), "site_th_field_name"),
        (_module(hint_ru=["a"]), "site_th_hint_text"),
        (_module(type="ref", ref="nope"), "site_th_field_ref"),
        (
            {"name": "t", "modules": {"m": {"fields": [{"name": "a", "type": "text"}] * 2}}},
            "site_th_field_dup",
        ),
        ({"name": "t", "modules": {"m": {"kinds": ["nope"]}}}, "site_th_module_kind"),
        ({"name": "t", "types": {"p": {"uses": ["intro"], "sections": {"x": {}}}}}, None),
        ({"name": "t", "types": {"p": {"children_type": "nope"}}}, "site_th_children_type"),
        (
            {"name": "t", "types": {"p": {"views": {"default": "a", "options": {"b": {}}}}}},
            "site_th_view_default",
        ),
        ({"name": "t", "types": {"p": {"views": {"default": "a", "options": {}}}}}, None),
        ({"name": "t", "languages": ["RU"]}, "site_th_language"),
        (_module(nope=1), None),
    ],
)
def test_invalid_contract_is_refused(data, key):
    with pytest.raises(ValueError) as caught:
        ThemeConfig.model_validate(data)
    if key:
        # самый длинный кусок текста сообщения между подстановками - в тексте ошибки
        chunks = re.split(r"\{[^}]*\}", TEXT["ru"][key])
        assert max(chunks, key=len).strip() in str(caught.value), (key, str(caught.value))


def test_invalid_contract_in_a_site_is_e041(tmp_path):
    root = _site(tmp_path, lambda d: d["modules"]["faq"]["fields"][0].update(md="nowhere"))
    out = CliRunner().invoke(main, ["check", str(root), "--notes", "en"])
    assert out.exit_code == 1
    assert "E041" in out.output and "nowhere" in out.output


def test_sections_wildcard_and_children_type_are_accepted():
    theme = ThemeConfig.model_validate(
        {
            "name": "t",
            "types": {
                "page": {
                    "uses": ["intro", "how:steps", "*"],
                    "children_type": "page",
                    "sections": {"*": {"hint": "any"}, "how": {"required": True}},
                }
            },
        }
    )
    assert theme.types["page"].sections["how"].required


def test_theme_schema_describes_localized_hints():
    validator = Draft202012Validator(schemas.theme_schema())
    base = {"name": "t", "modules": {"m": {"hint_ru": "а", "help_pt-br": "b", "fields": []}}}
    assert validator.is_valid(base)
    assert validator.is_valid({"name": "t", "modules": ["a", "b"]})  # прежняя форма
    assert not validator.is_valid({"name": "t", "modules": {"m": {"hint_RU": "a"}}})
    assert "i18n" not in json.dumps(schemas.theme_schema()["$defs"]["ModuleSpec"]["properties"])


# --- служебные поля -----------------------------------------------------------------


def test_service_fields_have_hints_and_help_in_ru_and_en():
    for spec in service.SERVICE:
        assert spec.group in service.GROUPS and spec.where in service.PLACES
        assert spec.type in FIELD_TYPES
        for lang in ("ru", "en"):
            assert f"field_{spec.name}_hint" in TEXT[lang], (spec.name, lang)
            assert f"field_{spec.name}_help" in TEXT[lang], (spec.name, lang)
            assert spec.hint(lang) and len(spec.help(lang)) > len(spec.hint(lang))
        assert spec.hint("ru") != spec.hint("en")
    for group in service.GROUPS:
        assert service.group_title("ru", group) != service.group_title("en", group)
    names = [spec.name for spec in service.SERVICE]
    for name in ("title", "h1", "description", "slug", "category", "image", "og_image"):
        assert name in names
    assert {"noindex", "menu", "anchor"} <= set(names)


def test_md_places_have_hints_in_both_languages():
    for place in MD_PLACES:
        key = "describe_md_" + place.replace("-", "_")
        assert say("ru", key) and say("en", key) and say("ru", key) != say("en", key)


# --- виды категории стартовой темы --------------------------------------------------


def test_category_view_list_is_drawn_as_rows(tmp_path):
    root = _site(tmp_path)
    folder = root / "content" / "en" / "guides"
    folder.mkdir()
    head = "---\ntitle: {t}\nh1: {t}\ndescription: About {t}\n{extra}---\n\nText.\n"
    (folder / "_index.md").write_text(head.format(t="Guides", extra="view: list\n"), "utf-8")
    (folder / "one.md").write_text(head.format(t="One", extra=""), "utf-8")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    html = (root / "dist" / "guides" / "index.html").read_text(encoding="utf-8")
    assert '<ul class="rows">' in html and "One" in html
    (folder / "_index.md").write_text(head.format(t="Guides", extra=""), "utf-8")
    pipeline.run(root)
    html = (root / "dist" / "guides" / "index.html").read_text(encoding="utf-8")
    assert '<ul class="cards">' in html
