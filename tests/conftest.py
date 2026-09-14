"""Общие заготовки конфигов для тестов контрактов."""

from pathlib import Path

import pytest
import yaml

SITE_MIN = {
    "heron": ">=0.1,<0.2",
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
