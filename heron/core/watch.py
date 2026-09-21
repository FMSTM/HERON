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

WATCHED = ("content", "data", "img", "static", "theme")
POLL = 1.0


def _stamp(root: Path) -> float:
    latest = 0.0
    for folder in (*WATCHED, "."):
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*") if base.is_dir() else [base]:
            if path.is_file() and ".heron-cache" not in path.parts and "dist" not in path.parts:
                latest = max(latest, path.stat().st_mtime)
    return latest


def preview_dist(root: Path) -> Path:
    """Куда собирать просмотр.

    Не в папку сайта: она монтируется только на чтение и принадлежит тому,
    кто правит контент. Локальный просмотр не имеет права оставлять в ней
    ни dist, ни кэш — иначе человек видит в своём репозитории мусор,
    которого не просил, и рано или поздно коммитит его.
    """
    key = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:10]
    return Path(tempfile.gettempdir()) / f"heron-serve-{root.name}-{key}" / "dist"


def once(root: Path, drafts: bool, dist: Path | None = None) -> None:
    try:
        result = pipeline.run(root, dist=dist, drafts=drafts)
    except HeronError as error:
        click.secho(str(error), fg="red")
        return
    if result.collector.errors:
        click.secho(report_module.summary(result.collector), fg="red")
        return
    click.secho(f"собрано: {len(result.written)} файлов", fg="green")
    if result.collector.warnings:
        click.secho(f"предупреждений: {len(result.collector.warnings)}", fg="yellow")


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


def serve(root: Path, port: int = 8000, drafts: bool = True) -> None:
    """Собрать, поднять сервер и пересобирать при изменениях."""
    root = Path(root).resolve()
    dist = preview_dist(root)
    once(root, drafts, dist)
    click.secho(f"собрано в {dist}", fg="cyan")

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

    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    click.secho(f"открыто: http://127.0.0.1:{port}/  (Ctrl+C — выход)", fg="green")

    last = _stamp(root)
    try:
        while True:
            time.sleep(POLL)
            current = _stamp(root)
            if current > last:
                last = current
                click.echo("изменения — пересобираю")
                once(root, drafts, dist)
    except KeyboardInterrupt:
        click.echo("\nостановлено")
    finally:
        server.shutdown()
