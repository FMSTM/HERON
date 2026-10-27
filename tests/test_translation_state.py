"""Состояние перевода: пара README репозитория и отсутствие исключений missing.

docs/ru/spec/23-distribution.md §10: английский `README.md` и русский `README.ru.md`
лежат в корне. Пара ведётся в docs/translation.yaml отдельным списком `root_files`
(ключ `files` остаётся перечнем docs/ru), а scripts/check_translation.py сверяет
ru_sha256 с README.ru.md так же, как у файлов docs/ru. Первая часть — сам
репозиторий, вторая — скрипт на временных деревьях.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_translation.py"
CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- сам репозиторий ------------------------------------------------------------


def _repo_data() -> dict:
    return yaml.safe_load((ROOT / "docs" / "translation.yaml").read_text(encoding="utf-8"))


def test_repository_lists_the_readme_pair() -> None:
    """Пара README.ru.md → README.md есть в translation.yaml, current, хеш от README.ru.md."""
    pairs = _repo_data()["root_files"]
    assert pairs == [
        {
            "ru": "README.ru.md",
            "en": "README.md",
            "ru_sha256": hashlib.sha256((ROOT / "README.ru.md").read_bytes()).hexdigest(),
            "en_status": "current",
        }
    ]


def test_readme_pair_is_one_language_each() -> None:
    """README.md английский, README.ru.md русский: язык файла = язык темы `heron docs readme`."""
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    # единственная кириллица в английском — подпись ссылки на русский файл
    assert "[Русский](README.ru.md)" in english
    assert not CYRILLIC.search(english.replace("[Русский](README.ru.md)", ""))
    assert CYRILLIC.search((ROOT / "README.ru.md").read_text(encoding="utf-8"))


def test_no_missing_entries_in_the_repository() -> None:
    """После полного перевода missing нет нигде: beta и prod требуют current (E12.S7)."""
    data = _repo_data()
    statuses = [e["en_status"] for e in [*data["files"], *data["root_files"]]]
    assert statuses and "missing" not in statuses


def test_check_passes_on_beta_for_the_repository() -> None:
    done = _run(ROOT, "beta")
    assert done.returncode == 0, done.stderr
    assert "и у README.ru.md" in done.stdout


# --- скрипт на временных деревьях -----------------------------------------------

DOCS_RU = {"README.md": "# Читать первым\n"}
README_RU = "# Русский readme\n"
README_EN = "# English readme\n"


def _tree(
    tmp_path: Path,
    *,
    status: str = "current",
    readme_ru: str | None = README_RU,
    readme_en: str | None = README_EN,
    pair: dict[str, object] | None | bool = True,
) -> Path:
    """docs/ru, docs/translation.yaml и README корня; pair=True — запись пары по README_RU."""
    root = tmp_path / "repo"
    for rel, text in DOCS_RU.items():
        path = root / "docs" / "ru" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if readme_ru is not None:
        (root / "README.ru.md").write_text(readme_ru, encoding="utf-8")
    if readme_en is not None:
        (root / "README.md").write_text(readme_en, encoding="utf-8")
    data: dict[str, object] = {
        "files": [
            {"path": rel, "ru_sha256": _sha(text), "en_status": "current"}
            for rel, text in DOCS_RU.items()
        ]
    }
    if pair is True:
        data["root_files"] = [
            {
                "ru": "README.ru.md",
                "en": "README.md",
                "ru_sha256": _sha(README_RU),
                "en_status": status,
            }
        ]
    elif isinstance(pair, dict):
        data["root_files"] = [pair]
    _write(root, data)
    return root


def _write(root: Path, data: object) -> None:
    (root / "docs" / "translation.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _run(root: Path, branch: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "HERON_BRANCH"}
    env["HERON_BRANCH"] = branch
    env["GIT_CEILING_DIRECTORIES"] = str(root.parent)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _pair(**override: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ru": "README.ru.md",
        "en": "README.md",
        "ru_sha256": _sha(README_RU),
        "en_status": "current",
    }
    return base | override


@pytest.mark.parametrize("branch", ["dev", "beta", "prod"])
def test_matching_pair_passes_everywhere(tmp_path: Path, branch: str) -> None:
    done = _run(_tree(tmp_path), branch)
    assert done.returncode == 0, done.stderr
    assert "совпадают у всех 1 файлов docs/ru и у README.ru.md" in done.stdout
    assert done.stderr == ""


@pytest.mark.parametrize(
    ("branch", "code", "level"),
    [("beta", 1, "ошибка"), ("prod", 1, "ошибка"), ("dev", 0, "предупреждение")],
)
def test_changed_readme_ru_with_current_entry(
    tmp_path: Path, branch: str, code: int, level: str
) -> None:
    root = _tree(tmp_path)
    (root / "README.ru.md").write_text("# Русский readme, правка\n", encoding="utf-8")
    done = _run(root, branch)
    assert done.returncode == code
    assert (
        f"перевод: {level}: README.ru.md: русский текст изменился, а запись current" in done.stderr
    )
    assert "README.md:" not in done.stderr


def test_changed_readme_en_alone_is_not_a_problem(tmp_path: Path) -> None:
    """Хеш берётся от русского файла: правка английского README.md статуса не меняет."""
    root = _tree(tmp_path)
    (root / "README.md").write_text("# English readme, edited\n", encoding="utf-8")
    assert _run(root, "prod").returncode == 0


def test_stale_pair_is_not_compared(tmp_path: Path) -> None:
    root = _tree(tmp_path, status="stale")
    (root / "README.ru.md").write_text("# Русский, ушёл вперёд\n", encoding="utf-8")
    assert _run(root, "prod").returncode == 0


def test_missing_pair_with_wrong_hash_is_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path, pair=_pair(en_status="missing", ru_sha256="0" * 64))
    done = _run(root, "prod")
    assert done.returncode == 1
    assert f"README.ru.md: ru_sha256 не совпадает с файлом, сейчас {_sha(README_RU)}" in done.stderr


def test_readme_ru_without_entry(tmp_path: Path) -> None:
    done = _run(_tree(tmp_path, pair=False), "beta")
    assert done.returncode == 1
    assert (
        "README.ru.md: файла нет в translation.yaml — добавьте запись в root_files" in done.stderr
    )
    assert _run(_tree(tmp_path / "dev", pair=False), "dev").returncode == 0


def test_entry_without_readme_ru(tmp_path: Path) -> None:
    done = _run(_tree(tmp_path, readme_ru=None), "beta")
    assert done.returncode == 1
    assert "README.ru.md: запись есть, файла в корне нет — уберите запись" in done.stderr


def test_current_entry_without_english_readme(tmp_path: Path) -> None:
    done = _run(_tree(tmp_path, readme_en=None), "beta")
    assert done.returncode == 1
    assert "README.ru.md: запись current, а английского README.md в корне нет" in done.stderr


def test_tree_without_pair_and_without_readme_ru_is_unchanged(tmp_path: Path) -> None:
    """Старые деревья (только docs/ru) проверяются как раньше, без упоминания пары."""
    done = _run(_tree(tmp_path, pair=False, readme_ru=None, readme_en=None), "prod")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "перевод: ru_sha256 совпадают у всех 1 файлов docs/ru"


@pytest.mark.parametrize(
    ("pair", "text"),
    [
        (_pair(ru="OTHER.ru.md"), "root_files, запись 1: ждём ru: README.ru.md"),
        (_pair(en="OTHER.md"), "root_files, запись 1: ждём ru: README.ru.md"),
        (_pair(ru_sha256="abc"), "README.ru.md: ru_sha256 — не 64 шестнадцатеричных"),
        (_pair(en_status="done"), "README.ru.md: en_status 'done'"),
    ],
)
def test_broken_pair_fails_even_on_dev(tmp_path: Path, pair: dict[str, object], text: str) -> None:
    done = _run(_tree(tmp_path, pair=pair), "dev")
    assert done.returncode == 1
    assert "docs/translation.yaml повреждён" in done.stderr
    assert text in done.stderr


def test_root_files_must_be_a_list_of_mappings_without_duplicates(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    data = yaml.safe_load((root / "docs" / "translation.yaml").read_text(encoding="utf-8"))
    for bad, text in (
        ("README.ru.md", "root_files — не список"),
        (["README.ru.md"], "root_files, запись 1 — не словарь"),
        ([_pair(), _pair()], "README.ru.md: запись повторяется"),
    ):
        _write(root, data | {"root_files": bad})
        done = _run(root, "dev")
        assert done.returncode == 1, bad
        assert text in done.stderr, bad
