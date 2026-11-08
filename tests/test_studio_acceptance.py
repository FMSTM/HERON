"""Приёмка выпуска 0.3.0 STUDIO: каждая находка независимого ревью - своим тестом.

Блокеры 1-3, баги 4-10, решения владельца A, C, D, E, расхождения документации
и движка, свои поля фронтматтера у типа страницы. Блокеры 1 и 9 (YAML SEO-блока) -
tests/test_edit_front_yaml.py, блокер 2 и баг 10 (студия) - tests/test_studio.py и
tests/test_studio_e2e.py.
"""

from __future__ import annotations

import json
import shutil

import pytest
import yaml
from click.testing import CliRunner

from heron import studio
from heron.cli import main
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.core.errors import HeronError
from heron.edit import console, model
from heron.edit import entity as ops
from heron.scaffold import create

LANGS = ["ru", "en", "de"]

SERVICE = """  service:
    uses: [intro, "includes:list", "how:steps", "faq:faq"]
    jsonld: [Service]
    hint_ru: Услуга
    hint_en: A service
    sections:
      intro:
        required: true
        hint_ru: Вводный абзац
        hint_en: The intro paragraph
        fields:
          - {name: text, type: markdown, required: true, md: body, hint_ru: Абзац, hint_en: Text}
      includes:
        required: true
        hint_ru: Что входит
        hint_en: What is included
      how: {hint_ru: Как проходит работа, hint_en: How the work goes}
      faq: {hint_ru: Вопросы, hint_en: Questions}
"""


def run(*args, input=None):
    return CliRunner().invoke(main, [str(a) for a in args], input=input)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=LANGS, notes="ru", demo=True)
    return root


@pytest.fixture
def service_site(site):
    """Копия стартовой темы с типом service из guide/07 «Пример целиком»."""
    theme = site / "theme" / "theme.yaml"
    theme.write_text(theme.read_text("utf-8").replace("types:\n", "types:\n" + SERVICE, 1), "utf-8")
    templates = site / "theme" / "templates"
    shutil.copy(templates / "page.html", templates / "service.html")
    return site


def front(path):
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def answers(tmp_path, data, name="a.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def check(site, env="dev", **kw):
    return pipeline.check(site, env=BuildEnv.resolve(env), notes_lang="ru", **kw)


def codes(result):
    return [e.code for e in result.collector.errors]


class Script:
    def __init__(self, items):
        self.items = list(items)
        self.out = []

    def io(self):
        def ask(prompt):
            self.out.append(prompt)
            return self.items.pop(0) if self.items else ""

        def echo(text="", color=None, dim=False, bold=False):
            self.out.append(text)

        return console.Io(ask, echo)


# --- блокер 3: секции новой страницы - в форме темы, с образцом модуля --------------------


def test_new_service_page_with_enter_everywhere_builds(service_site):
    made = run("category", "add", "services", service_site, "--children-type", "service", "-y")
    assert made.exit_code == 0, made.output
    added = run("page", "add", "roofing", service_site, "--category", "services", "-y")
    assert added.exit_code == 0, added.output
    text = (service_site / "content" / "ru" / "services" / "roofing.md").read_text("utf-8")
    assert "{#includes}\n\n- **" in text  # список с жирным зачином - образец модуля list
    assert "{#how}\n\n1. " in text  # нумерованные шаги
    assert "{#faq}\n\n### " in text  # вопросы группами ###
    assert "TODO содержимое." not in text
    result = check(service_site)
    found = codes(result)
    assert "E010" not in found and not result.collector.errors, found


def test_console_asks_a_list_one_item_per_line(service_site):
    run("category", "add", "services", service_site, "--children-type", "service", "-y")
    ctx = ops.context(service_site, "ru")
    entity = ops.open_entity(ctx, "services/roofing")
    item = next(f for f in ops.fields_of(entity, "ru") if f.path == "sections.includes.items")
    script = Script(["+", "Кровля", "Снять старое покрытие", "Замер", "Бесплатно", ""])
    assert console.Console(entity, script.io(), "ru").field("ru", item)
    value = model.get(entity.main, "sections.includes.items")
    assert [entry["term"] for entry in value] == ["Кровля", "Замер"]
    plain = next(f for f in ops.fields_of(entity, "ru") if f.path == "sections.how.items")
    assert plain.fields  # шаги тоже с полями: каждый пункт спрашивается по полям
    redirects = next(f for f in ops.fields_of(entity, "ru") if f.path == "redirect_from")
    script = Script(["/old/", "/older/", ""])
    assert console.Console(entity, script.io(), "ru").field("ru", redirects)
    assert entity.main.front.data["redirect_from"] == ["/old/", "/older/"]


# --- баг 4: перенос обратно в прежнюю категорию ----------------------------------------------


def test_moving_back_drops_the_new_address_from_redirect_from(site, tmp_path):
    there = run("page", "add", "blocks", site, "--answers", answers(tmp_path, {"key": "a/blocks"}))
    assert there.exit_code == 0, there.output
    back = run("page", "add", "a/blocks", site, "--answers", answers(tmp_path, {"key": "blocks"}))
    assert back.exit_code == 0, back.output
    for lang in LANGS:
        listed = front(site / "content" / lang / "blocks.md").get("redirect_from") or []
        own = "/blocks/" if lang == "ru" else f"/{lang}/blocks/"
        assert own not in listed, (lang, listed)
    result = check(site)
    found = codes(result)
    assert "E009" not in found, result.collector.errors


# --- баг 5: `key` в ответах главнее выгрузки ---------------------------------------------------


def test_key_beats_the_dumped_category(site, tmp_path):
    run("category", "add", "services", site, "-y")
    run("category", "add", "guides", site, "-y")
    dumped = yaml.safe_load(run("category", "add", "services", site, "--dump").output)
    dumped["key"] = "guides/services"
    result = run("category", "add", "services", site, "--answers", answers(tmp_path, dumped))
    assert result.exit_code == 0, result.output
    assert (site / "content" / "ru" / "guides" / "services" / "_index.md").is_file()

    run("page", "add", "roof", site, "--category", "guides", "-y")
    dumped = yaml.safe_load(run("page", "add", "guides/roof", site, "--dump").output)
    assert dumped["ru"]["category"] == "guides"
    dumped["key"] = "roof"
    result = run("page", "add", "guides/roof", site, "--answers", answers(tmp_path, dumped))
    assert result.exit_code == 0, result.output
    assert (site / "content" / "ru" / "roof.md").is_file()
    assert not (site / "content" / "ru" / "guides" / "roof.md").exists()


def test_dump_and_answers_round_trip_is_a_no_op(site, tmp_path):
    before = {p: p.read_bytes() for p in (site / "content").rglob("*.md")}
    dumped = run("page", "add", "blocks", site, "--dump").output
    path = tmp_path / "d.yaml"
    path.write_text(dumped, encoding="utf-8")
    result = run("page", "add", "blocks", site, "--answers", path)
    assert result.exit_code == 0, result.output
    assert {p: p.read_bytes() for p in (site / "content").rglob("*.md")} == before


# --- баг 6: картинка - те же правила, что у check ---------------------------------------------


@pytest.mark.parametrize("src", ["media/nope.png", "../../../etc/passwd", "content/ru/docs.md"])
def test_bad_image_blocks_the_save(site, tmp_path, src):
    data = {"ru": {"image": src, "image_alt": "Картинка"}}
    result = run("page", "add", "blocks", site, "--answers", answers(tmp_path, data))
    assert result.exit_code != 0, result.output
    assert "E039" in result.output and ("E007" in result.output or "E024" in result.output)
    assert front(site / "content" / "ru" / "blocks.md").get("image") is None


# --- баг 7: якорь - на всех языках, расхождение видит check ------------------------------------


def test_anchor_changes_on_every_language(site, tmp_path):
    page = model.load(
        (site / "content" / "ru" / "blocks.md").read_text("utf-8"),
        ops.context(site, "ru").contract,
        rel="content/ru/blocks.md",
    )
    anchor = next(s.id for s in page.body.sections if s.id != "intro")
    data = {"ru": {f"sections.{anchor}.anchor": "launch"}}
    result = run("page", "add", "blocks", site, "--answers", answers(tmp_path, data))
    assert result.exit_code == 0, result.output
    for lang in LANGS:
        text = (site / "content" / lang / "blocks.md").read_text("utf-8")
        assert "{#launch" in text and f"{{#{anchor}" not in text.replace("{#launch", ""), lang


def test_check_warns_about_anchors_that_differ(site):
    path = site / "content" / "en" / "docs.md"
    text = path.read_text("utf-8")
    first = text.index("{#") + 2
    end = min(text.index("}", first), *(i for i in (text.find(" ", first),) if i > 0))
    path.write_text(text[:first] + "renamed-by-hand" + text[end:], "utf-8")
    result = check(site)
    lines = [w.message.text("ru") for w in result.collector.warnings if w.path == "en/docs.md"]
    assert any("якоря секций" in line for line in lines), lines


# --- баг 8: slug - с 301 со старых адресов -----------------------------------------------------


def test_page_slug_change_leaves_a_redirect(site, tmp_path):
    data = {"en": {"slug": "all-blocks"}}
    result = run("page", "add", "blocks", site, "--answers", answers(tmp_path, data))
    assert result.exit_code == 0, result.output
    assert "/en/blocks/" in front(site / "content" / "en" / "blocks.md")["redirect_from"]
    assert not front(site / "content" / "ru" / "blocks.md").get("redirect_from")


def test_category_slug_change_redirects_every_page_inside(site, tmp_path):
    data = {"ru": {"slug": "struktura"}}
    result = run("category", "add", "structure", site, "--answers", answers(tmp_path, data))
    assert result.exit_code == 0, result.output
    assert "/structure/" in front(site / "content/ru/structure/_index.md")["redirect_from"]
    inside = front(site / "content/ru/structure/categories.md")["redirect_from"]
    assert "/structure/categories/" in inside
    found = codes(check(site))
    assert not found


# --- решение A: текст заготовки в бою - ошибка E040 --------------------------------------------


def test_placeholders_are_an_error_in_production_and_a_warning_in_dev(site):
    run("page", "add", "draft-page", site, "-y")
    dev = check(site)
    found = codes(dev)
    assert "E040" not in found
    assert any("заготовки" in w.message.text("ru") for w in dev.collector.warnings)
    prod = check(site, env="prod")
    errors = [e for e in prod.collector.errors if e.code == "E040"]
    assert errors and errors[0].path == "ru/draft-page.md"
    assert any("description" in e.message.text("ru") for e in errors)


def test_stub_text_of_another_notes_language_is_caught(site):
    path = site / "content" / "en" / "docs.md"
    text = path.read_text("utf-8")
    path.write_text(text + "\nIntro paragraph - what goes into the search snippet.\n", "utf-8")
    assert any(e.path == "en/docs.md" for e in check(site, env="prod").collector.errors)


# --- решение C: новый блок снимает переводы с публикации - спросить ------------------------


def test_console_asks_before_a_new_block_unpublishes_translations(site):
    ctx = ops.context(site, "ru")
    entity = ops.open_entity(ctx, "docs")
    # de - копия демо без своего текста, уже с пометкой: с публикации уходит только en
    assert ops.unpublishes(entity, "sections.extra-block.heading") == ["en"]
    item = model.Field(
        path="sections.extra-block.heading", name="heading", type="text", group="section", value=""
    )
    script = Script(["Новый блок", "n"])
    assert not console.Console(entity, script.io(), "ru").field("ru", item)
    assert any("en:" in line or " en " in line for line in script.out)
    assert not ops.is_pending(entity, "en")
    script = Script(["Новый блок", "y"])
    assert console.Console(entity, script.io(), "ru").field("ru", item)
    assert ops.is_pending(entity, "en") and ops.is_pending(entity, "de")


def test_studio_save_asks_before_unpublishing_translations(site):
    request = {
        "target": {"kind": "page", "key": "docs"},
        "ops": [{"op": "add_section", "anchor": "extra", "kind": "prose", "heading": "Ещё"}],
    }
    before = (site / "content" / "en" / "docs.md").read_bytes()
    out = studio.save(site, request, "ru")
    assert out["confirm"]["langs"] == ["en"]
    assert out["confirm"]["message"].startswith("en ")
    assert (site / "content" / "en" / "docs.md").read_bytes() == before
    out = studio.save(site, {**request, "confirm_pending": True}, "ru")
    assert "content/en/docs.md" in out["saved"]["pending"]


# --- решение D: страницы внутри непереведённой категории --------------------------------------


def test_translated_pages_inside_a_pending_category_stay_out_of_production(site):
    index = site / "content" / "de" / "structure" / "_index.md"
    text = index.read_text("utf-8")
    if "\ntranslation: pending" not in text:
        index.write_text(text.replace("\n---\n", "\ntranslation: pending\n---\n", 1), "utf-8")
    inner = site / "content" / "de" / "structure" / "categories.md"
    inner.write_text(inner.read_text("utf-8").replace("\ntranslation: pending", ""), "utf-8")
    prod = check(site, env="prod")
    urls = {p.url for p in prod.site.pages}
    assert "/de/structure/categories/" not in urls
    held = {p.source: p.held_by for p in prod.site.held}
    assert held.get("de/structure/categories.md") == "structure"
    data = json.loads(run("check", site, "--json", "--env", "prod").output)
    assert {"lang": "de", "path": "de/structure/categories.md", "published": False} in data[
        "pending"
    ]


# --- решение E: демо для языка без своего текста ------------------------------------------------


def test_demo_copied_for_a_language_without_its_own_text_is_pending(site):
    for path in (site / "content" / "de").rglob("*.md"):
        assert front(path).get("translation") == "pending", path
    for lang in ("ru", "en"):
        for path in (site / "content" / lang).rglob("*.md"):
            assert front(path).get("translation") is None, path


def test_demo_of_the_main_language_is_never_pending(tmp_path):
    root = tmp_path / "d"
    create(root, name="Demo", languages=["de", "en"], notes="en", demo=True)
    for path in (root / "content" / "de").rglob("*.md"):
        assert front(path).get("translation") is None


# --- документация и движок ----------------------------------------------------------------------


def test_required_field_of_a_block_blocks_the_save(site, tmp_path):
    data = {"ru": {"sections.intro.text": ""}}
    before = (site / "content" / "ru" / "docs.md").read_bytes()
    result = run("page", "add", "docs", site, "--answers", answers(tmp_path, data))
    assert result.exit_code != 0 and "sections.intro.text" in result.output
    assert (site / "content" / "ru" / "docs.md").read_bytes() == before


def test_wrong_shaped_top_level_fields_is_e023(site):
    theme = site / "theme" / "theme.yaml"
    theme.write_text(theme.read_text("utf-8") + "\nfields:\n  - {name: x, type: text}\n", "utf-8")
    with pytest.raises(HeronError) as caught:
        check(site)
    assert caught.value.code == "E023"
    assert "valid string" not in caught.value.message.text("en")


def test_theme_contract_errors_are_e041_and_e008_is_only_templates(site):
    theme = site / "theme" / "theme.yaml"
    theme.write_text(theme.read_text("utf-8").replace("hint_en:", "hint_xx:", 1), "utf-8")
    result = check(site)
    found = codes(result)
    assert "E041" in found and "E008" not in found
    from heron.messages import title

    assert "theme.yaml" in title("ru", "E012") and "theme.yaml" in title("en", "E012")
    assert "шаблон" in title("ru", "E008")


def test_check_theme_with_only_demo_gaps_does_not_say_the_build_fails(site):
    theme = site / "theme" / "theme.yaml"
    text = theme.read_text("utf-8").replace("types:\n", "types:\n" + SERVICE, 1)
    theme.write_text(text, "utf-8")
    shutil.copy(site / "theme/templates/page.html", site / "theme/templates/service.html")
    result = run("check", site, "--theme")
    assert result.exit_code == 1 and "E037" in result.output
    assert "Сборка с ними не пройдёт" not in result.output


def test_category_add_root_explains_itself(site):
    result = run("category", "add", "/", site, "-y")
    assert result.exit_code != 0
    assert "category add /" not in result.output.replace("category add services", "")
    assert "главная" in result.output or "home page" in result.output


def test_moving_a_page_keeps_the_flow_style_of_the_menu(site, tmp_path):
    before = (site / "site.yaml").read_text("utf-8")
    line = next(x for x in before.splitlines() if x.strip().startswith("main: ["))
    result = run("page", "add", "docs", site, "--answers", answers(tmp_path, {"key": "g/docs"}))
    assert result.exit_code == 0, result.output
    after = (site / "site.yaml").read_text("utf-8")
    assert line.replace("docs", "g/docs") in after
    assert len(after.splitlines()) == len(before.splitlines())
