"""Ход сборки.

Сборка сайта на полсотни картинок идёт минуту с лишним, и всё это время
человек смотрит в пустой терминал и не знает, работает движок или повис.
Тишина — это не «нет новостей», это «непонятно, что происходит».

Ядро не печатает: оно зовёт обработчик. Куда пойдёт текст — в терминал,
в лог или никуда — решает тот, кто запустил сборку.
"""

from __future__ import annotations

from typing import Protocol


class Progress(Protocol):
    """Приёмник сообщений о ходе работы."""

    def step(self, title: str) -> None:
        """Начался этап."""

    def done(self, detail: str = "") -> None:
        """Этап закончился. `detail` — чем именно, например «39 страниц»."""

    def tick(self, current: int, total: int, detail: str = "") -> None:
        """Продвижение внутри длинного этапа."""


class Silent:
    """Ничего не говорит. Для тестов и для вызова из кода."""

    def step(self, title: str) -> None: ...

    def done(self, detail: str = "") -> None: ...

    def tick(self, current: int, total: int, detail: str = "") -> None: ...
