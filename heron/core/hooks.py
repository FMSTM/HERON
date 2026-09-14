"""Реестр точек расширения.

Модули ядра и внешние плагины пишутся против одного набора хуков — разница
только в поставке. Это же не даёт набору разрастись: каждый новый хук требует
правки документа 21, а не одной строки в коде.

Хуки действуют только на этапе сборки. Плагина, который «принимает форму»,
не существует: в момент POST движок уже отработал и вышел.

Спецификация: docs/spec/21-engine.md, раздел 15.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

NAMES = (
    "on_config",
    "on_page_parsed",
    "on_tree_built",
    "on_page_rendered",
    "on_build_finished",
)

BLOCK = "block:"


@dataclass(slots=True)
class Hooks:
    """Кто на что подписан."""

    handlers: dict[str, list[Callable[..., Any]]] = field(default_factory=dict)
    filters: dict[str, Callable[..., Any]] = field(default_factory=dict)
    globals: dict[str, Any] = field(default_factory=dict)

    def on(self, name: str, handler: Callable[..., Any]) -> None:
        """Подписать обработчик на хук."""
        if name not in NAMES and not name.startswith(BLOCK):
            raise ValueError(
                f"неизвестный хук {name!r}; доступны: " + ", ".join([*NAMES, "block:<имя>"])
            )
        self.handlers.setdefault(name, []).append(handler)

    def filter(self, name: str, handler: Callable[..., Any]) -> None:
        self.filters[name] = handler

    def add_global(self, name: str, value: Any) -> None:
        self.globals[name] = value

    def call(self, name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Вызвать всех подписчиков по порядку регистрации."""
        return [handler(*args, **kwargs) for handler in self.handlers.get(name, [])]

    def block(self, kind: str):
        """Разборщик своего типа секции, если его кто-то предоставил."""
        handlers = self.handlers.get(f"{BLOCK}{kind}")
        return handlers[0] if handlers else None

    def has(self, name: str) -> bool:
        return bool(self.handlers.get(name))
