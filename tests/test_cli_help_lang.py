"""Справка и служебные строки click на языке пояснений (E15.S1.T3; F02, F18, F23, F16).

Язык справки выбирается до разбора аргументов: `--notes`, затем HERON_NOTES,
затем build.notes из site.yaml текущей папки, иначе en (21 §10). В en-справке
нет ни одной кириллической буквы; в ru-справке нет латинских слов, кроме
токенов: команд, флагов, ключей, имён файлов и форматов.

Спецификация: docs/ru/spec/21-engine.md §10; docs/ru/spec/20-data-contract.md §5.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from heron import cli
from heron.cli import main
from heron.messages import CLICK_RU, TEXT

CYRILLIC = re.compile(r"[А-Яа-яЁё]")

# Латинские слова, которые в русской справке — токены: имена команд, форматов,
# программ и значений, которые набирают как есть.
TOKENS = {
    "heron",
    "HERON",
    "JSON",
    "Schema",
    "YAML",
    "CI",
    "git",
    "docker",
    "nginx",
    "Dockerfile",
    "README",
    "stdin",
    "starter",
    "https",
    "prod",
    "true",
    "false",
    "ru",
    "en",
    # темы и подкоманды heron docs из примеров
    "kit",
    "template",
    "engine",
}


def commands(group: click.Group = main, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Все команды и группы: (), ("new",), …, ("theme", "get")."""
    found = [prefix]
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            found += commands(command, prefix + (name,))
        else:
            found.append(prefix + (name,))
    return found


ALL = commands()
NAMES = {part for path in ALL for part in path}


def foreign_latin(text: str) -> list[str]:
    """Латинские слова русского текста вне токенов.

    Токен — то, что набирают как есть: `в обратных кавычках`, флаг (-x, --x),
    слово с точкой, слешем, подчёркиванием, цифрой и прочими знаками путей и
    ключей, значение в кавычках click ('--x', 'de'), имя команды, слово из TOKENS.
    """
    text = re.sub(r"-\n\s*", "-", text)  # click переносит по дефису: --no-⏎agents
    text = re.sub(r"`[^`]*`", " ", text)
    bad = []
    for chunk in text.split():
        if chunk.startswith(("'", '"')):
            continue
        core = chunk.lstrip("([«“").rstrip(".,;:!?)]»”")
        if not core or core.startswith("-"):
            continue
        if re.search(r"[./_=$<>|#{}\d@+%*'\\]", core):
            continue
        bad += [w for w in re.findall(r"[A-Za-z]{2,}", core) if w not in TOKENS | NAMES]
    return bad


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.delenv("HERON_DEBUG", raising=False)
    monkeypatch.setattr(cli, "in_container", lambda: False)
    return tmp_path


def run(*args: str, env: dict[str, str] | None = None):
    return CliRunner().invoke(main, list(args), env=env, prog_name="heron")


def site_yaml(folder: Path, notes: str) -> None:
    (folder / "site.yaml").write_text(
        f"site:\n  name: S\n  languages: [en]\nbuild:\n  notes: {notes}\n", encoding="utf-8"
    )


# --- справка всех команд: язык из трёх источников ---------------------------------


def _help(path: tuple[str, ...], source: str, lang: str, folder: Path):
    if source == "flag":
        return run(*path, "--notes", lang, "--help")
    if source == "env":
        return run(*path, "--help", env={"HERON_NOTES": lang})
    site_yaml(folder, lang)
    return run(*path, "--help")


@pytest.mark.parametrize("source", ["flag", "env", "site"])
@pytest.mark.parametrize("path", ALL, ids=lambda p: " ".join(p) or "heron")
def test_english_help_has_no_cyrillic(here, path, source):
    result = _help(path, source, "en", here)
    assert result.exit_code == 0, result.output
    assert "Usage: " in result.output and "Options:" in result.output
    lines = [line for line in result.output.splitlines() if CYRILLIC.search(line)]
    assert not lines, f"{' '.join(path) or 'heron'} --help (en, {source}): {lines}"


@pytest.mark.parametrize("source", ["flag", "env", "site"])
@pytest.mark.parametrize("path", ALL, ids=lambda p: " ".join(p) or "heron")
def test_russian_help_has_no_english_words(here, path, source):
    result = _help(path, source, "ru", here)
    assert result.exit_code == 0, result.output
    out = result.output
    assert out.startswith("Использование: heron") and "Параметры:" in out
    assert "Показать эту справку и выйти." in out
    bad = foreign_latin(out)
    assert not bad, f"{' '.join(path) or 'heron'} --help (ru, {source}): {sorted(set(bad))}"


def test_group_help_lists_commands_in_its_language(here):
    ru = run("--notes", "ru", "--help").output
    assert "Команды:" in ru and "КОМАНДА [АРГУМЕНТЫ]..." in ru
    assert "Собрать сайт в dist/" in ru
    en = run("--notes", "en", "--help").output
    assert "Commands:" in en and "COMMAND [ARGS]..." in en
    assert "Build the site into dist/" in en


def test_optional_arguments_are_bracketed(here):
    assert (
        "Использование: heron build [ПАРАМЕТРЫ] [ПУТЬ]"
        in run("build", "--notes", "ru", "-h").output
    )
    assert "Usage: heron page [OPTIONS] TYPE SLUG [PATH]" in run("page", "--help").output
    assert "heron docs [OPTIONS] [TOPIC] [FILE]" in run("docs", "--help").output


def test_default_and_range_labels(here):
    ru = run("serve", "--notes", "ru", "--help").output
    assert "[по умолчанию: 8000; 1<=x<=65535]" in ru
    assert "--port ПОРТ" in ru and "--workers N" in ru
    en = run("serve", "--help").output
    assert "[default: 8000; 1<=x<=65535]" in en and "--port PORT" in en


# --- порядок источников и место флага --------------------------------------------


def test_flag_beats_env_and_env_beats_site_yaml(here):
    site_yaml(here, "ru")
    assert run("build", "--help").output.startswith("Использование:")
    assert run("build", "--help", env={"HERON_NOTES": "en"}).output.startswith("Usage:")
    flag = run("build", "--notes", "ru", "--help", env={"HERON_NOTES": "en"})
    assert flag.output.startswith("Использование:")
    site_yaml(here, "en")
    assert run("build", "--help", env={"HERON_NOTES": "ru"}).output.startswith("Использование:")
    assert run("build", "--notes", "en", "--help", env={"HERON_NOTES": "ru"}).output.startswith(
        "Usage:"
    )


@pytest.mark.parametrize(
    "args",
    [
        ["build", "--help", "--notes", "ru"],  # --help раньше --notes
        ["build", "--notes=ru", "--help"],
        ["--notes", "ru", "build", "--help"],  # флаг у корня
        ["--notes", "en", "build", "--notes", "ru", "--help"],  # ближний побеждает
        ["theme", "get", "-h", "--notes", "ru"],
    ],
)
def test_notes_anywhere_sets_the_help_language(here, args):
    assert run(*args).output.startswith("Использование: heron")


def test_bad_or_missing_sources_fall_back_to_english(here):
    (here / "site.yaml").write_text("site: [\n", encoding="utf-8")  # не разбирается
    assert run("build", "--help").output.startswith("Usage:")
    assert run("build", "--help", env={"HERON_NOTES": "de"}).output.startswith("Usage:")
    assert run("build", "--notes", "de", "--help").exit_code == 0  # --help раньше проверки
    (here / "site.yaml").unlink()
    (here / "site.yaml").mkdir()  # папка вместо файла — не повод падать
    assert run("--help").output.startswith("Usage:")


def test_language_does_not_stick_to_the_command_object(here):
    """click кеширует --help на объекте команды: подпись не должна застыть."""
    first = run("check", "--notes", "ru", "--help").output
    second = run("check", "--notes", "en", "--help").output
    third = run("check", "--notes", "ru", "--help").output
    assert "Показать эту справку и выйти." in first and first == third
    assert "Show this message and exit." in second and not CYRILLIC.search(second)
    assert cli._UI.lang == "en"  # язык запуска не утекает в следующий


def test_version_line_is_the_same_in_both_languages(here):
    """`heron, version …` разбирают скрипты и CI: строка одна на оба языка."""
    ru = run("--version", env={"HERON_NOTES": "ru"})
    en = run("--version")
    assert ru.output == en.output and ru.output.startswith("heron, version ")
    assert "Показать версию и выйти." in run("--notes", "ru", "--help").output


# --- ошибки разбора аргументов (F18) ---------------------------------------------


@pytest.mark.parametrize(
    "args, ru_part, en_part",
    [
        (["new", "x", "--notes", "de", "-y"], "неверное значение '--notes'", "Invalid value"),
        (["build", "--bogus"], "нет такого параметра '--bogus'", "No such option"),
        (["nosuchcommand"], "нет такой команды 'nosuchcommand'", "No such command"),
        (["page", "page"], "не хватает аргумента", "Missing argument"),
        (["serve", "--port", "0"], "вне диапазона", "is not in the range"),
        (["build", "--workers", "x"], "не число", "is not a valid integer"),
        (["check", "a", "b"], "лишний аргумент", "unexpected extra argument"),
        (["build", "--out"], "нужно значение", "requires an argument"),
    ],
)
def test_click_errors_follow_the_language(here, args, ru_part, en_part):
    ru = run(*args, env={"HERON_NOTES": "ru"})
    assert ru.exit_code == 2
    assert "Ошибка: " in ru.output and ru_part in ru.output, ru.output
    assert "Справка: 'heron" in ru.output or "Использование:" not in ru.output
    assert not foreign_latin(ru.output), ru.output
    en = run(*args, env={"HERON_NOTES": "en"})
    assert en.exit_code == 2
    assert "Error: " in en.output and en_part in en.output, en.output
    assert not CYRILLIC.search(en.output), en.output


def test_file_where_a_folder_is_expected(here):
    (here / "file.txt").write_text("x", encoding="utf-8")
    ru = run("build", "file.txt", "--notes", "ru")
    assert ru.exit_code == 2 and "путь 'file.txt' - файл, а нужна папка" in ru.output
    en = run("build", "file.txt", "--notes", "en")
    assert "Directory 'file.txt' is a file." in en.output


def test_usage_error_raised_by_a_command_is_in_the_site_language(here):
    """Рамка click у ошибки, поднятой командой, — на языке её сайта, как и текст."""
    site_yaml(here, "ru")
    result = run("docs", "--all-langs")
    assert result.exit_code == 2
    assert "Ошибка: --all-langs работает только вместе с --export" in result.output
    init = run("init", ".", "--agents", "--no-agents")
    assert "Ошибка: --agents и --no-agents вместе не задаются" in init.output


def test_click_catalog_keys_are_real_click_strings():
    """Каждый перевод — строка, которую click действительно печатает.

    click переименовал строку — перевод перестал бы подставляться молча.
    """
    msgids: set[str] = set()
    for source in Path(click.__file__).parent.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("_", "ngettext")
            ):
                msgids |= {a.value for a in node.args if isinstance(a, ast.Constant)}
    msgids.add("required")  # click зовёт _(extra["required"]) со значением "required"
    missing = sorted(set(CLICK_RU) - msgids)
    assert not missing, missing


def test_click_modules_use_the_heron_catalog():
    import click.core
    import click.exceptions
    import click.formatting

    for module in (click.core, click.exceptions, click.formatting):
        assert module._ is cli._click_text
    assert click.exceptions.ngettext is cli._click_plural


# --- тексты справки — только из messages.py ---------------------------------------


def _objects():
    def walk(command: click.Command, path: str):
        yield path, command
        for param in command.params:
            yield f"{path} {param.opts or param.name}", param
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                yield from walk(sub, f"{path} {name}")

    yield from walk(main, "heron")


def test_every_help_text_is_a_message_key():
    """Ни одного литерала справки в cli.py: каждая подпись — ключ help_* на обоих языках."""
    problems = []
    for where, obj in _objects():
        attrs = ("help",) if isinstance(obj, click.Command) else ("help", "metavar")
        for attr in attrs:
            raw = obj.__dict__.get(f"_heron_{attr}", obj.__dict__.get(attr))
            if raw is None:
                if attr == "help" and not (isinstance(obj, click.Argument)):
                    problems.append(f"{where}: no {attr}")
                continue
            if not (isinstance(raw, str) and raw.startswith("help_")):
                problems.append(f"{where}: {attr}={raw!r}")
            elif raw not in TEXT["ru"] or raw not in TEXT["en"]:
                problems.append(f"{where}: {raw} missing in a language")
    assert not problems, problems


def test_help_keys_are_the_same_in_both_languages():
    ru = {key for key in TEXT["ru"] if key.startswith("help_")}
    en = {key for key in TEXT["en"] if key.startswith("help_")}
    assert ru == en
    assert len(ru) > 60
    for key in ru:
        assert not CYRILLIC.search(TEXT["en"][key]), key
        assert not foreign_latin(TEXT["ru"][key]), (key, foreign_latin(TEXT["ru"][key]))


@pytest.mark.parametrize("path", [p for p in ALL if p], ids=" ".join)
def test_every_command_takes_notes(here, path):
    command = main
    for name in path:
        command = command.commands[name]
    assert any("--notes" in param.opts for param in command.params), path


# --- --notes у команд работы с сайтом (F23) --------------------------------------


@pytest.mark.parametrize("command", ["check", "build", "serve", "page", "setup", "init"])
def test_folder_messages_follow_notes_outside_a_site(here, command):
    args = [command, "nosuch"] if command != "page" else ["page", "page", "x", "nosuch"]
    ru = run(*args, "--notes", "ru")
    assert ru.exit_code == 1 and "Папки nosuch нет." in ru.output, ru.output
    root = run("--notes", "ru", *args)
    assert "Папки nosuch нет." in root.output, root.output
    en = run(*args, "--notes", "en", env={"HERON_NOTES": "ru"})
    assert "There is no folder nosuch." in en.output and not CYRILLIC.search(en.output)


def test_check_and_build_messages_follow_notes(here):
    assert run("new", "s", "--notes", "en", "-y").exit_code == 0
    check = run("check", "s", "--notes", "ru")
    assert check.exit_code == 0, check.output
    assert "HERON" in check.output and "проверка s" in check.output
    assert "Ошибок нет." in check.output
    built = run("build", "s", "--notes", "ru")
    assert built.exit_code == 0, built.output
    assert "Собрано файлов:" in built.output
    plain = run("check", "s")
    assert "No errors." in plain.output and "checking s" in plain.output


def test_page_notes_sets_the_draft_comments_and_leaves_the_env_alone(here):
    assert run("new", "s", "--notes", "en", "-y").exit_code == 0
    made = run("page", "page", "about", "s", "--notes", "ru")
    assert made.exit_code == 0, made.output
    assert "Создана страница:" in made.output
    text = (here / "s" / "content" / "en" / "about.md").read_text(encoding="utf-8")
    assert "TODO: что человек получит на странице" in text
    assert "HERON_NOTES" not in os.environ
    again = run("page", "page", "faq", "s")
    assert "TODO: what the visitor gets" in (here / "s/content/en/faq.md").read_text("utf-8")
    assert "Page created:" in again.output


def test_docs_and_schema_follow_notes(here):
    ru = run("docs", "--search", "zzzz-nothing", "--notes", "ru")
    assert "в документации не нашлось" in ru.output
    en = run("docs", "--search", "zzzz-nothing", "--notes", "en", env={"HERON_NOTES": "ru"})
    assert "is not in the documentation" in en.output
    both = run("schema", "--site", "--theme", "--notes", "ru")
    assert both.exit_code == 2 and "Схема одна за раз" in both.output


def test_docs_fallback_note_and_contents_follow_notes(here):
    """F10, F11: пометка фолбэка и отметки оглавления — на языке запрошенной темы."""
    from heron import docs

    fallback = [t.name for t in docs.TOPICS if docs.resolve(t.name, "en").note]
    for name in fallback:
        first = run("docs", name, "--notes", "en").output.split("\n", 1)[0]
        assert first.startswith("[") and not CYRILLIC.search(first), (name, first)
    contents = run("docs", "--notes", "en").output
    assert not [line for line in contents.splitlines() if CYRILLIC.search(line)]
    other = [n for n in fallback if docs.resolve(n, "en").lang_used != "en"]
    for name in other:
        row = next(line for line in contents.splitlines() if line.startswith(f"  {name} "))
        assert row.endswith(")") and "(opens in " in row, row
    ru = run("docs", "--notes", "ru").output
    assert "(opens in" not in ru


# --- heron recipe на языке пояснений (F16, решение владельца) ----------------------


def _recipe(*args: str, env: dict[str, str] | None = None) -> str:
    result = run("recipe", *args, env=env)
    assert result.exit_code == 0, result.output
    return result.output


def test_recipe_in_english_has_no_cyrillic(here):
    text = _recipe("--notes", "en")
    lines = [line for line in text.splitlines() if CYRILLIC.search(line)]
    assert not lines, lines
    assert "nginx-unprivileged" in text
    assert 'echo "no $conf - rebuild the site with HERON 0.1.0 or newer"' in text


def test_recipe_in_russian_is_the_file_as_is(here):
    from heron.docs import recipe_text

    text = _recipe("--notes", "ru")
    assert text == recipe_text()
    assert text.startswith("# Образ готового сайта: nginx и статика")
    site_yaml(here, "ru")
    assert _recipe() == text  # build.notes текущей папки
    assert _recipe(env={"HERON_NOTES": "en"}) == _recipe("--notes", "en")


def test_recipe_translation_changes_only_comments_and_the_message():
    """Инструкции Dockerfile в обоих языках одни и те же, строка в строку."""
    from heron.cli import recipe_for

    def instructions(text: str) -> list[str]:
        return [
            line
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "echo" not in line
        ]

    ru, en = recipe_for("ru"), recipe_for("en")
    assert instructions(ru) == instructions(en)
    assert len(instructions(ru)) > 10
    assert en != ru


# --- site.yaml, который нельзя прочесть как конфиг (E15.S1.T9, E1) -------------------

# Справка и `--version` выбирают язык до HeronGroup.invoke, раньше рамки ошибок:
# любой сбой там — язык en, но не трейсбек. Строку --version разбирают
# .github/workflows/site-image.yml (sed по первой строке) и scripts/site.sh.
VERSION_LINE = re.compile(r"^heron, version ([0-9]+\.[0-9]+)\.[0-9].*$")

ODD_SITE_YAML = {
    "build-scalar": "site:\n  languages: [en]\nbuild: x\n",
    "build-list": "site:\n  languages: [en]\nbuild: [1]\n",
    "build-notes-list": "site:\n  languages: [en]\nbuild:\n  notes: [1]\n",
    "top-list": "- a\n- b\n",
    "top-scalar": "just a line of text\n",
    "empty": "",
    "site-list": "site: [x]\n",
    "languages-int": "site:\n  languages: 5\n",
}


def write_odd(folder: Path, case: str) -> None:
    if case == "binary":
        (folder / "site.yaml").write_bytes(bytes(range(256)) * 16)
    else:
        (folder / "site.yaml").write_text(ODD_SITE_YAML[case], encoding="utf-8")


ODD_CASES = [*ODD_SITE_YAML, "binary"]


def no_crash(result) -> None:
    """Вышла сама команда (SystemExit) или всё прошло — исключение не улетело."""
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        result.exc_info,
        result.output,
    )
    assert "Traceback" not in result.output, result.output


@pytest.mark.parametrize("case", ODD_CASES)
def test_version_works_whatever_is_in_site_yaml(here, case):
    write_odd(here, case)
    for args in (["--version"], ["-V"], ["--notes", "ru", "--version"]):
        result = run(*args)
        no_crash(result)
        assert result.exit_code == 0, result.output
        lines = result.output.splitlines()
        assert len(lines) == 1 and VERSION_LINE.match(lines[0]), result.output


@pytest.mark.parametrize("case", ODD_CASES)
def test_help_works_whatever_is_in_site_yaml(here, case):
    write_odd(here, case)
    for args in (["--help"], ["check", "--help"], ["build", "--help"]):
        result = run(*args)
        no_crash(result)
        assert result.exit_code == 0 and result.output.startswith("Usage: heron"), result.output
    ru = run("check", "--help", "--notes", "ru")
    assert ru.output.startswith("Использование: heron")  # флаг по-прежнему главнее


def test_help_lang_falls_back_to_english_on_any_error(here, monkeypatch):
    """Не только ValueError и OSError: любой сбой выбора языка — en."""
    import heron.scaffold

    site_yaml(here, "ru")

    def boom(_path):
        raise AttributeError("'str' object has no attribute 'get'")

    monkeypatch.setattr(heron.scaffold, "_declared", boom)
    assert cli._help_lang(["--help"]) == "en"
    assert run("--version").exit_code == 0
    assert run("--help").output.startswith("Usage: heron")


def test_help_does_not_read_a_huge_site_yaml(here, monkeypatch):
    """Огромный site.yaml справка и --version не разбирают: язык из флага, env или en."""
    import heron.scaffold

    site_yaml(here, "ru")
    monkeypatch.setattr(cli, "HELP_SITE_LIMIT", 16)

    read: list[Path] = []

    def must_not_read(path):
        # исключение здесь _help_lang проглотил бы; поэтому чтение записывается
        read.append(path)
        return None

    monkeypatch.setattr(heron.scaffold, "_declared", must_not_read)
    monkeypatch.setattr(heron.scaffold, "notes_in_text", must_not_read)
    assert cli._help_lang([]) == "en"
    assert cli._help_lang(["--notes", "ru"]) == "ru"
    assert run("--help").output.startswith("Usage: heron")
    assert run("--help", env={"HERON_NOTES": "ru"}).output.startswith("Использование: heron")
    assert VERSION_LINE.match(run("--version").output.strip())
    assert read == []  # site.yaml больше предела не читался ни разу


def test_help_site_yaml_of_normal_size_is_still_read(here):
    site_yaml(here, "ru")
    assert (here / "site.yaml").stat().st_size < cli.HELP_SITE_LIMIT
    assert cli._help_lang([]) == "ru"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="нужен mkfifo")
def test_version_does_not_hang_on_a_fifo_named_site_yaml(here):
    """FIFO вместо site.yaml: чтение повисло бы навсегда, --version обязана ответить."""
    import subprocess
    import sys

    os.mkfifo(here / "site.yaml")
    code = "import sys; from heron.cli import main; main(sys.argv[1:], prog_name='heron')"
    env = {k: v for k, v in os.environ.items() if k != "HERON_NOTES"}
    for args in (["--version"], ["--help"], ["check"]):
        done = subprocess.run(
            [sys.executable, "-c", code, *args],
            cwd=here,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "Traceback" not in done.stderr + done.stdout, done.stderr
        if args == ["--version"]:
            assert done.returncode == 0 and VERSION_LINE.match(done.stdout.strip()), done


@pytest.mark.parametrize("case", ["build-scalar", "build-list"])
def test_real_process_prints_no_traceback(here, case):
    """Тот же сайт в настоящем процессе: в выводе нет трейсбека, --version — одна строка."""
    import subprocess
    import sys

    write_odd(here, case)
    code = "import sys; from heron.cli import main; main(sys.argv[1:], prog_name='heron')"
    env = {k: v for k, v in os.environ.items() if k not in ("HERON_NOTES", "HERON_DEBUG")}
    for args in (["--version"], ["--help"], ["check"], ["build"]):
        done = subprocess.run(
            [sys.executable, "-c", code, *args],
            cwd=here,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        both = done.stdout + done.stderr
        assert "Traceback" not in both, both
        if args == ["--version"]:
            assert done.returncode == 0 and VERSION_LINE.match(done.stdout.strip()), both
        elif args == ["--help"]:
            assert done.returncode == 0 and done.stdout.startswith("Usage: heron"), both
        else:
            assert done.returncode == 1 and "Error E011: site.yaml is not valid" in both, both


# --- язык запуска не течёт между потоками (E15.S1.T9, W2) ---------------------------


def test_language_does_not_leak_between_threads(here):
    """Поток с ru не меняет язык другого потока: ни справку heron, ни строки click."""
    import threading

    import click.formatting

    ru_ready = threading.Event()
    other_done = threading.Event()
    seen: dict[str, object] = {}

    def russian() -> None:
        try:
            seen["a_lang"] = cli._lang("ru")
            ru_ready.set()
            other_done.wait(30)
            # свой язык поток держит, пока другой работал по-английски
            seen["a_after"] = cli._UI.lang
            seen["a_usage"] = click.formatting._("Usage:")
        finally:
            ru_ready.set()

    def english() -> None:
        try:
            ru_ready.wait(30)
            seen["b_lang"] = cli._UI.lang
            seen["b_usage"] = click.formatting._("Usage:")
            seen["b_help"] = say_help()
            command = click.Command(
                "x", params=[click.Option(["--x"], type=int)], callback=lambda x: None
            )
            try:
                command.main(["--x", "abc"], standalone_mode=False)
            except click.BadParameter as error:
                seen["b_error"] = error.format_message()
        finally:
            other_done.set()

    def say_help() -> str:
        ctx = click.Context(main, info_name="heron")
        return main.get_help(ctx)

    threads = [threading.Thread(target=russian), threading.Thread(target=english)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert seen["a_lang"] == "ru" and seen["a_after"] == "ru"
    assert seen["a_usage"] == "Использование:"
    assert seen["b_lang"] == "en" and seen["b_usage"] == "Usage:"
    assert "'abc' is not a valid integer." in str(seen["b_error"]), seen
    assert not CYRILLIC.search(str(seen["b_help"])), seen["b_help"]
    assert cli._UI.lang == "en"  # и в основном потоке язык прежний


def test_main_restores_the_language_of_its_thread(here):
    """main ставит язык токеном и возвращает тот, что был до него, даже если это ru."""
    cli._UI.lang = "ru"
    try:
        assert run("--notes", "en", "--help").output.startswith("Usage: heron")
        assert cli._UI.lang == "ru"
    finally:
        cli._UI.lang = "en"
    assert isinstance(cli._LANG.get(), str)
