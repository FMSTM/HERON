"""Словарь сообщений ядра, разложенный по группам: heron/texts/<группа>.py.

Каждый модуль группы содержит только данные: `TEXT = {"ru": {...}, "en": {...}}`.
Новую группу регистрировать не нужно: её находит pkgutil.
"""

from __future__ import annotations

import importlib
import pkgutil


def groups() -> dict[str, dict[str, dict[str, str]]]:
    """Группа -> её TEXT."""
    found: dict[str, dict[str, dict[str, str]]] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        found[info.name] = module.TEXT
    return found


def load() -> dict[str, dict[str, str]]:
    """Сведённый словарь всех групп: язык -> ключ -> шаблон."""
    merged: dict[str, dict[str, str]] = {}
    for table in groups().values():
        for lang, texts in table.items():
            merged.setdefault(lang, {}).update(texts)
    return merged
