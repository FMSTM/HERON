"""Поверхность CLI: команды на месте, версия печатается."""

from click.testing import CliRunner

from heron import __version__
from heron.cli import main

EXPECTED = {"new", "init", "check", "serve", "build", "page"}


def test_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_all_commands_registered():
    assert set(main.commands) >= EXPECTED


def test_unimplemented_exits_with_task_id():
    result = CliRunner().invoke(main, ["check"])
    assert result.exit_code == 2
    assert "E5.S1.T1" in result.output
