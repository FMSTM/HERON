"""Командный интерфейс HERON.

Шесть команд — вся поверхность движка для человека. Внутрь него заходить
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
from pathlib import Path

import click

from heron import __version__
from heron.core import build as pipeline
from heron.core import report as report_module
from heron.core.environment import BuildEnv
from heron.core.errors import HeronError
from heron.core.notes import NOTE
from heron.messages import say, title
from heron.scaffold import (
    SERVICE,
    Plan,
    adopt,
    create,
    foreign_files,
    placeholder_domain,
    resolve_notes,
)

DIST = "dist"


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


LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
CONTAINER_ENV = "HERON_IN_CONTAINER"


# --- язык и окружение ---------------------------------------------------------


def _lang(flag: str | None = None, root: Path | None = None) -> str:
    """Язык сообщений: тот же, что язык пояснений сайта. Не разобрался — en."""
    try:
        return resolve_notes(flag, root / "site.yaml" if root is not None else None)
    except ValueError:
        return "en"


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
    _err(say(lang, "error_head", code=error.code, title=title(lang, error.code)))
    if error.path:
        where = error.path if error.line is None else f"{error.path}:{error.line}"
        _err(say(lang, "error_where", where=where), None)
    _err(say(lang, "error_what", message=error.message), None)
    if error.hint:
        _err(say(lang, "error_hint", hint=error.hint), None)
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


class HeronGroup(click.Group):
    """Группа команд, которая не выпускает наружу трейсбек.

    Ошибки движка печатаются по форме; непредвиденные — коротко, с советом
    повторить с `--debug`. Сам `--debug` (или HERON_DEBUG=1) отдаёт трейсбек
    целиком — для того, кто чинит движок.
    """

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
            _fail(error, _lang())
        except PermissionError as error:
            if _debug(ctx):
                raise
            lang = _lang()
            _err(say(lang, "denied", path=error.filename or error))
            _err(say(lang, "denied_hint"), None)
            if error.filename and in_container():
                _err(_missing_hint(Path(error.filename), lang), None)
            sys.exit(1)
        except Exception as error:  # noqa: BLE001 — последний рубеж перед человеком
            if _debug(ctx):
                raise
            lang = _lang()
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
    summary = report_module.summary(result.collector, full=full)
    if result.collector.errors:
        _err(summary)
        _err("\n" + say(lang, f"{kind}_failed", count=len(result.collector.errors)))
        sys.exit(1)

    if result.report is not None:
        click.echo(result.report.render())
    if summary:
        click.secho(summary, fg="yellow")

    if strict and result.collector.warnings:
        _err(say(lang, f"{kind}_strict", count=len(result.collector.warnings)))
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


def _report_plan(plan: Plan, verbose: bool = False) -> None:
    lang = plan.notes
    if plan.found:
        click.echo(say(lang, "plan_found"))
        for line in plan.found:
            click.echo(f"  · {line}")
    if plan.created:
        click.echo(say(lang, "plan_made"))
        if verbose:
            for name in plan.created:
                click.secho(f"  + {name}", fg="green")
        else:
            for line in _group_plan(plan.created, lang):
                click.secho(f"  + {line}", fg="green")
    else:
        click.echo(say(lang, "plan_nothing"))
    if plan.skipped:
        if verbose or len(plan.skipped) <= 5:
            click.echo(say(lang, "plan_kept", files=", ".join(plan.skipped)))
        else:
            click.echo(say(lang, "plan_kept_many", count=len(plan.skipped)))


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
    if in_container():
        click.echo("  " + say(lang, "next_docker"))


# --- команды ------------------------------------------------------------------


@click.group(cls=HeronGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="heron")
@click.option(
    "--debug",
    is_flag=True,
    help="Показать трейсбек непредвиденной ошибки. То же — HERON_DEBUG=1.",
)
def main(debug: bool) -> None:
    """HERON — файловый движок сайтов."""


NOTES_OPTION = click.option(
    "--notes",
    type=click.Choice(["ru", "en"]),
    default=None,
    help="Язык комментариев в файлах сайта и сообщений на экране: ru или en. "
    "Иначе HERON_NOTES, иначе build.notes из site.yaml, иначе en.",
)
VERBOSE_OPTION = click.option(
    "-v", "--verbose", is_flag=True, help="Перечислить каждый созданный файл."
)


def _ask(lang: str, key: str, default: str, check) -> str:
    """Один вопрос: подсказка, значение по умолчанию, повтор до годного ответа."""
    click.echo(
        click.style(say(lang, key), bold=True)
        + click.style(f" — {say(lang, key + '_help')}", dim=True)
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
            return say(lang, "bad_langs", bad=", ".join(bad) or "—")
        return None

    return check


def _check_domain(lang: str):
    def check(text: str) -> str | None:
        return None if DOMAIN_RE.match(text.lower()) else say(lang, "bad_domain")

    return check


def _questionnaire(
    lang: str, name: str, domain: str, languages: list[str], default: str
) -> tuple[str, str, list[str], str] | None:
    """Опрос в терминале. Отказ на последнем шаге — None, ничего не создаётся."""
    click.echo(say(lang, "ask_intro") + "\n")
    name = _ask(lang, "ask_name", name, lambda text: None if text else "—")
    domain = _ask(lang, "ask_domain", domain or placeholder_domain(name), _check_domain(lang))
    domain = domain.lower()
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


@main.command()
@NOTES_OPTION
@VERBOSE_OPTION
@click.option("--name", "site_name", default=None, help="Название сайта.")
@click.option("--domain", default=None, help="Домен без схемы: example.com.")
@click.option(
    "--lang",
    "langs",
    default=None,
    metavar="КОДЫ",
    help="Языки через запятую, первый — основной: en или en,ru.",
)
@click.option(
    "-y", "--yes", is_flag=True, help="Не задавать вопросов: флаги и значения по умолчанию."
)
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def new(
    path: Path,
    notes: str | None,
    verbose: bool,
    site_name: str | None,
    domain: str | None,
    langs: str | None,
    yes: bool,
) -> None:
    """Создать сайт с нуля: в новой папке или в текущей (`.`).

    В терминале задаёт пять вопросов: язык пояснений, название, домен,
    языки сайта, основной язык. Без терминала (агент, CI, docker без -it)
    не спрашивает: значения из флагов или по умолчанию.

    Папка может быть под git: .git, .gitignore, README и прочее служебное
    не мешают.
    """
    lang = _lang(notes)
    foreign = foreign_files(path)
    if foreign:
        shown = ", ".join(foreign[:5]) + ("…" if len(foreign) > 5 else "")
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

    asking = can_ask() and not yes
    if asking and notes is None and not os.environ.get("HERON_NOTES"):
        click.echo(
            click.style("Notes and messages language / Язык пояснений и сообщений", bold=True)
        )
        lang = click.prompt("  ›", type=click.Choice(["en", "ru"]), default="en", prompt_suffix=" ")

    folder = path.resolve().name
    # в контейнере текущая папка называется /site — имя ничего не говорит
    guess = site_name or (folder if not (in_container() and folder == "site") else "my-site")
    languages = _parse_langs(langs) if langs else ["en"]
    bad = [x for x in languages if not LANG_RE.match(x)]
    if bad or not languages:
        _err(say(lang, "bad_langs", bad=", ".join(bad) or "—"))
        sys.exit(2)
    if domain and not DOMAIN_RE.match(domain.lower()):
        _err(say(lang, "bad_domain"))
        sys.exit(2)

    click.secho(say(lang, "new_title", path=_shown(path)), bold=True)
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
    plan = create(
        path,
        name=guess,
        languages=languages,
        notes=lang,
        domain=domain.lower() if domain else None,
        default_lang=default,
    )
    click.secho("\n" + say(lang, "new_done", path=_shown(path)), fg="green", bold=True)
    _report_plan(plan, verbose)
    ordered = [default] + [x for x in languages if x != default]
    _next(path, lang, ordered, domain.lower() if domain else placeholder_domain(guess))


@main.command()
@click.option("--force", is_flag=True, help="Перезаписывать существующие файлы.")
@NOTES_OPTION
@VERBOSE_OPTION
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def init(path: Path, force: bool, notes: str | None, verbose: bool) -> None:
    """Дополнить папку недостающим по тому, что написано в site.yaml.

    Ничего не перезаписывает без --force. Нет site.yaml — кладёт его и
    весь скелет. Язык пояснений: --notes, иначе HERON_NOTES, иначе
    build.notes из site.yaml, иначе en.
    """
    _need_dir(path, _lang(notes, path))
    plan = adopt(path, force=force, notes=notes)
    click.secho(say(plan.notes, "init_done", path=_shown(path)), fg="green", bold=True)
    _report_plan(plan, verbose)
    from heron.scaffold import _declared

    declared = _declared(path / "site.yaml") or {}
    domain = None
    try:
        import yaml

        data = yaml.safe_load((path / "site.yaml").read_text(encoding="utf-8")) or {}
        domain = str((data.get("site") or {}).get("domain") or "") or None
    except Exception:  # noqa: BLE001 — конфиг проверит сборка
        pass
    _next(path, plan.notes, declared.get("languages") or ["en"], domain)


@main.command()
@click.option("--strict", is_flag=True, help="Считать предупреждения ошибками.")
@click.option("--drafts", is_flag=True, help="Включить страницы с published: false.")
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def check(path: Path, strict: bool, drafts: bool) -> None:
    """Проверить контент и конфиг, ничего не собирая."""
    lang = _lang(None, path)
    _need_site(path, lang)
    click.secho(
        say(lang, "check_head", version=__version__, path=_shown(path)), bold=True, err=True
    )
    try:
        result = pipeline.check(path, drafts=drafts)
    except HeronError as error:
        _fail(error, lang)
    _finish(result, strict, lang, "check")
    click.secho(say(lang, "check_done", path=_shown(path)), fg="green")


@main.command()
@click.option("--strict", is_flag=True, help="Считать предупреждения ошибками.")
@click.option("--drafts", is_flag=True, help="Включить страницы с published: false.")
@click.option("--out", default=None, type=click.Path(path_type=Path), help="Куда собирать.")
@click.option(
    "--env",
    "env_name",
    default=None,
    metavar="ИМЯ",
    help="Окружение сборки: prod открывает индексацию и счётчики, всё прочее — нет.",
)
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def build(path: Path, strict: bool, drafts: bool, out: Path | None, env_name: str | None) -> None:
    """Собрать сайт в dist/ или в указанную папку."""
    lang = _lang(None, path)
    _need_site(path, lang)
    env = BuildEnv.resolve(env_name)
    click.secho(
        say(lang, "build_head", version=__version__, path=_shown(path), env=env.name),
        bold=True,
        err=True,
    )
    try:
        result = pipeline.run(
            path, dist=out, drafts=drafts, strict=strict, env=env, progress=_Terminal(lang)
        )
    except HeronError as error:
        _fail(error, lang)

    target = out or (path / DIST)
    _finish(result, strict, lang, "build", full=target.parent / ".heron-cache" / "warnings.txt")
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
    click.echo(say(lang, "build_next", path=_shown(path)))


@main.command()
@click.option("--port", default=8000, show_default=True)
@click.option("--drafts/--no-drafts", default=True, show_default=True)
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def serve(path: Path, port: int, drafts: bool) -> None:
    """Локальный просмотр с пересборкой при изменениях."""
    from heron.core.watch import serve as run_server

    _need_site(path, _lang(None, path))
    run_server(path, port=port, drafts=drafts)


@main.command()
@click.argument("page_type")
@click.argument("slug")
@click.option("--lang", default=None, help="Язык. По умолчанию основной язык сайта.")
@click.option("--folder", default="", help="Папка внутри языкового дерева.")
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def page(page_type: str, slug: str, lang: str | None, folder: str, path: Path) -> None:
    """Заготовка страницы со всеми секциями своего типа."""
    from heron.scaffold.page import write_page

    language = _lang(None, path)
    _need_site(path, language)
    try:
        created = write_page(path, page_type=page_type, slug=slug, lang=lang, folder=folder)
    except HeronError as error:
        _fail(error, language)
    click.secho(say(language, "page_done", path=created), fg="green")
    click.echo(say(language, "page_next", root=_shown(path)))


if __name__ == "__main__":
    main()
