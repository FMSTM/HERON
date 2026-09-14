"""Командный интерфейс HERON.

Шесть команд — вся поверхность движка для человека. Внутрь него заходить
не нужно: ни один сценарий работы с сайтом этого не требует.

Спецификация: docs/spec/23-distribution.md, раздел 3.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from heron import __version__
from heron.core import build as pipeline
from heron.core import report as report_module
from heron.core.errors import HeronError
from heron.scaffold import Plan, adopt, create

DIST = "dist"


def _fail(error: HeronError) -> None:
    click.secho(str(error), fg="red", err=True)
    sys.exit(1)


def _finish(result: pipeline.Result, strict: bool, what: str) -> None:
    """Напечатать сводку и выйти с нужным кодом."""
    summary = report_module.summary(result.collector)
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
@click.option("--lang", default="uk", help="Языки сайта через запятую. Первый — основной.")
@click.option("--theme", default=None, help="Имя темы. По умолчанию main.")
@click.option("--no-docker", is_flag=True, help="Не класть Dockerfile, compose.yml и build.sh.")
def new(name: str, lang: str, theme: str | None, no_docker: bool) -> None:
    """Создать папку сайта с нуля."""
    root = Path(name)
    if root.exists() and any(root.iterdir()):
        click.secho(f"папка {name} не пуста — используйте `heron init` внутри неё", fg="red")
        sys.exit(1)
    root.mkdir(parents=True, exist_ok=True)
    plan = create(
        root,
        name=name,
        languages=[part.strip() for part in lang.split(",") if part.strip()],
        theme=theme,
        docker=not no_docker,
    )
    click.secho(f"сайт {name} создан", fg="green")
    _report_plan(plan)
    click.echo("\nдальше: cd " + name + " && heron serve")


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
@click.option("--image", default=None, metavar="TAG", help="Упаковать результат в образ nginx.")
@click.option("--out", default=None, type=click.Path(path_type=Path), help="Куда собирать.")
@click.argument("path", type=click.Path(file_okay=False, path_type=Path), default=".")
def build(path: Path, strict: bool, drafts: bool, image: str | None, out: Path | None) -> None:
    """Собрать сайт в dist/ или в образ."""
    try:
        result = pipeline.run(path, dist=out, drafts=drafts, strict=strict)
    except HeronError as error:
        _fail(error)

    _finish(result, strict, "Сборка")
    target = out or (path / DIST)
    click.secho(f"собрано файлов: {len(result.written)} → {target}", fg="green")

    if image:
        _pack(path, image)


def _pack(path: Path, tag: str) -> None:
    """Упаковать собранный сайт в образ. Выполняет хост, не контейнер."""
    if shutil.which("docker") is None:
        click.secho(
            "собрать образ отсюда нельзя: docker недоступен.\n"
            "Запустите ./build.sh --image " + tag + " на хосте — "
            "сокет докера внутрь контейнера не пробрасывается никогда.",
            fg="red",
        )
        sys.exit(1)
    if not (path / "Dockerfile").is_file():
        click.secho(f"нет {path}/Dockerfile — нечем упаковывать", fg="red")
        sys.exit(1)
    import subprocess

    subprocess.run(["docker", "build", "-t", tag, str(path)], check=True)
    click.secho(f"готов образ {tag}", fg="green")


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
