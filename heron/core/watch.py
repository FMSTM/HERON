"""Локальный просмотр с пересборкой.

Инкрементальная сборка на этом объёме не нужна: сотня страниц собирается
за секунды. Поэтому при изменении любого файла пересобирается всё — это
проще, предсказуемее и не расходится с тем, что соберёт прод.
"""

from __future__ import annotations

import http.server
import socketserver
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


def once(root: Path, drafts: bool) -> None:
    try:
        result = pipeline.run(root, drafts=drafts)
    except HeronError as error:
        click.secho(str(error), fg="red")
        return
    if result.collector.errors:
        click.secho(report_module.summary(result.collector), fg="red")
        return
    click.secho(f"собрано: {len(result.written)} файлов", fg="green")
    if result.collector.warnings:
        click.secho(f"предупреждений: {len(result.collector.warnings)}", fg="yellow")


def serve(root: Path, port: int = 8000, drafts: bool = True) -> None:
    """Собрать, поднять сервер и пересобирать при изменениях."""
    root = Path(root).resolve()
    dist = root / "dist"
    once(root, drafts)

    handler = type(
        "Handler",
        (http.server.SimpleHTTPRequestHandler,),
        {
            "directory_root": str(dist),
            "__init__": lambda self, *a, **kw: http.server.SimpleHTTPRequestHandler.__init__(
                self, *a, directory=str(dist), **kw
            ),
            "log_message": lambda self, *a: None,
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
                once(root, drafts)
    except KeyboardInterrupt:
        click.echo("\nостановлено")
    finally:
        server.shutdown()
