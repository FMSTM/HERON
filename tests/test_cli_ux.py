"""Командная строка для человека: опрос, понятные ошибки, папка под git.

Каждое сообщение отвечает, что случилось, почему и что делать. Трейсбек
наружу не выходит — только с --debug.

Спецификация: docs/spec/23-distribution.md, раздел 4; docs/spec/21-engine.md, раздел 10.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron import cli
from heron.cli import main


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.delenv("HERON_IN_CONTAINER", raising=False)
    monkeypatch.delenv("HERON_DEBUG", raising=False)
    monkeypatch.setattr(cli, "in_container", lambda: False)
    return tmp_path


def run(*args, **kwargs):
    return CliRunner().invoke(main, list(args), **kwargs)


def config(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))


# --- папка под git -------------------------------------------------------------


def test_new_in_current_folder_under_git(here):
    (here / ".git").mkdir()
    (here / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    (here / "README.md").write_text("# repo\n", encoding="utf-8")

    result = run("new", ".")

    assert result.exit_code == 0, result.output
    assert (here / "site.yaml").is_file()
    assert (here / "content" / "en" / "index.md").is_file()
    # чужой .gitignore не перезаписан
    assert (here / ".gitignore").read_text(encoding="utf-8") == "secret.txt\n"
    assert "Left untouched (already there): .gitignore" in result.output


def test_new_names_the_files_that_get_in_the_way(here):
    folder = here / "busy"
    folder.mkdir()
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    (folder / ".git").mkdir()

    result = run("new", "busy", "--notes", "ru")

    assert result.exit_code == 1
    assert "notes.txt" in result.output
    assert ".git" not in result.output.split("в ней есть")[1].split("\n")[0]
    assert "heron init busy" in result.output
    assert not (folder / "site.yaml").exists()


# --- опрос --------------------------------------------------------------------


@pytest.fixture
def terminal(monkeypatch):
    monkeypatch.setattr(cli, "can_ask", lambda: True)


def test_questionnaire_fills_site_yaml(here, terminal):
    answers = "ru\nСтудия: Киев\nstudio.example.org\nen, ru\nru\ny\n"
    result = run("new", "studio", input=answers)

    assert result.exit_code == 0, result.output
    root = here / "studio"
    site = config(root)["site"]
    assert site["name"] == "Студия: Киев"
    assert site["domain"] == "studio.example.org"
    assert site["default_lang"] == "ru"
    assert site["languages"] == ["ru", "en"]
    assert config(root)["build"]["notes"] == "ru"
    for lang in ("ru", "en"):
        assert (root / "content" / lang / "index.md").is_file()
        assert (root / "theme" / "i18n" / f"{lang}.yaml").is_file()
    assert "Сайт создан" in result.output
    assert "Что дальше" in result.output


def test_questionnaire_asks_again_on_bad_answers(here, terminal):
    # «shop» без точки — не домен; https://shop.com/ — домен со схемой: его,
    # как и site.yaml, принимаем и приводим к shop.com
    answers = "en\nShop\nshop\nhttps://shop.com/\nen, english\nen\ny\n"
    result = run("new", "shop", input=answers)

    assert result.exit_code == 0, result.output
    assert "no scheme and no path" in result.output
    assert "not valid: english" in result.output
    assert config(here / "shop")["site"]["domain"] == "shop.com"


def test_questionnaire_single_language_skips_main_language_question(here, terminal):
    result = run("new", "one", "--notes", "en", input="One\n\nen\ny\n")

    assert result.exit_code == 0, result.output
    assert "Main language" not in result.output
    assert config(here / "one")["site"]["domain"] == "one.example"
    assert "placeholder" in result.output


def test_questionnaire_can_be_cancelled(here, terminal):
    result = run("new", "nope", "--notes", "en", input="Nope\n\nen\nn\n")

    assert result.exit_code == 0, result.output
    assert "nothing created" in result.output
    assert not (here / "nope" / "site.yaml").exists()


def test_flags_without_terminal(here):
    result = run(
        "new", "flags", "--name", "Flags", "--domain", "flags.org", "--lang", "en,ru", "-y"
    )

    assert result.exit_code == 0, result.output
    site = config(here / "flags")["site"]
    assert (site["name"], site["domain"], site["languages"]) == (
        "Flags",
        "flags.org",
        ["en", "ru"],
    )
    assert "No questions asked" not in result.output


def test_without_terminal_says_why_there_are_no_questions(here):
    result = run("new", "quiet")
    assert result.exit_code == 0, result.output
    assert "No questions asked" in result.output
    assert "-it" in result.output


# --- пути и контейнер -------------------------------------------------------------


def test_build_of_missing_folder_explains_the_container(here, monkeypatch):
    monkeypatch.setattr(cli, "in_container", lambda: True)
    result = run("build", "/Users/someone/SOURCE/site")

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "/site" in result.output
    assert "relative to the current folder" in result.output


def test_new_in_missing_host_path_explains_the_container(here, monkeypatch):
    monkeypatch.setattr(cli, "in_container", lambda: True)
    result = run("new", "/Users/someone/SOURCE/site", "--notes", "ru")

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "смонтированную в /site" in result.output


def test_build_of_folder_without_site_yaml(here):
    (here / "empty").mkdir()
    result = run("build", "empty")

    assert result.exit_code == 1
    assert "has no site.yaml" in result.output
    assert "heron new empty" in result.output


# --- непредвиденное ---------------------------------------------------------------


def test_unexpected_error_has_no_traceback(here, monkeypatch):
    run("new", "demo")

    def boom(*args, **kwargs):
        raise RuntimeError("что-то пошло не так")

    monkeypatch.setattr(cli.pipeline, "run", boom)
    result = run("build", "demo")

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "RuntimeError" in result.output
    assert "--debug" in result.output


def test_debug_lets_the_traceback_through(here, monkeypatch):
    run("new", "demo")

    def boom(*args, **kwargs):
        raise RuntimeError("для разработчика")

    monkeypatch.setattr(cli.pipeline, "run", boom)
    result = run("--debug", "build", "demo")

    assert isinstance(result.exception, RuntimeError)


def test_permission_error_is_explained(here, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "/site/theme")

    monkeypatch.setattr(cli, "create", denied)
    result = run("new", "locked")

    assert result.exit_code == 1
    assert "No permission to write: /site/theme" in result.output
    assert "--user $(id -u):$(id -g)" in result.output


# --- сводка ---------------------------------------------------------------------


def test_summary_is_grouped_and_verbose_lists_files(here):
    short = run("new", "a")
    assert "theme:" in short.output
    assert "theme/base.html" not in short.output

    full = run("new", "b", "--verbose")
    assert "theme/base.html" in full.output


def test_init_tells_what_next(here):
    run("new", "site", "--lang", "en,ru", "-y")
    result = run("init", "site")
    assert result.exit_code == 0, result.output
    assert "What next" in result.output
    assert "content/en/index.md, content/ru/index.md" in result.output


def test_starter_site_builds_for_production_without_a_single_warning(here):
    run("new", "clean", "--lang", "en,ru", "-y")
    result = run("build", "clean", "--env", "prod", "--strict")
    assert result.exit_code == 0, result.output


def test_build_messages_follow_the_site_language(here):
    run("new", "ru-site", "--notes", "ru", "-y")
    result = run("build", "ru-site")
    assert result.exit_code == 0, result.output
    assert "обход контента" in result.output
    assert "Собрано файлов" in result.output


# --- папка, где сайт уже есть, и init без site.yaml ----------------------------------


def test_new_where_a_site_already_lives(here):
    run("new", "ready", "--notes", "ru", "--lang", "ru,en", "-y")
    result = run("new", "ready")

    assert result.exit_code == 1
    # язык — из build.notes найденного сайта, без флага
    assert "уже есть сайт" in result.output
    assert "языки ru, en" in result.output
    assert "heron init ready" in result.output
    assert "git clean -dn" in result.output


def test_busy_folder_list_has_no_double_period(here):
    folder = here / "many"
    folder.mkdir()
    for index in range(7):
        (folder / f"f{index}.txt").write_text("x", encoding="utf-8")
    result = run("new", "many")
    assert "…." not in result.output
    assert "f0.txt" in result.output


def test_init_without_site_yaml_asks_the_same_questions(here, terminal):
    (here / ".git").mkdir()
    result = run("init", ".", input="ru\nWorkshop\nworkshop.org\nuk, ru\nuk\ny\n")

    assert result.exit_code == 0, result.output
    site = config(here)["site"]
    assert (site["name"], site["domain"], site["default_lang"]) == (
        "Workshop",
        "workshop.org",
        "uk",
    )
    assert site["languages"] == ["uk", "ru"]


def test_init_without_site_yaml_offers_languages_found_in_content(here):
    (here / "content" / "ru").mkdir(parents=True)
    (here / "content" / "en").mkdir(parents=True)
    result = run("init", ".")

    assert result.exit_code == 0, result.output
    assert "en, ru" in result.output
    assert config(here)["site"]["languages"] == ["en", "ru"]


def test_init_with_site_yaml_asks_nothing(here, terminal):
    run("new", "s", "-y")
    result = run("init", "s", input="")
    assert result.exit_code == 0, result.output
    assert "Site name" not in result.output


def test_site_name_comes_from_the_git_remote(here, monkeypatch):
    monkeypatch.setattr(cli, "in_container", lambda: True)
    (here / ".git").mkdir()
    (here / ".git" / "config").write_text(
        '[core]\n\tbare = false\n[remote "origin"]\n'
        "\turl = git@github.com:SOMEORG/MYSITE.git\n\tfetch = +refs/heads/*\n",
        encoding="utf-8",
    )
    assert cli.site_name_guess(here) == "MYSITE"


def test_site_name_in_container_is_not_the_mount_point(here, monkeypatch):
    monkeypatch.setattr(cli, "in_container", lambda: True)
    folder = here / "site"
    folder.mkdir()
    assert cli.site_name_guess(folder) == "my-site"


# --- язык рамки, когда site.yaml не разбирается (F05, E15.S1.T6) -----------------


def broken(here: Path, name: str, notes: str) -> Path:
    """Сайт с build.notes и испорченным в конце site.yaml: YAML не разбирается."""
    assert run("new", name, "--notes", notes, "-y").exit_code == 0
    site_yaml = here / name / "site.yaml"
    with site_yaml.open("a", encoding="utf-8") as handle:
        handle.write("site: [\n")
    return here / name


FRAME = {
    "ru": ("Ошибка E011: site.yaml не проходит валидацию", "  где: ", "  подробно: "),
    "en": ("Error E011: site.yaml is not valid", "  where: ", "  details: "),
}


def frame_lines(output: str) -> list[str]:
    """Строки рамки ошибки: заголовок и подписи «где», «подробно», «что сделать»."""
    labels = ("Ошибка ", "Error ", "  где:", "  where:", "  подробно:", "  details:")
    labels += ("  что сделать:", "  what to do:")
    return [line for line in output.splitlines() if line.startswith(labels)]


@pytest.mark.parametrize(
    "args",
    [["check"], ["build"], ["page", "page", "about"]],
    ids=["check", "build", "page"],
)
def test_broken_site_yaml_of_a_russian_site_gives_a_russian_frame(here, args):
    root = broken(here, "s", "ru")
    result = run(*args, str(root))
    assert result.exit_code == 1, result.output
    head, where, details = FRAME["ru"]
    assert head in result.output and where in result.output and details in result.output
    assert "  что сделать: " in result.output
    lines = frame_lines(result.output)
    assert len(lines) == 4, result.output
    # ни одной английской подписи в рамке
    for label in ("Error", "where:", "details:", "what to do:"):
        assert label not in result.output, result.output


def test_broken_site_yaml_of_an_english_site_keeps_an_english_frame(here):
    root = broken(here, "s", "en")
    result = run("check", str(root))
    assert result.exit_code == 1
    head, where, details = FRAME["en"]
    assert head in result.output and where in result.output and details in result.output
    assert "  what to do: " in result.output
    for label in ("Ошибка", "где:", "подробно:", "что сделать:"):
        assert label not in result.output


def test_flag_and_env_beat_the_notes_line_of_a_broken_file(here, monkeypatch):
    root = broken(here, "s", "ru")
    flag = run("check", str(root), "--notes", "en")
    assert FRAME["en"][0] in flag.output and "подробно:" not in flag.output
    monkeypatch.setenv("HERON_NOTES", "en")
    env = run("build", str(root))
    assert FRAME["en"][0] in env.output
    both = run("check", str(root), "--notes", "ru")
    assert FRAME["ru"][0] in both.output


def test_broken_site_yaml_also_sets_the_help_language(here, monkeypatch):
    broken(here, "s", "ru")
    assert run("check", "--help").output.startswith("Usage:")  # здесь site.yaml нет
    monkeypatch.chdir(here / "s")
    assert run("--help").output.startswith("Использование: ")
    assert run("check", "--help").output.startswith("Использование: ")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("build:\n  notes: ru\nsite: [\n", "ru"),
        ('build:\n  notes: "ru"  # язык пояснений\nsite: [\n', "ru"),
        ("build:\n  notes: 'RU'\nsite: [\n", "ru"),  # регистр как у YAML: RU = ru
        ("build:\n\tnotes: ru\n  oops: [\n", "ru"),  # табуляция ломает YAML, строка видна
        ("# notes: ru\nsite: [\n", "en"),  # закомментированная строка не считается
        ("build:\n  notes: de\nsite: [\n", "en"),  # чужой язык — по умолчанию
        ("build:\n  footnotes: ru\nsite: [\n", "en"),  # другой ключ
        ("site: [\n", "en"),
        ("", "en"),
    ],
)
def test_notes_of_a_broken_file_from_its_text(tmp_path, monkeypatch, text, expected):
    from heron.scaffold import resolve_notes

    monkeypatch.delenv("HERON_NOTES", raising=False)
    site_yaml = tmp_path / "site.yaml"
    site_yaml.write_text(text, encoding="utf-8")
    assert resolve_notes(None, site_yaml) == expected
    assert resolve_notes("en", site_yaml) == "en"
    assert cli._lang(None, tmp_path) == expected


def test_notes_of_a_valid_file_come_from_yaml_not_from_text(tmp_path, monkeypatch):
    """Разобранный конфиг — источник правды: строка в другом блоке не перебивает его."""
    from heron.scaffold import resolve_notes

    monkeypatch.delenv("HERON_NOTES", raising=False)
    site_yaml = tmp_path / "site.yaml"
    site_yaml.write_text(
        "site:\n  name: S\n  languages: [en]\nbuild:\n  notes: en\nextra:\n  notes: ru\n",
        encoding="utf-8",
    )
    assert resolve_notes(None, site_yaml) == "en"
    missing = tmp_path / "nothing.yaml"
    assert resolve_notes(None, missing) == "en"
    folder = tmp_path / "dir"
    (folder / "site.yaml").mkdir(parents=True)
    assert resolve_notes(None, folder / "site.yaml") == "en"


def test_init_of_a_broken_russian_site_speaks_russian(here):
    root = broken(here, "s", "ru")
    result = run("init", str(root))
    assert result.exit_code == 0, result.output
    assert "Папка" in result.output and "дополнена по site.yaml" in result.output
    assert "build.notes is en" not in result.output and "Already in the folder" not in result.output


# --- склонение числа в сообщениях (E15.S1.T8) ---------------------------------------


@pytest.mark.parametrize(
    ("count", "ru", "en"),
    [
        (0, "файлов", "files"),
        (1, "файл", "file"),
        (2, "файла", "files"),
        (4, "файла", "files"),
        (5, "файлов", "files"),
        (11, "файлов", "files"),
        (12, "файлов", "files"),
        (14, "файлов", "files"),
        (21, "файл", "files"),
        (22, "файла", "files"),
        (24, "файла", "files"),
        (25, "файлов", "files"),
        (101, "файл", "files"),
        (111, "файлов", "files"),
    ],
)
def test_plural_forms(count, ru, en):
    from heron.messages import plural

    assert plural(count, "файл|файла|файлов") == ru
    assert plural(count, "file|files") == en


@pytest.mark.parametrize(
    ("count", "text"),
    [
        (1, "тема: 1 файл —"),
        (2, "тема: 2 файла —"),
        (5, "тема: 5 файлов —"),
        (11, "тема: 11 файлов —"),
        (21, "тема: 21 файл —"),
        (24, "тема: 24 файла —"),
    ],
)
def test_russian_counters_agree_with_the_number(count, text):
    from heron.messages import say

    assert say("ru", "plan_theme", count=count).startswith(text)
    assert say("ru", "serve_built", count=count) == "собрано: " + text[6:-2]
    assert say("en", "plan_theme", count=count).startswith(
        f"theme: {count} {'file' if count == 1 else 'files'} —"
    )


def test_counters_keep_other_format_specs():
    from heron.messages import say

    line = say("ru", "report_missing_line", section="blog", count=5, shown="a, b, c")
    assert line == "  blog         — 5 страниц: a, b, c"
    assert say("ru", "found_content", pages=21, langs="ru") == "content/: 21 страница, языки: ru"


def test_new_summary_in_russian_agrees_with_the_number(here):
    import re

    result = run("new", "s", "--notes", "ru", "-y")
    assert result.exit_code == 0, result.output
    found = re.search(r"тема: (\d+) (\S+) —", result.output)
    assert found, result.output
    from heron.messages import plural

    assert found.group(2) == plural(int(found.group(1)), "файл|файла|файлов")
    assert "24 файлов" not in result.output
