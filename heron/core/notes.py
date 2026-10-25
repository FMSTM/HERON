"""Служебные записки внутри папки сайта и мусор операционной системы.

Записка `heron-readme.md` объясняет человеку, что класть в эту папку и чего
не класть. Имя зарезервировано и не пересекается с обычным `README.md`:
у него две беды. В `content/` он не становится страницей по случайности,
а не по правилу; в `static/` он уезжает в сеть, потому что эта папка
копируется байт в байт, и на сайте появляется `/README.md` — забытый
файл разработчика.

Правило одно на весь движок и без исключений по каталогам: файл с этим
именем движок не замечает нигде. Регистр не учитывается: на macOS и Windows
`Heron-README.md` — тот же файл.

Мусор операционной системы разбирается здесь же: `.DS_Store` попадает в
`static/` сам, без участия человека, и уезжает в сеть по той же причине.

Спецификация: docs/spec/20-data-contract.md, раздел 2.
"""

from __future__ import annotations

from pathlib import Path

NOTE = "heron-readme.md"

# Зарезервированные имена корня сайта: комплект инструкций для агентов
# (20 §1). Сборка, `check` и `serve` их не читают.
RESERVED_DIRS = ("agents",)
RESERVED_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")

# Мусор, который создают файловые менеджеры. В сборке ему делать нечего.
JUNK = {".ds_store", "thumbs.db", "desktop.ini"}


def is_note(name: str | Path) -> bool:
    """Записка ли это."""
    return Path(name).name.lower() == NOTE


def is_junk(name: str | Path) -> bool:
    """Мусор операционной системы."""
    return Path(name).name.lower() in JUNK


def skip(name: str | Path) -> bool:
    """Файл, которого движок не должен замечать ни в одной папке."""
    return is_note(name) or is_junk(name)


def is_reserved_root(site_root: Path, path: Path) -> bool:
    """Зарезервированное ли это имя корня сайта.

    True только для прямых детей корня с именами из RESERVED_DIRS и
    RESERVED_FILES (регистр — как в файловой системе). В отличие от NOTE,
    которая не замечается нигде, правило действует только в корне:
    `content/<язык>/agents.md` и `static/AGENTS.md` — обычные файлы своих
    папок (20 §1).
    """
    path = Path(path)
    if path.parent != Path(site_root):
        return False
    return path.name in RESERVED_DIRS or path.name in RESERVED_FILES
