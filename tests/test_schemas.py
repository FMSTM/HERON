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
    return set(re.findall(r"`(E0\d\d|SCH0\d\d)`", text[start:end]))


def test_errors_json_matches_spec_section_11() -> None:
    codes = set(schemas.errors_registry()["errors"])
    spec = _spec_codes()
    assert spec, "в разделе 11 не нашлось ни одного кода"
    assert codes == spec, f"только в errors.json: {codes - spec}; только в спеке: {spec - codes}"


def test_errors_entries_have_title_and_hint() -> None:
    for code, entry in schemas.errors_registry()["errors"].items():
        assert re.fullmatch(r"E0\d\d|SCH0\d\d", code)
        assert entry["title"].strip()
        assert isinstance(entry["hint"], str)


# --- E15.S1.T2: описания схем и названия ошибок - на языке комплекта -------------

import hashlib  # noqa: E402

from click.testing import CliRunner  # noqa: E402

from heron.cli import main  # noqa: E402

CYR = re.compile(r"[А-Яа-яЁё]")


def _walk(node, path=""):
    """Все строки схемы: (JSON Pointer, текст)."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}/{i}")
    elif isinstance(node, str):
        yield path, node


def _keys(node):
    """Структура без текстов: ключи и тип значения."""
    if isinstance(node, dict):
        return {key: _keys(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_keys(value) for value in node]
    return type(node).__name__


def test_english_schemas_have_no_cyrillic_at_all() -> None:
    for name, text in schemas.all_schemas("en").items():
        assert not CYR.search(text), (name, CYR.search(text).group(0))


def test_russian_schemas_keep_their_russian_descriptions() -> None:
    ru = schemas.all_schemas("ru")
    assert ru == schemas.all_schemas()  # без языка - как раньше
    for name in ("site.schema.json", "theme.schema.json", "frontmatter.schema.json"):
        assert CYR.search(ru[name]), name
    assert CYR.search(ru["errors.json"])


@pytest.mark.parametrize("name", schemas.FILES)
def test_languages_differ_only_in_descriptions_and_error_titles(name: str) -> None:
    ru = json.loads(schemas.all_schemas("ru")[name])
    en = json.loads(schemas.all_schemas("en")[name])
    assert _keys(ru) == _keys(en)  # те же ключи, порядок и типы
    assert ru["$id"] == en["$id"] and ru["x-heron-version"] == en["x-heron-version"]
    differs = {
        path.rsplit("/", 1)[-1]
        for (path, a), (_, b) in zip(_walk(ru), _walk(en), strict=True)
        if a != b
    }
    assert differs <= {"description", "title"}, differs
    assert differs  # язык различим


def test_every_russian_text_has_a_current_english_translation() -> None:
    """Таблица EN покрывает все русские тексты схем и не отстаёт от русского источника."""
    found: dict[str, str] = {}
    for name, text in schemas.all_schemas("ru").items():
        if name == "errors.json":
            continue
        for path, value in _walk(json.loads(text)):
            if CYR.search(value):
                found[f"{name}#{path}"] = value
    assert set(found) == set(schemas.EN), set(found) ^ set(schemas.EN)
    for key, value in found.items():
        digest, english = schemas.EN[key]
        assert hashlib.sha256(value.encode()).hexdigest()[:10] == digest, f"перевод устарел: {key}"
        assert english.strip() and not CYR.search(english), key


def test_english_error_titles_are_the_cli_titles() -> None:
    from heron.core.errors import ERRORS, SCHEMA_CODES
    from heron.messages import TITLES

    ru_titles = {**ERRORS, **SCHEMA_CODES}
    en = schemas.errors_registry("en")["errors"]
    assert set(en) == set(ru_titles)
    for code, entry in en.items():
        assert entry["title"] == TITLES["en"][code], code
        assert entry["title"] != ru_titles[code]


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_each_language_is_byte_deterministic(lang: str, tmp_path: Path) -> None:
    first = schemas.all_schemas(lang)
    assert first == schemas.all_schemas(lang)
    schemas.export(tmp_path / "a", lang)
    schemas.export(tmp_path / "b", lang)
    for name in schemas.FILES:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
        assert (tmp_path / "a" / name).read_text("utf-8") == first[name]
        assert first[name].endswith("}\n")


@pytest.mark.parametrize("name", schemas.FILES)
def test_english_schema_is_valid_and_checks_the_samples(name: str) -> None:
    data = json.loads(schemas.all_schemas("en")[name])
    Draft202012Validator.check_schema(data)
    samples = {
        "site.schema.json": "site.yaml",
        "theme.schema.json": "theme.yaml",
    }
    if name in samples:
        validator = Draft202012Validator(data)
        assert not list(validator.iter_errors(_sample(samples[name])))


def test_unknown_language_is_refused() -> None:
    with pytest.raises(ValueError):
        schemas.all_schemas("de")
    with pytest.raises(ValueError):
        schemas.errors_registry("de")


def _cli(*args: str, env: dict[str, str] | None = None):
    return CliRunner().invoke(main, list(args), env=env)


def test_cli_prints_the_chosen_language(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HERON_NOTES", raising=False)
    assert (
        _cli("schema", "--site", "--lang", "en").output
        == schemas.all_schemas("en")["site.schema.json"]
    )
    assert (
        _cli("schema", "--site", "--lang", "ru").output
        == schemas.all_schemas("ru")["site.schema.json"]
    )
    assert not CYR.search(_cli("schema", "--errors").output)  # без языка и конфига - en
    assert CYR.search(_cli("schema", "--errors", "--notes", "ru").output)
    assert CYR.search(_cli("schema", "--errors", env={"HERON_NOTES": "ru"}).output)
    # --lang сильнее --notes
    assert not CYR.search(_cli("schema", "--errors", "--notes", "ru", "--lang", "en").output)
    (tmp_path / "site.yaml").write_text("build:\n  notes: ru\n", encoding="utf-8")
    assert CYR.search(_cli("schema", "--errors").output)


def test_cli_rejects_an_unknown_schema_language() -> None:
    result = _cli("schema", "--lang", "de")
    assert result.exit_code == 2
    assert "de" in result.output


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_cli_export_writes_the_chosen_language(tmp_path: Path, lang: str) -> None:
    target = tmp_path / lang
    result = _cli("schema", "--export", str(target), "--lang", lang)
    assert result.exit_code == 0, result.output
    for name, text in schemas.all_schemas(lang).items():
        assert (target / name).read_text("utf-8") == text
    assert bool(CYR.search((target / "site.schema.json").read_text("utf-8"))) is (lang == "ru")


def test_cli_export_follows_notes_without_lang(tmp_path: Path) -> None:
    result = _cli("schema", "--export", str(tmp_path / "x"), "--notes", "ru")
    assert result.exit_code == 0, result.output
    assert CYR.search((tmp_path / "x" / "site.schema.json").read_text("utf-8"))
    result = _cli("schema", "--export", str(tmp_path / "y"))
    assert not CYR.search((tmp_path / "y" / "errors.json").read_text("utf-8"))


def test_ru_copy_next_to_the_english_one_keeps_the_same_ids(tmp_path: Path) -> None:
    """Как в CI сайта движка: en в schema/<версия>/, ru рядом в ru/ - $id один и тот же."""
    base = tmp_path / "schema" / "0.1"
    assert _cli("schema", "--export", str(base), "--lang", "en").exit_code == 0
    assert _cli("schema", "--export", str(base / "ru"), "--lang", "ru").exit_code == 0
    for name in schemas.FILES:
        en = json.loads((base / name).read_text("utf-8"))
        ru = json.loads((base / "ru" / name).read_text("utf-8"))
        assert en["$id"] == ru["$id"]
        assert (base / name).read_bytes() != (base / "ru" / name).read_bytes()


def test_site_image_workflow_publishes_english_main_and_russian_next_to_it() -> None:
    text = (ROOT / ".github" / "workflows" / "site-image.yml").read_text(encoding="utf-8")
    assert 'schema --export "/out/schema/$version" --lang en' in text
    assert 'schema --export "/out/schema/$version/ru" --lang ru' in text
    assert '"schema/$version/ru/site.schema.json"' in text  # и проверка, что файл лёг
    yaml.safe_load(text)  # файл остаётся корректным YAML


# --- E17.S2.T2: коды разметки SCH001-SCH006 в реестре ---------------------------


def test_errors_registry_lists_e_then_sch() -> None:
    from heron.core.errors import ERRORS, SCHEMA_CODES

    codes = list(schemas.errors_registry()["errors"])
    assert codes == [*ERRORS, *SCHEMA_CODES]


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_schema_codes_have_titles(lang: str) -> None:
    from heron.core.errors import SCHEMA_CODES

    errors = schemas.errors_registry(lang)["errors"]
    for code in SCHEMA_CODES:
        title = errors[code]["title"]
        assert title.strip() and title != code, (lang, code)
        assert bool(CYR.search(title)) == (lang == "ru"), (lang, code)


def test_schema_export_writes_sch_codes(tmp_path) -> None:
    import json

    schemas.export(tmp_path, "en")
    data = json.loads((tmp_path / "errors.json").read_text("utf-8"))
    assert data["errors"]["SCH002"] == {
        "title": "the property does not belong to this type",
        "hint": "",
    }
    assert "SCH006" in data["errors"]
