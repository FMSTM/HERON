"""Отчёт check: заполненность, переводы, битые ссылки, сироты, долги."""

import re
import shutil
from pathlib import Path

import pytest

from heron.core import links, report, tree
from heron.core.errors import Collector
from tests import sites

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/services/_index.md": sites.page("Послуги", type="category", children_type="service"),
    "uk/services/design.md": (
        "---\ntitle: Дизайн\nh1: Дизайн\ndescription: Опис\n---\n\n"
        "## Що це {#what}\n\nТекст.\n\n## Зайва {#leftover}\n\nТекст.\n"
    ),
    "ru/index.md": sites.page("Главная"),
}

THEME = {"types": {"service": {"uses": ["what", "contra", "faq"]}}}


@pytest.fixture
def built(tmp_path):
    content = sites.build(tmp_path, FILES)
    config = sites.config()
    site, collector = tree.scan(content, config)
    theme = sites.theme(**THEME)
    links.resolve(site, config, theme, collector)
    return site, config, theme, collector


def test_counts_by_language_and_type(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert result.pages_by_lang["uk"] == 3
    assert result.pages_by_type["service"] == 1


def test_missing_sections_become_debts(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert set(result.missing_sections) == {"contra", "faq"}
    assert "uk/services/design.md" in result.missing_sections["contra"]


def test_section_theme_does_not_use_is_reported(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert ("uk/services/design.md", "leftover") in result.unused_sections


def test_untranslated_pages_listed(built):
    site, config, theme, _ = built
    result = report.build(site, config, theme)
    assert "ru" in result.untranslated
    assert "services/design" in result.untranslated["ru"]


def test_broken_internal_link(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/a.md": (
            "---\ntitle: А\nh1: А\ndescription: Опис\n---\n\n"
            "## Текст {#what}\n\n[кудись](/нет-такой/)\n"
        ),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    result = report.build(site, config, sites.theme())
    assert result.broken_links == [("uk/a.md", 9, "/нет-такой/")]


def test_asset_links_are_not_broken_pages(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/a.md": (
            "---\ntitle: А\nh1: А\ndescription: Опис\n---\n\n"
            "## Текст {#what}\n\n[файл](/static/doc.pdf)\n"
        ),
    }
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    result = report.build(site, sites.config(), sites.theme())
    assert result.broken_links == []


def test_unused_theme_modules(tmp_path):
    content = sites.build(tmp_path, FILES)
    theme_dir = sites.theme_dir(tmp_path)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    result = report.build(site, config, sites.theme(), theme_dir=theme_dir)
    assert "facts" not in result.unused_modules  # шаблон его зовёт
    assert result.unused_modules == []


def test_render_is_readable(built):
    site, config, theme, _ = built
    text = report.build(site, config, theme).render("ru")
    assert "Страниц —" in text
    assert "Тема ждёт секцию, а в файле её нет:" in text
    assert "contra" in text


def test_summary_lists_errors_and_warnings(built):
    _, _, _, collector = built
    collector.error("E001", "битый YAML", path="a.md", line=2)
    collector.warn("title длиннее 60 знаков", path="b.md")
    text = report.summary(collector, lang="ru")
    assert "E001 a.md:2" in text
    assert "b.md: title длиннее" in text


def test_summary_groups_warnings_by_kind():
    """Сотня замечаний про переводы не должна прятать десяток про картинки."""
    collector = Collector()
    for index in range(40):
        collector.warn(f"нет строки перевода {index}", kind="переводы")
    collector.warn("нет файла img/a.png", path="uk/index.md", kind="картинки")

    text = report.summary(collector, lang="ru")
    assert "картинки — 1:" in text
    assert "переводы — 40:" in text
    assert text.index("картинки —") < text.index("переводы —")
    assert "uk/index.md: нет файла img/a.png" in text


def test_summary_writes_full_list(tmp_path):
    collector = Collector()
    for index in range(20):
        collector.warn(f"замечание {index}", kind="картинки")
    target = tmp_path / "warnings.txt"

    text = report.summary(collector, full=target)
    assert str(target) in text
    assert len(target.read_text(encoding="utf-8").strip().splitlines()) == 20


def test_format_mismatch_is_information_not_error(tmp_path):
    """Секция пришла прозой, а тема ждала таблицу — это строка отчёта."""
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/one.md": (
            "---\ntitle: Одна\nh1: Одна\ndescription: Опис\ntype: service\n---\n\n"
            "Вступ.\n\n## Відновлення {#recovery}\n\nПроза замість шкали.\n"
        ),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    theme = sites.theme(types={"service": {"uses": ["intro", "recovery:timeline"]}})
    links.resolve(site, config, theme, collector)

    result = report.build(site, config, theme)
    assert result.format_mismatch == [("uk/one.md", "recovery", "timeline", "prose")]
    assert "ждали timeline, пришло prose" in result.render("ru")
    assert "expected timeline, got prose" in result.render("en")
    assert not collector.errors


def test_uneven_keys_in_a_list_are_reported(tmp_path):
    """Поле есть у части элементов — шаблон упадёт на первом же без него."""
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/docs.md": (
            "---\ntitle: Документи\nh1: Документи\ndescription: Опис\n"
            "docs:\n"
            "  - name: Перший\n    note: з поміткою\n"
            "  - name: Другий\n"
            "  - name: Третій\n"
            "---\n\n## Що {#what}\n\nТекст.\n"
        ),
    }
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    site.data = {"docs": [{"name": "А", "place": "Місто"}, {"name": "Б"}]}
    result = report.build(site, sites.config(), sites.theme())
    found = {(owner, key, have, total) for owner, _, key, have, total in result.uneven_keys}
    assert ("data/docs", "place", 1, 2) in found


def test_even_list_is_quiet(tmp_path):
    content = sites.build(tmp_path, {"uk/index.md": sites.page("Головна")})
    site, collector = tree.scan(content, sites.config())
    links.resolve(site, sites.config(), sites.theme(), collector)
    site.data = {"docs": [{"name": "А"}, {"name": "Б"}]}
    assert report.build(site, sites.config(), sites.theme()).uneven_keys == []


# --- язык отчёта и сводки: build.notes (E13.S1.T6) -----------------------------------

CYRILLIC = re.compile("[Ѐ-ӿ]")


def _full_report() -> report.Report:
    """Отчёт, где заполнен каждый раздел: печать обходит все строки."""
    from collections import Counter

    return report.Report(
        pages_by_lang=Counter({"en": 2}),
        pages_by_type=Counter({"page": 2}),
        missing_sections={"faq": ["en/a.md"]},
        format_mismatch=[("en/a.md", "steps", "timeline", "prose")],
        unused_sections=[("en/a.md", "extra")],
        unused_modules=["facts"],
        broken_links=[("en/a.md", 3, "/nowhere/")],
        orphans=["/lost/"],
        nameless_in_nav=["en/b.md"],
        untranslated={"de": ["about"]},
        unused_media=["media/x.png"],
        static_media=["static/photo.jpg"],
        notes_missing=[report.ROOT, "content/"],
        uneven_keys=[("data/docs", report.LIST, "place", 1, 2)],
        schema_nodes=Counter({"Article": 1}),
        manual_dates=(1, 2, "git"),
        nginx_test=(True, ""),
        kit=report.KitStatus(present=True, engine="0.1.0", lang="en", current=None),
    )


def test_render_in_english_has_no_russian_frame():
    text = _full_report().render("en")
    assert not CYRILLIC.search(text), [line for line in text.splitlines() if CYRILLIC.search(line)]
    for needle in (
        "Pages — 2 (en: 2)",
        "Types — page: 2",
        "Not translated:",
        "The theme expects a section the file does not have:",
        "faq          — 1 pages: en/a.md",
        "en/a.md: steps — expected timeline, got prose",
        "how to fix:",
        "In the menu without a short name",
        "Sections the theme does not use",
        "Theme modules no template calls: facts",
        "Links to nowhere:",
        "en/a.md:3 -> /nowhere/",
        "No page links to these: /lost/",
        "schema.org markup — Article: 1",
        "Files in media nothing expects — 1:",
        "Content sits in static",
        "data/docs: list — place in 1 of 2",
        "nginx -t on the built config: passed",
        "overrides updated_from: git",
        "No explanatory note (not an error): root, content/",
    ):
        assert needle in text, needle


def test_render_in_russian_keeps_the_old_text():
    text = _full_report().render("ru")
    for needle in (
        "Страниц — 2 (en: 2)",
        "Типы — page: 2",
        "Не переведено:",
        "Тема ждёт секцию, а в файле её нет:",
        "faq          — 1 страниц: en/a.md",
        "en/a.md: steps — ждали timeline, пришло prose",
        "как исправить: если по смыслу это форма из «ждали»",
        "`## Заголовок {#якорь .checklist}`",
        "Ссылки в никуда:",
        "На эти страницы никто не ссылается: /lost/",
        "Разметка schema.org — Article: 1",
        "Файлы в media, которых никто не ждёт — 1:",
        "data/docs: список — place у 1 из 2",
        "nginx -t на собранном конфиге: прошёл",
        "Ручная дата updated у 1 из 2 страниц перекрывает updated_from: git",
        "Без пояснительной записки (это не ошибка): корень, content/",
    ):
        assert needle in text, needle


@pytest.mark.parametrize(("notes", "head"), [("en", "Pages — 4"), ("ru", "Страниц — 4")])
def test_render_follows_build_notes_of_the_site(built, notes, head):
    site, _, theme, _ = built
    config = sites.config(build={"notes": notes})
    result = report.build(site, config, theme)
    assert result.notes_lang == notes
    assert head in result.render()
    # явный язык сообщений сильнее build.notes (флаг --notes, HERON_NOTES)
    other = "ru" if notes == "en" else "en"
    assert head not in result.render(other)


def _collector() -> Collector:
    collector = Collector()
    collector.error("E001", "битый YAML", path="a.md", line=2, hint="поправьте отступ")
    collector.error("E011", "без файла")
    for index in range(8):
        collector.warn(f"замечание {index}", path="b.md", kind="картинки")
    collector.warn("свой вид", kind="плагин-x")
    return collector


def test_summary_in_english(tmp_path):
    target = tmp_path / "warnings.txt"
    text = report.summary(_collector(), full=target, lang="en")
    assert "E001 a.md:2: битый YAML\n  what to do: поправьте отступ" in text
    assert "E011 <unknown file>: без файла" in text
    assert "Warnings — 9:" in text
    assert "  images — 8:" in text
    assert "    … and 2 more" in text
    assert f"  full list: {target}" in text
    assert "  плагин-x — 1:" in text  # вид, которого нет в таблице, — как есть
    # тексты замечаний движок пока пишет по-русски (21 §10); рамка — по-английски
    assert "Предупреждений" not in text and "что сделать" not in text
    # файл для разбора — с видами как в коде
    assert target.read_text(encoding="utf-8").startswith("картинки\tb.md\t")


def test_summary_in_russian_is_unchanged(tmp_path):
    target = tmp_path / "warnings.txt"
    collector = _collector()
    text = report.summary(collector, full=target, lang="ru")
    assert text.splitlines()[0] == "E001 a.md:2: битый YAML"
    assert "\n  что сделать: поправьте отступ" in text
    assert str(collector.errors[0]) in text  # как str(HeronError)
    assert "E011 <неизвестный файл>: без файла" in text
    assert "Предупреждений — 9:" in text
    assert "  картинки — 8:" in text
    assert "    … и ещё 2" in text
    assert f"  полный список: {target}" in text


def test_every_warning_kind_of_the_engine_has_an_english_label():
    from heron.messages import KINDS

    assert set(report.ORDER) <= set(KINDS["en"])
    assert not any(CYRILLIC.search(label) for label in KINDS["en"].values())


def test_report_keys_exist_in_both_languages():
    from heron.messages import TEXT

    keys = [k for k in TEXT["ru"] if k.startswith(("report_", "summary_"))]
    assert len(keys) > 20
    assert set(keys) == {k for k in TEXT["en"] if k.startswith(("report_", "summary_"))}


# --- CLI: check и build печатают отчёт на языке сайта ---------------------------------


@pytest.fixture
def cli(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from heron.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HERON_NOTES", raising=False)
    runner = CliRunner()
    return lambda *args: runner.invoke(main, list(args))


def _page_with_warning(root) -> None:
    (root / "content/en/long.md").write_text(
        "---\ntitle: " + "t" * 80 + "\nh1: Long\ndescription: D\n---\n\nText.\n",
        encoding="utf-8",
    )


def test_cli_check_and_build_on_english_site(cli):
    assert cli("new", "site", "--notes", "en", "-y").exit_code == 0
    _page_with_warning(Path("site"))
    for command in (("check", "site"), ("build", "site")):
        result = cli(*command)
        assert result.exit_code == 0, result.output
        assert "Pages — " in result.output and "Types — " in result.output
        assert "Warnings — " in result.output
        assert "Страниц" not in result.output and "Типы —" not in result.output
        assert "Предупреждений" not in result.output


def test_cli_check_on_russian_site(cli):
    assert cli("new", "site", "--notes", "ru", "-y").exit_code == 0
    _page_with_warning(Path("site"))
    result = cli("check", "site")
    assert result.exit_code == 0, result.output
    assert "Страниц — " in result.output and "Типы — " in result.output
    assert "Предупреждений — " in result.output
    assert "Pages —" not in result.output


def test_cli_notes_env_overrides_site_notes_for_the_report(cli, monkeypatch):
    assert cli("new", "site", "--notes", "ru", "-y").exit_code == 0
    monkeypatch.setenv("HERON_NOTES", "en")
    result = cli("check", "site")
    assert "Pages — " in result.output and "Страниц" not in result.output


def test_cli_check_errors_frame_follows_notes(cli):
    assert cli("new", "site", "--notes", "en", "-y").exit_code == 0
    Path("site/content/en/bad.md").write_text("---\ntitle: [\n---\n", encoding="utf-8")
    result = cli("check", "site")
    assert result.exit_code == 1
    assert "E001 " in result.output
    assert "что сделать" not in result.output


# --- E024 у init и new — на языке сайта, как у setup ------------------------------------


@pytest.mark.parametrize(
    ("notes", "head", "where", "foreign"),
    [
        ("ru", "Ошибка E024: ", "  где: ", "Error E024"),
        ("en", "Error E024: a path leaves the allowed folders", "  where: ", "Ошибка E024"),
    ],
)
def test_init_e024_speaks_the_site_language(cli, tmp_path, notes, head, where, foreign):
    assert cli("new", "site", "--notes", notes, "-y").exit_code == 0
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.rmtree("site/agents")
    Path("site/agents").symlink_to(outside, target_is_directory=True)
    result = cli("init", "site", "--agents")
    assert result.exit_code == 1
    assert head in result.output, result.output
    assert where in result.output
    assert foreign not in result.output
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    ("notes", "head", "foreign"),
    [("ru", "Ошибка E024: ", "Error E024"), ("en", "Error E024: ", "Ошибка E024")],
)
def test_new_e024_speaks_the_chosen_language(cli, tmp_path, notes, head, foreign):
    outside = tmp_path / "outside"
    outside.mkdir()
    Path("s").mkdir()
    Path("s/agents").symlink_to(outside, target_is_directory=True)
    result = cli("new", "s", "--notes", notes, "-y")
    assert result.exit_code == 1
    assert head in result.output, result.output
    assert foreign not in result.output
    assert not Path("s/site.yaml").exists()
