"""Шаг назад в опросах терминала: `<` - вернуться к предыдущему вопросу.

Опрос - обычный код, который задаёт вопросы по ходу (`new` и `init`, `page add`,
`category add`). Отмотать такой код назад нельзя, а пройти заново - можно:
каждый ответ записан, и опрос начинается сначала, получая записанные ответы
без вопросов, до вопроса перед тем, на котором ввели `<`. Его спрашивают
вживую, и в скобках стоит ответ, данный раньше: Enter его оставляет. Ответы
на вопросы дальше тоже не теряются: когда опрос снова до них дойдёт, они стоят
в скобках.

Повтор молчит: всё, что опрос печатает по пути, копится, и на экран выходит
только то, что относится к вопросу, к которому вернулись (заголовок группы,
подсказка поля). До последнего «записать?» опросы ничего не пишут на диск, так
что повтор ничего не трогает.

Вопрос узнаётся по ключу (`key`): по нему ответ, данный раньше, находит своё
место, даже если подпись вопроса изменилась (домен по умолчанию следует за
названием). Повторный вопрос после отказа проверки (`again=True`) - тот же
вопрос: `<` на нём уводит к вопросу перед ним.

`<` - весь ответ целиком; `<b>` и `a < b` - обычный текст. Значение, которому
нужен именно `<`, вводится как `\\<` (а `\\<` - как `\\\\<`).

Спецификация: docs/ru/spec/21-engine.md, §10 («Опрос в терминале: шаг назад»).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

BACK = "<"
_ESCAPED = re.compile(r"\s*\\+<\s*")
_BRACKET = re.compile(r"\[[^\[\]]*\]\s*$")

T = TypeVar("T")


class Back(Exception):
    """Ввели `<`: опрос проходит заново с записанными ответами."""


def literal(raw: str) -> str:
    """Ответ как значение: `\\<` - это `<`, `\\\\<` - `\\<`; остальное как есть."""
    if _ESCAPED.fullmatch(raw):
        return raw.strip()[1:]
    return raw


def with_default(prompt: str, shown: str) -> str:
    """Подпись вопроса с ответом, данным раньше, в скобках вместо прежних."""
    found = _BRACKET.search(prompt)
    if found:
        return prompt[: found.start()] + f"[{shown}]"
    if prompt.rstrip().endswith("›"):
        head = prompt.rstrip()[:-1].rstrip()
        return f"{head} [{shown}] ›"
    return f"{prompt.rstrip()} [{shown}]"


@dataclass(slots=True)
class _Question:
    key: str
    answers: list[str] = field(default_factory=list)  # попытки по порядку; последняя - принята


class Steps:
    """Ввод опроса с шагом назад: `ask` вместо прямого вопроса, `echo` вместо печати.

    `ask(prompt)` - строка ответа как есть (терминал или сценарий теста), `echo` -
    печать с теми же аргументами, что дал опрос. `first` - что сказать на `<` у
    первого вопроса.
    """

    def __init__(self, ask: Callable[[str], str], echo: Callable[..., None], first: str) -> None:
        self._ask = ask
        self._echo = echo
        self._first = first
        self.log: list[_Question] = []  # вопросы этого прохода по порядку
        self._feed: list[_Question] = []  # что повторить без вопросов
        self._pos = 0
        self._tries = 0  # сколько попыток текущего повторяемого вопроса уже отдано
        self._quiet: list[tuple[tuple[Any, ...], dict[str, Any]]] | None = None
        self._kept: dict[str, str] = {}  # ключ вопроса - ответ, данный раньше
        self._default: str | None = None  # ответ в скобках у текущего живого вопроса

    # --- печать -------------------------------------------------------------------

    def echo(self, *args: Any, **kwargs: Any) -> None:
        if self._quiet is not None:
            self._quiet.append((args, kwargs))
            return
        self._echo(*args, **kwargs)

    def _live(self) -> None:
        """Повтор кончился: напечатать то, что относится к текущему вопросу."""
        held, self._quiet = self._quiet or [], None
        for remaining in self._feed[self._pos :]:
            last = remaining.answers[-1] if remaining.answers else ""
            if last.strip():
                self._kept.setdefault(remaining.key, last)
        self._feed, self._pos = [], 0
        for args, kwargs in held:
            self._echo(*args, **kwargs)

    # --- вопрос -------------------------------------------------------------------

    def ask(self, prompt: str, key: str | None = None, again: bool = False) -> str:
        """Ответ на вопрос; `<` - шаг назад (исключение `Back` для `run`)."""
        key = key if key is not None else prompt
        if self._quiet is not None:
            replayed = self._replay(key, again)
            if replayed is not None:
                return literal(replayed)
            self._live()
        if not again:
            self._default = self._kept.pop(key, None)
        while True:
            shown = with_default(prompt, self._default) if self._default else prompt
            raw = self._ask(shown)
            if raw.strip() == BACK:
                self._back(key, again)
                continue
            if raw.strip() == "" and self._default:
                raw = self._default
            if again and self.log:
                self.log[-1].answers.append(raw)
            else:
                self.log.append(_Question(key, [raw]))
            return literal(raw)

    def _replay(self, key: str, again: bool) -> str | None:
        """Записанный ответ, пока повтор идёт тем же путём; иначе None - спросить вживую."""
        if again:
            current = self.log[-1] if self.log else None
            if current is not None and self._tries < len(current.answers):
                self._tries += 1
                self._quiet = []
                return current.answers[self._tries - 1]
            return None
        if self._pos >= len(self._feed) or self._feed[self._pos].key != key:
            return None
        question = self._feed[self._pos]
        self._pos += 1
        self.log.append(_Question(question.key, list(question.answers)))
        self._tries = 1
        self._quiet = []  # печать до этого вопроса уже не нужна
        return question.answers[0]

    def _back(self, key: str, again: bool) -> None:
        current = len(self.log) - 1 if again else len(self.log)
        if current <= 0:
            self._echo(f"  {self._first}", "yellow")
            return
        if self._default:  # ответ, данный раньше на этот вопрос, ждёт и дальше
            self._kept.setdefault(key, self._default)
        target = self.log[current - 1]
        last = target.answers[-1] if target.answers else ""
        if last.strip():
            self._kept[target.key] = last
        else:
            self._kept.pop(target.key, None)
        self._feed = self.log[: current - 1]
        self._pos = 0
        self.log = []
        self._quiet = []
        raise Back

    def run(self, body: Callable[[], T], reset: Callable[[], None] = lambda: None) -> T:
        """Пройти опрос; на `<` - `reset()` (вернуть начальное состояние) и заново."""
        while True:
            try:
                result = body()
            except Back:
                reset()
                continue
            if self._quiet is not None:
                self._live()
            return result
