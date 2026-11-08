"""Консольный опросник страницы и категории: те же поля и группы, что у студии.

Поля - `heron.edit.fields` по группам `heron.edit.groups`. У каждого поля
показано значение, которое останется, если ничего не вводить (Enter), рядом -
одна строка подсказки (`hint`); `?` печатает справку целиком (`help`), `-`
очищает поле. Проверка - на лету, теми же правилами, что у `heron check`
(`heron.edit.validate`): ошибка - поле спрашивается снова, предупреждение -
печатается и не мешает.

Основной язык спрашивается целиком; на остальных - только поля с текстом:
перевод сразу или Enter - пропустить. Пропущенное - пометка
`translation: pending` в SEO-блоке файла языка.

Ввод и вывод - через `Io`: консоль (`click`) или сценарий теста.

Спецификация: docs/ru/spec/21-engine.md, «Страницы и категории: page add, category add».
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import click

from heron.core.errors import HeronError
from heron.edit import entity as ops
from heron.edit.model import Field, groups
from heron.messages import say

# Группы, которые новичку не нужны каждый раз: открываются вопросом «изменить?».
FOLDED = ("menu", "cover", "social", "publishing", "schema")
SKIP = "?"  # справка
CLEAR = "-"  # очистить поле
NEW = "+"  # новая категория
YES = ("y", "yes", "1", "true", "on", "д", "да")
NO = ("n", "no", "0", "false", "off", "н", "нет")


class Cancelled(Exception):
    """Человек отказался записывать: ничего не меняется."""


@dataclass(slots=True)
class Io:
    """Ввод и вывод опросника: строка ответа и печать (цвет - необязательный)."""

    ask: Callable[[str], str]
    echo: Callable[..., None]

    @classmethod
    def terminal(cls) -> Io:
        def ask(prompt: str) -> str:
            return str(click.prompt(prompt, default="", show_default=False, prompt_suffix=" "))

        def echo(text: str = "", color: str | None = None, dim: bool = False, bold=False) -> None:
            click.secho(text, fg=color, dim=dim, bold=bold)

        return cls(ask, echo)


def _shown(value: Any, lang: str) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return say(lang, "edit_con_empty")
    if isinstance(value, bool):
        return say(lang, "edit_con_yes" if value else "edit_con_no")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return say(lang, "edit_con_items", count=len(value))
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}={v}" for k, v in value.items())
    text = " ".join(str(value).split())
    return text if len(text) <= 70 else text[:67] + "..."


def _current(item: Field) -> Any:
    return item.value if item.present and item.value not in (None, "") else item.default


def _parse(item: Field, raw: str, lang: str) -> Any:
    """Ответ строкой - в значение поля его типа; не разобрать - ValueError с текстом."""
    if raw == CLEAR:
        return None
    if item.type == "flag":
        low = raw.lower()
        if low in YES:
            return True
        if low in NO:
            return False
        raise ValueError(say(lang, "edit_con_bad_flag"))
    if item.type == "enum":
        values = item.limits.get("values") or []
        if raw.isdigit() and 0 < int(raw) <= len(values):
            return values[int(raw) - 1]
        return raw
    if item.type == "number":
        try:
            return int(raw)
        except ValueError as error:
            raise ValueError(say(lang, "edit_con_bad_number")) from error
    if item.type == "date":
        try:
            return dt.date.fromisoformat(raw).isoformat()
        except ValueError as error:
            raise ValueError(say(lang, "edit_con_bad_date")) from error
    if item.type == "list":
        return [part.strip() for part in raw.split(";") if part.strip()]
    if item.type == "schema":
        out: dict[str, str] = {}
        for part in raw.split(";"):
            name, sep, value = part.partition("=")
            if not sep or not name.strip():
                raise ValueError(say(lang, "edit_con_bad_schema"))
            out[name.strip()] = value.strip()
        return out
    return raw


def _askable(item: Field) -> bool:
    """Поле, которое опросник спрашивает строкой: список пунктов с полями - в файле или студии."""
    return not (item.type == "list" and item.fields)


class Console:
    """Один проход опросника по странице или категории на всех языках."""

    def __init__(self, entity: ops.Entity, io: Io, lang: str) -> None:
        self.entity = entity
        self.io = io
        self.lang = lang  # язык подсказок и сообщений опросника

    def _say(self, name: str, /, **values: Any) -> str:
        return say(self.lang, name, **values)

    # --- одно поле -------------------------------------------------------------

    def _hint(self, item: Field) -> None:
        hint = item.hint or ""
        need = f" {self._say('edit_con_required')}" if item.required else ""
        self.io.echo(f"  {item.path}{need}" + (f" - {hint}" if hint else ""), None, False, True)
        if item.type == "enum" and item.fields:
            for number, option in enumerate(item.fields, 1):
                tail = f" - {option['hint']}" if option.get("hint") else ""
                self.io.echo(f"    {number}  {option['name']}{tail}", None, True)

    def _help(self, item: Field) -> None:
        text = item.help or item.hint or self._say("edit_con_no_help")
        for line in str(text).splitlines():
            self.io.echo(f"    {line}", None, True)
        if item.example:
            self.io.echo(f"    {self._say('edit_con_example', example=item.example)}", None, True)

    def _issues(self, lang: str, path: str) -> list[Any]:
        found = ops.issues(self.entity, lang)
        return [i for i in found if i.path == path or i.path.startswith(path + ".")]

    def field(self, lang: str, item: Field, prompt_value: Any = None, hint: bool = True) -> bool:
        """Спросить поле; True - значение изменилось."""
        if hint:
            self._hint(item)
        if not item.editable:
            reason = item.readonly or "-"
            shown = _shown(item.value, self.lang)
            self.io.echo(
                f"    {shown}  ({self._say('edit_con_readonly', reason=reason)})", None, True
            )
            return False
        if not _askable(item):
            shown = _shown(item.value, self.lang)
            self.io.echo(f"    {shown}  ({self._say('edit_con_in_file')})", None, True)
            return False
        current = _current(item) if prompt_value is None else prompt_value
        while True:
            raw = self.io.ask(f"  › [{_shown(current, self.lang)}]").strip()
            if raw == "":
                return False
            if raw == SKIP:
                self._help(item)
                continue
            try:
                value = _parse(item, raw, self.lang)
            except ValueError as error:
                self.io.echo(f"    {error}", "yellow")
                continue
            before = dict(self.entity.pages)
            try:
                ops.set_value(self.entity, lang, item.path, value)
            except HeronError as error:
                self.io.echo(f"    {_text(error.message, self.lang)}", "yellow")
                self.entity.pages = before
                continue
            bad = False
            for issue in self._issues(lang, item.path):
                level = "red" if issue.level == "error" else "yellow"
                self.io.echo(f"    {issue.message.text(self.lang)}", level)
                bad = bad or issue.level == "error"
            if bad:
                self.entity.pages = before
                continue
            return True

    # --- категория и тип новой страницы -----------------------------------------

    def category(self) -> None:
        """Категория из дерева; номер с `+` - новая категория внутри выбранной."""
        nodes = ops.categories(self.entity.ctx)
        current = ops.parent_of(self.entity.target)
        self.io.echo(self._say("edit_con_category"), None, False, True)
        self.io.echo(f"    0  / - {self._say('edit_con_root')}", None, True)
        for number, node in enumerate(nodes, 1):
            pad = "  " * (node.depth - 1)
            title = f"  {node.title}" if node.title else ""
            self.io.echo(f"    {number}  {pad}{node.key}{title}", None, True)
        self.io.echo(f"    {self._say('edit_con_category_how')}", None, True)
        choices = [""] + [node.key for node in nodes]
        default = current if current in choices else ""
        while True:
            raw = self.io.ask(f"  › [{default or '/'}]").strip()
            if raw == "":
                choice = default
                break
            if raw == SKIP:
                self._help_named("category")
                continue
            base, plus = (raw[:-1], True) if raw.endswith(NEW) else (raw, False)
            if base == "" and plus:
                base = "0"
            if not base.isdigit() or int(base) >= len(choices):
                self.io.echo(f"    {self._say('edit_con_bad_choice')}", "yellow")
                continue
            choice = choices[int(base)]
            if plus:
                name = self.io.ask(f"  {self._say('edit_con_new_category', parent=choice or '/')}")
                try:
                    name = ops.norm_key(name)
                except HeronError as error:
                    self.io.echo(f"    {_text(error.message, self.lang)}", "yellow")
                    continue
                if not name:
                    continue
                choice = ops.join(choice, name)
                self.io.echo(f"    {self._say('edit_con_category_made', key=choice)}", None, True)
            break
        target = ops.join(choice, ops.name_of(self.entity.target))
        try:
            ops.move(self.entity, target)
        except HeronError as error:
            self.io.echo(f"    {_text(error.message, self.lang)}", "yellow")
            self.category()

    def _help_named(self, name: str) -> None:
        item = next(
            (f for f in ops.fields_of(self.entity, self.entity.ctx.default) if f.name == name), None
        )
        if item is not None:
            self._help(item)

    def page_type(self) -> None:
        """Тип новой страницы: от него зависят секции заготовки."""
        ctx = self.entity.ctx
        types = [t for t in ctx.contract.get("types", []) if t["name"] not in ("home", "404")]
        if len(types) <= 1:
            return
        current = self.entity.main.type
        self.io.echo(self._say("edit_con_type"), None, False, True)
        for number, info in enumerate(types, 1):
            tail = f" - {info['hint']}" if info.get("hint") else ""
            self.io.echo(f"    {number}  {info['name']}{tail}", None, True)
        names = [info["name"] for info in types]
        while True:
            raw = self.io.ask(f"  › [{current}]").strip()
            if raw == "":
                return
            if raw == SKIP:
                self._help_named("type")
                continue
            chosen = names[int(raw) - 1] if raw.isdigit() and 0 < int(raw) <= len(names) else raw
            if chosen not in names:
                self.io.echo(f"    {self._say('edit_con_bad_choice')}", "yellow")
                continue
            replaced = ops.retype(self.entity, chosen)
            self.entity.pages = replaced.pages
            return

    # --- язык целиком и перевод ---------------------------------------------------

    def language(self, lang: str, skip: tuple[str, ...] = ()) -> None:
        """Все поля языка по группам; свёрнутые группы - по вопросу «изменить?»."""
        page = ops.page_of(self.entity, lang)
        for group in groups(page):
            name = group["name"]
            items = [
                f
                for f in ops.fields_of(self.entity, lang)
                if f.group == name and f.name not in skip and f.path not in skip
            ]
            if not items:
                continue
            self.io.echo("")
            self.io.echo(f"{group['title']}", "cyan", False, True)
            if name in FOLDED:
                summary = "; ".join(
                    f"{f.name}: {_shown(_current(f), self.lang)}" for f in items[:4]
                )
                answer = self.io.ask(f"  {summary} - {self._say('edit_con_open_group')}").strip()
                if answer.lower() not in YES:
                    continue
            section = None
            for item in items:
                if item.section and item.section != section:
                    section = item.section
                    self.io.echo(f"  [{section}]", None, True)
                if item.name == "category" and item.where == "path":
                    if item.editable:
                        self.category()
                    continue
                # поле могло измениться после предыдущего ответа (секция добавлена)
                fresh = next(
                    (f for f in ops.fields_of(self.entity, lang) if f.path == item.path), item
                )
                self.field(lang, fresh)

    def translate(self, lang: str) -> None:
        """Поля с текстом на языке `lang`: перевод или Enter - пропустить (пометка pending)."""
        entity = self.entity
        created = entity.created(lang)
        self.io.echo("")
        key = "edit_con_translate_new" if created else "edit_con_translate"
        self.io.echo(self._say(key, lang=lang, main=entity.ctx.default), "cyan", False, True)
        main = {
            f.path: f for f in ops.fields_of(entity, entity.ctx.default, only_translatable=True)
        }
        given: set[str] = set()
        for item in ops.fields_of(entity, lang, only_translatable=True):
            source = main.get(item.path)
            if source is None or not ops._filled(source.value) or not _askable(item):
                continue
            self._hint(item)
            self.io.echo(f"    {entity.ctx.default}: {_shown(source.value, self.lang)}", None, True)
            shown = None if created else item.value
            if created:
                shown = self._say("edit_con_skip")
            if self.field(lang, item, prompt_value=shown, hint=False) or (
                not created and ops._filled(item.value) and item.value != source.value
            ):
                given.add(item.path)
        if created:
            left = ops.untranslated(entity, lang, given)
            ops.mark(entity, lang, bool(left))
        elif ops.is_pending(entity, lang):
            answer = self.io.ask(f"  {self._say('edit_con_ready', lang=lang)}").strip()
            if answer.lower() in YES:
                ops.mark(entity, lang, False)

    # --- весь проход ----------------------------------------------------------------

    def run(self, only: str | None = None, asked: tuple[str, ...] = ()) -> None:
        """Опросить: новая страница - категория, тип, основной язык, переводы; правка - так же.

        `only` - один язык целиком (`--lang`); `asked` - что уже задано флагами.
        """
        entity = self.entity
        ctx = entity.ctx
        head = "edit_con_head_new" if entity.new else "edit_con_head_edit"
        kind = self._say("edit_con_category_word" if entity.category else "edit_con_page_word")
        langs = ", ".join(
            f"{lang} ({self._say('edit_con_main')})" if lang == ctx.default else lang
            for lang in ctx.langs
        )
        self.io.echo(
            self._say(head, kind=kind, key=entity.target or "/", langs=langs), None, False, True
        )
        self.io.echo(self._say("edit_con_keys"), None, True)
        if only is not None and only != ctx.default:
            self.language(only, skip=("category",))
            return
        skip: tuple[str, ...] = ("type",) if entity.new else ()
        if entity.new:
            if "category" not in asked and not entity.category:
                self.category()
            if "type" not in asked:
                self.page_type()
            skip += ("category",)
        self.language(ctx.default, skip=skip)
        if only is not None:
            return
        for lang in ctx.langs[1:]:
            self.translate(lang)

    def confirm(self) -> bool:
        """Итог и вопрос «записать?»: что создаётся, что меняется, какие переводы не готовы."""
        entity = self.entity
        ctx = entity.ctx
        self.io.echo("")
        self.io.echo(self._say("edit_con_summary"), None, False, True)
        for lang in ctx.langs:
            rel = entity.rel(lang)
            state = self._say("edit_con_new_file" if entity.created(lang) else "edit_con_changed")
            if not entity.created(lang) and ops.page_of(entity, lang).text == entity.disk.get(lang):
                state = self._say("edit_con_same")
            mark = f", {self._say('edit_con_pending')}" if ops.is_pending(entity, lang) else ""
            self.io.echo(f"  {rel} - {state}{mark}")
        if entity.moved:
            self.io.echo("  " + self._say("edit_con_move", old=entity.key, new=entity.target))
        parent = ops.parent_of(entity.target)
        if parent and ops.where(ctx, parent) is None:
            self.io.echo("  " + self._say("edit_con_category_made", key=parent))
        if entity.site:
            self.io.echo("  site.yaml - " + self._say("edit_con_menu"))
        answer = self.io.ask(f"{self._say('edit_con_save')} [Y/n]").strip().lower()
        return answer == "" or answer in YES


def _text(value: Any, lang: str) -> str:
    from heron.messages import rendered

    return str(rendered(value, lang) if value is not None else "")
