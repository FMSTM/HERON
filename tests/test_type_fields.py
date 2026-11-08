"""Свои поля фронтматтера у типа страницы (`types.<тип>.fields`, выпуск 0.3.0).

Контракт (имена движка заняты, без `md`, подсказки обязательны), `describe --json`,
модель правки (группа «Поля темы», без потерь, языки), `--dump`/`--answers`,
`heron check` (E042), стартовая тема (`eyebrow`) и справка темы.
"""

from __future__ import annotations

import shutil

import pytest
import yaml

from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.edit import entity as ops
from heron.edit import model
from heron.scaffold import create
from tests.test_studio_acceptance import LANGS, SERVICE, answers, check, codes, front, run


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=LANGS, notes="ru", demo=True)
    return root


@pytest.fixture
def service_site(site):
    """Тип service из guide/07 «Пример целиком» - копия шаблона page."""
    theme = site / "theme" / "theme.yaml"
    theme.write_text(theme.read_text("utf-8").replace("types:\n", "types:\n" + SERVICE, 1), "utf-8")
    templates = site / "theme" / "templates"
    shutil.copy(templates / "page.html", templates / "service.html")
    return site


# --- свои поля фронтматтера у типа страницы ------------------------------------------------


OWN = """    fields:
      - {name: status, type: enum, values: [open, closed], required: true,
         hint_ru: Статус, hint_en: Status}
      - {name: metrics, type: list, item: text, max_items: 3, hint_ru: Цифры, hint_en: Figures}
      - {name: rank, type: number, hint_ru: Место, hint_en: Rank}
"""


@pytest.fixture
def case_site(service_site):
    theme = service_site / "theme" / "theme.yaml"
    text = theme.read_text("utf-8").replace(
        "    jsonld: [Service]\n", "    jsonld: [Service]\n" + OWN
    )
    theme.write_text(text, "utf-8")
    run("category", "add", "services", service_site, "--children-type", "service", "-y")
    run("page", "add", "roofing", service_site, "--category", "services", "-y")
    return service_site


# начало списка своих полей типа page стартовой темы: свои поля теста - перед eyebrow
EYEBROW = "\n    fields:\n      - name: eyebrow"


@pytest.mark.parametrize("name", ["title", "slug", "order", "image", "translation", "view"])
def test_own_field_may_not_take_an_engine_name(site, name):
    theme = site / "theme" / "theme.yaml"
    own = f"\n    fields:\n      - {{name: {name}, type: text, hint_ru: x, hint_en: x}}"
    text = theme.read_text("utf-8").replace(EYEBROW, own + EYEBROW[len("\n    fields:") :], 1)
    theme.write_text(text, "utf-8")
    with pytest.raises(HeronError) as caught:
        check(site)
    assert caught.value.code == "E041"
    assert name in caught.value.message.text("ru")


def test_own_field_has_no_md_and_needs_hints(site):
    theme = site / "theme" / "theme.yaml"
    base = theme.read_text("utf-8")
    own = "\n    fields:\n      - {name: tag, type: text, md: body, hint_ru: x, hint_en: x}"
    theme.write_text(base.replace(EYEBROW, own + EYEBROW[len("\n    fields:") :], 1))
    with pytest.raises(HeronError) as caught:
        check(site)
    assert caught.value.code == "E041"
    own = "\n    fields:\n      - {name: tag, type: text, hint_ru: x}"
    theme.write_text(base.replace(EYEBROW, own + EYEBROW[len("\n    fields:") :], 1))
    result = check(site)
    found = codes(result)
    assert "E041" in found
    assert any(
        "types.page.fields.tag" in str(e.message.text("ru")) for e in result.collector.errors
    )


def _describe(root):
    from heron.core import describe

    theme, config = describe.load(root)
    return describe.contract(theme, config, "en")


def test_starter_theme_shows_an_own_field(site):
    data = _describe(site)
    page = next(t for t in data["types"] if t["name"] == "page")
    assert [f["name"] for f in page["fields"]] == ["eyebrow"]
    assert page["fields"][0]["hint"] and page["fields"][0]["md"] is None
    assert front(site / "content" / "ru" / "blocks.md")["eyebrow"]
    pipeline.run(site, dist=site / "dist")
    assert 'class="eyebrow"' in (site / "dist" / "blocks" / "index.html").read_text("utf-8")
    ref = (site / "dist" / "_heron" / "theme" / "index.html").read_text("utf-8")
    assert "eyebrow" in ref


def test_describe_json_with_own_fields_is_valid(case_site):
    import jsonschema

    from heron.contracts import schemas

    data = _describe(case_site)
    jsonschema.Draft202012Validator(schemas.describe_schema("en")).validate(data)
    service = next(t for t in data["types"] if t["name"] == "service")
    assert [f["name"] for f in service["fields"]] == ["status", "metrics", "rank"]


def test_own_fields_in_the_editor_group_values_and_languages(case_site, tmp_path):
    ctx = ops.context(case_site, "ru")
    entity = ops.open_entity(ctx, "services/roofing")
    own = [f for f in ops.fields_of(entity, "ru") if f.group == "theme"]
    assert [f.name for f in own] == ["status", "metrics", "rank"]
    assert {"name": "theme", "title": "Поля темы"} in model.groups(entity.main)
    assert [
        f.name for f in ops.fields_of(entity, "en", only_translatable=True) if f.group == "theme"
    ] == ["metrics"]
    bad = {"ru": {"status": "maybe"}}
    result = run("page", "add", "services/roofing", case_site, "--answers", answers(tmp_path, bad))
    assert result.exit_code != 0 and "status" in result.output
    good = {
        "ru": {"status": "open", "metrics": ["10 лет", "500 крыш"], "rank": "2"},
        "en": {"metrics": ["10 years"]},
    }
    result = run("page", "add", "services/roofing", case_site, "--answers", answers(tmp_path, good))
    assert result.exit_code == 0, result.output
    ru = front(case_site / "content/ru/services/roofing.md")
    en = front(case_site / "content/en/services/roofing.md")
    assert ru["status"] == "open" and ru["metrics"] == ["10 лет", "500 крыш"] and ru["rank"] == 2
    # enum и число - одни на все языки; список с текстом - свой у каждого
    assert en["status"] == "open" and en["rank"] == 2 and en["metrics"] == ["10 years"]
    dumped = yaml.safe_load(run("page", "add", "services/roofing", case_site, "--dump").output)
    assert dumped["ru"]["status"] == "open" and dumped["en"]["metrics"] == ["10 years"]


def test_own_field_is_checked_by_heron_check(case_site):
    path = case_site / "content/ru/services/roofing.md"
    path.write_text(path.read_text("utf-8").replace('\nstatus: "open"', "\n# status:", 1))
    result = check(case_site)
    found = codes(result)
    assert "E042" in found  # status обязателен
    path.write_text(path.read_text("utf-8").replace("\n---\n", "\nstatus: maybe\n---\n", 1))
    result = check(case_site)
    assert any(
        e.code == "E042" and "maybe" in e.message.text("ru") for e in result.collector.errors
    )


def test_own_field_edit_is_lossless(case_site):
    path = case_site / "content/ru/services/roofing.md"
    text = path.read_text("utf-8").replace(
        "\n---\n", "\nstatus: open   # статус\nmetrics: [a, 'b']\n# конец\n---\n", 1
    )
    page = model.load(
        text, ops.context(case_site, "ru").contract, rel="content/ru/services/roofing.md"
    )
    assert model.dump(page) == text
    edited = model.set_field(page, "metrics", ["a", "b", "c"])
    assert "metrics: [a, 'b', c]" in edited.text and "# статус" in edited.text
    assert "# конец" in edited.text


def test_console_shows_the_values_of_an_own_enum_and_takes_a_number(case_site):
    from heron.edit import console
    from tests.test_studio_acceptance import Script

    ctx = ops.context(case_site, "ru")
    entity = ops.open_entity(ctx, "services/roofing")
    item = next(f for f in ops.fields_of(entity, "ru") if f.path == "status")
    script = Script(["2"])
    assert console.Console(entity, script.io(), "ru").field("ru", item)
    assert "    1  open" in script.out and "    2  closed" in script.out
    assert entity.main.front.data["status"] == "closed"
