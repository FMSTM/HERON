"""Общие заготовки конфигов для тестов контрактов."""

import os
from pathlib import Path

import pytest
import yaml

from heron import __version__
from heron.cli import IGNORE_DOCKERENV_ENV


def pytest_configure(config):
    """Тесты не наследуют режим образа от машины: `/.dockerenv` в docker-прогоне не в счёт.

    Ставится в окружение процесса до сбора тестов, поэтому видно и дочерним
    процессам (CLI через subprocess). Режим образа тест включает сам:
    `HERON_IN_CONTAINER=1` или подмена `heron.cli.in_container`.
    """
    os.environ.setdefault(IGNORE_DOCKERENV_ENV, "1")


_MAJOR, _MINOR = __version__.split(".")[:2]
# Требование под текущий движок: тесты не должны падать от подъёма версии.
_SPEC = f">={_MAJOR}.{_MINOR},<{_MAJOR}.{int(_MINOR) + 1}"

SITE_MIN = {
    "heron": _SPEC,
    "site": {"domain": "example.com", "theme": "demo", "default_lang": "uk", "languages": ["uk"]},
}

THEME_MIN = {"name": "demo", "version": "1.0"}


@pytest.fixture
def write_yaml(tmp_path: Path):
    def _write(name: str, data) -> Path:
        path = tmp_path / name
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            if not isinstance(data, str)
            else data,
            encoding="utf-8",
        )
        return path

    return _write
