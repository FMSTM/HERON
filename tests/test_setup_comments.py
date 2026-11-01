"""Анкета сохраняет комментарии автора в site.yaml и не трогает чужие ключи."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from heron import setup
from heron.scaffold import create
from heron.setup.answers import read

KEY = re.compile(r"^(\s*)(?:- )?(\"[^\"]*\"|'[^']*'|[^\s#:\"'\-][^:#]*?):(?:\s|$)")

# Ручной файл автора: комментарии над ключами, в конце строки, в конце блока,
# пустые разделы и ключи, которыми анкета не управляет.
MANUAL = """\
# Мой сайт: правлю руками, не удалять.
heron: ">=0.1"

# --- сайт ---
site:
  name: Dr. Example   # имя в шапке
  domain: example.test
  # язык по умолчанию
  default_lang: en
  languages: [en]
  # конец блока site

organization:
  name: Dr. Example

# контакты врача
contact:
  phone: "+00 000 000 00 00"
  # адрес приёма
  street: Main street 1

# пустой раздел, наполню позже
custom:

# разметка, анкета её не трогает
schema:
  entity:
    "@type": IndividualPhysician
    # телефон из контактов
    telephone: "{{ contact.phone }}"
    sameAs:
      # основной профиль
      - https://profile.example.test/x  # профиль

# финальный комментарий файла
"""


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _comments(text: str) -> list[tuple[str, str]]:
    """Множество комментариев: (текст, путь ключа, к которому привязаны)."""
    found: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    pending: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            pending.append(stripped)
            continue
        match = KEY.match(line)
        if not match and stripped.startswith("- "):
            indent = _indent(line)
            owner = ".".join(n for i, n in stack if i < indent)
            path = f"{owner}[-]"
            found += [(c, path) for c in pending]
            pending = []
            inline = re.search(r"\s#\s.*$", line)
            if inline:
                found.append((inline.group(0).strip(), path))
            continue
        if not match:
            continue
        indent = len(match.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, match.group(2)))
        path = ".".join(name for _, name in stack)
        found += [(c, path) for c in pending]
        pending = []
        inline = re.search(r"\s#\s.*$", line)
        if inline:
            found.append((inline.group(0).strip(), path))
    found += [(c, "<end>") for c in pending]
    return sorted(found)


def _config(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text("utf-8"))


def _text(root: Path) -> str:
    return (root / "site.yaml").read_text("utf-8")


def _resave(root: Path, change=None) -> str:
    data = read(setup.raw_config(root)).model_dump()
    if change:
        change(data)
    setup.apply(root, setup.Answers.model_validate(data))
    return _text(root)


def _rename(data: dict) -> None:
    data["site"]["name"] = "Renamed Example"


def _scaffold(tmp_path: Path, notes: str) -> Path:
    root = tmp_path / notes
    create(root, name="S", languages=["en"], demo=True, notes=notes)
    return root


def _manual(tmp_path: Path) -> Path:
    root = _scaffold(tmp_path, "en")
    (root / "site.yaml").write_text(MANUAL, encoding="utf-8")
    return root


@pytest.mark.parametrize("notes", ["ru", "en"])
def test_scaffold_comments_survive_save(tmp_path, notes):
    root = _scaffold(tmp_path, notes)
    before = _text(root)
    assert _comments(before), "фикстура heron new должна содержать комментарии"
    after = _resave(root, _rename)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert _comments(after) == _comments(before)


def test_manual_file_comments_survive_save(tmp_path):
    root = _manual(tmp_path)
    before = _text(root)
    assert len(_comments(before)) >= 8
    after = _resave(root, _rename)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert _comments(after) == _comments(before)
    for needle in ("# Мой сайт: правлю руками", "# конец блока site", "# пустой раздел"):
        assert needle in after


def test_unmanaged_keys_untouched(tmp_path):
    root = _manual(tmp_path)
    before = _config(root)
    after_text = _resave(root, _rename)
    after = yaml.safe_load(after_text)
    assert after["schema"] == before["schema"]
    assert "custom" in after and after["custom"] is None
    # блок schema остаётся в тексте как был, байт в байт
    block = MANUAL[MANUAL.index("schema:\n") : MANUAL.index("# профиль\n") + len("# профиль\n")]
    assert block in after_text


@pytest.mark.parametrize("notes", ["ru", "en", "manual"])
def test_repeat_save_is_idempotent(tmp_path, notes):
    root = _manual(tmp_path) if notes == "manual" else _scaffold(tmp_path, notes)
    first = _resave(root, _rename)
    second = _resave(root, _rename)
    assert second == first
    assert _resave(root) == first


def test_file_without_comments_saved_as_before(tmp_path):
    root = _scaffold(tmp_path, "en")
    data = _config(root)
    (root / "site.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    assert not _comments(_text(root))
    after = _resave(root, _rename)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert after.startswith(setup.HEADER["en"])
    assert _resave(root) == after
