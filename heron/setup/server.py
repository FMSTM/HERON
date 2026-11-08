"""Локальная страница конфигуратора `heron setup` и студии `heron studio`.

Сервер живёт ровно столько, сколько открыта страница. Граница доступа — токен,
который видит только тот, кто запустил команду: движок печатает его в терминале
в адресе страницы (`http://localhost:8000/#ключ`). В саму страницу токен не
вшивается: её может получить любой, кто дотянулся до порта, а читать
настройки, загружать тему и записывать site.yaml без токена нельзя — каждый
запрос `/api/*` несёт его в заголовке X-Heron-Token. Часть после `#` браузер
на сервер не отправляет, поэтому ключ не попадает ни в журналы, ни в Referer.

Просмотр черновой сборки, справка темы и картинки из `media/` - на втором
порту (`порт + 1`, по умолчанию 8001), то есть на другом источнике (origin)
браузера. Там работают скрипты темы, и они не должны дотянуться до ключа и до
`/api/*`: со своего источника скрипт не читает адрес страницы студии (ключ в нём
после `#`, и страница сразу убирает его из адресной строки) и не шлёт запросы
с заголовком ключа - браузер не пускает их без CORS, которого у сервера нет.
Второй порт пускает по своему ключу просмотра (`?k=` в адресе, затем cookie
`heron-preview`): с ним можно только смотреть, писать на этом порту нечем.
Рамка студии с просмотром и справкой - `<iframe sandbox>` без выхода наверх.

Заголовок Host дополнительно обязан быть локальным: это закрывает подмену DNS
(чужой сайт, имя которого вдруг указывает на 127.0.0.1), но границей доступа
не является — его подделывает любой клиент.

Скрипты страницы — отдельными файлами (`/_studio/*.js`): политика CSP
`script-src 'self'`, как у собранного сайта, встроенных скриптов и
обработчиков в разметке нет.

В образе HERON сервер слушает все интерфейсы контейнера, а порты публикуются
только на петлю машины: `-p 127.0.0.1:8000:8000 -p 127.0.0.1:8001:8001`. На
машине человека сервер слушает только 127.0.0.1 — те же правила, что у `heron serve`.
"""

from __future__ import annotations

import hmac
import http.server
import json
import mimetypes
import secrets
import socketserver
import tempfile
import threading
import urllib.parse
from pathlib import Path
from typing import Any

from heron.core.errors import HeronError
from heron.messages import rendered
from heron.setup.reasons import plain, run_lang, say

MAX_BODY = 210 * 1024 * 1024
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"}
PREVIEW_COOKIE = "heron-preview"
ASSETS = {
    "/_studio/setup.js": ("setup", "application/javascript; charset=utf-8"),
    "/_studio/studio.js": ("studio.js", "application/javascript; charset=utf-8"),
    "/_studio/studio.css": ("studio.css", "text/css; charset=utf-8"),
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: {preview}; frame-src {preview}; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
# Просмотр: страницы сайта со своими скриптами; рамкой - только в студии.
PREVIEW_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors {studio}"
)
STUDIO = ("tree", "open", "check", "save", "site-check", "preview", "start")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run(
    root: Path,
    host: str,
    port: int,
    on_ready=None,
    start: dict[str, Any] | None = None,
) -> None:
    """Поднять страницу. `on_ready(token)` вызывается, когда порт открыт.

    `start` - с чего открыться: `{"tab": "site"|"pages"|"ref", "target": {...},
    "answers": {...}}` (`heron studio`, `page add --web`, `category add --web`).
    """
    from heron import setup, studio

    token = secrets.token_urlsafe(24)
    # Ключ второго порта: только смотреть просмотр, справку и картинки (не ключ API).
    preview_key = secrets.token_urlsafe(24)
    preview_port = port + 1
    # Язык ответов сервера — язык запуска (--notes, HERON_NOTES, build.notes);
    # причины отказа при сохранении — на языке, который выбран на странице.
    lang = run_lang(root)
    uploads: dict[str, Path] = {}
    workdir = tempfile.TemporaryDirectory(prefix="heron-setup-")
    dist = Path(workdir.name) / "preview"
    built = threading.Event()
    lock = threading.Lock()
    done = threading.Event()
    opening = dict(start or {"tab": "site"})
    opening["preview"] = {"port": preview_port, "key": preview_key}

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

        def _send(self, code: int, body: bytes, kind: str, extra=()) -> None:
            name = _hostname(self.headers.get("Host"))
            policy = CSP.format(preview=_origin(name, preview_port))
            _write(self, code, body, kind, policy, extra)

        def _json(self, code: int, data: Any, extra=()) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8", extra=extra)

        def _route(self) -> tuple[str, dict[str, list[str]]]:
            parsed = urllib.parse.urlsplit(self.path)
            return urllib.parse.unquote(parsed.path), urllib.parse.parse_qs(parsed.query)

        def do_GET(self) -> None:  # noqa: N802
            if not self._local():
                self._json(403, {"error": say(lang, "srv_local_only")})
                return
            route, _query = self._route()
            if route == "/":
                self._send(200, setup.page(), "text/html; charset=utf-8")
            elif route in ASSETS:
                name, kind = ASSETS[route]
                body = setup.script() if name == "setup" else studio.asset(name)
                self._send(200, body, kind)
            elif route.startswith("/api/"):
                if not self._allowed():
                    self._json(403, {"error": say(lang, "srv_token")})
                elif route == "/api/state":
                    self._json(200, setup.state(root, lang=lang))
                else:
                    self._json(404, {"error": say(lang, "srv_not_found")})
            else:
                # просмотр, справка темы и картинки - только на порту просмотра
                self._json(404, {"error": say(lang, "srv_not_found")})

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed():
                self._json(403, {"error": say(lang, "srv_token")})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._json(413, {"error": say(lang, "srv_too_large")})
                return
            body = self.rfile.read(length)
            route, query = self._route()
            if route == "/api/upload":
                ident = secrets.token_hex(8)
                path = Path(workdir.name) / f"{ident}.archive"
                path.write_bytes(body)
                uploads[ident] = path
                self._json(200, {"ok": True, "upload": ident})
                return
            if route == "/api/stop":
                self._json(200, {"ok": True})
                done.set()
                return
            if route.startswith("/api/studio/"):
                with lock:
                    self._studio(route[len("/api/studio/") :], body, query)
                return
            if route != "/api/save":
                self._json(404, {"error": say(lang, "srv_not_found")})
                return
            with lock:
                self._setup_save(body)

        def _studio(self, name: str, body: bytes, query: dict[str, list[str]]) -> None:
            """Вкладка «Страницы» и справка темы: те же функции ядра, что у CLI."""
            shown = lang
            try:
                if name == "upload":
                    shown = _ui_lang((query.get("lang") or [lang])[0], lang)
                    names = query.get("name") or [""]
                    self._json(200, {"ok": True, **studio.upload(root, names[0], body)})
                    return
                if name not in STUDIO:
                    self._json(404, {"error": say(lang, "srv_not_found")})
                    return
                data = json.loads(body.decode("utf-8") or "{}")
                if not isinstance(data, dict):
                    data = {}
                shown = _ui_lang(data.get("lang"), lang)
                if name == "start":
                    out: dict[str, Any] = {"ok": True, **opening}
                elif name == "tree":
                    out = {"ok": True, **studio.tree(root, shown)}
                elif name in ("open", "check"):
                    out = {"ok": True, "state": studio.check(root, data, shown)}
                elif name == "save":
                    out = {"ok": True, **studio.save(root, data, shown)}
                elif name == "site-check":
                    out = studio.site_check(root, shown)
                else:
                    out = studio.preview(root, dist, shown, data.get("target"))
                    built.set()
                self._json(200, out)
            except HeronError as error:
                self._json(
                    400,
                    {
                        "ok": False,
                        "code": error.code,
                        "error": rendered(error.message, shown),
                        "hint": rendered(error.hint, shown) or "",
                    },
                )
            except (ValueError, UnicodeDecodeError) as error:
                self._json(400, {"ok": False, "error": str(error)})

        def _setup_save(self, body: bytes) -> None:
            shown = lang
            try:
                data = json.loads(body.decode("utf-8") or "{}")
                if isinstance(data, dict) and data.get("lang") in ("ru", "en"):
                    shown = data["lang"]
                answers = setup.Answers.model_validate(data.get("answers") or {})
                upload = uploads.get(str(data.get("upload") or ""))
                decision = data.get("schema") if isinstance(data, dict) else None
                result = setup.apply(
                    root,
                    answers,
                    lang=lang,
                    upload=upload,
                    schema=decision if isinstance(decision, dict) else None,
                )
            except setup.SchemaFindings as error:
                from heron.schemaorg import RELEASE

                self._json(
                    409,
                    {"ok": False, "schema": {"release": RELEASE, "findings": error.findings}},
                )
                return
            except HeronError as error:
                self._json(
                    400,
                    {
                        "ok": False,
                        "error": rendered(error.message, shown),
                        "hint": rendered(error.hint, shown) or "",
                    },
                )
                return
            except ValueError as error:
                self._json(400, {"ok": False, "error": _plain(error, shown)})
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
                    "dropped": result.dropped,
                    "excepted": result.excepted,
                    "state": setup.state(root, lang=lang),
                },
            )

    class Preview(http.server.BaseHTTPRequestHandler):
        """Порт просмотра: черновая сборка, справка темы, картинки из media/. Только GET."""

        server_version = "heron-preview"

        def log_message(self, *args: Any) -> None:
            return

        def _key(self, query: dict[str, list[str]]) -> tuple[bool, bool]:
            """(пускать ли, пришёл ли ключ в адресе - тогда поставить cookie)."""
            given = (query.get("k") or [""])[0]
            if given and hmac.compare_digest(given.encode(), preview_key.encode()):
                return True, True
            for part in (self.headers.get("Cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == PREVIEW_COOKIE and hmac.compare_digest(
                    value.encode(), preview_key.encode()
                ):
                    return True, False
            return False, False

        def _send(self, code: int, body: bytes, kind: str, extra=()) -> None:
            name = _hostname(self.headers.get("Host"))
            policy = PREVIEW_CSP.format(studio=_origin(name, port))
            _write(self, code, body, kind, policy, extra)

        def _json(self, code: int, data: Any) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            name = _hostname(self.headers.get("Host"))
            if name not in LOCAL_HOSTS:
                self._json(403, {"error": say(lang, "srv_local_only")})
                return
            parsed = urllib.parse.urlsplit(self.path)
            route = urllib.parse.unquote(parsed.path)
            allowed, fresh = self._key(urllib.parse.parse_qs(parsed.query))
            if not allowed:
                self._json(403, {"error": say(lang, "srv_token")})
                return
            extra = []
            if fresh:
                extra.append(
                    (
                        "Set-Cookie",
                        f"{PREVIEW_COOKIE}={preview_key}; Path=/; HttpOnly; SameSite=Lax",
                    )
                )
            if route.startswith("/_studio/media/"):
                found = studio.media_file(root, route[len("/_studio/") :])
                if found is None:
                    self._json(404, {"error": say(lang, "srv_not_found")})
                else:
                    self._file(found, extra=extra)
                return
            self._preview(route, extra)

        def _file(self, path: Path, code: int = 200, extra=()) -> None:
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
                kind += "; charset=utf-8"
            self._send(code, path.read_bytes(), kind, extra)

        def _preview(self, route: str, extra) -> None:
            from heron.core import paths
            from heron.core.watch import not_found

            if not built.is_set():
                self._json(404, {"error": say(lang, "srv_not_found")})
                return
            target = dist / route.lstrip("/")
            if route.endswith("/") or target.is_dir():
                target = target / "index.html"
            if paths.inside(dist, target) and target.is_file():
                self._file(target, extra=extra)
                return
            page = not_found(dist, route)
            if page is not None:
                self._file(page, 404, extra)
            else:
                self._json(404, {"error": say(lang, "srv_not_found")})

    servers = []
    for number, handler in ((port, Handler), (preview_port, Preview)):
        try:
            servers.append(_Server((host, number), handler))
        except OSError as error:
            for server in servers:
                server.server_close()
            raise HeronError(
                code="E031",
                message=say(
                    lang, "srv_port", host=host, port=number, reason=error.strerror or error
                ),
                hint=say(lang, "srv_port_hint", next=port + 2, preview=port + 3),
            ) from error
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    if on_ready:
        on_ready(token)
    try:
        while not done.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        workdir.cleanup()


def _hostname(host: str | None) -> str:
    """Имя из заголовка Host без порта: `localhost`, `127.0.0.1`, `[::1]`."""
    return (host or "").rsplit(":", 1)[0].lower() if not (host or "").endswith("]") else host


def _origin(name: str, port: int) -> str:
    """Источник страницы на порту `port` того же имени, что открыл человек."""
    if name not in LOCAL_HOSTS or name == "0.0.0.0":
        name = "localhost"
    return f"http://{name}:{port}"


def _write(handler, code: int, body: bytes, kind: str, policy: str, extra=()) -> None:
    handler.send_response(code)
    handler.send_header("Content-Type", kind)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Content-Security-Policy", policy)
    for name, value in extra:
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)


def _ui_lang(value: Any, fallback: str) -> str:
    """Язык ответа студии: язык страницы (ru, en), иначе язык запуска."""
    return value if value in ("ru", "en") else fallback


def _plain(error: ValueError, lang: str | None = None) -> str:
    """Ошибка проверки ответов человеческим языком: поле и что с ним не так.

    Язык не передан (так зовёт `heron setup --answers`) — язык запуска, как у
    сообщений терминала (`reasons.run_lang`).
    """
    return plain(error, lang)
