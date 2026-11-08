"""Вывод в терминал без управляющих последовательностей из чужого текста.

Тема, демо и контент - чужой текст: подсказка темы с `ESC ] 52 ; c ; … BEL`
пишет в буфер обмена, `ESC [ 2 J` стирает экран, `\\r` затирает строку и
подделывает вывод. Поэтому весь вывод команды идёт через `Stream`: управляющие
символы C0 и C1 (кроме `\\n` и `\\t`) печатаются видимыми (`\\x1b`), а не
исполняются - одним местом, а не у каждого `click.echo`.

Своё оформление движка (цвет, жирный, очистка строки у хода сборки) помечено
меткой процесса: `install` подменяет `click.style`, и код ESC в его выводе
становится меткой; `Stream` превращает метку обратно в ESC, только если вывод -
терминал (иначе убирает, как убирал click). Метка случайная на каждый запуск,
текст темы её не знает и подделать не может.

Спецификация: docs/ru/spec/21-engine.md, §11 («Вывод в терминал»).
"""

from __future__ import annotations

import contextlib
import re
import secrets
import sys
from collections.abc import Iterator
from typing import Any

import click

# управляющие символы C0 (без \t и \n), DEL и C1
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# метка своего ESC: символы из области частного использования, случайные на запуск
MARK = "".join(chr(0xE000 + secrets.randbelow(0x1800)) for _ in range(8))
OURS = re.compile(re.escape(MARK) + r"(\[[0-9;]*[A-Za-z]|\r)")
CR = MARK + "\r"  # возврат в начало строки (живая строка хода сборки)
EL = MARK + "[K"  # стереть до конца строки


def visible(char: str) -> str:
    return f"\\x{ord(char):02x}"


def clean(text: str) -> str:
    """Текст без управляющих символов: они видны как `\\x1b`, а не исполняются."""
    return CONTROL.sub(lambda match: visible(match.group()), text.replace("\r\n", "\n"))


def controls(text: str) -> list[str]:
    """Управляющие символы в тексте (`\\x1b`, `\\x07`), по одному разу, по порядку."""
    found: list[str] = []
    for char in CONTROL.findall(text.replace("\r\n", "\n")):
        if visible(char) not in found:
            found.append(visible(char))
    return found


class Stream:
    """Поток вывода, который пропускает только своё оформление движка."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def write(self, text: Any) -> int:
        if not isinstance(text, str):
            raise TypeError("text stream")  # click так узнаёт текстовый поток
        tty = self._tty()
        out: list[str] = []
        pos = 0
        for match in OURS.finditer(text):
            out.append(clean(text[pos : match.start()]))
            sequence = match.group(1)
            if tty:
                out.append(sequence if sequence == "\r" else "\x1b" + sequence)
            pos = match.end()
        out.append(clean(text[pos:]))
        self._inner.write("".join(out))
        return len(text)

    def writelines(self, lines: Any) -> None:
        for line in lines:
            self.write(line)

    def _tty(self) -> bool:
        try:
            return bool(self._inner.isatty())
        except (AttributeError, ValueError, OSError):
            return False

    def isatty(self) -> bool:
        return self._tty()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _style(original):
    probe = "heron"

    def style(text: Any, *args: Any, **kwargs: Any) -> str:
        styled = original(probe, *args, **kwargs)
        head, _, tail = styled.partition(probe)
        return head.replace("\x1b", MARK) + str(text) + tail.replace("\x1b", MARK)

    style.__wrapped__ = original  # type: ignore[attr-defined]
    return style


@contextlib.contextmanager
def guarded() -> Iterator[None]:
    """На время команды: stdout и stderr через `Stream`, оформление click - с меткой."""
    if isinstance(sys.stdout, Stream):
        yield
        return
    saved = sys.stdout, sys.stderr, click.style, click.termui.style
    sys.stdout, sys.stderr = Stream(sys.stdout), Stream(sys.stderr)
    click.style = click.termui.style = _style(saved[2])
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved[0], saved[1]
        click.style, click.termui.style = saved[2], saved[3]
