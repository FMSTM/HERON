"""Поверхность CLI: шесть команд и коды выхода."""

import pathlib

import pytest
import yaml
from click.testing import CliRunner

from heron import __version__
from heron.cli import main

EXPECTED = {"new", "init", "check", "serve", "build", "page"}


@pytest.fixture
def run(tmp_path, monkeypatch):
    """CLI, запущенный из чистой временной папки."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    return runner.invoke


def test_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_all_commands_registered():
    assert set(main.commands) >= EXPECTED


def test_new_then_build(run):
    created = run(main, ["new", "demo"])
    assert created.exit_code == 0, created.output
    built = run(main, ["build", "demo"])
    assert built.exit_code == 0, built.output
    assert "Files written" in built.output


def test_new_refuses_to_overwrite_a_busy_folder(run):
    run(main, ["new", "demo"])
    again = run(main, ["new", "demo"])
    assert again.exit_code == 1
    assert "heron init" in again.output


def test_init_adopts_existing_content(run):
    root = pathlib.Path("готовый")
    (root / "content" / "uk").mkdir(parents=True)
    (root / "content" / "uk" / "index.md").write_text(
        "---\ntitle: Є\nh1: Є\ndescription: Опис\n---\n\nТекст.\n", encoding="utf-8"
    )
    result = run(main, ["init", str(root)])
    assert result.exit_code == 0, result.output
    assert "content/ already has languages: uk" in result.output
    assert (root / "site.yaml").is_file()
    assert "languages: [uk]" in (root / "site.yaml").read_text(encoding="utf-8")
    assert "Є" in (root / "content" / "uk" / "index.md").read_text(encoding="utf-8")


def _content_with_images(root: pathlib.Path) -> None:
    """Выгрузка с сайта: страница в content/ru и картинки рядом, в content/images."""
    (root / "content" / "ru").mkdir(parents=True)
    (root / "content" / "images").mkdir()
    (root / "content" / "ru" / "index.md").write_text(
        "---\ntitle: Я\nh1: Я\ndescription: Описание\n---\n\nТекст.\n", encoding="utf-8"
    )
    (root / "content" / "images" / "a.png").write_bytes(b"png")


def _no_language_from_images(root: pathlib.Path) -> None:
    assert not (root / "content" / "images" / "index.md").exists()
    assert not (root / "content" / "images" / "404.md").exists()
    assert not (root / "theme" / "i18n" / "images.yaml").exists()


def _block(output: str, title: str) -> list[str]:
    """Строки сводки под заголовком: идут с отступом, блок кончается первой без него."""
    lines = output.splitlines()
    if title not in lines:
        return []
    block = []
    for line in lines[lines.index(title) + 1 :]:
        if not line.startswith("  "):
            break
        block.append(line.strip())
    return block


def test_init_force_takes_languages_from_language_folders_only(run):
    root = pathlib.Path("выгрузка")
    _content_with_images(root)

    result = run(main, ["init", str(root), "--force"])

    assert result.exit_code == 0, result.output
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    assert data["site"]["languages"] == ["ru"]
    assert data["site"]["default_lang"] == "ru"
    assert "languages: ru" in result.output
    assert "images" not in [x.strip() for x in result.output.replace(",", " ").split()]
    _no_language_from_images(root)
    assert (root / "content" / "images" / "a.png").read_bytes() == b"png"

    checked = run(main, ["check", str(root)])
    assert "does not look like one" not in checked.output
    assert "не похож на код языка" not in checked.output


@pytest.mark.parametrize(
    "broken",
    ["site: [не закрыта\n", "site:\n  name: Сайт\n  languages: []\n"],
    ids=["broken_yaml", "empty_languages"],
)
def test_init_with_unusable_site_yaml_makes_no_language_from_images(run, broken):
    root = pathlib.Path("выгрузка")
    _content_with_images(root)
    (root / "site.yaml").write_text(broken, encoding="utf-8")

    result = run(main, ["init", str(root)])

    assert result.exit_code == 0, result.output
    _no_language_from_images(root)
    # без --force свой site.yaml остаётся как был, а язык ru получает своё
    assert (root / "site.yaml").read_text(encoding="utf-8") == broken
    assert (root / "content" / "ru" / "404.md").is_file()


def test_init_force_shows_overwritten_apart_from_created(run):
    run(main, ["new", "demo"])
    root = pathlib.Path("demo")
    site_yaml = root / "site.yaml"
    own = site_yaml.read_text(encoding="utf-8").replace("demo.example", "own-domain.example")
    assert "own-domain.example" in own
    site_yaml.write_text(own, encoding="utf-8")
    (root / ".gitignore").unlink()

    result = run(main, ["init", str(root), "--force"])

    assert result.exit_code == 0, result.output
    overwritten = _block(result.output, "Overwritten (--force):")
    created = _block(result.output, "Created:")
    assert "~ site.yaml" in overwritten
    assert not any("site.yaml" in line for line in created)
    assert any(".gitignore" in line for line in created)
    assert not any(".gitignore" in line for line in overwritten)
    # значение --force прежнее: шаблон заменил свой site.yaml
    assert "own-domain.example" not in site_yaml.read_text(encoding="utf-8")


def test_init_force_with_only_overwritten_does_not_say_nothing_to_create(run):
    run(main, ["new", "demo"])

    result = run(main, ["init", "demo", "--force"])

    assert result.exit_code == 0, result.output
    assert "~ site.yaml" in _block(result.output, "Overwritten (--force):")
    assert "Created:" not in result.output
    assert "Nothing to create" not in result.output


def test_check_reports_and_exits_zero(run):
    run(main, ["new", "demo"])
    result = run(main, ["check", "demo"])
    assert result.exit_code == 0, result.output
    assert "Pages -" in result.output  # build.notes: en — отчёт по-английски


def test_strict_turns_warnings_into_failure(run):
    run(main, ["new", "demo"])
    page = pathlib.Path("demo/content/en/long.md")
    page.write_text(
        "---\ntitle: " + "д" * 80 + "\nh1: Довга\ndescription: Опис\n---\n\nТекст.\n",
        encoding="utf-8",
    )
    soft = run(main, ["check", "demo"])
    assert soft.exit_code == 0
    hard = run(main, ["check", "demo", "--strict"])
    assert hard.exit_code == 1
    assert "--strict" in hard.output


def test_broken_site_exits_with_one(run):
    run(main, ["new", "demo"])
    pathlib.Path("demo/content/en/bad.md").write_text("нет фронтматтера\n", encoding="utf-8")
    result = run(main, ["build", "demo"])
    assert result.exit_code == 1
    assert "E001" in result.output


def test_page_command_creates_a_draft(run):
    run(main, ["new", "demo"])
    result = run(main, ["page", "page", "нова", "demo"])
    assert result.exit_code == 1  # нелатинский слаг не пройдёт обход
    good = run(main, ["page", "page", "nova", "demo"])
    assert good.exit_code == 0, good.output
    text = pathlib.Path("demo/content/en/nova.md").read_text(encoding="utf-8")
    assert "title:" in text and "{#intro}" not in text


def test_page_refuses_unknown_type(run):
    run(main, ["new", "demo"])
    result = run(main, ["page", "неттакого", "slug", "demo"])
    assert result.exit_code == 1
    assert "E008" in result.output
