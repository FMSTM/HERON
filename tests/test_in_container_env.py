"""Режим образа в тестах: `/.dockerenv` не в счёт при HERON_IGNORE_DOCKERENV=1 (аудит TEST-01).

Внутри docker-прогона тестов `/.dockerenv` есть всегда, и без переопределения
CLI печатал подсказки `docker run …` и слушал `0.0.0.0` - 15 тестов падали.
"""

from __future__ import annotations

import os
from pathlib import Path

from heron import cli


def _dockerenv(monkeypatch, exists: bool) -> None:
    real = Path.exists

    def fake(self):
        return exists if str(self) == "/.dockerenv" else real(self)

    monkeypatch.setattr(Path, "exists", fake)


def test_conftest_sets_the_override_for_the_whole_run():
    assert os.environ.get(cli.IGNORE_DOCKERENV_ENV) == "1"


def test_dockerenv_is_ignored_with_the_override(monkeypatch):
    _dockerenv(monkeypatch, True)
    monkeypatch.delenv(cli.CONTAINER_ENV, raising=False)
    monkeypatch.setenv(cli.IGNORE_DOCKERENV_ENV, "1")
    assert cli.in_container() is False


def test_dockerenv_counts_without_the_override(monkeypatch):
    _dockerenv(monkeypatch, True)
    monkeypatch.delenv(cli.CONTAINER_ENV, raising=False)
    monkeypatch.delenv(cli.IGNORE_DOCKERENV_ENV, raising=False)
    assert cli.in_container() is True


def test_explicit_container_mode_wins_over_the_override(monkeypatch):
    _dockerenv(monkeypatch, False)
    monkeypatch.setenv(cli.CONTAINER_ENV, "1")
    monkeypatch.setenv(cli.IGNORE_DOCKERENV_ENV, "1")
    assert cli.in_container() is True


def test_no_dockerenv_no_container(monkeypatch):
    _dockerenv(monkeypatch, False)
    monkeypatch.delenv(cli.CONTAINER_ENV, raising=False)
    monkeypatch.delenv(cli.IGNORE_DOCKERENV_ENV, raising=False)
    assert cli.in_container() is False
