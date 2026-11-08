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
from heron.setup.files import gitignore


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


def test_new_gitignore_protects_env(here):
    result = run("new", "fresh")

    assert result.exit_code == 0, result.output
    lines = (here / "fresh" / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".env") == 1


def test_init_leaves_foreign_gitignore_untouched(here):
    (here / ".gitignore").write_text("secret.txt\n", encoding="utf-8")

    result = run("init", ".", "--lang", "en", "-y")

    assert result.exit_code == 0, result.output
    assert (here / "site.yaml").is_file()
    assert (here / ".gitignore").read_text(encoding="utf-8") == "secret.txt\n"


def test_setup_does_not_repeat_env_in_scaffold_gitignore(here):
    run("new", "fresh")
    current = (here / "fresh" / ".gitignore").read_text(encoding="utf-8")

    merged = gitignore(current)

    # setup дописывает своё (*.env), но строку .env из заготовки не повторяет
    assert merged is not None
    assert merged.startswith(current)
    assert "*.env" in merged.splitlines()
    assert merged.splitlines().count(".env") == 1


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


def test_flags_lang_duplicates_removed_and_check_passes(here):
    result = run("new", "dup", "--lang", "ru,en,en", "-y")
    assert result.exit_code == 0, result.output
    assert config(here / "dup")["site"]["languages"] == ["ru", "en"]
    checked = run("check", str(here / "dup"))
    assert checked.exit_code == 0, checked.output


def test_flags_domain_is_normalized_like_questionnaire(here):
    from heron.contracts import site as site_contract

    result = run("new", "dom", "--domain", "https://Shop.com/", "-y")
    assert result.exit_code == 0, result.output
    expected = site_contract.domain("https://Shop.com/")
    assert expected and config(here / "dom")["site"]["domain"] == expected


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


DOCKER = 'docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:'


def test_next_steps_in_container_are_ready_docker_commands(here, monkeypatch):
    # В контейнере команды `heron` нет: подсказка - полная команда под тот же образ.
    monkeypatch.setattr(cli, "in_container", lambda: True)
    monkeypatch.setenv("HERON_CHANNEL", "beta")
    result = run("new", "my-site", "--notes", "en", "--lang", "en", "-y")

    assert result.exit_code == 0, result.output
    assert "`heron " not in result.output
    # page add спрашивает в терминале: -it, как у new и init
    page = DOCKER.replace("--rm ", "--rm -it ") + "beta page add about my-site"
    assert f"\n      {page}\n" in result.output
    assert f"\n      {DOCKER}beta check my-site\n" in result.output
    setup = (
        "docker run --rm -it -p 127.0.0.1:8000:8000 -p 127.0.0.1:8001:8001 "
        '-v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta setup my-site'
    )
    assert setup in result.output
    assert 'docker run --rm -it -v "$PWD:/site"' in result.output  # init спрашивает


def test_next_steps_outside_container_stay_short(here):
    result = run("new", "my-site", "--notes", "en", "--lang", "en", "-y")

    assert result.exit_code == 0, result.output
    assert "`heron check my-site`" in result.output
    assert "docker run" not in result.output


@pytest.mark.parametrize(
    ("channel", "image"),
    [("prod", "heron:prod"), ("beta", "heron:beta"), ("v0.2.0", "heron:0.2.0"), ("", "heron:prod")],
)
def test_docker_hint_follows_the_image_channel(monkeypatch, channel, image):
    from heron import messages

    monkeypatch.setenv("HERON_CHANNEL", channel)
    assert f"ghcr.io/fmstm/{image} build ." in messages.for_docker("`heron build .`")


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
    [["check"], ["build"], ["page", "add", "about"]],
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


# --- build не блок ключей (E15.S1.T9, E1) -------------------------------------------


NOT_A_BLOCK = {
    "scalar": "site:\n  name: S\n  languages: [en]\nbuild: x\n",
    "list": "site:\n  name: S\n  languages: [en]\nbuild: [1]\n",
}


def no_crash(result) -> None:
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        result.exc_info,
        result.output,
    )
    assert "Traceback" not in result.output, result.output


@pytest.mark.parametrize("case", sorted(NOT_A_BLOCK))
@pytest.mark.parametrize("command", ["check", "build"])
def test_build_that_is_not_a_block_gives_e011(here, case, command):
    (here / "site.yaml").write_text(NOT_A_BLOCK[case], encoding="utf-8")
    for args in ([command], [command, "."], [command, str(here)]):
        result = run(*args)
        no_crash(result)
        assert result.exit_code == 1, result.output
        head, where, details = FRAME["en"]
        assert head in result.output and where in result.output, result.output
        assert "unexpected error" not in result.output


@pytest.mark.parametrize("case", sorted(NOT_A_BLOCK))
@pytest.mark.parametrize("flags", [[], ["--agents"], ["--no-agents"]], ids=["-", "agents", "no"])
def test_init_on_build_that_is_not_a_block_touches_nothing(here, case, flags):
    """init отвечает E011, как check, и не дописывает в site.yaml второй блок build."""
    text = NOT_A_BLOCK[case]
    (here / "site.yaml").write_text(text, encoding="utf-8")
    result = run("init", ".", *flags)
    no_crash(result)
    assert result.exit_code == 1, result.output
    assert FRAME["en"][0].split(":")[0] in result.output  # Error E011
    assert "not a block of keys, the folder is left alone" in result.output, result.output
    assert (here / "site.yaml").read_text(encoding="utf-8") == text
    assert sorted(p.name for p in here.iterdir()) == ["site.yaml"]
    ru = run("init", ".", "--notes", "ru", *flags)
    assert "Ошибка E011" in ru.output and "не блок ключей, папка не тронута" in ru.output
    assert "Error" not in ru.output, ru.output


def test_new_in_a_folder_with_build_that_is_not_a_block(here):
    (here / "site.yaml").write_text(NOT_A_BLOCK["scalar"], encoding="utf-8")
    result = run("new", ".", "-y")
    no_crash(result)
    assert result.exit_code != 0
    assert (here / "site.yaml").read_text(encoding="utf-8") == NOT_A_BLOCK["scalar"]


def test_declared_ignores_build_that_is_not_a_block(tmp_path):
    from heron.scaffold import _declared, resolve_notes

    site_yaml = tmp_path / "site.yaml"
    site_yaml.write_text(NOT_A_BLOCK["list"], encoding="utf-8")
    declared = _declared(site_yaml)
    assert declared is not None
    assert declared["notes"] is None and declared["agents"] is None
    assert declared["build_error"] == "[1]"
    assert resolve_notes(None, site_yaml) == "en"
    site_yaml.write_text("site:\n  languages: [en]\nbuild:\n  notes: ru\n", encoding="utf-8")
    assert _declared(site_yaml)["build_error"] is None
    site_yaml.write_text("site:\n  languages: [en]\nbuild:\n", encoding="utf-8")
    assert _declared(site_yaml)["build_error"] is None  # пустой build — не ошибка


def test_build_error_value_is_short_even_when_huge(tmp_path):
    from heron.scaffold import _declared

    site_yaml = tmp_path / "site.yaml"
    items = ", ".join(str(i) for i in range(5000))
    site_yaml.write_text(f"site:\n  languages: [en]\nbuild: [{items}]\n", encoding="utf-8")
    assert len(_declared(site_yaml)["build_error"]) < 80


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
        (1, "тема: 1 файл -"),
        (2, "тема: 2 файла -"),
        (5, "тема: 5 файлов -"),
        (11, "тема: 11 файлов -"),
        (21, "тема: 21 файл -"),
        (24, "тема: 24 файла -"),
    ],
)
def test_russian_counters_agree_with_the_number(count, text):
    from heron.messages import say

    assert say("ru", "plan_theme", count=count).startswith(text)
    assert say("ru", "serve_built", count=count) == "собрано: " + text[6:-2]
    assert say("en", "plan_theme", count=count).startswith(
        f"theme: {count} {'file' if count == 1 else 'files'} -"
    )


def test_counters_keep_other_format_specs():
    from heron.messages import say

    line = say("ru", "report_missing_line", section="blog", count=5, shown="a, b, c")
    assert line == "  blog         - 5 страниц: a, b, c"
    assert say("ru", "found_content", pages=21, langs="ru") == "content/: 21 страница, языки: ru"


def test_new_summary_in_russian_agrees_with_the_number(here):
    import re

    result = run("new", "s", "--notes", "ru", "-y")
    assert result.exit_code == 0, result.output
    found = re.search(r"тема: (\d+) (\S+) -", result.output)
    assert found, result.output
    from heron.messages import plural

    assert found.group(2) == plural(int(found.group(1)), "файл|файла|файлов")
    assert "24 файлов" not in result.output


# --- склонение чисел в итогах check и build (E15.S1.T11, W4, F29) --------------------

ERRORS_EN = {0: "errors", 1: "error", 2: "errors", 5: "errors", 11: "errors", 21: "errors"}


@pytest.mark.parametrize("count", sorted(ERRORS_EN))
def test_check_and_build_totals_agree_with_the_number(count):
    from heron.messages import say

    word = ERRORS_EN[count]
    them = "it" if count == 1 else "them"
    assert say("en", "check_failed", count=count) == (
        f"Check found {count} {word}. A build would fail on {them}."
    )
    assert say("en", "build_failed", count=count).startswith(f"Build failed: {count} {word}.")
    warn = "warning" if count == 1 else "warnings"
    assert f"{count} {warn}." in say("en", "check_strict", count=count)
    assert f"{count} {warn}." in say("en", "build_strict", count=count)
    # по-русски число стоит после подписи: «ошибок: 1» — форма слова от числа не зависит
    assert say("ru", "check_failed", count=count).startswith(f"Проверка нашла ошибок: {count}.")


@pytest.mark.parametrize(
    ("count", "pages", "files", "images"),
    [
        (1, "1 page", "1 file", "1 source image"),
        (2, "2 pages", "2 files", "2 source images"),
        (21, "21 pages", "21 files", "21 source images"),
    ],
)
def test_build_step_totals_agree_with_the_number(count, pages, files, images):
    from heron.messages import say

    assert say("en", "done_pages", count=count) == pages
    assert say("en", "done_files", count=count) == files
    assert say("en", "done_masters", count=count) == images


def test_check_with_one_error_says_one_error(here):
    """Обычный check с одной ошибкой: «Check found 1 error.», без «1 errors»."""
    assert run("new", "s", "--notes", "en", "-y").exit_code == 0
    page = here / "s" / "content" / "en" / "index.md"
    text = page.read_text(encoding="utf-8")
    page.write_text(text.replace("title:", "titel:", 1), encoding="utf-8")
    result = run("check", "s")
    assert result.exit_code == 1, result.output
    found = [line for line in result.output.splitlines() if line.startswith("Check found")]
    assert found, result.output
    count = int(found[0].split()[2])
    assert found[0].startswith(f"Check found {count} {'error' if count == 1 else 'errors'}.")
    assert "1 errors" not in result.output
