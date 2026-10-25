"""JSON Schema контрактов и errors.json (21 §10 «heron schema»)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

import heron
from heron.contracts import schemas
from heron.contracts.frontmatter import PageMeta
from heron.contracts.site import load_site
from heron.contracts.theme import load_theme

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "docs" / "ru" / "templates"
ENGINE_SPEC = ROOT / "docs" / "ru" / "spec" / "21-engine.md"

BUILDERS = {
    "site.schema.json": schemas.site_schema,
    "theme.schema.json": schemas.theme_schema,
    "frontmatter.schema.json": schemas.frontmatter_schema,
    "setup.schema.json": schemas.setup_schema,
    "errors.json": schemas.errors_registry,
}


@pytest.mark.parametrize("name", schemas.FILES)
def test_header_fields(name: str) -> None:
    data = BUILDERS[name]()
    major, minor = heron.__version__.split(".")[:2]
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert data["$id"] == f"https://sitebuilder.heron.software/schema/{major}.{minor}/{name}"
    assert data["x-heron-version"] == heron.__version__


@pytest.mark.parametrize("name", schemas.FILES)
def test_schema_is_valid_json_schema(name: str) -> None:
    Draft202012Validator.check_schema(BUILDERS[name]())


def _plain(value):
    """Данные образца как их видит редактор с YAML 1.2: `on` — строка, даты — строки."""
    if isinstance(value, dict):
        return {("on" if key is True else key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _sample(name: str):
    raw = (TEMPLATES / name).read_text(encoding="utf-8")
    if name.endswith(".md"):
        raw = raw.split("---", 2)[1]
    return json.loads(json.dumps(_plain(yaml.safe_load(raw)), default=str))


@pytest.mark.parametrize(
    ("sample", "builder"),
    [
        ("site.yaml", schemas.site_schema),
        ("theme.yaml", schemas.theme_schema),
        ("page.md", schemas.frontmatter_schema),
    ],
)
def test_samples_pass_their_json_schema(sample: str, builder) -> None:
    validator = Draft202012Validator(builder())
    errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(_sample(sample))]
    assert not errors, errors


def test_site_schema_localized_values() -> None:
    validator = Draft202012Validator(schemas.site_schema())
    base = {
        "heron": ">=0.1",
        "site": {"domain": "example.com", "theme": "t", "name_ru": "Имя", "name_pt-br": "N"},
    }
    problems = [e.message for e in validator.iter_errors(base)]
    assert not problems, problems
    assert validator.is_valid(
        {**base, "seo": {"title_suffix_ru": "x", "og_default_image_en": "a.png"}}
    )
    assert validator.is_valid(base)
    assert not validator.is_valid({**base, "site": {**base["site"], "name_RUS": "x"}})
    assert "E011" in schemas.site_schema()["description"]
    assert not validator.is_valid({**base, "seo": {"nope_ru": "x"}})
    defs = schemas.site_schema()["$defs"]
    assert "i18n" not in defs["SiteBlock"]["properties"]
    assert "i18n" not in defs["SeoBlock"]["properties"]
    assert "\\Z" not in json.dumps(schemas.site_schema())


def test_frontmatter_schema_accepts_what_model_accepts() -> None:
    validator = Draft202012Validator(schemas.frontmatter_schema())
    page = {"title": "a", "h1": "b", "description": "c"}
    empty = {
        "order": None,
        "published": None,
        "noindex": None,
        "redirect_from": None,
        "gone": None,
        "date": None,
        "slug": None,
    }
    numbers = {"type": 404, "children_type": 5, "slug": 2024}
    for extra in (empty, numbers, {"my_field": [1, 2], "related": ["a"]}):
        data = {**page, **extra}
        PageMeta(**data)
        assert validator.is_valid(data), extra
    assert not validator.is_valid({"title": "a", "h1": "b"})
    assert not validator.is_valid({**page, "order": "x"})


def test_theme_schema_accepts_numeric_version() -> None:
    validator = Draft202012Validator(schemas.theme_schema())
    assert validator.is_valid({"name": "t", "version": 0.1})
    assert validator.is_valid({"name": "t", "version": "0.1"})
    assert not validator.is_valid({"name": "t", "version": ["x"]})
    assert "on" in schemas.theme_schema()["description"]


def test_frontmatter_schema_open_and_documented() -> None:
    data = schemas.frontmatter_schema()
    assert data["additionalProperties"] is True
    assert {"title", "h1", "description"} <= set(data["required"])
    text = data["description"]
    assert "\\Z" not in text
    assert "date" in text and "updated" in text
    assert "redirect_from" in text and "slug" in text


def test_all_schemas_matches_dump() -> None:
    files = schemas.all_schemas()
    assert tuple(files) == schemas.FILES
    for name, text in files.items():
        assert text.endswith("}\n")
        assert text == schemas.dump(BUILDERS[name]())
        assert json.loads(text)["x-heron-version"] == heron.__version__


def test_dump_is_sorted_indented_unescaped() -> None:
    text = schemas.dump({"b": "я", "a": 1})
    assert text == '{\n  "a": 1,\n  "b": "я"\n}\n'


def test_export_creates_target_and_is_byte_stable(tmp_path: Path) -> None:
    first, second = tmp_path / "one" / "nested", tmp_path / "two"
    names = schemas.export(first)
    assert sorted(names) == sorted(schemas.FILES)
    schemas.export(second)
    for name in schemas.FILES:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        json.loads((first / name).read_text(encoding="utf-8"))


def test_export_idempotent_over_existing_files(tmp_path: Path) -> None:
    schemas.export(tmp_path)
    before = {n: (tmp_path / n).read_bytes() for n in schemas.FILES}
    schemas.export(tmp_path)
    assert before == {n: (tmp_path / n).read_bytes() for n in schemas.FILES}


def test_samples_pass_their_models() -> None:
    load_site(TEMPLATES / "site.yaml")
    load_theme(TEMPLATES / "theme.yaml")
    meta = PageMeta(**yaml.safe_load((TEMPLATES / "page.md").read_text("utf-8").split("---", 2)[1]))
    assert meta.title and meta.h1 and meta.description


def _spec_codes() -> set[str]:
    text = ENGINE_SPEC.read_text(encoding="utf-8")
    start = text.index("## 11. Ошибки и предупреждения")
    end = text.index("\n## 12.", start)
    return set(re.findall(r"`(E0\d\d)`", text[start:end]))


def test_errors_json_matches_spec_section_11() -> None:
    codes = set(schemas.errors_registry()["errors"])
    spec = _spec_codes()
    assert spec, "в разделе 11 не нашлось ни одного кода"
    assert codes == spec, f"только в errors.json: {codes - spec}; только в спеке: {spec - codes}"


def test_errors_entries_have_title_and_hint() -> None:
    for code, entry in schemas.errors_registry()["errors"].items():
        assert re.fullmatch(r"E0\d\d", code)
        assert entry["title"].strip()
        assert isinstance(entry["hint"], str)
