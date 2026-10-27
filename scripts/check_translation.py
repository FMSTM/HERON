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

Пара README репозитория: английский ``README.md`` и русский ``README.ru.md``
лежат в корне, не в docs/. Она ведётся отдельным списком ``root_files`` в том же
translation.yaml (ключ ``files`` остаётся перечнем docs/ru, его читает и ``heron
docs``): запись ``ru: README.ru.md``, ``en: README.md``, ``ru_sha256`` — хеш
README.ru.md, ``en_status`` — как у остальных; проверяется по тем же правилам.
Есть README.ru.md без записи или запись без файла — расхождение. Списка нет и
README.ru.md нет — пара не проверяется.

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
# Пара README репозитория: русский источник и английский перевод (корень, не docs/).
ROOT_RU = "README.ru.md"
ROOT_EN = "README.md"


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


def load(root: Path) -> dict:
    """Разобранный docs/translation.yaml (словарь)."""
    path = root / "docs" / "translation.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise Broken(f"{path.name} не читается: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise Broken("нет списка files")
    return data


def _sha_status(label: str, item: dict) -> tuple[str, str]:
    sha, status = item.get("ru_sha256"), item.get("en_status")
    if not isinstance(sha, str) or not SHA256.match(sha):
        raise Broken(f"{label}: ru_sha256 — не 64 шестнадцатеричных символа")
    if status not in STATUSES:
        raise Broken(f"{label}: en_status {status!r}, ждём current | stale | missing")
    return sha, status


def entries(root: Path) -> dict[str, tuple[str, str]]:
    """Путь → (ru_sha256, en_status) из docs/translation.yaml."""
    result: dict[str, tuple[str, str]] = {}
    for number, item in enumerate(load(root)["files"], start=1):
        if not isinstance(item, dict):
            raise Broken(f"запись {number} — не словарь")
        rel = item.get("path")
        if not isinstance(rel, str) or not rel:
            raise Broken(f"запись {number}: нет path")
        sha, status = _sha_status(rel, item)
        if rel in result:
            raise Broken(f"{rel}: запись повторяется")
        result[rel] = (sha, status)
    return result


def root_entries(root: Path) -> dict[str, tuple[str, str]]:
    """Пара README репозитория: русский файл → (ru_sha256, en_status) из ``root_files``.

    Допустима одна пара: README.ru.md → README.md; другие файлы корня не переводятся.
    """
    items = load(root).get("root_files", [])
    if not isinstance(items, list):
        raise Broken("root_files — не список")
    result: dict[str, tuple[str, str]] = {}
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise Broken(f"root_files, запись {number} — не словарь")
        if item.get("ru") != ROOT_RU or item.get("en") != ROOT_EN:
            raise Broken(
                f"root_files, запись {number}: ждём ru: {ROOT_RU} и en: {ROOT_EN}, "
                f"а не {item.get('ru')!r} и {item.get('en')!r}"
            )
        if ROOT_RU in result:
            raise Broken(f"{ROOT_RU}: запись повторяется")
        result[ROOT_RU] = _sha_status(ROOT_RU, item)
    return result


def root_real(root: Path) -> dict[str, str]:
    """Русский README корня → sha256; нет файла — пусто."""
    path = root / ROOT_RU
    if not path.is_file():
        return {}
    try:
        return {ROOT_RU: hashlib.sha256(path.read_bytes()).hexdigest()}
    except OSError as exc:
        raise Unreadable(f"{ROOT_RU}: {exc.strerror or exc}") from exc


def _compare(
    real: dict[str, str],
    listed: dict[str, tuple[str, str]],
    *,
    where: str,
    entry_hint: str,
) -> list[str]:
    """Файлы против записей: нет записи, устарел перевод, не тот хеш, нет файла."""
    found: list[str] = []
    for rel, digest in real.items():
        if rel not in listed:
            found.append(f"{rel}: файла нет в translation.yaml — {entry_hint}")
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
            found.append(f"{rel}: запись есть, файла в {where} нет — уберите запись")
    return found


def problems(root: Path) -> list[str]:
    found = _compare(
        ru_files(root),
        entries(root),
        where="docs/ru",
        entry_hint="добавьте запись (en_status: missing)",
    )
    found += _compare(
        root_real(root),
        root_entries(root),
        where="корне",
        entry_hint="добавьте запись в root_files (en_status: missing)",
    )
    # Запись current обещает английский файл: без README.md перевод не «current».
    for rel, (_, status) in root_entries(root).items():
        if status == "current" and not (root / ROOT_EN).is_file():
            found.append(f"{rel}: запись current, а английского {ROOT_EN} в корне нет")
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
        tail = f" и у {ROOT_RU}" if root_real(root) else ""
        print(f"перевод: ru_sha256 совпадают у всех {len(ru_files(root))} файлов docs/ru{tail}")
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
