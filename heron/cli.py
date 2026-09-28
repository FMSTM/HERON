"""Командный интерфейс HERON.

Шесть команд — вся поверхность движка для человека. Внутрь него заходить
не нужно: ни один сценарий работы с сайтом этого не требует.

Спецификация: docs/spec/23-distribution.md, раздел 3.
"""

from __future__ import annotations

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
from heron.scaffold import Plan, adopt, create

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

    def __init__(self) -> None:
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

    def step(self, title: str) -> None:
        self._title = title
        self._detail = ""
        self._started = time.monotonic()
        self._said = self._started
        if not self._interactive:
            self._say(f"→ {title}…")
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

    def done(self, detail: str = "") -> None:
        text = detail or "готово"
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


def _fail(error: HeronError) -> None:
    click.secho(str(error), fg="red", err=True)
    sys.exit(1)


def _finish(result: pipeline.Result, strict: bool, what: str, full: Path | None = None) -> None:
    """Напечатать сводку и выйти с нужным кодом."""
    summary = report_module.summary(result.collector, full=full)
    if result.collector.errors:
        click.secho(summary, fg="red", err=True)
        click.secho(f"\n{what} не выполнена: ошибок {len(result.collector.errors)}", fg="red")
        sys.exit(1)

    if result.report is not None:
        click.echo(result.report.render())
    if summary:
        click.secho(summary, fg="yellow")

    if strict and result.collector.warnings:
        click.secho(
            f"{what} остановлена: --strict, предупреждений {len(result.collector.warnings)}",
            fg="red",
        )
        sys.exit(1)


def _report_plan(plan: Plan) -> None:
    for line in plan.found:
        click.echo(f"  нашёл: {line}")
    for name in plan.created:
        click.secho(f"  создал: {name}", fg="green")
    if plan.skipped:
        click.echo(f"  оставил как есть: {len(plan.skipped)} файлов")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="heron")
def main() -> None:
    """HERON — файловый движок сайтов."""


@main.command()
@click.argument("name")
def new(name: str) -> None:
    """Создать папку сайта с нуля.

    Ни языков, ни темы аргументами: всё это объявляет site.yaml, и он
    единственный источник правды. Заполнили его — `heron init` достроит
    папки под написанное.
    """
    root = Path(name)
    if root.exists() and any(root.iterdir()):
        click.secho(f"папка {name} не пуста — используйте `heron init` внутри неё", fg="red")
        sys.exit(1)
    root.mkdir(parents=True, exist_ok=True)
    plan = create(root, name=name)
    click.secho(f"сайт {name} создан", fg="green")
    _report_plan(plan)
    click.echo(
        "\nдальше:\n"
        f"  1. заполните {name}/site.yaml — домен, языки, тема, меню\n"
        f"  2. heron init {name} — папки догонят конфиг\n"
        "  3. разложите контент и собирайте"
    )


@main.command()
@click.option("--force", is_flag=True, help="Перезаписывать существующие файлы.")
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def init(path: Path, force: bool) -> None:
    """Дополнить существующую папку недостающим."""
    plan = adopt(path, force=force)
    click.secho(f"папка {path} дополнена", fg="green")
    _report_plan(plan)


@main.command()
@click.option("--strict", is_flag=True, help="Считать предупреждения ошибками.")
@click.option("--drafts", is_flag=True, help="Включить страницы с published: false.")
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def check(path: Path, strict: bool, drafts: bool) -> None:
    """Проверить контент и конфиг, ничего не собирая."""
    try:
        result = pipeline.check(path, drafts=drafts)
    except HeronError as error:
        _fail(error)
    _finish(result, strict, "Проверка")


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
    env = BuildEnv.resolve(env_name)
    click.secho(f"HERON {__version__} · окружение {env.name}", bold=True, err=True)
    try:
        result = pipeline.run(
            path, dist=out, drafts=drafts, strict=strict, env=env, progress=_Terminal()
        )
    except HeronError as error:
        _fail(error)

    target = out or (path / DIST)
    _finish(result, strict, "Сборка", full=target.parent / ".heron-cache" / "warnings.txt")
    # Одной строкой — чем собралось. Домен выбирается окружением, и
    # страховки «дев канонизируется на прод» больше нет: «собрал не то»
    # должно быть видно сразу, а не через неделю из выдачи.
    index = "индексация закрыта" if not env.indexable else "ИНДЕКСАЦИЯ ОТКРЫТА"
    counters = "счётчики выключены" if not env.analytics else "счётчики включены"
    click.secho(
        f"окружение {env.name} · домен {result.config.site.domain} · {index} · {counters}",
        fg="yellow" if not env.indexable else "green",
    )
    click.secho(f"собрано файлов: {len(result.written)} → {target}", fg="green")


@main.command()
@click.option("--port", default=8000, show_default=True)
@click.option("--drafts/--no-drafts", default=True, show_default=True)
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def serve(path: Path, port: int, drafts: bool) -> None:
    """Локальный просмотр с пересборкой при изменениях."""
    from heron.core.watch import serve as run_server

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

    try:
        created = write_page(path, page_type=page_type, slug=slug, lang=lang, folder=folder)
    except HeronError as error:
        _fail(error)
    click.secho(f"создан {created}", fg="green")


if __name__ == "__main__":
    main()
