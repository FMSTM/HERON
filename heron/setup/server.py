"""Локальная страница анкеты `heron setup`.

Сервер живёт ровно столько, сколько открыта анкета. Граница доступа — токен,
который видит только тот, кто запустил анкету: движок печатает его в терминале
в адресе страницы (`http://localhost:8000/#ключ`). В саму страницу токен не
вшивается: её может получить любой, кто дотянулся до порта, а читать
настройки, загружать тему и записывать site.yaml без токена нельзя — каждый
запрос `/api/*` несёт его в заголовке X-Heron-Token. Часть после `#` браузер
на сервер не отправляет, поэтому ключ не попадает ни в журналы, ни в Referer.

Заголовок Host дополнительно обязан быть локальным: это закрывает подмену DNS
(чужой сайт, имя которого вдруг указывает на 127.0.0.1), но границей доступа
не является — его подделывает любой клиент.

В образе HERON сервер слушает все интерфейсы контейнера, а порт публикуется
только на петлю машины: `-p 127.0.0.1:8000:8000`. На машине человека сервер
слушает только 127.0.0.1 — те же правила, что у `heron serve`.
"""

from __future__ import annotations

import hmac
import http.server
import json
import secrets
import socketserver
import tempfile
import threading
from pathlib import Path
from typing import Any

from heron.core.errors import HeronError

PAGE = Path(__file__).parent / "page.html"
MAX_BODY = 210 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"}


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run(root: Path, host: str, port: int, in_container: bool, on_ready=None) -> None:
    """Поднять анкету. `on_ready(token)` вызывается, когда порт открыт."""
    from heron import setup

    token = secrets.token_urlsafe(24)
    uploads: dict[str, Path] = {}
    workdir = tempfile.TemporaryDirectory(prefix="heron-setup-")
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "heron-setup"

        def log_message(self, *args: Any) -> None:
            return

        def _local(self) -> bool:
            name = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
            return name in LOCAL_HOSTS

        def _allowed(self) -> bool:
            given = self.headers.get("X-Heron-Token") or ""
            return self._local() and hmac.compare_digest(given.encode(), token.encode())

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: Any) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            if not self._local():
                self._json(403, {"error": "local only"})
                return
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif not self._allowed():
                self._json(403, {"error": "open the address printed in the terminal"})
            elif self.path == "/api/state":
                self._json(200, setup.state(root, in_container))
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed():
                self._json(403, {"error": "open the address printed in the terminal"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._json(413, {"error": "too large"})
                return
            body = self.rfile.read(length)
            if self.path == "/api/upload":
                ident = secrets.token_hex(8)
                path = Path(workdir.name) / f"{ident}.archive"
                path.write_bytes(body)
                uploads[ident] = path
                self._json(200, {"ok": True, "upload": ident})
                return
            if self.path == "/api/stop":
                self._json(200, {"ok": True})
                done.set()
                return
            if self.path != "/api/save":
                self._json(404, {"error": "not found"})
                return
            try:
                data = json.loads(body.decode("utf-8") or "{}")
                answers = setup.Answers.model_validate(data.get("answers") or {})
                upload = uploads.get(str(data.get("upload") or ""))
                result = setup.apply(
                    root,
                    answers,
                    in_container=in_container,
                    upload=upload,
                )
            except HeronError as error:
                self._json(400, {"ok": False, "error": error.message, "hint": error.hint or ""})
                return
            except ValueError as error:
                self._json(400, {"ok": False, "error": _plain(error)})
                return
            self._json(
                200,
                {
                    "ok": True,
                    "written": result.written,
                    "removed": result.removed,
                    "kept": result.kept,
                    "created": result.created,
                    "theme": result.theme,
                    "backup": result.backup,
                    "warnings": result.warnings,
                    "state": setup.state(root, in_container),
                },
            )

    try:
        server = _Server((host, port), Handler)
    except OSError as error:
        raise HeronError(
            code="E031",
            message=f"cannot open the configurator on {host}:{port}: {error.strerror or error}",
            hint=(
                f"take another port: --port {port + 1} "
                f"(and -p 127.0.0.1:{port + 1}:{port + 1} in docker)"
            ),
        ) from error
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if on_ready:
        on_ready(token)
    try:
        while not done.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        workdir.cleanup()


def _plain(error: ValueError) -> str:
    """Ошибка проверки ответов человеческим языком: поле и что с ним не так."""
    errors = getattr(error, "errors", None)
    if callable(errors):
        parts = []
        for item in errors():
            where = ".".join(str(x) for x in item.get("loc", ()) if x != "__root__")
            message = str(item.get("msg", "")).removeprefix("Value error, ")
            parts.append(f"{where}: {message}" if where else message)
        if parts:
            return "; ".join(parts)
    return str(error)
