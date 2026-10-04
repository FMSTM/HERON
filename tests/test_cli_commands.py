"""Поверхность CLI: шесть команд и коды выхода."""

import pathlib

import pytest
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
    assert "собрано файлов" in built.output


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
    assert "нашёл" in result.output
    assert (root / "site.yaml").is_file()
    assert "Є" in (root / "content" / "uk" / "index.md").read_text(encoding="utf-8")


def test_check_reports_and_exits_zero(run):
    run(main, ["new", "demo"])
    result = run(main, ["check", "demo"])
    assert result.exit_code == 0, result.output
    assert "Страниц —" in result.output


def test_strict_turns_warnings_into_failure(run):
    run(main, ["new", "demo"])
    page = pathlib.Path("demo/content/uk/long.md")
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
    pathlib.Path("demo/content/uk/bad.md").write_text("нет фронтматтера\n", encoding="utf-8")
    result = run(main, ["build", "demo"])
    assert result.exit_code == 1
    assert "E001" in result.output


def test_page_command_creates_a_draft(run):
    run(main, ["new", "demo"])
    result = run(main, ["page", "page", "нова", "demo"])
    assert result.exit_code == 1  # нелатинский слаг не пройдёт обход
    good = run(main, ["page", "page", "nova", "demo"])
    assert good.exit_code == 0, good.output
    text = pathlib.Path("demo/content/uk/nova.md").read_text(encoding="utf-8")
    assert "title:" in text and "{#intro}" not in text


def test_page_refuses_unknown_type(run):
    run(main, ["new", "demo"])
    result = run(main, ["page", "неттакого", "slug", "demo"])
    assert result.exit_code == 1
    assert "E008" in result.output
