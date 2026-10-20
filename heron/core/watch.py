"""Локальный просмотр с пересборкой.

Инкрементальная сборка на этом объёме не нужна: сотня страниц собирается
за секунды. Поэтому при изменении любого файла пересобирается всё — это
проще, предсказуемее и не расходится с тем, что соберёт прод.
"""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import tempfile
import threading
import time
from pathlib import Path

import click

from heron.core import build as pipeline
from heron.core import report as report_module
from heron.core.errors import HeronError
from heron.messages import say


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _Server6(_Server):
    import socket as _socket

    address_family = _socket.AF_INET6


# plugins — код локальных плагинов сайта: правка плагина меняет сборку так же,
# как правка темы.
WATCHED = ("content", "data", "media", "img", "static", "theme", "plugins")
POLL = 1.0


Snapshot = dict[str, tuple[int, int]]


def snapshot(root: Path) -> Snapshot:
    """Состав и состояние файлов сайта: путь → (время в нс, размер).

    Сравнивался один максимальный mtime — и удаление, переименование или
    файл, скопированный со старым временем, пересборку не будили. Снимок
    видит и состав, и каждое изменение. Обход один: папки сайта рекурсивно,
    корень — только верхним уровнем (site.yaml и соседи), без повторного
    прохода по тем же папкам.
    """
    found: Snapshot = {}

    def take(path: Path, name: str) -> None:
        # Файл, исчезнувший между обходом и stat (временный файл редактора),
        # просто не попадает в снимок, а не роняет просмотр.
        try:
            if path.is_file():
                stat = path.stat()
                found[name] = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            pass

    for entry in sorted(root.iterdir()) if root.is_dir() else []:
        take(entry, entry.name)
    for folder in WATCHED:
        base = root / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            take(path, path.relative_to(root).as_posix())
    return found


def changed(before: Snapshot, after: Snapshot) -> list[str]:
    """Что изменилось: добавлено, удалено, переименовано или правлено."""
    return sorted(
        {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    )


def preview_dist(root: Path) -> Path:
    """Куда собирать просмотр.

    Не в папку сайта: она монтируется только на чтение и принадлежит тому,
    кто правит контент. Локальный просмотр не имеет права оставлять в ней
    ни dist, ни кэш — иначе человек видит в своём репозитории мусор,
    которого не просил, и рано или поздно коммитит его.
    """
    key = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:10]
    return Path(tempfile.gettempdir()) / f"heron-serve-{root.name}-{key}" / "dist"


def once(root: Path, drafts: bool, dist: Path | None = None, lang: str = "en") -> None:
    try:
        result = pipeline.run(root, dist=dist, drafts=drafts)
    except HeronError as error:
        click.secho(str(error), fg="red")
        return
    if result.collector.errors:
        click.secho(report_module.summary(result.collector), fg="red")
        return
    click.secho(say(lang, "serve_built", count=len(result.written)), fg="green")
    if result.collector.warnings:
        click.secho(say(lang, "serve_warnings", count=len(result.collector.warnings)), fg="yellow")


# Внутри контейнера 127.0.0.1 — это сам контейнер: проброшенный порт
# (`docker run -p 8000:8000`) приходит на его внешний интерфейс, и сервер,
# слушающий только петлю, снаружи не открывается. Поэтому в образе
# умолчание — все интерфейсы, а на машине человека — только своя:
# просмотр черновиков не должен быть виден всей сети кафе.
LOOPBACK = "127.0.0.1"
EVERYWHERE = "0.0.0.0"


def default_host(in_container: bool) -> str:
    """Где слушать, если `--host` не задан."""
    return EVERYWHERE if in_container else LOOPBACK


def shown_url(host: str, port: int) -> str:
    """Адрес, который человеку открыть в браузере.

    `0.0.0.0` — не адрес, по нему браузер не ходит: показываем localhost.
    """
    visible = "localhost" if host in (EVERYWHERE, "::", "") else host
    if ":" in visible and not visible.startswith("["):
        visible = f"[{visible}]"
    return f"http://{visible}:{port}/"


def not_found(dist: Path, path: str) -> Path | None:
    """Наша страница 404 для этого адреса: сначала на его языке.

    Локальный просмотр должен показывать то же, что покажет сеть, иначе
    нарисованную 404 никто не увидит до самого прода.
    """
    lang = path.strip("/").split("/", 1)[0]
    for candidate in (dist / lang / "404" / "index.html", dist / "404.html"):
        if candidate.is_file():
            return candidate
    return None


def _send_404(handler: http.server.SimpleHTTPRequestHandler, dist: Path) -> bool:
    page = not_found(dist, handler.path)
    if page is None:
        return False
    body = page.read_bytes()
    handler.send_response(404)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)
    return True


def serve(
    root: Path,
    port: int = 8000,
    drafts: bool = True,
    host: str = LOOPBACK,
    lang: str = "en",
    in_container: bool = False,
) -> None:
    """Собрать, поднять сервер и пересобирать при изменениях."""
    root = Path(root).resolve()
    dist = preview_dist(root)
    once(root, drafts, dist, lang)
    click.secho(say(lang, "serve_dist", dist=dist), fg="cyan")

    handler = type(
        "Handler",
        (http.server.SimpleHTTPRequestHandler,),
        {
            "directory_root": str(dist),
            "__init__": lambda self, *a, **kw: http.server.SimpleHTTPRequestHandler.__init__(
                self, *a, directory=str(dist), **kw
            ),
            "log_message": lambda self, *a: None,
            "send_error": lambda self, code, message=None, explain=None: (
                None
                if code == 404 and _send_404(self, dist)
                else http.server.SimpleHTTPRequestHandler.send_error(self, code, message, explain)
            ),
        },
    )

    server_class = _Server6 if ":" in host else _Server
    try:
        server = server_class((host, port), handler)
    except OSError as error:
        raise HeronError(
            code="E031",
            message=say(lang, "serve_busy", host=host, port=port, problem=error.strerror or error),
            hint=say(lang, "serve_busy_hint", port=port, next=port + 1),
        ) from error
    threading.Thread(target=server.serve_forever, daemon=True).start()
    click.secho(say(lang, "serve_open", url=shown_url(host, port)), fg="green")
    if in_container:
        click.echo(say(lang, "serve_container", port=port))
    elif host not in (LOOPBACK, "localhost", "::1"):
        click.secho(say(lang, "serve_lan", port=port), fg="yellow")

    last = snapshot(root)
    try:
        while True:
            time.sleep(POLL)
            current = snapshot(root)
            diff = changed(last, current)
            if diff:
                last = current
                shown = ", ".join(diff[:3]) + (
                    say(lang, "serve_more", count=len(diff) - 3) if len(diff) > 3 else ""
                )
                click.echo(say(lang, "serve_changed", files=shown))
                once(root, drafts, dist, lang)
    except KeyboardInterrupt:
        click.echo("\n" + say(lang, "serve_stopped"))
    finally:
        server.shutdown()
