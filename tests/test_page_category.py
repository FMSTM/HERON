"""`heron page add`, `page list`, `category add`: есть - правка, нет - создание на всех языках.

ST4, ST5, опросник ST6 (консоль, --answers, --dump) и пометка перевода ST7 -
сценарий новичка от `new` до боевой сборки и каждое правило по отдельности.
"""

from __future__ import annotations

import json
import re

import pytest
import yaml
from click.testing import CliRunner

from heron import cli
from heron.cli import main
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.edit import console
from heron.edit import entity as ops
from heron.scaffold import create

LANGS = ["ru", "en", "de"]


def _yaml(path, data):
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def run(*args, input=None):
    return CliRunner().invoke(main, [str(a) for a in args], input=input)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=LANGS, notes="ru", demo=True)
    translated(root / "content" / "de")
    return root


def translated(folder):
    """Демо de - копия английского с пометкой; здесь считаем его переведённым (без пометки)."""
    for path in folder.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"(?m)^translation: pending  (#.*)$", r"# translation:               \1", text
        )
        path.write_text(text, encoding="utf-8")


def files(root, key, category=False):
    tail = f"{key}/_index.md" if category else f"{key}.md"
    return [root / "content" / lang / tail for lang in LANGS]


def front(path):
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


ANSWERS = {
    "ru": {
        "title": "Об агентстве - кто мы и как работаем",
        "h1": "Об агентстве",
        "description": "Кто мы, как работаем и почему нам доверяют крыши.",
        "menu": True,
        "nav_title": "Агентство",
        "sections.intro.text": "Мы чиним крыши с 2005 года.",
    },
    "en": {
        "title": "About the agency - who we are and how we work",
        "h1": "About the agency",
        "description": "Who we are, how we work and why roofs trust us.",
        "nav_title": "Agency",
        "sections.intro.text": "We fix roofs since 2005.",
    },
    "de": "pending",
}


# --- сценарий новичка ---------------------------------------------------------------


SERVICES = {
    "ru": {
        "title": "Услуги агентства - ремонт и осмотр крыш",
        "h1": "Услуги",
        "description": "Что мы делаем: ремонт, осмотр и обслуживание крыш.",
        "sections.intro.text": "Всё, что мы делаем для крыш.",
    },
    "en": {
        "title": "Agency services - roof repair and inspection",
        "h1": "Services",
        "description": "What we do: roof repair, inspection and upkeep.",
        "sections.intro.text": "Everything we do for roofs.",
    },
    "de": "pending",
}


def test_newcomer_scenario_from_new_to_production(site, tmp_path):
    # категория с текстом: заготовка (TODO) в боевую сборку не пройдёт (E040)
    made = run(
        "category",
        "add",
        "services",
        site,
        "--answers",
        _yaml(tmp_path / "services.yaml", SERVICES),
    )
    assert made.exit_code == 0, made.output
    for path in files(site, "services", category=True):
        assert path.is_file()
    answers = tmp_path / "about.yaml"
    answers.write_text(yaml.safe_dump(ANSWERS, allow_unicode=True), encoding="utf-8")
    result = run(
        "page", "add", "about-agency", "--category", "services", site, "--answers", answers
    )
    assert result.exit_code == 0, result.output
    ru, en, de = files(site, "services/about-agency")
    assert front(ru)["h1"] == "Об агентстве" and "translation" not in front(ru)
    assert front(en)["h1"] == "About the agency" and "translation" not in front(en)
    assert front(de)["translation"] == "pending"
    assert front(de)["h1"] == "Об агентстве"  # текст основного языка до перевода
    assert (
        "services/about-agency" in yaml.safe_load((site / "site.yaml").read_text())["nav"]["main"]
    )

    # боевая сборка: de-версии нет нигде, отчёт её называет
    prod = pipeline.run(site, dist=tmp_path / "prod", env=BuildEnv.named("prod"))
    assert not prod.collector.errors, prod.collector.errors
    assert not (tmp_path / "prod" / "de" / "services" / "about-agency").exists()
    assert (tmp_path / "prod" / "en" / "services" / "about-agency" / "index.html").is_file()
    sitemaps = "".join(p.read_text() for p in (tmp_path / "prod").glob("sitemap*.xml"))
    assert "/de/services/about-agency/" not in sitemaps
    ru_html = (tmp_path / "prod" / "services" / "about-agency" / "index.html").read_text()
    assert 'hreflang="en"' in ru_html and 'hreflang="de"' not in ru_html
    de_home = (tmp_path / "prod" / "de" / "index.html").read_text()
    assert "/de/services/about-agency/" not in de_home  # и не в меню de
    assert ("de", "de/services/about-agency.md", False) in prod.report.pending
    text = prod.report.render("ru")
    assert "Перевод не готов" in text and "de/services/about-agency.md (не опубликована)" in text
    strict = pipeline.run(site, dist=tmp_path / "strict", env=BuildEnv.named("prod"), strict=True)
    assert any("translation: pending" in str(w.message) for w in strict.collector.warnings)

    # черновая сборка: страница есть, с плашкой
    dev = pipeline.run(site, dist=tmp_path / "dev", env=BuildEnv.named("dev"))
    page = (tmp_path / "dev" / "de" / "services" / "about-agency" / "index.html").read_text()
    assert re.search(r"<body[^>]*><div class=\"heron-pending\"", page)
    assert "content/de/services/about-agency.md" in page
    other = (tmp_path / "dev" / "services" / "about-agency" / "index.html").read_text()
    assert "heron-pending" not in other
    assert ("de", "de/services/about-agency.md", True) in dev.report.pending

    # второй page add открывает правку и ничего не создаёт
    before = {p: p.read_bytes() for p in (site / "content").rglob("*.md")}
    again = run("page", "add", "about-agency", site)
    assert again.exit_code == 0, again.output
    assert "уже есть" in again.output and "services/about-agency" in again.output
    assert {p: p.read_bytes() for p in (site / "content").rglob("*.md")} == before

    # перевели - пометку сняли - страница появляется в боевой сборке
    done = tmp_path / "de.yaml"
    done.write_text(
        yaml.safe_dump({"de": {"h1": "Über die Agentur", "translation": None}}), encoding="utf-8"
    )
    assert run("page", "add", "services/about-agency", site, "--answers", done).exit_code == 0
    assert "translation" not in front(de)
    # категория de ещё не переведена: страница внутри не выходит вместе с ней (решение D)
    pipeline.run(site, dist=tmp_path / "prod2", env=BuildEnv.named("prod"))
    assert not (tmp_path / "prod2" / "de" / "services" / "about-agency").exists()
    category = {
        "de": {
            "title": "Leistungen der Agentur - Dachreparatur",
            "h1": "Leistungen",
            "description": "Was wir tun: Dachreparatur, Inspektion und Pflege.",
            "sections.intro.text": "Alles, was wir für Dächer tun.",
            "translation": None,
        }
    }
    made = run(
        "category", "add", "services", site, "--answers", _yaml(tmp_path / "c.yaml", category)
    )
    assert made.exit_code == 0, made.output
    pipeline.run(site, dist=tmp_path / "prod3", env=BuildEnv.named("prod"))
    assert (tmp_path / "prod3" / "de" / "services" / "about-agency" / "index.html").is_file()


# --- page add ---------------------------------------------------------------------------


def test_page_add_creates_every_language_and_marks_the_others(site):
    result = run("page", "add", "about-agency", site)
    assert result.exit_code == 0, result.output
    ru, en, de = files(site, "about-agency")
    assert all(p.is_file() for p in (ru, en, de))
    assert "translation" not in front(ru)
    assert front(en)["translation"] == front(de)["translation"] == "pending"
    assert "content/de/about-agency.md - перевод не готов" in result.output
    # заготовка: полный SEO-блок и пометка в своей группе, комментарий на месте
    text = de.read_text(encoding="utf-8")
    assert "# ================= 7. СЛУЖЕБНОЕ" in text
    assert re.search(r"\ntranslation: pending +# pending - ", text)


def test_second_page_add_edits_and_changes_nothing(site):
    assert run("page", "add", "about", site).exit_code == 0
    before = [p.read_bytes() for p in files(site, "about")]
    again = run("page", "add", "about", site)
    assert again.exit_code == 0
    assert "уже есть" in again.output
    assert [p.read_bytes() for p in files(site, "about")] == before


def test_old_form_gives_a_coded_error_with_the_new_command(site):
    result = run("page", "page", "about", site)
    assert result.exit_code == 1
    assert "E038" in result.output
    assert f"`heron page add about {site}`" in result.output
    other = run("page", "service", "roof", site, "--folder", "services", "--lang", "ru")
    assert f"`heron page add roof --type service --category services {site}`" in other.output
    assert not (site / "content" / "ru" / "about.md").exists()


def test_old_form_in_a_container_is_a_ready_docker_command(site, monkeypatch):
    monkeypatch.setattr(cli, "in_container", lambda: True)
    result = run("page", "page", "about", site)
    assert "E038" in result.output
    assert re.search(
        r"docker run --rm -it .* ghcr\.io/fmstm/heron:\S+ page add about ", result.output
    )
    assert "`heron" not in result.output


def test_page_add_finds_the_page_by_name_in_its_category(site):
    assert run("page", "add", "roof", "--category", "services", site).exit_code == 0
    again = run("page", "add", "roof", site)
    assert "services/roof" in again.output
    assert not (site / "content" / "ru" / "roof.md").exists()


def test_page_add_type_and_unknown_type(site):
    bad = run("page", "add", "x", "--type", "nosuch", site)
    assert bad.exit_code == 1 and "E041" in bad.output
    assert not (site / "content" / "ru" / "x.md").exists()


def test_page_and_category_with_one_key_are_refused(site):
    assert run("category", "add", "services", site, "-y").exit_code == 0
    clash = run("page", "add", "services", site)
    assert clash.exit_code == 1 and "E004" in clash.output
    assert "`heron category add services`" in clash.output


def test_lang_flag_limits_editing_to_one_language(site, tmp_path):
    assert run("page", "add", "about", site).exit_code == 0
    answers = tmp_path / "a.yaml"
    answers.write_text(yaml.safe_dump({"en": {"h1": "About us"}}), encoding="utf-8")
    result = run("page", "add", "about", site, "--lang", "en", "--answers", answers)
    assert result.exit_code == 0, result.output
    assert front(files(site, "about")[1])["h1"] == "About us"
    bad = run("page", "add", "about", site, "--lang", "fr")
    assert bad.exit_code == 1 and "E005" in bad.output


def test_web_flag_opens_the_studio_on_the_page_and_writes_nothing(site, monkeypatch):
    from heron.setup import server

    seen = {}

    def fake(root, host, port, on_ready=None, start=None):
        seen.update(start=start, port=port)
        on_ready("KEY")

    monkeypatch.setattr(server, "run", fake)
    result = run("page", "add", "about", site, "--web", "--port", "8123")
    assert result.exit_code == 0, result.output
    assert "#KEY" in result.output and "about" in result.output
    assert seen["port"] == 8123
    assert seen["start"]["tab"] == "pages"
    assert seen["start"]["target"]["kind"] == "page" and seen["start"]["target"]["key"] == "about"
    assert not (site / "content" / "ru" / "about.md").exists()


# --- --dump и --answers ---------------------------------------------------------------


def test_dump_then_answers_is_a_no_op_byte_for_byte(site, tmp_path):
    assert run("page", "add", "about", site).exit_code == 0
    before = {p: p.read_bytes() for p in (site / "content").rglob("*.md")}
    yaml_before = (site / "site.yaml").read_bytes()
    dumped = run("page", "add", "about", site, "--dump")
    assert dumped.exit_code == 0
    data = yaml.safe_load(dumped.output)
    assert data["key"] == "about" and data["kind"] == "page"
    assert data["ru"]["title"] and data["de"]["translation"] == "pending"
    answers = tmp_path / "a.yaml"
    answers.write_text(dumped.output, encoding="utf-8")
    result = run("page", "add", "about", site, "--answers", answers)
    assert result.exit_code == 0, result.output
    assert "изменений нет" in result.output
    assert {p: p.read_bytes() for p in (site / "content").rglob("*.md")} == before
    assert (site / "site.yaml").read_bytes() == yaml_before


def test_dump_of_a_new_page_writes_nothing(site):
    result = run("page", "add", "fresh", site, "--dump")
    assert result.exit_code == 0
    assert yaml.safe_load(result.output)["ru"]["title"] == "Fresh"
    assert not (site / "content" / "ru" / "fresh.md").exists()


def test_answers_from_stdin_and_errors(site):
    good = run("page", "add", "x", site, "--answers", "-", input="ru:\n  h1: Икс\n")
    assert good.exit_code == 0, good.output
    unknown = run("page", "add", "y", site, "--answers", "-", input="fr: {}\n")
    assert unknown.exit_code == 1 and "E039" in unknown.output and "fr" in unknown.output
    blank = run("page", "add", "z", site, "--answers", "-", input="ru:\n  title: ''\n")
    assert blank.exit_code == 1 and "E039" in blank.output
    assert not (site / "content" / "ru" / "z.md").exists()
    broken = run("page", "add", "w", site, "--answers", "-", input="ru: [\n")
    assert broken.exit_code == 1 and "E039" in broken.output


def test_partial_translation_stays_pending_full_one_does_not(site, tmp_path):
    data = {
        "ru": {"title": "Цены на ремонт", "h1": "Цены", "description": "Сколько стоит ремонт."},
        "en": {"title": "Prices"},
        "de": {
            "title": "Preise für Reparatur",
            "h1": "Preise",
            "description": "Was kostet die Reparatur.",
            "sections.intro.text": "Kurz.",
        },
    }
    answers = tmp_path / "a.yaml"
    answers.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert run("page", "add", "prices", site, "--answers", answers).exit_code == 0
    _, en, de = files(site, "prices")
    assert front(en)["translation"] == "pending" and front(en)["title"] == "Prices"
    assert "translation" not in front(de)


# --- перенос с 301 --------------------------------------------------------------------


def test_moving_a_page_moves_every_language_and_keeps_old_addresses(site, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text(yaml.safe_dump({"ru": {"menu": True}}), encoding="utf-8")
    assert run("page", "add", "about", site, "--answers", answers).exit_code == 0
    moved = run("page", "add", "about", "--category", "company", site)
    assert moved.exit_code == 0, moved.output
    for old, new in zip(files(site, "about"), files(site, "company/about"), strict=True):
        assert not old.exists() and new.is_file()
    assert front(files(site, "company/about")[0])["redirect_from"] == ["/about/"]
    assert front(files(site, "company/about")[2])["redirect_from"] == ["/de/about/"]
    assert "company/about" in yaml.safe_load((site / "site.yaml").read_text())["nav"]["main"]
    assert (site / "content" / "en" / "company" / "_index.md").is_file()
    built = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.named("dev"))
    assert not built.collector.errors, built.collector.errors
    moves = (tmp_path / "d" / "redirects.map").read_text()
    assert "/about/  /company/about/;" in moves
    assert "/en/about/  /en/company/about/;" in moves


def test_moving_a_category_moves_its_pages_with_301_and_menu_keys(site, tmp_path):
    (site / "site.yaml").write_text(
        (site / "site.yaml").read_text(encoding="utf-8") + "# свой комментарий в конце\n",
        encoding="utf-8",
    )
    answers = tmp_path / "a.yaml"
    answers.write_text("key: guide\n", encoding="utf-8")
    result = run("category", "add", "structure", site, "--answers", answers)
    assert result.exit_code == 0, result.output
    assert not (site / "content" / "ru" / "structure").exists()
    child = site / "content" / "en" / "guide" / "one-intent.md"
    assert front(child)["redirect_from"] == ["/en/structure/one-intent/"]
    assert front(site / "content" / "ru" / "guide" / "_index.md")["redirect_from"] == [
        "/structure/"
    ]
    text = (site / "site.yaml").read_text(encoding="utf-8")
    menu = yaml.safe_load(text)["nav"]["main"]
    assert "guide" in menu and "structure" not in menu
    assert "main: [" in text  # меню в скобках так и осталось в скобках
    assert "# свой комментарий в конце" in text
    built = pipeline.run(site, dist=tmp_path / "d", env=BuildEnv.named("prod"))
    assert not built.collector.errors, built.collector.errors
    moves = (tmp_path / "d" / "redirects.map").read_text()
    assert "/structure/one-intent/  /guide/one-intent/;" in moves


def test_move_refusals(site, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text("key: structure/inner\n", encoding="utf-8")
    inside = run("category", "add", "structure", site, "--answers", answers)
    assert inside.exit_code == 1 and "E005" in inside.output
    answers.write_text("key: blocks\n", encoding="utf-8")
    taken = run("category", "add", "structure", site, "--answers", answers)
    assert taken.exit_code == 1 and "E004" in taken.output
    assert (site / "content" / "ru" / "structure" / "_index.md").is_file()


# --- category add ---------------------------------------------------------------------


def test_category_add_nested_on_every_language(site):
    result = run("category", "add", "services/roofing", "--view", "list", site)
    assert result.exit_code == 0, result.output
    for path in files(site, "services/roofing", category=True):
        assert path.is_file()
        data = front(path)
        assert data["view"] == "list" and data["children_type"] == "page"
    for path in files(site, "services", category=True):
        assert path.is_file()  # родитель создан попутно
    assert front(files(site, "services/roofing", True)[1])["translation"] == "pending"
    before = [p.read_bytes() for p in files(site, "services/roofing", True)]
    again = run("category", "add", "services/roofing", site)
    assert again.exit_code == 0 and "уже есть" in again.output
    assert [p.read_bytes() for p in files(site, "services/roofing", True)] == before
    built = pipeline.check(site)
    assert not built.collector.errors, built.collector.errors


def test_category_add_unknown_view_and_existing_category_view(site):
    bad = run("category", "add", "x", "--view", "grid3d", site)
    assert bad.exit_code == 1 and "E041" in bad.output and "cards" in bad.output
    edit = run("category", "add", "structure", "--view", "cards", site)
    assert edit.exit_code == 0, edit.output
    assert front(site / "content" / "ru" / "structure" / "_index.md")["view"] == "cards"


# --- page list --------------------------------------------------------------------------


def test_page_list_shows_the_tree_languages_and_pending(site):
    assert run("page", "add", "roof", "--category", "services", site).exit_code == 0
    result = run("page", "list", site)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    roof = next(line for line in lines if "roof" in line)
    assert roof.startswith("    roof") and "ru " in roof and "en!" in roof and "de!" in roof
    assert any(line.startswith("  services/") for line in lines)
    assert "Не переведено: 4" in result.output
    data = json.loads(run("page", "list", site, "--json").output)
    item = next(i for i in data["items"] if i["key"] == "services/roof")
    assert item["langs"] == {"ru": "ok", "en": "pending", "de": "pending"}
    (site / "content" / "de" / "services" / "roof.md").unlink()
    data = json.loads(run("page", "list", site, "--json").output)
    item = next(i for i in data["items"] if i["key"] == "services/roof")
    assert item["langs"]["de"] == "missing"


def test_check_json_lists_pending(site):
    assert run("page", "add", "roof", site).exit_code == 0
    data = json.loads(run("check", site, "--json").output)
    assert {"lang": "de", "path": "de/roof.md", "published": True} in data["pending"]
    prod = json.loads(run("check", site, "--json", "--env", "prod").output)
    assert {"lang": "de", "path": "de/roof.md", "published": False} in prod["pending"]


# --- консольный опросник --------------------------------------------------------------


class Script:
    """Сценарий ответов опросника и всё, что он напечатал."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.out: list[str] = []

    def io(self):
        def ask(prompt):
            self.out.append(prompt)
            return self.answers.pop(0)

        def echo(text="", color=None, dim=False, bold=False):
            self.out.append(text)

        return console.Io(ask, echo)

    @property
    def text(self):
        return "\n".join(self.out)


def test_console_creates_with_help_validation_and_skipped_translation(site):
    ctx = ops.context(site, "ru")
    entity = ops.open_entity(ctx, "about-agency")
    script = Script(
        [
            "+",  # категория: новая в корне
            "services",
            "Об агентстве - кто мы и как работаем",  # title
            "?",  # h1: справка
            "Об агентстве",
            "",  # description - оставить
            "Bad Slug",  # slug - ошибка, вопрос снова
            "",
            "y",  # меню - открыть группу
            "y",  # в меню
            "Агентство",
            "",  # order
            "",  # обложка - не открывать
            "",  # соцсети
            "",  # публикация
            "",  # поля темы: eyebrow стартовой темы - оставить пустым
            "Мы чиним крыши.",  # intro
            # en: всё переведено
            "About the agency - who we are",
            "About the agency",
            "What we do.",
            "Agency",
            "We fix roofs.",
            # de: всё пропущено
            "",
            "",
            "",
            "",
            "",
            "",  # записать - да
        ]
    )
    session = console.Console(entity, script.io(), "ru")
    session.run()
    assert session.confirm()
    assert not script.answers, script.answers
    text = script.text
    assert "Поиск: заголовок и описание" in text
    assert "Крупный заголовок вверху страницы" in text  # справка h1 по ?
    assert "слаг - латиница" in text  # проверка на лету
    assert "перевод не готов" in text
    saved = ops.save(entity)
    assert "content/de/services/about-agency.md" in saved.pending
    ru, en, de = files(site, "services/about-agency")
    assert front(ru)["nav_title"] == "Агентство" and "slug" not in front(ru)
    assert "translation" not in front(en) and front(en)["nav_title"] == "Agency"
    assert front(de)["translation"] == "pending"
    assert (
        "services/about-agency" in yaml.safe_load((site / "site.yaml").read_text())["nav"]["main"]
    )


def test_console_edit_of_one_language_and_marking_ready(site):
    assert run("page", "add", "about", site).exit_code == 0
    ctx = ops.context(site, "ru")
    entity = ops.open_entity(ctx, "about")
    fields = [f for f in ops.fields_of(entity, "de") if f.editable]
    folded = {"menu", "cover", "social", "publishing", "schema"}
    answers = []
    groups = []
    for item in fields:
        if item.group not in groups:
            groups.append(item.group)
            if item.group in folded:
                answers.append("y" if item.group == "publishing" else "")
        if item.group in folded and item.group != "publishing":
            continue
        answers.append("-" if item.name == "translation" else "")
    entity_script = Script(answers)
    console.Console(entity, entity_script.io(), "ru").run(only="de")
    assert not ops.is_pending(entity, "de")
    assert not entity_script.answers


# --- контракт: поле translation, describe, подсказки Docker ----------------------------


def test_docker_hint_has_a_terminal_only_when_the_command_asks():
    from heron import messages

    assert " -it " in messages.docker_command("page add about .")
    assert " -it " in messages.docker_command("category add services .")
    assert " -it " not in messages.docker_command("page add about . --answers a.yaml")
    assert " -it " not in messages.docker_command("page add about . --dump")
    assert " -it " not in messages.docker_command("page list .")
