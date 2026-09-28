"""Дата обновления страницы: из истории репозитория или из времени файла.

Поле `updated` во фронтматтере заполняется руками, а значит почти всегда
врёт: правку вносят, дату забывают. Врёт при этом сразу в трёх местах —
в подписи под текстом, в `lastmod` карты сайта и в `dateModified`
разметки, — и одно из них читает поисковик.

Источник выбирается в `site.yaml`, ключом `build.updated_from`:

    manual  как было: только то, что написано во фронтматтере
    git     дата последнего коммита, затронувшего файл
    file    время файла на диске, сознательно и молча

Умолчание — `manual`: обновление движка не меняет поведение существующих
сайтов само по себе.

Спецификация: docs/spec/21-engine.md, раздел 4, этап 2.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

from heron.core.errors import Collector
from heron.core.models import Site

TIMEOUT = 30
STAMP = re.compile(r"^\d+$")

# Гит отказывается работать в папке, которой владеет кто-то другой. В нашем
# случае «кто-то другой» — хозяин папки сайта, а мы внутри контейнера с
# чужим uid, и это норма, а не подозрительная ситуация.
SAFE = ["-c", "safe.directory=*"]

# Сорок файлов, записанных в одну минуту, — это копирование, а не правка.
# Время файла говорит, когда его записали на диск, а не когда изменили
# текст: `cp` без `-a`, распаковка архива, свежий клон — и у всего сайта
# одна дата. Объявить в такой ситуации весь сайт обновлённым значит
# соврать поисковику, и соврать заметно.
HUDDLE = 60


def resolve(site: Site, site_root: Path, mode: str, collector: Collector) -> None:
    """Проставить страницам дату обновления по выбранному источнику.

    Ручное `updated` во фронтматтере не трогается никогда: есть страницы,
    где дата — факт, а не метка сборки, и двигать её перекомпиляцией нельзя.
    """
    if mode == "manual" or not site.pages:
        return

    content = site_root / "content"
    pages = [page for page in site.pages if page.meta.updated is None]
    if not pages:
        return

    if mode == "git":
        _by_git(pages, site_root, content, collector)
    else:
        _by_file(pages, content, collector, loud=True)


def _mtime(path: Path) -> date | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).date()
    except OSError:
        return None


def _git(site_root: Path, *args: str) -> str | None:
    """Позвать гит. Не вышло — вернуть ничего, а не уронить сборку."""
    try:
        done = subprocess.run(
            ["git", "-C", str(site_root), *SAFE, *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _history(site_root: Path) -> dict[str, date] | None:
    """Дата последнего коммита по каждому пути — одним вызовом.

    Не `git log -1` на файл: на сайте в несколько сотен страниц это сотни
    запусков процесса, минуты вместо секунд. Один обход истории отдаёт
    всё сразу, а первое попадание пути и есть последнее его изменение.

    Берётся дата автора, а не коммитера: коммитер переписывается при
    каждом ребейзе, и даты на сайте прыгали бы от перекладывания веток,
    хотя текст не менялся.

    Переименования не отслеживаются намеренно. Для сайта переименование
    файла — это смена адреса, то есть страница действительно изменилась.
    """
    prefix = _git(site_root, "rev-parse", "--show-prefix")
    out = _git(site_root, "log", "--pretty=format:%at", "--name-only", "--no-renames")
    if prefix is None or out is None:
        return None

    root = prefix.strip()
    found: dict[str, date] = {}
    stamp: date | None = None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if STAMP.match(line):
            stamp = datetime.fromtimestamp(int(line), UTC).date()
        elif stamp is not None and line.startswith(root):
            found.setdefault(line[len(root) :], stamp)
    return found


def _dirty(site_root: Path) -> set[str]:
    """Пути с незакоммиченными правками: их дата в истории уже неправда."""
    out = _git(site_root, "-c", "core.quotepath=false", "status", "--porcelain")
    if not out:
        return set()
    return {line[3:].strip().strip('"') for line in out.splitlines() if len(line) > 3}


def _by_git(pages, site_root: Path, content: Path, collector: Collector) -> None:
    history = _history(site_root)
    if history is None:
        collector.warn(
            f"истории нет — даты взяты из времени файлов, страниц {len(pages)}",
            path=str(site_root),
            kind="даты",
        )
        _by_file(pages, content, collector, loud=False)
        return

    dirty = _dirty(site_root)
    prefix = f"{content.name}/"
    for page in pages:
        rel = prefix + page.source
        if rel in dirty:
            page.auto_updated = _mtime(content / page.source)
            collector.warn(
                "файл изменён, но не закоммичен — дата взята из времени файла",
                path=page.source,
                kind="даты",
            )
            continue
        stamp = history.get(rel)
        if stamp is None:
            page.auto_updated = _mtime(content / page.source)
            collector.warn(
                "файла нет в истории — дата взята из времени файла",
                path=page.source,
                kind="даты",
            )
            continue
        page.auto_updated = stamp


def _by_file(pages, content: Path, collector: Collector, loud: bool) -> None:
    """Время файлов. С проверкой на подпись копирования."""
    stamps = {page.source: _mtime(content / page.source) for page in pages}
    times = [
        (content / page.source).stat().st_mtime
        for page in pages
        if stamps.get(page.source) is not None
    ]
    if len(times) > 1 and max(times) - min(times) <= HUDDLE:
        collector.warn(
            "у всех файлов одно время — так выглядит копирование, а не правка; "
            "дата обновления не проставлена",
            path=str(content),
            kind="даты",
        )
        return
    if loud:
        missing = [source for source, stamp in stamps.items() if stamp is None]
        for source in missing:
            collector.warn("файл не читается — даты нет", path=source, kind="даты")
    for page in pages:
        page.auto_updated = stamps.get(page.source)
