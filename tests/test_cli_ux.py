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
    answers = "en\nShop\nhttps://shop.com/\nshop.com\nen, english\nen\ny\n"
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
