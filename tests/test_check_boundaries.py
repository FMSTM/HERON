"""Граница ядра: исключение для словаря schema.org узкое (E18.S1.T6)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_boundaries.py"
_spec = importlib.util.spec_from_file_location("check_boundaries", SCRIPT)
assert _spec and _spec.loader
cb = importlib.util.module_from_spec(_spec)
sys.modules["check_boundaries"] = cb
_spec.loader.exec_module(cb)

FAKE = "zxqvwordfake"  # вымышленное запрещённое слово


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hashes = tmp_path / "hashes.txt"
    hashes.write_text(cb.entry_for(FAKE) + "\n", encoding="utf-8")
    monkeypatch.setattr(cb, "HASHES", hashes)
    monkeypatch.setattr(cb, "LOCAL", tmp_path / "none.txt")
    monkeypatch.chdir(tmp_path)

    def go(name: str, text: str) -> int:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return cb.main([name])

    return go


@pytest.mark.parametrize(
    "name",
    [
        "heron/setup/vocab.yaml",
        "tests/test_schema_validate.py",
        "docs/ru/guide/05-seo.md",
        "docs/en/spec/20-data-contract.md",
        "heron/schemaorg/schemaorg-29.3.json",
    ],
)
def test_schemaorg_file_is_not_checked_for_terms(run, name: str) -> None:
    assert run(name, f"type: {FAKE}\n") == 0


@pytest.mark.parametrize(
    "name",
    ["tests/test_other.py", "docs/ru/other.md", "heron/schemaorg/x.py", "heron/schemaorg/sub/x.json"],
)
def test_neighbour_paths_are_still_checked(run, name: str) -> None:
    assert run(name, f"type: {FAKE}\n") == 1


def test_ordinary_file_with_forbidden_word_fails(run) -> None:
    assert run("heron/core.py", f"# {FAKE}\n") == 1


def test_phone_still_caught_in_excluded_file(run) -> None:
    # номер собирается при запуске, чтобы сам тест не попадал под PHONE
    phone = "+" + "1" + "2345678901"
    assert run("heron/setup/vocab.yaml", f"tel: {phone}\n") == 1


def test_is_schemaorg_standard_is_exact() -> None:
    assert cb.is_schemaorg_standard("tests/test_schema_validate.py")
    assert not cb.is_schemaorg_standard("tests/test_other.py")
    assert not cb.is_schemaorg_standard("docs/ru/other.md")
    assert not cb.is_schemaorg_standard("heron/schemaorg/x.py")
