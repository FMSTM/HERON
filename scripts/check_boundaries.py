#!/usr/bin/env python3
"""Граница ядра: движок не знает ни про один конкретный сайт.

Падает, если в файлах репозитория встретилось имя сайта, клиента, раздела
конкретного сайта или настоящий телефонный номер.

Сами имена в публичном репозитории не хранятся — только их SHA-256
(`scripts/boundary-hashes.txt`). Текст режется на слова (буквы и цифры,
регистр и форма Unicode не важны), и хешируются:

- начала каждого слова длиной от 4 знаков, с пометкой `^` — так одна запись
  ловит и слово, и все его продолжения: `сайтов`, `сайтом`;
- сочетания из двух и трёх подряд идущих слов через пробел — так ловятся
  имена из нескольких слов и имена с дефисом или точкой.

Добавить запись (в репозиторий уходит только хеш):

    python3 scripts/check_boundaries.py --hash "имя сайта"

Локально, вне репозитория, можно держать и регулярные выражения:
`scripts/boundary-patterns.local.txt` (в .gitignore), по одному на строку.

Без аргументов проверяется всё дерево `git ls-files`, с аргументами —
только названные файлы (так зовёт pre-commit).

Обоснование: docs/spec/23-distribution.md, раздел 9.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
HASHES = HERE / "boundary-hashes.txt"
LOCAL = HERE / "boundary-patterns.local.txt"
SKIP = {"scripts/boundary-hashes.txt", "uv.lock"}

WORD = re.compile(r"[^\W_]+", re.UNICODE)
# Настоящий международный номер. Вымышленные в тестах и доках пишутся
# нулями: +00 000 000 00 00.
PHONE = re.compile(r"\+[1-9][0-9]{10,12}\b")
PREFIX_MIN = 4


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def entry_for(phrase: str) -> str:
    """Хеш записи: одно слово — как начало слова, несколько — как сочетание."""
    words = WORD.findall(normalize(phrase))
    if not words:
        raise SystemExit("в записи нет ни одного слова")
    if len(words) == 1:
        return digest("^" + words[0])
    return digest(" ".join(words))


def load() -> set[str]:
    out: set[str] = set()
    for line in HASHES.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def hits(text: str, known: set[str], cache: dict[str, bool]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if PHONE.search(line.replace(" ", "")):
            found.append((number, line.strip()))
            continue
        words = WORD.findall(normalize(line))
        bad = False
        for word in words:
            if word not in cache:
                cache[word] = any(
                    digest("^" + word[:size]) in known for size in range(PREFIX_MIN, len(word) + 1)
                )
            if cache[word]:
                bad = True
                break
        if not bad:
            for size in (2, 3):
                for start in range(len(words) - size + 1):
                    if digest(" ".join(words[start : start + size])) in known:
                        bad = True
                        break
                if bad:
                    break
        if bad:
            found.append((number, line.strip()))
    return found


def local_patterns() -> list[re.Pattern[str]]:
    if not LOCAL.is_file():
        return []
    out = []
    for line in LOCAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(re.compile(line, re.IGNORECASE))
    return out


def files_to_check(args: list[str]) -> list[str]:
    if args:
        return args
    listed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [line for line in listed.stdout.splitlines() if line]


def main(argv: list[str]) -> int:
    if argv[:1] == ["--hash"]:
        for phrase in argv[1:]:
            print(entry_for(phrase))
        return 0

    known = load()
    extra = local_patterns()
    cache: dict[str, bool] = {}
    failed = False
    for name in files_to_check(argv):
        path = Path(name)
        if name in SKIP or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # бинарные файлы
        found = hits(text, known, cache)
        for pattern in extra:
            found += [
                (n, line.strip())
                for n, line in enumerate(text.splitlines(), 1)
                if pattern.search(line)
            ]
        if found:
            failed = True
            print(f"ГРАНИЦА ЯДРА НАРУШЕНА: {name}", file=sys.stderr)
            for number, line in sorted(set(found))[:10]:
                print(f"    {number}: {line[:120]}", file=sys.stderr)

    if failed:
        print(
            "\nЯдро не должно знать о конкретных сайтах. Варианты:\n"
            "  - вынести специфичное в тему, content/ или site.yaml сайта;\n"
            "  - в тестах и доках — вымышленные имена, example.com, телефоны нулями;\n"
            "  - если запись устарела — править scripts/boundary-hashes.txt осознанно.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
