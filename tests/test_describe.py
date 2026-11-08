"""`heron describe`: контракт темы и служебные поля наружу (STUDIO ST2).

Спецификация: docs/ru/spec/21-engine.md, §10 «heron describe».
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from jsonschema import Draft202012Validator

import heron
from heron.cli import main
from heron.contracts import fields as service
from heron.contracts import schemas
from heron.core import describe
from heron.core.errors import HeronError
from heron.scaffold import create

CYRILLIC = re.compile(r"[А-Яа-яЁё]")


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="demo", languages=["ru", "en"], notes="en")
    return root


def _run(*args: str):
    return CliRunner().invoke(main, list(args))


def _validator(lang: str = "ru") -> Draft202012Validator:
    return Draft202012Validator(schemas.describe_schema(lang))


def _contract(root: Path, lang: str = "en", name: str | None = None) -> dict:
    theme, config = describe.load(root)
    return describe.contract(theme, config, lang, name)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_describe_json_is_valid_by_the_published_schema(site, lang):
    data = _contract(site, lang)
    errors = [f"{list(e.path)}: {e.message}" for e in _validator(lang).iter_errors(data)]
    assert not errors, errors[:5]
    assert data["$schema"].endswith("/describe.schema.json")
    assert data["heron"] == heron.__version__ and data["lang"] == lang


def test_describe_json_from_the_cli(site, monkeypatch):
    monkeypatch.chdir(site)
    out = _run("describe", "--json", "--lang", "en")
    assert out.exit_code == 0, out.output
    assert json.loads(out.output) == _contract(site, "en")
    result = _run("describe", "faq", str(site), "--json", "--lang", "en")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["selected"] == {"kind": "module", "name": "faq"}
    assert [m["name"] for m in data["modules"]] == ["faq"] and data["types"] == []
    assert not list(_validator().iter_errors(data))


def test_describe_outside_a_site_says_so(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = _run("describe", "--notes", "en")
    assert out.exit_code == 1 and "site.yaml" in out.output


def test_contract_carries_types_sections_fields_views_and_defaults(site):
    data = _contract(site, "en")
    types = {t["name"]: t for t in data["types"]}
    assert list(types) == ["home", "page", "404"]
    page = types["page"]
    assert [s["id"] for s in page["sections"]] == ["intro", "*"]
    assert page["sections"][0]["required"] and page["sections"][1]["any"]
    assert page["children_type"] == "page"
    assert page["views"]["key"] == "view" and page["views"]["default"] == "cards"
    assert [v["name"] for v in page["views"]["options"]] == ["cards", "list"]
    assert page["hint"].startswith("An ordinary page")
    modules = {m["name"]: m for m in data["modules"]}
    faq = modules["faq"]
    assert faq["kinds"] == [{"kind": "faq", "class": "faq", "auto": True}]
    q = faq["fields"][0]["fields"][0]
    assert q["name"] == "q" and q["md"] == "heading" and q["schemaorg"] == "Question.name"
    assert modules["gallery"]["kinds"] == [{"kind": "gallery", "class": "gallery", "auto": False}]
    assert modules["breadcrumbs"]["scope"] == "page"
    # служебные поля - словарь движка, значения по умолчанию - из site.yaml
    page_fields = {f["name"]: f for f in data["service"]["page"]}
    assert [f["name"] for f in data["service"]["page"]] == [
        s.name for s in service.of_scope("page")
    ]
    assert page_fields["title"]["required"] and page_fields["title"]["max_length"] == 60
    assert page_fields["og_image"]["default"] == data["site"]["og_default_image"]
    assert page_fields["image"]["min_width"] == 1200
    assert page_fields["type"]["values"] == ["home", "page", "404"]
    assert page_fields["menu"]["where"] == "site.yaml" and page_fields["menu"]["key"] == "nav.main"
    assert data["site"]["languages"] == ["ru", "en"] and data["site"]["default_lang"] == "ru"
    assert [g["name"] for g in data["groups"]] == list(service.GROUPS)
    assert {s["name"] for s in data["service"]["section"]} == {"heading", "anchor"}


def test_hints_follow_the_language(site):
    ru = _contract(site, "ru")
    en = _contract(site, "en")
    assert CYRILLIC.search(ru["types"][1]["hint"]) and not CYRILLIC.search(en["types"][1]["hint"])
    for item in en["service"]["page"] + en["md_places"]:
        assert not CYRILLIC.search(item["hint"]), item["name"]
    # языка нет у темы - английский текст, у служебных полей - тоже
    de = _contract(site, "de")
    assert de["types"][1]["hint"] == en["types"][1]["hint"]
    assert de["service"]["page"][0]["hint"] == en["service"]["page"][0]["hint"]


def test_type_filter_keeps_the_modules_its_page_needs(site):
    data = _contract(site, "en", "page")
    assert data["selected"] == {"kind": "type", "name": "page"}
    assert [t["name"] for t in data["types"]] == ["page"]
    assert len(data["modules"]) == 13  # "*" - любой блок
    theme, config = describe.load(site)
    theme.types["page"].uses = ["intro", "how:steps"]
    names = [m["name"] for m in describe.contract(theme, config, "en", "page")["modules"]]
    assert names == ["steps", "breadcrumbs", "children"]


def test_unknown_name_is_e041_with_the_known_names(site):
    with pytest.raises(HeronError) as caught:
        _contract(site, "en", "nope")
    assert caught.value.code == "E041"
    text = caught.value.message.text("en")
    assert "home, page, 404" in text and "faq" in text
    result = _run("describe", "nope", str(site), "--notes", "en")
    assert result.exit_code == 1 and "E041" in result.output


def test_human_text_is_short_without_a_name_and_full_with_one(site):
    out = CliRunner().invoke(main, ["--notes", "en", "describe", "faq", str(site), "--lang", "en"])
    assert out.exit_code == 0, out.output
    assert "Questions and answers" in out.output
    assert "### Is this a real page?" in out.output  # образец markdown
    assert "schema.org Question.name" in out.output


def test_human_text_of_the_whole_theme(site, monkeypatch):
    monkeypatch.chdir(site)
    out = _run("describe", "--notes", "en")
    assert out.exit_code == 0, out.output
    text = out.output
    for part in ("Service fields", "title*", "Page types", "Blocks", "view", "heron describe"):
        assert part in text, part
    assert "if left empty: media/cover.png" in text
    ru = _run("describe", "--notes", "ru")
    assert "Служебные поля" in ru.output and "если не заполнить" in ru.output


def test_bad_lang_is_a_usage_error(site, monkeypatch):
    monkeypatch.chdir(site)
    out = _run("describe", "--lang", "Russian")
    assert out.exit_code == 2


def test_old_theme_is_described_without_fields(site):
    path = site / "theme" / "theme.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["modules"] = list(data["modules"])
    data["types"] = {name: {"uses": spec["uses"]} for name, spec in data["types"].items()}
    data.pop("languages")
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    contract = _contract(site, "en")
    assert not contract["theme"]["described"]
    assert all(module["fields"] is None for module in contract["modules"])
    assert contract["service"]["page"]  # служебные поля есть всегда
    assert not list(_validator().iter_errors(contract))
    out = CliRunner().invoke(main, ["--notes", "en", "describe", "list", str(site)])
    assert "has not described the fields" in out.output


def test_describe_schema_is_published_with_the_others(tmp_path):
    assert "describe.schema.json" in schemas.FILES
    out = _run("schema", "--describe", "--lang", "en")
    assert out.exit_code == 0
    assert json.loads(out.output)["$id"].endswith("/describe.schema.json")
    assert out.output == schemas.all_schemas("en")["describe.schema.json"]
    _run("schema", "--export", str(tmp_path / "x"))
    assert (tmp_path / "x" / "describe.schema.json").is_file()


def test_schema_rejects_a_broken_object(site):
    data = _contract(site, "en")
    validator = _validator("en")
    broken = json.loads(json.dumps(data))
    broken["modules"][0]["fields"][0]["md"] = "nowhere"
    assert not validator.is_valid(broken)
    broken = json.loads(json.dumps(data))
    del broken["service"]
    assert not validator.is_valid(broken)


def test_hints_in_a_container_are_full_docker_commands(site, monkeypatch):
    monkeypatch.chdir(site)
    out = CliRunner().invoke(main, ["describe", "--notes", "en"], env={"HERON_IN_CONTAINER": "1"})
    assert out.exit_code == 0, out.output
    assert "ghcr.io/fmstm/heron:prod describe --json" in out.output
    assert out.output.endswith("\n") and not out.output.endswith("\n\n")
