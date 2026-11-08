"""Командный интерфейс HERON.

Команды — вся поверхность движка для человека. Внутрь него заходить
не нужно: ни один сценарий работы с сайтом этого не требует.

Каждое сообщение отвечает на три вопроса: что случилось, почему и что
делать. Трейсбек человек не видит никогда — только с `--debug`: путь к
файлу внутри движка не помогает тому, кто ведёт сайт.

Спецификация: docs/spec/23-distribution.md, раздел 3.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import click

from heron import __version__, build_info, messages
from heron.contracts import site as site_contract
from heron.contracts.site import LANG_RE
from heron.core import build as pipeline
from heron.core import report as report_module
from heron.core.environment import BuildEnv
from heron.core.errors import HeronError
from heron.core.notes import NOTE
from heron.messages import CLICK_RU, RECIPE_EN, title
from heron.scaffold import (
    ENV_NOTES,
    NOTE_LANGS,
    SERVICE,
    Plan,
    adopt,
    create,
    ctx_notes,
    foreign_files,
    language_folders,
    placeholder_domain,
    resolve_notes,
    site_yaml_problem,
)

DIST = "dist"


# --- язык справки и служебных строк click ---------------------------------------


# Язык запуска — в ContextVar, а не в общей переменной процесса: у каждого
# потока (и у каждого контекста asyncio) свой, новый поток начинает с en.
# Пока один поток работает по-русски, чужая команда click в другом потоке
# того же процесса получает свои английские строки.
_LANG: ContextVar[str] = ContextVar("heron_ui_lang", default="en")


class _Ui:
    """Язык этого запуска для справки и рамки ошибок click.

    Справку `--help` click печатает прямо во время разбора аргументов, раньше
    любой команды, поэтому язык выбирается до разбора (`_help_lang`): флаг
    `--notes` из сырых аргументов, затем HERON_NOTES, затем build.notes из
    site.yaml текущей папки, иначе en. Команда, узнавшая язык своего сайта
    (`_lang`), уточняет его: ошибки click после этого — на том же языке.
    Значение живёт в `_LANG` — своё у каждого потока и контекста.
    """

    @property
    def lang(self) -> str:
        return _LANG.get()

    @lang.setter
    def lang(self, value: str) -> None:
        _LANG.set(value)


_UI = _Ui()
HELP_PREFIX = "help_"


def _click_text(message: str) -> str:
    """gettext для click: для ru — перевод из messages.CLICK_RU, иначе как есть.

    Язык читается из `_LANG` при каждом вызове: подмена `_` в модулях click
    общая на процесс, а язык — свой у каждого потока.
    """
    if _LANG.get() == "ru":
        return CLICK_RU.get(message, message)
    return message


def _click_plural(singular: str, plural: str, count: int) -> str:
    return _click_text(singular if count == 1 else plural)


def _install_click_catalog() -> None:
    """Строки click (Usage, Options, Error: …) — через наш каталог.

    click берёт их через gettext, импортированный в каждый модуль как `_` и
    `ngettext`; каталога .mo для своего домена у click нет. Подмена — только
    имён в модулях click, и для en она прозрачна: строка возвращается как есть.
    Язык — из `_LANG` текущего потока: другие потоки процесса остаются на своём.
    """
    import click.core
    import click.decorators
    import click.exceptions
    import click.formatting
    import click.parser
    import click.termui
    import click.types
    import click.utils

    for module in (
        click.core,
        click.decorators,
        click.exceptions,
        click.formatting,
        click.parser,
        click.termui,
        click.types,
        click.utils,
    ):
        if hasattr(module, "_"):
            module._ = _click_text  # type: ignore[attr-defined]
        if hasattr(module, "ngettext"):
            module.ngettext = _click_plural  # type: ignore[attr-defined]


_install_click_catalog()


def _notes_in(args: list[str]) -> str | None:
    """`--notes X` или `--notes=X` в сырых аргументах; последний годный побеждает."""
    found: str | None = None
    items = iter(args)
    for arg in items:
        if arg == "--":
            break
        value = None
        if arg == "--notes":
            value = next(items, None)
        elif arg.startswith("--notes="):
            value = arg.partition("=")[2]
        if value is not None and value.lower() in NOTE_LANGS:
            found = value.lower()
    return found


# Справке site.yaml больше 64 КБ не читается: настоящий файл весит килобайты, а
# разбор тяжёлого занял бы секунды и десятки секунд. `--version` site.yaml не
# читает вовсе: её строка одна на оба языка, язык ей не нужен.
HELP_SITE_LIMIT = 1 << 16


def _help_site_yaml() -> Path | None:
    """./site.yaml, если по нему стоит выбирать язык справки: обычный небольшой файл."""
    site_yaml = Path("site.yaml")
    if not site_yaml.is_file() or site_yaml.stat().st_size > HELP_SITE_LIMIT:
        return None
    return site_yaml


def _only_version(args: list[str]) -> bool:
    """В аргументах `--version` или `-V`, а справки (`-h`, `--help`) рядом нет."""
    seen: set[str] = set()
    for arg in args:
        if arg == "--":
            break
        seen.add(arg)
    return bool(seen & {"--version", "-V"}) and not seen & {"--help", "-h"}


def _help_lang(args: list[str]) -> str:
    """Язык справки до разбора аргументов: --notes, HERON_NOTES, ./site.yaml, en.

    Выбор идёт раньше HeronGroup.invoke, рамки ошибок ещё нет. Поэтому любой
    сбой (битый или странный site.yaml, недоступная папка) даёт en: справка и
    `--version` на английском лучше трейсбека, а ошибку конфига check и build
    покажут по форме.
    """
    if _only_version(args):
        return "en"
    try:
        return resolve_notes(_notes_in(args), _help_site_yaml())
    except Exception:  # noqa: BLE001 — до рамки ошибок: только язык справки
        return "en"


class _Localized:
    """Атрибут, в котором лежит ключ messages.py (help_*), а читается текст.

    Текст берётся в момент чтения на языке этого запуска: справка одного и
    того же объекта команды выходит то по-русски, то по-английски. Значение
    не ключ (None, обычная строка) отдаётся как есть.
    """

    def __set_name__(self, owner: type, name: str) -> None:
        self.slot = f"_heron_{name}"

    def __get__(self, obj: object, owner: type | None = None):
        if obj is None:
            return self
        raw = obj.__dict__.get(self.slot)
        if isinstance(raw, str) and raw.startswith(HELP_PREFIX):
            return say(_UI.lang, raw)
        return raw

    def __set__(self, obj: object, value: object) -> None:
        obj.__dict__[self.slot] = value


class HeronOption(click.Option):
    """Параметр, у которого подпись и имя значения — ключи справки."""

    help = _Localized()
    metavar = _Localized()


class HeronArgument(click.Argument):
    help = _Localized()
    metavar = _Localized()

    def make_metavar(self, ctx: click.Context) -> str:
        # click отдаёт заданное имя как есть, а необязательный аргумент в строке
        # использования — в скобках: heron build [ПАРАМЕТРЫ] [ПУТЬ]
        text = super().make_metavar(ctx)
        if self.metavar is not None and not self.required and not text.startswith("["):
            return f"[{text}]"
        return text


class _LocalizedCommand:
    """Справка команды на языке пояснений: тексты — ключи help_* из messages.py."""

    help = _Localized()
    short_help = _Localized()
    options_metavar = _Localized()

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("options_metavar", "help_mv_options")
        super().__init__(*args, **kwargs)

    def get_help_option(self, ctx: click.Context):
        # click создаёт --help один раз и с подписью на языке первого показа;
        # подпись ставится заново при каждом обращении
        option = super().get_help_option(ctx)  # type: ignore[misc]
        if option is not None:
            option.help = say(_UI.lang, "help_opt_help")
        return option

    def main(self, args=None, *rest, **extra):
        raw = list(sys.argv[1:] if args is None else args)
        token = _LANG.set(_help_lang(raw))
        try:
            return super().main(args, *rest, **extra)  # type: ignore[misc]
        finally:
            _LANG.reset(token)


class HeronCommand(_LocalizedCommand, click.Command):
    pass


def _option(*decls: str, **attrs):
    attrs.setdefault("cls", HeronOption)
    return click.option(*decls, **attrs)


def _argument(*decls: str, **attrs):
    attrs.setdefault("cls", HeronArgument)
    return click.argument(*decls, **attrs)


def _path_argument(func):
    """Необязательный путь к папке сайта, по умолчанию текущая."""
    return _argument(
        "path",
        type=click.Path(file_okay=False, path_type=Path),
        default=".",
        metavar="help_mv_path",
    )(func)


class _Terminal:
    """Ход сборки в терминал: одна живая строка на этап.

    Этапы неравномерные: обход контента и рендер идут секунды, нарезка
    картинок — минуту. Статичная строка на долгом этапе неотличима от
    зависшей программы, поэтому строка крутится и показывает, что именно
    сейчас обрабатывается и сколько это уже длится.

    В не-терминал (лог CI, сборка внутри докера без -t, перенаправление в
    файл) крутиться нечему: там этап объявляется сразу, как начался,
    длинные этапы отмечаются раз в секунду, и в конце пишется итог.
    Молчать до конца этапа нельзя ни в том, ни в другом случае — это
    неотличимо от зависшей сборки.
    """

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    WIDTH = 22
    QUIET = 2.0  # как часто отмечаться в логе, секунды

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang
        self._title = ""
        self._detail = ""
        self._started = 0.0
        self._said = 0.0
        self._interactive = sys.stderr.isatty()
        self._stop: threading.Event | None = None
        self._spinner: threading.Thread | None = None

    def _say(self, text: str) -> None:
        """Строка в лог немедленно: буфер держал бы её до конца сборки."""
        click.echo(text, err=True)
        sys.stderr.flush()

    def _elapsed(self) -> str:
        seconds = time.monotonic() - self._started
        return f"{seconds:4.1f}s"

    def _line(self, frame: str = "") -> None:
        mark = f"{frame} " if frame else "  "
        head = self._title.ljust(self.WIDTH)
        tail = f"  {self._detail}" if self._detail else ""
        click.echo(f"\r{mark}{head} {self._elapsed()}{tail}\x1b[K", nl=False, err=True)

    def _spin(self) -> None:
        index = 0
        while self._stop is not None and not self._stop.wait(0.09):
            self._line(self.FRAMES[index % len(self.FRAMES)])
            index += 1

    def _text(self, key: str, **fields: object) -> str:
        """Ключ сообщения — в текст на языке сообщений; не ключ — как есть."""
        try:
            return say(self._lang, key, **fields)
        except KeyError:
            return key

    def step(self, title: str) -> None:
        self._title = self._text(title)
        self._detail = ""
        self._started = time.monotonic()
        self._said = self._started
        if not self._interactive:
            self._say(f"→ {self._title}…")
            return
        self._stop = threading.Event()
        self._spinner = threading.Thread(target=self._spin, daemon=True)
        self._spinner.start()

    def _park(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._spinner is not None:
            self._spinner.join(timeout=0.3)
        self._stop = None
        self._spinner = None

    def done(self, detail: str = "", **fields: object) -> None:
        text = self._text(detail or "done", **fields)
        head = self._title.ljust(self.WIDTH)
        if self._interactive:
            self._park()
            self._detail = ""
            click.echo("\r\x1b[K", nl=False, err=True)
            click.secho("✓ ", fg="green", nl=False, err=True)
            click.echo(f"{head} {self._elapsed()}  ", nl=False, err=True)
            click.secho(text, fg="green", err=True)
        else:
            self._say(f"✓ {head} {self._elapsed()}  {text}")

    def note(self, key: str, **fields: object) -> None:
        """Замечание по ходу сборки: отдельной строкой, не мешая полоске."""
        text = self._text(key, **fields)
        if self._interactive:
            click.echo("\r\x1b[K", nl=False, err=True)
        click.secho(f"! {text}", fg="yellow", err=True)

    def tick(self, current: int, total: int, detail: str = "") -> None:
        """Продвижение внутри этапа: счётчик, полоска и что сейчас в работе."""
        if not self._interactive:
            now = time.monotonic()
            if current < total and now - self._said < self.QUIET:
                return
            self._said = now
            tail = f"  {detail[-40:]}" if detail else ""
            self._say(
                f"  {self._title.ljust(self.WIDTH)} {self._elapsed()}  {current}/{total}{tail}"
            )
            return
        filled = round(10 * current / total) if total else 0
        bar = "━" * filled + "─" * (10 - filled)
        room = max(0, 46 - len(bar))
        self._detail = f"{bar} {current:>3}/{total:<3} {detail[-room:] if room else ''}"


def say(lang: str, key: str, /, **fields: object) -> str:
    """Текст сообщения; в контейнере подсказки `heron …` - полной командой Docker."""
    text = messages.say(lang, key, **fields)
    if key.startswith("help_") or not in_container():
        return text
    return messages.for_docker(text)


def rendered(value: str | None, lang: str) -> str | None:
    """Сообщение ядра на языке lang; в контейнере - с командами Docker."""
    text = messages.rendered(value, lang)
    if text is None or not in_container():
        return text
    return messages.for_docker(text)


CONTAINER_ENV = "HERON_IN_CONTAINER"


# --- язык и окружение ---------------------------------------------------------


def _lang(flag: str | None = None, root: Path | None = None) -> str:
    """Язык сообщений: тот же, что язык пояснений сайта. Не разобрался — en.

    Найденный язык становится и языком рамки ошибок click в этом запуске.
    """
    site_yaml = root / "site.yaml" if root is not None else None
    try:
        lang = resolve_notes(flag or ctx_notes(), site_yaml)
    except ValueError:
        lang = "en"
    _UI.lang = lang
    return lang


@contextmanager
def _notes_env(notes: str | None) -> Iterator[None]:
    """HERON_NOTES = --notes на время вызова того, кто читает язык из окружения."""
    if not notes:
        yield
        return
    saved = os.environ.get(ENV_NOTES)
    os.environ[ENV_NOTES] = notes
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop(ENV_NOTES, None)
        else:
            os.environ[ENV_NOTES] = saved


def in_container() -> bool:
    """Движок запущен в образе: там пути с компьютера человека не видны."""
    return os.environ.get(CONTAINER_ENV) == "1" or Path("/.dockerenv").exists()


def can_ask() -> bool:
    """Можно ли задавать вопросы: и ввод, и вывод — терминал."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _err(text: str, color: str | None = "red") -> None:
    click.secho(text, fg=color, err=True)


# --- ошибки -------------------------------------------------------------------


def _fail(error: HeronError, lang: str = "en") -> None:
    """Ошибка движка по форме: что, где, подробно, что сделать."""
    # Ошибка переменной окружения — не про site.yaml: заголовок по имени переменной.
    named = (pipeline.WORKERS_ENV, ENV_NOTES, "--notes")
    head = error.path if error.path in named else title(lang, error.code)
    _err(say(lang, "error_head", code=error.code, title=head))
    if error.path:
        shown = rendered(error.path, lang)
        where = shown if error.line is None else f"{shown}:{error.line}"
        _err(say(lang, "error_where", where=where), None)
    _err(say(lang, "error_what", message=rendered(error.message, lang)), None)
    if error.hint:
        _err(say(lang, "error_hint", hint=rendered(error.hint, lang)), None)
    elif error.path and error.code == "E011" and not Path(error.path).exists():
        _err(_missing_hint(Path(error.path).parent, lang), None)
    sys.exit(1)


def _missing_hint(path: Path, lang: str) -> str:
    if in_container() and path.is_absolute() and not path.exists():
        return say(lang, "container_path", path=path)
    return say(lang, "path_hint")


def _need_dir(path: Path, lang: str) -> None:
    """Папка есть — дальше; нет — объяснить, почему её не видно."""
    if path.is_dir():
        return
    _err(say(lang, "no_path", path=path))
    _err(_missing_hint(path, lang), None)
    sys.exit(1)


def _need_site(path: Path, lang: str) -> None:
    _need_dir(path, lang)
    if not (path / "site.yaml").is_file():
        _err(say(lang, "no_site", path=path))
        sys.exit(1)


class HeronGroup(_LocalizedCommand, click.Group):
    """Группа команд, которая не выпускает наружу трейсбек.

    Ошибки движка печатаются по форме; непредвиденные — коротко, с советом
    повторить с `--debug`. Сам `--debug` (или HERON_DEBUG=1) отдаёт трейсбек
    целиком — для того, кто чинит движок. Язык рамки — язык этого запуска:
    `--notes`, HERON_NOTES, build.notes сайта, с которым работает команда.
    """

    command_class = HeronCommand
    group_class = type
    subcommand_metavar = _Localized()

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("subcommand_metavar", "help_mv_command")
        super().__init__(*args, **kwargs)

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except (click.exceptions.Exit, click.exceptions.Abort, click.ClickException):
            raise
        except SystemExit:
            raise
        except HeronError as error:
            if _debug(ctx):
                raise
            _fail(error, _UI.lang)
        except PermissionError as error:
            if _debug(ctx):
                raise
            lang = _UI.lang
            _err(say(lang, "denied", path=error.filename or error))
            _err(say(lang, "denied_hint"), None)
            if error.filename and in_container():
                _err(_missing_hint(Path(error.filename), lang), None)
            sys.exit(1)
        except Exception as error:  # noqa: BLE001 — последний рубеж перед человеком
            if _debug(ctx):
                raise
            lang = _UI.lang
            _err(say(lang, "crash_head", kind=type(error).__name__))
            _err(say(lang, "crash_text", text=error), None)
            if isinstance(error, FileNotFoundError) and error.filename:
                _err(_missing_hint(Path(error.filename), lang), None)
            _err(say(lang, "crash_hint"), None)
            sys.exit(1)


def _debug(ctx: click.Context) -> bool:
    root = ctx.find_root()
    return bool((root.params or {}).get("debug")) or os.environ.get("HERON_DEBUG") == "1"


# --- сборка и проверка: итог ----------------------------------------------------


def _finish(
    result: pipeline.Result,
    strict: bool,
    lang: str,
    kind: str,
    full: Path | None = None,
) -> None:
    """Напечатать сводку и выйти с нужным кодом."""
    summary = report_module.summary(result.collector, full=full, lang=lang)
    if result.collector.errors:
        _err(summary)
        _err("\n" + say(lang, f"{kind}_failed", count=len(result.collector.errors)))
        sys.exit(1)

    if result.report is not None:
        click.echo(result.report.render(lang))
    if summary:
        click.secho(summary, fg="yellow")

    if strict and result.collector.warnings:
        _err(say(lang, f"{kind}_strict", count=len(result.collector.warnings)))
        sys.exit(1)


def _check_json(
    path: Path,
    strict: bool,
    drafts: bool,
    env: BuildEnv,
    allow_schema: tuple[str, ...] = (),
    old_urls: Path | None = None,
    lang: str = "en",
    theme_demo: bool = False,
) -> None:
    """`heron check --json`: коды, файлы и строки — разбирать, а не читать.

    Агенту текст отчёта на языке человека не нужен: ему нужны код ошибки,
    файл, строка и подсказка. Код выхода тот же, что у обычного check.
    """
    import json

    def error(item: HeronError) -> dict:
        return {
            "code": item.code,
            "path": rendered(item.path, lang),
            "line": item.line,
            "message": rendered(item.message, lang),
            "hint": rendered(item.hint, lang),
        }

    kit = None
    schema = None
    old_section = None
    try:
        result = pipeline.check(
            path,
            drafts=drafts,
            strict=strict,
            env=env,
            allow_schema=list(allow_schema),
            notes_lang=lang,
            theme_demo=theme_demo,
        )
        if old_urls is not None:
            listed = report_module.read_old_urls(old_urls)
            lost, old_summary = report_module.old_urls(listed, result.site, result.config)
            result.collector.warnings.extend(lost)
            old_section = {
                "summary": rendered(old_summary, lang),
                "lost": [
                    {
                        "path": rendered(w.path, lang),
                        "line": w.line,
                        "message": rendered(w.message, lang),
                    }
                    for w in lost
                ],
            }
        kit = result.report.kit if result.report is not None else None
        section = result.report.schema if result.report is not None else None
        schema = section.as_json() if section is not None else None
        errors = [error(item) for item in result.collector.errors]
        warnings = [
            {
                "kind": w.kind,
                "path": rendered(w.path, lang),
                "line": w.line,
                "message": rendered(w.message, lang),
            }
            for w in result.collector.warnings
        ]
        strict = result.strict
        pages = len(result.site.pages) if getattr(result, "site", None) is not None else None
    except HeronError as item:
        errors, warnings, pages = [error(item)], [], None
    if kit is None:
        # до разбора конфига не дошло: о комплекте всё равно есть что сказать
        from types import SimpleNamespace

        kit = report_module.kit_status(path.resolve(), SimpleNamespace(build=None))
    failed = bool(errors) or (strict and bool(warnings))
    click.echo(
        json.dumps(
            {
                "ok": not failed,
                "version": build_info.label(),
                "strict": strict,
                "pages": pages,
                "errors": errors,
                "warnings": warnings,
                "kit": kit.as_json(),
                "schema": schema,
                **({"old_urls": old_section} if old_section is not None else {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if failed:
        sys.exit(1)


def _no_site_json(path: Path, strict: bool, lang: str) -> None:
    """`check --json` без папки или site.yaml: тот же объект, что у `_check_json` (21 §10)."""
    import json
    from types import SimpleNamespace

    kit = report_module.kit_status(path.resolve(), SimpleNamespace(build=None))
    click.echo(
        json.dumps(
            {
                "ok": False,
                "version": build_info.label(),
                "strict": strict,
                "pages": None,
                "errors": [
                    {
                        "code": "E011",
                        "path": "site.yaml",
                        "line": None,
                        "message": say(lang, "no_site", path=path),
                        "hint": "",
                    }
                ],
                "warnings": [],
                "kit": kit.as_json(),
                "schema": None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    sys.exit(1)


# --- сводка того, что разложено --------------------------------------------------


def _group_plan(created: list[str], lang: str) -> list[str]:
    """Разложенные файлы — по смыслу, а не списком в тридцать строк."""
    config, content, theme, i18n, folders, notes, other = [], {}, 0, [], [], 0, []
    for rel in created:
        name = rel.rstrip("/")
        parts = name.split("/")
        if name in ("site.yaml", ".gitignore"):
            config.append(name)
        elif parts[-1] == NOTE:
            notes += 1
        elif rel.endswith("/") and len(parts) == 1:
            folders.append(name)
        elif parts[0] == "content" and len(parts) >= 3:
            label = {"index.md": say(lang, "plan_home"), "404.md": say(lang, "plan_404")}
            content.setdefault(parts[1], []).append(label.get(parts[-1], "/".join(parts[2:])))
        elif parts[0] == "theme" and len(parts) >= 3 and parts[1] == "i18n":
            i18n.append(parts[2].removesuffix(".yaml"))
        elif parts[0] == "theme":
            theme += 1
        else:
            other.append(name)
    lines = []
    if config:
        lines.append(say(lang, "plan_config", files=", ".join(config)))
    for code, files in content.items():
        lines.append(say(lang, "plan_content", code=code, files=", ".join(files)))
    if theme:
        lines.append(say(lang, "plan_theme", count=theme))
    if i18n:
        lines.append(say(lang, "plan_i18n", langs=", ".join(i18n)))
    if folders:
        lines.append(say(lang, "plan_folders", folders=", ".join(folders)))
    if notes:
        lines.append(say(lang, "plan_notes", count=notes))
    if other:
        lines.append(say(lang, "plan_other", files=", ".join(other)))
    return lines


KIT_ROOT = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")


def _is_kit(rel: str) -> bool:
    """Файл комплекта для агентов: agents/** или корневой указатель (20 §1)."""
    name = rel.rstrip("/")
    return name in KIT_ROOT or name == "agents" or name.startswith("agents/")


def _kit_lines(plan: Plan, kit_off: bool) -> list[tuple[str, str, str | None]]:
    """Комплект одной строкой (и строками о правленых и лишних): (знак, текст, цвет)."""
    lang, kit = plan.notes, plan.kit
    if kit is None:
        return [("·", say(lang, "kit_off"), None)] if kit_off else []
    lines: list[tuple[str, str, str | None]] = []
    # манифест переписывается при каждом обновлении — в счёт заменённых он не идёт
    updated = [rel for rel in kit.updated if rel != "agents/heron-kit.yaml"]
    if kit.mode == "update" or updated:
        if updated or kit.created:
            text = say(
                lang, "kit_updated", code=kit.lang, updated=len(updated), created=len(kit.created)
            )
            lines.append(("+", text, "green"))
        else:
            lines.append(("·", say(lang, "kit_current", code=kit.lang), None))
    elif kit.created:
        lines.append(("+", say(lang, "kit_created", code=kit.lang, n=len(kit.created)), "green"))
    else:
        lines.append(("·", say(lang, "kit_in_place"), None))
    if kit.lang_from:
        text = say(lang, "kit_lang_changed", old=kit.lang_from, new=kit.lang)
        lines.append(("!", text, "yellow"))
    if kit.notes_lang:
        text = say(lang, "kit_lang_kept", kit=kit.lang, notes=kit.notes_lang)
        lines.append(("·", text, None))
    if kit.fallback:
        other = "en" if kit.lang == "ru" else "ru"
        text = say(lang, "kit_fallback", want=kit.lang, have=other, n=len(kit.fallback))
        lines.append(("·", text, None))
    if kit.edited:
        lines.append(("!", say(lang, "kit_skipped_edited", files=", ".join(kit.edited)), "yellow"))
    if kit.forced:
        lines.append(("!", say(lang, "kit_forced", files=", ".join(kit.forced)), "yellow"))
    if kit.orphans:
        lines.append(("!", say(lang, "kit_orphan", files=", ".join(kit.orphans)), "yellow"))
    if kit.damaged:
        lines.append(("!", say(lang, "kit_manifest_damaged"), "yellow"))
    return lines


def _report_plan(plan: Plan, verbose: bool = False, kit_off: bool = False) -> None:
    lang = plan.notes
    kit = plan.kit
    own = set(kit.found) if kit is not None else set()
    found = [line for line in plan.found if line not in own]
    created = [rel for rel in plan.created if kit is None or not _is_kit(rel)]
    skipped = [rel for rel in plan.skipped if kit is None or not _is_kit(rel)]
    overwritten = [rel for rel in plan.overwritten if kit is None or not _is_kit(rel)]
    kit_lines = _kit_lines(plan, kit_off)
    if found:
        click.echo(say(lang, "plan_found"))
        for line in found:
            click.echo(f"  · {line}")
    changed = kit is not None and (
        kit.created or any(rel != "agents/heron-kit.yaml" for rel in kit.updated)
    )
    if created or changed:
        click.echo(say(lang, "plan_made"))
        if verbose:
            for name in plan.created:
                click.secho(f"  + {name}", fg="green")
        else:
            for line in _group_plan(created, lang):
                click.secho(f"  + {line}", fg="green")
    elif not kit_lines and not overwritten:
        click.echo(say(lang, "plan_nothing"))
    if overwritten:
        click.echo(say(lang, "plan_overwritten"))
        for name in overwritten:
            click.secho(f"  ~ {name}", fg="yellow")
    for mark, text, color in kit_lines:
        click.secho(f"  {mark} {text}", fg=color)
    if skipped:
        if verbose or len(skipped) <= 5:
            click.echo(say(lang, "plan_kept", files=", ".join(skipped)))
        else:
            click.echo(say(lang, "plan_kept_many", count=len(skipped)))


def _shown(path: Path) -> str:
    """Путь так, как его стоит набирать в следующей команде."""
    text = str(path)
    return text if text else "."


def _next(path: Path, lang: str, languages: list[str], domain: str | None) -> None:
    """Что делать дальше — готовыми командами под эту папку."""
    where = _shown(path)
    homes = ", ".join(f"content/{code}/index.md" for code in languages)
    lines = [say(lang, "next_config", path=where)]
    if domain and domain.endswith(".example"):
        lines.append(say(lang, "next_domain", domain=domain))
    lines += [
        say(lang, "next_home", files=homes),
        say(lang, "next_page", path=where),
        say(lang, "next_check", path=where),
        say(lang, "next_build", path=where),
        say(lang, "next_langs", path=where),
    ]
    click.echo("\n" + say(lang, "next_title"))
    for number, line in enumerate(lines, 1):
        click.echo(f"  {number}. {line}")


# --- команды ------------------------------------------------------------------


def _show_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    # Строка одна на оба языка: её разбирают скрипты и CI («heron, version 0.1.0 …»).
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"heron, version {build_info.label()}", color=ctx.color)
    ctx.exit()


NOTES_OPTION = _option(
    "--notes",
    type=click.Choice(["ru", "en"]),
    default=None,
    help="help_opt_notes",
)
VERBOSE_OPTION = _option("-v", "--verbose", is_flag=True, help="help_opt_verbose")


@click.group(
    cls=HeronGroup,
    help="help_main",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@_option(
    "-V",
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_show_version,
    help="help_opt_version",
)
@_option("--debug", is_flag=True, help="help_opt_debug")
@NOTES_OPTION
def main(debug: bool, notes: str | None) -> None:
    """Корень команд: --debug и --notes действуют на любую подкоманду."""


def _ask(lang: str, key: str, default: str, check) -> str:
    """Один вопрос: подсказка, значение по умолчанию, повтор до годного ответа."""
    click.echo(
        click.style(say(lang, key), bold=True)
        + click.style(f" - {say(lang, key + '_help')}", dim=True)
    )
    while True:
        answer = click.prompt("  ›", default=default, show_default=True, prompt_suffix=" ")
        answer = str(answer).strip()
        problem = check(answer)
        if problem is None:
            return answer
        _err(f"  {problem}", "yellow")


def _parse_langs(text: str) -> list[str]:
    return [x.strip().lower() for x in re.split(r"[,\s]+", text) if x.strip()]


def _check_langs(lang: str):
    def check(text: str) -> str | None:
        codes = _parse_langs(text)
        bad = [x for x in codes if not LANG_RE.match(x)]
        if not codes or bad:
            return say(lang, "bad_langs", bad=", ".join(bad) or "-")
        return None

    return check


def _check_domain(lang: str):
    def check(text: str) -> str | None:
        return None if site_contract.domain(text) else say(lang, "bad_domain")

    return check


def _questionnaire(
    lang: str, name: str, domain: str, languages: list[str], default: str
) -> tuple[str, str, list[str], str] | None:
    """Опрос в терминале. Отказ на последнем шаге — None, ничего не создаётся."""
    click.echo(say(lang, "ask_intro") + "\n")
    name = _ask(lang, "ask_name", name, lambda text: None if text else "-")
    domain = _ask(lang, "ask_domain", domain or placeholder_domain(name), _check_domain(lang))
    domain = site_contract.domain(domain) or domain.lower()
    raw = _ask(lang, "ask_langs", ", ".join(languages), _check_langs(lang))
    languages = list(dict.fromkeys(_parse_langs(raw)))
    if len(languages) > 1:
        default = default if default in languages else languages[0]
        default = _ask(
            lang,
            "ask_default",
            default,
            lambda text: (
                None if text in languages else say(lang, "bad_default", langs=", ".join(languages))
            ),
        )
    else:
        default = languages[0]
    click.echo("\n" + say(lang, "ask_summary"))
    note = f"  ({say(lang, 'placeholder')})" if domain.endswith(".example") else ""
    click.echo(f"  name: {name}\n  domain: {domain}{note}")
    click.echo(f"  languages: {', '.join(languages)}\n  default_lang: {default}")
    click.echo(f"  notes: {lang}")
    if not click.confirm(say(lang, "ask_confirm"), default=True):
        return None
    return name, domain, languages, default


def site_name_guess(path: Path) -> str:
    """Название по умолчанию: имя репозитория, иначе имя папки.

    В контейнере текущая папка — всегда /site, и её имя ничего не говорит.
    Зато `.git/config` смонтирован вместе с папкой, и имя репозитория из
    адреса origin — ровно то, как человек называет проект.
    """
    config = path / ".git" / "config"
    if config.is_file():
        try:
            text = config.read_text(encoding="utf-8", errors="replace")
            found = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', text, re.S)
            if found:
                name = found.group(1).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
                name = name.removesuffix(".git")
                if name:
                    return name
        except OSError:
            pass
    folder = path.resolve().name
    if in_container() and folder == "site":
        return "my-site"
    return folder or "my-site"


def _existing_site(path: Path, notes: str | None) -> None:
    """В папке уже есть сайт: сказать это прямо, на языке самого сайта."""
    lang = _lang(notes, path)
    from heron.scaffold import _declared

    declared = _declared(path / "site.yaml") or {}
    langs = ", ".join(declared.get("languages") or []) or "-"
    _err(say(lang, "site_exists", path=_shown(path), langs=langs), "yellow")
    sys.exit(1)


def _start_site(
    path: Path,
    notes: str | None,
    verbose: bool,
    site_name: str | None,
    domain: str | None,
    langs: str | None,
    yes: bool,
    present: list[str] | None = None,
    done_key: str = "new_done",
    demo: bool = False,
    agents: str = "true",
) -> None:
    """Завести сайт: опрос в терминале или флаги, затем скелет и «Что дальше».

    Общая часть `new` и `init` в папке без site.yaml: человеку всё равно,
    какой командой он начал, — вопросы одни и те же.
    """
    lang = _lang(notes)
    asking = can_ask() and not yes
    if asking and notes is None and not os.environ.get("HERON_NOTES"):
        click.echo(
            click.style(
                "Language you prefer to work in: hints, messages, comments in files\n"
                "На каком языке вам удобнее работать: подсказки, сообщения, комментарии в файлах",
                bold=True,
            )
        )
        lang = click.prompt("  ›", type=click.Choice(["en", "ru"]), default="en", prompt_suffix=" ")
        _UI.lang = lang  # ответы да/нет и ошибки ввода дальше — на выбранном языке

    guess = site_name or site_name_guess(path)
    languages = _parse_langs(langs) if langs else (present or ["en"])
    bad = [x for x in languages if not LANG_RE.match(x)]
    if bad or not languages:
        _err(say(lang, "bad_langs", bad=", ".join(bad) or "-"))
        sys.exit(2)
    if domain and not site_contract.domain(domain):
        _err(say(lang, "bad_domain"))
        sys.exit(2)
    languages = list(dict.fromkeys(languages))
    if domain:
        domain = site_contract.domain(domain) or domain.lower()

    click.secho(say(lang, "new_title", path=_shown(path)), bold=True)
    if present:
        click.echo(say(lang, "found_langs", langs=", ".join(present)))
    if asking:
        answers = _questionnaire(lang, guess, domain or "", languages, languages[0])
        if answers is None:
            click.echo(say(lang, "ask_cancelled"))
            return
        guess, domain, languages, default = answers
    else:
        if not yes:
            click.secho(say(lang, "no_questions"), dim=True)
        default = languages[0]

    path.mkdir(parents=True, exist_ok=True)
    try:
        plan = create(
            path,
            name=guess,
            languages=languages,
            notes=lang,
            domain=domain or None,
            default_lang=default,
            demo=demo,
            agents=agents,
        )
    except HeronError as error:
        _fail(error, lang)  # на языке пояснений, который выбран для сайта
    click.secho("\n" + say(lang, done_key, path=_shown(path)), fg="green", bold=True)
    _report_plan(plan, verbose, kit_off=agents == "false")
    ordered = [default] + [x for x in languages if x != default]
    _next(path, lang, ordered, domain or placeholder_domain(guess))


SITE_OPTIONS = [
    _option("--name", "site_name", default=None, metavar="help_mv_name", help="help_opt_name"),
    _option("--domain", default=None, metavar="help_mv_domain", help="help_opt_domain"),
    _option("--lang", "langs", default=None, metavar="help_mv_codes", help="help_opt_langs"),
    _option("-y", "--yes", is_flag=True, help="help_opt_yes"),
]


def site_options(func):
    for option in reversed(SITE_OPTIONS):
        func = option(func)
    return func


NO_AGENTS_OPTION = _option("--no-agents", "no_agents", is_flag=True, help="help_opt_no_agents")
STRICT_OPTION = _option("--strict", is_flag=True, help="help_opt_strict")
DRAFTS_OPTION = _option("--drafts", is_flag=True, help="help_opt_drafts")


def _schema_key(
    ctx: click.Context, param: click.Parameter, values: tuple[str, ...]
) -> tuple[str, ...]:
    """Ключ `--allow-schema` проверяется тем же валидатором, что `schema_exceptions[].key`."""
    for value in values:
        try:
            site_contract.SchemaException(key=value, reason="-")
        except ValueError:
            raise click.UsageError(
                say(_lang(None, None), "schema_key_bad", finding=value)
            ) from None
    return values


ALLOW_SCHEMA_OPTION = _option(
    "--allow-schema",
    "allow_schema",
    multiple=True,
    callback=_schema_key,
    metavar="help_mv_key",
    help="help_opt_allow_schema",
)
WORKERS_OPTION = _option(
    "--workers",
    type=click.IntRange(0, 64),
    default=None,
    metavar="help_mv_n",
    help="help_opt_workers",
)
PORT_OPTION = _option(
    "--port",
    default=8000,
    show_default=True,
    type=click.IntRange(1, 65535),
    metavar="help_mv_port",
    help="help_opt_port",
)


# Код выхода, когда сайт записан, а завершающее действие плагина
# (on_build_finished) упало: не 0 — CI должен это заметить, и не 1 — сборка
# удалась, и сообщение «сборка не выполнена» было бы неправдой.
FINISH_FAILED = 3


@main.command(help="help_new")
@NOTES_OPTION
@VERBOSE_OPTION
@site_options
@NO_AGENTS_OPTION
@_path_argument
def new(
    path: Path,
    notes: str | None,
    verbose: bool,
    site_name: str | None,
    domain: str | None,
    langs: str | None,
    yes: bool,
    no_agents: bool,
) -> None:
    """Создать сайт с нуля. Справка для человека — help_new в heron/messages.py."""
    notes = notes or ctx_notes()
    if (path / "site.yaml").is_file():
        _existing_site(path, notes)

    lang = _lang(notes)
    foreign = foreign_files(path)
    if foreign:
        shown = ", ".join(foreign[:5]) + (" …" if len(foreign) > 5 else "")
        _err(
            say(
                lang,
                "not_empty",
                path=_shown(path),
                files=shown,
                service=", ".join(s for s in SERVICE if s.startswith(".git")),
            )
        )
        sys.exit(1)

    if not path.exists():
        parent = path.resolve().parent
        if not parent.is_dir():
            _err(say(lang, "no_path", path=path))
            _err(_missing_hint(path, lang), None)
            sys.exit(1)

    agents = "false" if no_agents else "true"
    _start_site(path, notes, verbose, site_name, domain, langs, yes, demo=True, agents=agents)


@main.command(help="help_init")
@_option("--force", is_flag=True, help="help_opt_force")
@NOTES_OPTION
@VERBOSE_OPTION
@site_options
@_option("--agents", "with_agents", is_flag=True, help="help_opt_agents")
@NO_AGENTS_OPTION
@_path_argument
def init(
    path: Path,
    force: bool,
    notes: str | None,
    verbose: bool,
    site_name: str | None,
    domain: str | None,
    langs: str | None,
    yes: bool,
    with_agents: bool,
    no_agents: bool,
) -> None:
    """Дополнить папку по site.yaml. Справка — help_init в heron/messages.py."""
    notes = notes or ctx_notes()
    if with_agents and no_agents:
        raise click.UsageError(say(_lang(notes, path), "agents_conflict"))
    _need_dir(path, _lang(notes, path))
    if not (path / "site.yaml").is_file() and not force:
        content = path / "content"
        present = language_folders(content)
        _start_site(
            path,
            notes,
            verbose,
            site_name,
            domain,
            langs,
            yes,
            present,
            done_key="init_done",
            agents="false" if no_agents else "true",
        )
        return

    # Ошибка раскладки (E024 и другие) — на языке сайта, как у setup и check,
    # а не на языке по умолчанию: --notes, затем HERON_NOTES, затем build.notes.
    try:
        if with_agents:
            plan = adopt(path, force=force, notes=notes, agents_only=True, agents_flag="true")
        elif no_agents:
            plan = adopt(path, force=force, notes=notes, agents_flag="false")
        else:
            plan = adopt(path, force=force, notes=notes)
    except HeronError as error:
        _fail(error, _lang(notes, path))
    from heron.scaffold import _declared

    declared = _declared(path / "site.yaml") or {}
    click.secho(say(plan.notes, "init_done", path=_shown(path)), fg="green", bold=True)
    _report_plan(plan, verbose, kit_off=declared.get("agents") == "false")
    if with_agents:
        return
    domain = None
    try:
        import yaml

        data = yaml.safe_load((path / "site.yaml").read_text(encoding="utf-8")) or {}
        domain = str((data.get("site") or {}).get("domain") or "") or None
    except Exception:  # noqa: BLE001 — конфиг проверит сборка
        pass
    _next(path, plan.notes, declared.get("languages") or ["en"], domain)


@main.command(help="help_check")
@STRICT_OPTION
@DRAFTS_OPTION
@_option("--env", "env_name", default=None, metavar="help_mv_env", help="help_opt_env_check")
@ALLOW_SCHEMA_OPTION
@_option("--json", "as_json", is_flag=True, help="help_opt_json")
@_option(
    "--old-urls",
    "old_urls",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    metavar="help_mv_file",
    help="help_opt_old_urls",
)
@_option("--theme", "theme_demo", is_flag=True, help="help_opt_check_theme")
@NOTES_OPTION
@_path_argument
def check(
    path: Path,
    strict: bool,
    drafts: bool,
    env_name: str | None,
    allow_schema: tuple[str, ...],
    as_json: bool,
    old_urls: Path | None,
    notes: str | None,
    theme_demo: bool = False,
) -> None:
    """Проверить контент и конфиг, ничего не собирая."""
    lang = _lang(notes, path)
    if as_json and not (path / "site.yaml").is_file():
        _no_site_json(path, strict, lang)
    _need_site(path, lang)
    env = BuildEnv.resolve(env_name)
    if as_json:
        _check_json(path, strict, drafts, env, allow_schema, old_urls, lang, theme_demo)
        return
    click.secho(
        say(lang, "check_head", version=__version__, path=_shown(path)), bold=True, err=True
    )
    try:
        result = pipeline.check(
            path,
            drafts=drafts,
            strict=strict,
            env=env,
            allow_schema=list(allow_schema),
            notes_lang=lang,
            theme_demo=theme_demo,
        )
    except HeronError as error:
        _fail(error, lang)
    old_summary = ""
    if old_urls is not None:
        try:
            listed = report_module.read_old_urls(old_urls)
        except HeronError as error:
            _fail(error, lang)
        lost, old_summary = report_module.old_urls(listed, result.site, result.config)
        result.collector.warnings.extend(lost)
    _finish(result, result.strict, lang, "check")
    if old_summary:
        click.echo(rendered(old_summary, lang))
    click.secho(say(lang, "check_done", path=_shown(path)), fg="green")


@main.command(help="help_build")
@STRICT_OPTION
@DRAFTS_OPTION
@_option(
    "--out",
    default=None,
    type=click.Path(path_type=Path),
    metavar="help_mv_folder",
    help="help_opt_out",
)
@_option("--env", "env_name", default=None, metavar="help_mv_env", help="help_opt_env")
@ALLOW_SCHEMA_OPTION
@WORKERS_OPTION
@NOTES_OPTION
@_path_argument
def build(
    path: Path,
    strict: bool,
    drafts: bool,
    out: Path | None,
    env_name: str | None,
    allow_schema: tuple[str, ...],
    workers: int | None,
    notes: str | None,
) -> None:
    """Собрать сайт в dist/ или в указанную папку."""
    lang = _lang(notes, path)
    _need_site(path, lang)
    env = BuildEnv.resolve(env_name)
    click.secho(
        say(lang, "build_head", version=__version__, path=_shown(path), env=env.name),
        bold=True,
        err=True,
    )
    try:
        result = pipeline.run(
            path,
            dist=out,
            drafts=drafts,
            strict=strict,
            env=env,
            progress=_Terminal(lang),
            workers=workers,
            allow_schema=list(allow_schema),
            notes_lang=lang,
        )
    except HeronError as error:
        _fail(error, lang)

    target = out or (path / DIST)
    _finish(
        result, result.strict, lang, "build", full=target.parent / ".heron-cache" / "warnings.txt"
    )
    # Одной строкой — чем собралось. Домен выбирается окружением, и
    # страховки «дев канонизируется на прод» больше нет: «собрал не то»
    # должно быть видно сразу, а не через неделю из выдачи.
    index = say(lang, "index_open" if env.indexable else "index_closed")
    counters = say(lang, "counters_on" if env.analytics else "counters_off")
    click.secho(
        say(
            lang,
            "build_env",
            env=env.name,
            domain=result.config.site.domain,
            index=index,
            counters=counters,
        ),
        fg="yellow" if not env.indexable else "green",
    )
    click.secho(say(lang, "build_done", count=len(result.written), target=target), fg="green")
    for notice in result.notices:
        click.secho(rendered(notice, lang), fg="yellow", err=True)
    if result.finish_errors:
        for problem in result.finish_errors:
            _err(say(lang, "finish_failed", problem=problem))
        sys.exit(FINISH_FAILED)
    click.echo(say(lang, "build_next", path=_shown(path)))


@main.command(help="help_serve")
@PORT_OPTION
@_option("--host", default=None, metavar="help_mv_host", help="help_opt_host")
@_option("--drafts/--no-drafts", default=True, help="help_opt_serve_drafts")
@WORKERS_OPTION
@NOTES_OPTION
@_path_argument
def serve(
    path: Path,
    port: int,
    host: str | None,
    drafts: bool,
    workers: int | None,
    notes: str | None,
) -> None:
    """Локальный просмотр с пересборкой при изменениях."""
    from heron.core.watch import default_host
    from heron.core.watch import serve as run_server

    lang = _lang(notes, path)
    _need_site(path, lang)
    inside = in_container()
    try:
        run_server(
            path,
            port=port,
            drafts=drafts,
            host=host or default_host(inside),
            lang=lang,
            in_container=inside,
            workers=workers,
        )
    except HeronError as error:
        _fail(error, lang)


@main.command(help="help_setup")
@_option(
    "--answers",
    "answers_file",
    default=None,
    metavar="help_mv_file",
    help="help_opt_answers",
)
@_option("--dump", is_flag=True, help="help_opt_dump")
@PORT_OPTION
@_option("--host", default=None, metavar="help_mv_host", help="help_opt_setup_host")
@NOTES_OPTION
@_path_argument
def setup(
    path: Path,
    answers_file: str | None,
    dump: bool,
    port: int,
    host: str | None,
    notes: str | None,
) -> None:
    """Конфигуратор-анкета. Справка — help_setup в heron/messages.py."""
    from heron import setup as configurator

    notes = notes or ctx_notes()
    lang = _lang(notes, path)
    _need_dir(path, lang)
    if not (path / "site.yaml").is_file():
        # Без этой проверки анкета открывалась пустой в любой папке: человек
        # заполнял её, а сайт лежал рядом, в другой папке, и ничего не знал.
        _err(say(lang, "setup_no_site", path=_shown(path)))
        _err(say(lang, "setup_no_site_hint", path=_shown(path)), None)
        sys.exit(1)
    if dump:
        click.echo(configurator.current_answers(path), nl=False)
        return
    inside = in_container()
    if answers_file is not None:
        text = sys.stdin.read() if answers_file == "-" else Path(answers_file).read_text("utf-8")
        try:
            answers = configurator.load_answers(text)
            result = configurator.apply(path, answers, lang=notes)
        except HeronError as error:
            _fail(error, lang)
        except ValueError as error:
            from heron.setup.server import _plain

            _err(say(lang, "setup_bad", problem=_plain(error)))
            sys.exit(2)
        _setup_report(result, lang, path)
        return

    from heron.core.watch import default_host, shown_url
    from heron.setup.server import run

    where = host or default_host(inside)

    def ready(token: str) -> None:
        url = f"{shown_url(where, port)}#{token}"
        click.secho(say(lang, "setup_open", url=url), fg="green", bold=True)
        if inside:
            click.echo(say(lang, "serve_container", port=port))

    try:
        run(path, where, port, on_ready=ready)
    except HeronError as error:
        _fail(error, lang)
    click.echo(say(lang, "serve_stopped"))


def _setup_report(result, lang: str, path: Path) -> None:
    click.secho(say(lang, "setup_done"), fg="green", bold=True)
    for key, items in (
        ("setup_written", result.written),
        ("setup_created", result.created),
        ("setup_removed", result.removed),
        ("setup_kept", result.kept),
    ):
        if items:
            shown = ", ".join(items[:8]) + (" …" if len(items) > 8 else "")
            click.echo("  " + say(lang, key, files=shown))
    if result.backup:
        click.echo("  " + say(lang, "setup_backup", file=result.backup))
    click.echo(say(lang, "setup_next", path=_shown(path)))


SCHEMA_KINDS = {
    "site": "site.schema.json",
    "theme": "theme.schema.json",
    "frontmatter": "frontmatter.schema.json",
    "setup": "setup.schema.json",
    "errors": "errors.json",
    "describe": "describe.schema.json",
}


def _write_schemas(target: Path, lang: str = "en", schema_lang: str | None = None) -> list[str]:
    """Шесть файлов схем в папку `target` — общим безопасным писателем (E024).

    Папку называет человек, и она может быть ссылкой. А вот ссылка или папка
    на месте файла схемы — ошибка до первой записи: `--export` не пишет туда,
    куда указывает чужая ссылка. Ошибка - на языке пояснений `lang`, описания в
    схемах - на `schema_lang` (по умолчанию тот же).
    """
    from heron.contracts.schemas import all_schemas
    from heron.scaffold.agents import write_files

    texts = all_schemas(schema_lang or lang)
    return write_files(target, [(name, text.encode("utf-8")) for name, text in texts.items()], lang)


@main.command(help="help_schema")
@_option("--site", "of_site", is_flag=True, help="help_opt_schema_site")
@_option("--theme", "of_theme", is_flag=True, help="help_opt_schema_theme")
@_option("--frontmatter", "of_frontmatter", is_flag=True, help="help_opt_schema_frontmatter")
@_option("--setup", "of_setup", is_flag=True, help="help_opt_schema_setup")
@_option("--errors", "of_errors", is_flag=True, help="help_opt_schema_errors")
@_option("--describe", "of_describe", is_flag=True, help="help_opt_schema_describe")
@_option(
    "--export",
    "target",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="help_mv_folder",
    help="help_opt_schema_export",
)
@_option(
    "--lang",
    "lang_flag",
    type=click.Choice(["ru", "en"]),
    default=None,
    metavar="help_mv_code",
    help="help_opt_schema_lang",
)
@NOTES_OPTION
def schema(
    of_site: bool,
    of_theme: bool,
    of_frontmatter: bool,
    of_setup: bool,
    of_errors: bool,
    of_describe: bool,
    target: Path | None,
    lang_flag: str | None,
    notes: str | None,
) -> None:
    """JSON Schema контрактов этой версии: для редактора, агента и CI (21 §10).

    Описания и названия ошибок - на языке `--lang`, иначе на языке пояснений
    (`--notes`, `HERON_NOTES`, `build.notes`, иначе en). Структура, ключи и `$id`
    от языка не зависят.
    """
    from heron.contracts import schemas

    lang = _lang(notes, Path.cwd())
    text_lang = lang_flag or lang
    chosen = [
        kind
        for kind, flag in (
            ("site", of_site),
            ("theme", of_theme),
            ("frontmatter", of_frontmatter),
            ("setup", of_setup),
            ("errors", of_errors),
            ("describe", of_describe),
        )
        if flag
    ]
    if len(chosen) > 1:
        flags = ", ".join(f"--{kind}" for kind in SCHEMA_KINDS)
        raise click.UsageError(say(lang, "schema_one_kind", flags=flags))
    if target is not None:
        try:
            written = _write_schemas(target, lang, text_lang)
        except HeronError as error:
            _fail(error, lang)
        for name in written:
            click.echo(str(target / name))
        click.secho(
            say(lang, "schema_exported", target=target, files=", ".join(written)),
            fg="green",
            err=True,
        )
        return
    kind = chosen[0] if chosen else "site"
    click.echo(schemas.all_schemas(text_lang)[SCHEMA_KINDS[kind]], nl=False)


@main.command(help="help_recipe")
@NOTES_OPTION
def recipe(notes: str | None) -> None:
    """Рецепт образа nginx: комментарии на языке пояснений текущей папки (F16)."""
    click.echo(recipe_for(_lang(notes, Path.cwd())), nl=False)


def recipe_for(lang: str) -> str:
    """Dockerfile.site этой версии; для en — с английскими комментариями (RECIPE_EN)."""
    from heron.docs import recipe_text

    text = recipe_text()
    if lang == "en":
        for ru, en in RECIPE_EN:
            text = text.replace(ru, en)
    return text


@main.group(help="help_theme")
@NOTES_OPTION
def theme(notes: str | None) -> None:
    """Темы: поставить, показать каталог, упаковать."""


@theme.command("get", help="help_theme_get")
@_argument("source", metavar="help_mv_source")
@_path_argument
@NOTES_OPTION
def theme_get(source: str, path: Path, notes: str | None) -> None:
    """Поставить тему по имени, ссылке или архиву."""
    from heron import themes
    from heron.scaffold import _declared

    lang = _lang(notes, path)
    _need_dir(path, lang)
    archive: Path | None = None
    if source.startswith("https://"):
        kind, value = "url", source
    elif source.startswith("http://"):
        _err(say(lang, "theme_https"))
        sys.exit(2)
    elif Path(source).is_file():
        # как набрано в терминале: от текущей папки (или абсолютный путь)
        kind, value, archive = "file", "", Path(source).resolve()
    elif (path / source).is_file():
        # иначе — от папки сайта; путь отдаётся абсолютным, чтобы install
        # не прибавил папку сайта второй раз
        kind, value, archive = "file", "", (path / source).resolve()
    else:
        kind, value = "name", source
    problem = site_yaml_problem(path / "site.yaml", lang)
    if problem is not None:
        _fail(problem, lang)
    declared = _declared(path / "site.yaml") or {}
    try:
        from heron.core import paths

        if (path / "site.yaml").exists() or (path / "site.yaml").is_symlink():
            paths.in_site(path, "site.yaml")  # E024 до установки, а не после
        installed = themes.install(
            path,
            kind,
            value,
            languages=declared.get("languages") or ["en"],
            archive=archive,
            notes=lang,
        )
    except HeronError as error:
        _fail(error, lang)
    if (path / "site.yaml").is_file():
        _set_theme_name(path / "site.yaml", installed.name)
    click.secho(say(lang, "theme_done", name=installed.name), fg="green", bold=True)
    if installed.backup:
        click.echo("  " + say(lang, "setup_backup", file=installed.backup))
    placed = [x for x in installed.created if x != "theme/"]
    if placed:
        # что именно легло: человек видит, какие файлы появились в его папке
        pages = len([x for x in placed if x.startswith("content/")])
        click.echo("  " + say(lang, "theme_demo", count=pages, files=len(placed)))
        for rel in placed:
            click.echo(f"    {rel}")
    if installed.kept:
        click.echo("  " + say(lang, "theme_demo_kept", count=len(installed.kept)))
    click.echo(say(lang, "setup_next", path=_shown(path)))


def _set_theme_name(site_yaml: Path, name: str) -> None:
    """Поменять `site.theme` одной строкой, не трогая остального файла."""
    text = site_yaml.read_text(encoding="utf-8")
    new, count = re.subn(
        r"(?m)^(\s+theme:\s*)([^\s#]+)(.*)$",
        lambda m: f"{m.group(1)}{name}{m.group(3)}",
        text,
        count=1,
    )
    if count:
        from heron.core import paths

        paths.in_site(site_yaml.parent, "site.yaml").write_text(new, encoding="utf-8")


@theme.command("list", help="help_theme_list")
@NOTES_OPTION
def theme_list(notes: str | None) -> None:
    """Каталог тем HERON."""
    from heron import themes

    lang = _lang(notes, Path.cwd())  # язык рамки ошибок click в этом запуске
    for item in themes.catalog():
        title = item.get("title") or item["name"]
        text = (item.get("description_ru") if lang == "ru" else None) or item.get("description")
        tail = f" - {text}" if text else ""
        click.echo(f"{item['name']:<16} {title}{tail}")


@theme.command("pack", help="help_theme_pack")
@_path_argument
@_option(
    "--out",
    "out",
    default=None,
    type=click.Path(path_type=Path),
    metavar="help_mv_file",
    help="help_opt_pack_out",
)
@NOTES_OPTION
def theme_pack(path: Path, out: Path | None, notes: str | None) -> None:
    """Упаковать тему сайта вместе с его контентом."""
    from heron import themes

    lang = _lang(notes, path)
    target = out or (path / "dist" / "theme.tar.gz")
    notices: list = []
    try:
        made = themes.pack(path, target, notices)
    except HeronError as error:
        _fail(error, lang)
    for notice in notices:
        _err(say(lang, "theme_pack_warning", warning=rendered(notice, lang)), "yellow")
    click.echo(str(made))


@main.command(help="help_page")
@_argument("page_type", metavar="help_mv_type")
@_argument("slug", metavar="help_mv_slug")
@_option("--lang", default=None, metavar="help_mv_code", help="help_opt_page_lang")
@_option("--folder", default="", metavar="help_mv_folder", help="help_opt_folder")
@NOTES_OPTION
@_path_argument
def page(
    page_type: str, slug: str, lang: str | None, folder: str, path: Path, notes: str | None
) -> None:
    """Заготовка страницы со всеми секциями своего типа."""
    from heron.scaffold.page import write_page

    language = _lang(notes, path)
    _need_site(path, language)
    try:
        # Комментарии заготовки write_page берёт из HERON_NOTES или build.notes:
        # --notes этого запуска передаётся ей тем же путём, на время записи.
        with _notes_env(notes or ctx_notes()):
            created = write_page(path, page_type=page_type, slug=slug, lang=lang, folder=folder)
    except HeronError as error:
        _fail(error, language)
    click.secho(say(language, "page_done", path=created), fg="green")
    click.echo(say(language, "page_next", root=_shown(path)))


@main.command(help="help_describe")
@_argument("name", required=False, metavar="help_mv_name")
@_option("--json", "as_json", is_flag=True, help="help_opt_describe_json")
@_option("--lang", "lang_flag", default=None, metavar="help_mv_code", help="help_opt_describe_lang")
@NOTES_OPTION
@_path_argument
def describe(
    name: str | None, as_json: bool, lang_flag: str | None, path: Path, notes: str | None
) -> None:
    """Контракт темы и служебные поля: человеку текстом, агенту - JSON (21 §10)."""
    import json

    from heron.contracts.site import LANG_RE
    from heron.core import describe as library

    language = _lang(notes, path)
    if lang_flag is not None and not LANG_RE.match(lang_flag):
        raise click.UsageError(say(language, "describe_bad_lang", lang=lang_flag))
    _need_site(path, language)
    try:
        theme_config, config = library.load(path)
        data = library.contract(theme_config, config, lang_flag or language, name)
    except HeronError as error:
        _fail(error, language)
    if as_json:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return
    click.echo((rendered(library.text(data, lang_flag or language), language) or "").rstrip("\n"))


@main.command(help="help_docs")
@_argument("name", required=False, metavar="help_mv_topic")
@_argument("file", required=False, metavar="help_mv_file")
@_option(
    "--lang",
    "lang_flag",
    type=click.Choice(["ru", "en"]),
    default=None,
    help="help_opt_docs_lang",
)
@_option("--search", "query", default=None, metavar="help_mv_text", help="help_opt_search")
@_option(
    "--export",
    "target",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="help_mv_folder",
    help="help_opt_docs_export",
)
@_option("--all-langs", "all_langs", is_flag=True, help="help_opt_all_langs")
@NOTES_OPTION
def docs(
    name: str | None,
    file: str | None,
    lang_flag: str | None,
    query: str | None,
    target: Path | None,
    all_langs: bool,
    notes: str | None,
) -> None:
    """Документация этой версии движка: оглавление, тема, поиск, выгрузка (21 §10)."""
    from heron import docs as library

    lang = lang_flag or _lang(notes, Path.cwd())
    _UI.lang = lang  # сообщения docs — на языке документации, рамка click тоже
    if all_langs and target is None:
        raise click.UsageError(say(lang, "docs_all_langs"))
    if query:
        found = library.search(query, lang)
        if not found:
            _err(say(lang, "docs_not_found", query=query), "yellow")
            sys.exit(1)
        click.echo("\n".join(found))
        return
    if target is not None:
        try:
            written = library.export(target, lang, all_langs=all_langs)
        except HeronError as error:
            _fail(error, lang)
        click.secho(say(lang, "docs_exported", target=target, n=len(written)), fg="green")
        if all_langs:
            click.echo(library.start_hint(target / lang, lang))
        else:
            click.echo(library.start_hint(target, lang))
        return
    if name is None:
        click.echo(library.contents(lang), nl=False)
        return
    if name == "theme-ref":
        site = Path(file or ".")
        # без --lang - язык пояснений самого сайта, а не текущей папки
        _theme_ref(site, lang_flag or _lang(notes, site))
        return
    if name == "template":
        names = library.templates(lang)
        if file not in names:
            _err(say(lang, "docs_no_template", file=file, names=", ".join(names)))
            sys.exit(1)
        found = library.localize(f"templates/{file}", lang)
        if found is not None and found.note:
            # образец копируют как есть: пометка — в stderr, не в текст файла
            click.echo(found.note, err=True)
        click.echo(library.read(f"{library.TEMPLATES}/{file}", lang), nl=False)
        return
    item = library.topic(name)
    if item is None:
        _err(say(lang, "docs_no_topic", name=name))
        sys.exit(1)
    click.echo(library.read(item.path, lang), nl=False)


def _theme_ref(path: Path, lang: str) -> None:
    """`heron docs theme-ref [путь]`: справка темы сайта из контракта и демо (21 §7)."""
    from heron.core.render import themeref

    _need_site(path, lang)
    try:
        data = themeref.load(path, lang)
    except HeronError as error:
        _fail(error, lang)
    click.echo((rendered(themeref.text(data, lang), lang) or "").rstrip("\n"))


if __name__ == "__main__":
    main()
