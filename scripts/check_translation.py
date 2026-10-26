"""Состояние перевода документации: docs/translation.yaml против docs/ru.

    python scripts/check_translation.py [--root <корень репозитория>]

Описание — docs/ru/spec/23-distribution.md, §10 «Два языка документации».
Для каждого файла docs/ru пересчитывается sha256 и сверяется с ``ru_sha256``
записи. Расхождение по смыслу статуса:

- ``current`` — русский изменился, перевод устарел;
- ``missing`` — перевода нет, но хеш ведётся тем же коммитом, что и правка;
- ``stale`` — хеш по определению от старого русского текста, не сверяется.

Сам статус ``missing`` или ``stale`` нарушением не считается: перевод ещё не
сделан. Файл docs/ru без записи и запись без файла — тоже расхождение.

На ветках beta и prod расхождение — ошибка (код 1), на остальных —
предупреждение (код 0). Ветка — переменная HERON_BRANCH (её задаёт CI, вид
``refs/heads/<ветка>`` тоже принимается), иначе ``git branch --show-current``.
Повреждённый translation.yaml и нечитаемый файл docs/ru — ошибка всегда.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

STRICT_BRANCHES = frozenset({"beta", "prod"})
STATUSES = frozenset({"current", "stale", "missing"})
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Broken(Exception):
    """translation.yaml не читается или не по форме."""


class Unreadable(Exception):
    """Файл docs/ru не читается: без него хеш не сверить."""


def branch(root: Path) -> str:
    name = os.environ.get("HERON_BRANCH", "").strip().removeprefix("refs/heads/")
    if name:
        return name
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def ru_files(root: Path) -> dict[str, str]:
    """Путь от docs/ru → sha256 содержимого. Скрытые файлы не в счёт."""
    ru = root / "docs" / "ru"
    found: dict[str, str] = {}
    for path in sorted(ru.rglob("*")):
        rel = path.relative_to(ru)
        if path.is_file() and not any(part.startswith(".") for part in rel.parts):
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise Unreadable(f"docs/ru/{rel.as_posix()}: {exc.strerror or exc}") from exc
            found[rel.as_posix()] = hashlib.sha256(data).hexdigest()
    return found


def entries(root: Path) -> dict[str, tuple[str, str]]:
    """Путь → (ru_sha256, en_status) из docs/translation.yaml."""
    path = root / "docs" / "translation.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise Broken(f"{path.name} не читается: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise Broken("нет списка files")
    result: dict[str, tuple[str, str]] = {}
    for number, item in enumerate(data["files"], start=1):
        if not isinstance(item, dict):
            raise Broken(f"запись {number} — не словарь")
        rel, sha, status = item.get("path"), item.get("ru_sha256"), item.get("en_status")
        if not isinstance(rel, str) or not rel:
            raise Broken(f"запись {number}: нет path")
        if not isinstance(sha, str) or not SHA256.match(sha):
            raise Broken(f"{rel}: ru_sha256 — не 64 шестнадцатеричных символа")
        if status not in STATUSES:
            raise Broken(f"{rel}: en_status {status!r}, ждём current | stale | missing")
        if rel in result:
            raise Broken(f"{rel}: запись повторяется")
        result[rel] = (sha, status)
    return result


def problems(root: Path) -> list[str]:
    real = ru_files(root)
    listed = entries(root)
    found: list[str] = []
    for rel, digest in real.items():
        if rel not in listed:
            found.append(
                f"{rel}: файла нет в translation.yaml — добавьте запись (en_status: missing)"
            )
            continue
        sha, status = listed[rel]
        if status == "stale" or sha == digest:
            continue
        if status == "current":
            found.append(
                f"{rel}: русский текст изменился, а запись current — перевод устарел; "
                f"переведите и обновите ru_sha256 или поставьте stale"
            )
        else:
            found.append(f"{rel}: ru_sha256 не совпадает с файлом, сейчас {digest}")
    for rel in listed:
        if rel not in real:
            found.append(f"{rel}: запись есть, файла в docs/ru нет — уберите запись")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args(argv).root
    try:
        found = problems(root)
    except Broken as exc:
        print(f"перевод: ошибка: docs/translation.yaml повреждён: {exc}", file=sys.stderr)
        return 1
    except Unreadable as exc:
        print(f"перевод: ошибка: не читается {exc}", file=sys.stderr)
        return 1
    name = branch(root) or "(ветка не определена)"
    if not found:
        print(f"перевод: ru_sha256 совпадают у всех {len(ru_files(root))} файлов docs/ru")
        return 0
    strict = name in STRICT_BRANCHES
    level = "ошибка" if strict else "предупреждение"
    for line in found:
        print(f"перевод: {level}: {line}", file=sys.stderr)
    tail = "в beta и prod так не уходит" if strict else "на beta и prod это ошибка"
    print(f"перевод: {len(found)} расхождений на ветке {name}; {tail}", file=sys.stderr)
    return 1 if strict else 0


if __name__ == "__main__":
    sys.exit(main())
