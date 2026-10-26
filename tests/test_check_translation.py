"""scripts/check_translation.py: docs/translation.yaml против настоящих docs/ru.

docs/ru/spec/23-distribution.md §10: расхождение ru_sha256 на beta и prod —
ошибка, на dev и прочих ветках — предупреждение; статус missing и stale сам по
себе не нарушение. Каждый тест строит дерево во временной папке.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_translation.py"

FILES = {"README.md": "# Читать первым\n", "spec/20.md": "# Контракт\n"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tree(tmp_path: Path, status: str = "missing", **sha: str) -> Path:
    """docs/ru из FILES и translation.yaml; sha переопределяет хеш записи."""
    root = tmp_path / "repo"
    for rel, text in FILES.items():
        path = root / "docs" / "ru" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    files = [
        {
            "path": rel,
            "ru_sha256": sha.get(rel.replace("/", "_").replace(".", "_"), _sha(text)),
            "en_status": status,
        }
        for rel, text in FILES.items()
    ]
    _write(root, {"files": files})
    return root


def _write(root: Path, data: object) -> None:
    (root / "docs" / "translation.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _entries(root: Path) -> list[dict[str, str]]:
    data = yaml.safe_load((root / "docs" / "translation.yaml").read_text(encoding="utf-8"))
    return data["files"]


def _run(root: Path, branch: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "HERON_BRANCH"}
    if branch is not None:
        env["HERON_BRANCH"] = branch
    env["GIT_CEILING_DIRECTORIES"] = str(root.parent)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("branch", ["dev", "beta", "prod", "feature/x"])
@pytest.mark.parametrize("status", ["missing", "current"])
def test_matching_hashes_pass_everywhere(tmp_path: Path, branch: str, status: str) -> None:
    done = _run(_tree(tmp_path, status), branch)
    assert done.returncode == 0, done.stderr
    assert "совпадают у всех 2 файлов" in done.stdout
    assert done.stderr == ""


@pytest.mark.parametrize(
    ("branch", "code", "level"),
    [
        ("beta", 1, "ошибка"),
        ("prod", 1, "ошибка"),
        ("dev", 0, "предупреждение"),
        ("e13-pre", 0, "предупреждение"),
    ],
)
def test_changed_current_file_by_branch(tmp_path: Path, branch: str, code: int, level: str) -> None:
    root = _tree(tmp_path, "current")
    (root / "docs/ru/spec/20.md").write_text("# Контракт, правка\n", encoding="utf-8")
    done = _run(root, branch)
    assert done.returncode == code
    assert f"перевод: {level}: spec/20.md: русский текст изменился, а запись current" in done.stderr
    assert "README.md" not in done.stderr
    assert f"1 расхождений на ветке {branch}" in done.stderr


def test_stale_hash_of_missing_entry_is_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path, "missing", README_md="0" * 64)
    done = _run(root, "prod")
    assert done.returncode == 1
    assert f"README.md: ru_sha256 не совпадает с файлом, сейчас {_sha(FILES['README.md'])}" in (
        done.stderr
    )


def test_stale_status_is_not_compared(tmp_path: Path) -> None:
    """stale: хеш от старого русского текста по определению, расхождение ожидаемо."""
    done = _run(_tree(tmp_path, "stale", README_md="0" * 64, spec_20_md="1" * 64), "prod")
    assert done.returncode == 0, done.stderr


def test_file_without_entry_and_entry_without_file(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "docs/ru/guide.md").write_text("# Новый\n", encoding="utf-8")
    entries = _entries(root)
    entries.append({"path": "old.md", "ru_sha256": "2" * 64, "en_status": "missing"})
    _write(root, {"files": entries})
    done = _run(root, "beta")
    assert done.returncode == 1
    assert "guide.md: файла нет в translation.yaml" in done.stderr
    assert "old.md: запись есть, файла в docs/ru нет" in done.stderr
    assert _run(root, "dev").returncode == 0


def test_hidden_files_are_ignored(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "docs/ru/.DS_Store").write_bytes(b"\0\1")
    assert _run(root, "prod").returncode == 0


@pytest.mark.parametrize(
    "data",
    [
        "files: [",
        {"files": "README.md"},
        {"files": [{"path": "README.md", "ru_sha256": "abc", "en_status": "missing"}]},
        {"files": [{"path": "README.md", "ru_sha256": "a" * 64, "en_status": "done"}]},
        {"files": [{"ru_sha256": "a" * 64, "en_status": "missing"}]},
        {
            "files": [
                {"path": "README.md", "ru_sha256": "a" * 64, "en_status": "stale"},
                {"path": "README.md", "ru_sha256": "a" * 64, "en_status": "stale"},
            ]
        },
    ],
)
def test_broken_translation_yaml_fails_even_on_dev(tmp_path: Path, data: object) -> None:
    root = _tree(tmp_path)
    if isinstance(data, str):
        (root / "docs/translation.yaml").write_text(data, encoding="utf-8")
    else:
        _write(root, data)
    done = _run(root, "dev")
    assert done.returncode == 1
    assert "docs/translation.yaml повреждён" in done.stderr


@pytest.mark.skipif(shutil.which("git") is None, reason="нет git")
@pytest.mark.parametrize(("branch", "code"), [("beta", 1), ("prod", 1), ("dev", 0)])
def test_branch_from_git_without_heron_branch(tmp_path: Path, branch: str, code: int) -> None:
    root = _tree(tmp_path, "current")
    (root / "docs/ru/README.md").write_text("# Правка\n", encoding="utf-8")
    subprocess.run(
        ["git", "-c", f"init.defaultBranch={branch}", "init", "-q", str(root)], check=True
    )
    done = _run(root, None)
    assert done.returncode == code
    assert f"на ветке {branch}" in done.stderr


def test_heron_branch_wins_over_git(tmp_path: Path) -> None:
    root = _tree(tmp_path, "current")
    (root / "docs/ru/README.md").write_text("# Правка\n", encoding="utf-8")
    if shutil.which("git"):
        subprocess.run(["git", "-c", "init.defaultBranch=dev", "init", "-q", str(root)], check=True)
    assert _run(root, "prod").returncode == 1


def test_repository_translation_yaml_is_current() -> None:
    """Сам репозиторий: проверка строгого режима проходит, как на prod."""
    done = _run(ROOT, "prod")
    assert done.returncode == 0, done.stderr
