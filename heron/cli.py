"""Командный интерфейс HERON.

Шесть команд — вся поверхность движка для человека. Внутрь движка заходить не нужно.
Спецификация: docs/spec/23-distribution.md, раздел 3.
"""

from __future__ import annotations

import sys

import click

from heron import __version__

NOT_READY = "Команда `{name}` ещё не реализована.\nЗадача {task} в registry/tasks.yaml проекта."


def _todo(name: str, task: str) -> None:
    click.echo(NOT_READY.format(name=name, task=task), err=True)
    sys.exit(2)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="heron")
def main() -> None:
    """HERON — файловый движок сайтов."""


@main.command()
@click.argument("name")
@click.option("--lang", default="uk", help="Языки сайта через запятую.")
@click.option("--theme", default=None, help="Имя темы. По умолчанию скелет в theme/.")
@click.option("--no-docker", is_flag=True, help="Не класть Dockerfile, compose.yml и build.sh.")
def new(name: str, lang: str, theme: str | None, no_docker: bool) -> None:
    """Создать папку сайта с нуля."""
    _todo("new", "E5.S1.T2")


@main.command()
@click.option("--force", is_flag=True, help="Перезаписывать существующие файлы.")
def init(force: bool) -> None:
    """Дополнить существующую папку недостающим."""
    _todo("init", "E5.S1.T3")


@main.command()
@click.option("--strict", is_flag=True, help="Считать предупреждения ошибками.")
def check(strict: bool) -> None:
    """Проверить контент и конфиг без сборки."""
    _todo("check", "E5.S1.T1")


@main.command()
@click.option("--port", default=8000, show_default=True)
def serve(port: int) -> None:
    """Локальный просмотр с пересборкой при изменениях."""
    _todo("serve", "E5.S1.T1")


@main.command()
@click.option("--drafts", is_flag=True, help="Включить страницы с published: false.")
@click.option("--strict", is_flag=True, help="Считать предупреждения ошибками.")
@click.option("--image", default=None, metavar="TAG", help="Упаковать результат в образ nginx.")
def build(drafts: bool, strict: bool, image: str | None) -> None:
    """Собрать сайт в dist/ или в образ."""
    _todo("build --image" if image else "build", "E5.S1.T5" if image else "E5.S1.T1")


@main.command()
@click.argument("page_type")
@click.argument("slug")
@click.option("--lang", default="uk", show_default=True)
def page(page_type: str, slug: str, lang: str) -> None:
    """Заготовка md-файла со всеми секциями типа."""
    _todo("page", "E5.S1.T4")


if __name__ == "__main__":
    main()
