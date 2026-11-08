"""Локальная страница конфигуратора `heron setup` и студии `heron studio`.

Сервер живёт ровно столько, сколько открыта страница. Граница доступа — токен,
который видит только тот, кто запустил команду: движок печатает его в терминале
в адресе страницы (`http://localhost:8000/#ключ`). В саму страницу токен не
вшивается: её может получить любой, кто дотянулся до порта, а читать
настройки, загружать тему и записывать site.yaml без токена нельзя — каждый
запрос `/api/*` несёт его в заголовке X-Heron-Token. Часть после `#` браузер
на сервер не отправляет, поэтому ключ не попадает ни в журналы, ни в Referer.

Просмотр черновой сборки и справка темы открываются обычными ссылками, без
заголовка: страница, у которой есть ключ, получает от `/api/session` cookie
`HttpOnly; SameSite=Strict` с тем же ключом, и только с ним сервер отдаёт
файлы просмотра и картинки из `media/`.

Заголовок Host дополнительно обязан быть локальным: это закрывает подмену DNS
(чужой сайт, имя которого вдруг указывает на 127.0.0.1), но границей доступа
не является — его подделывает любой клиент.

Скрипты страницы — отдельными файлами (`/_studio/*.js`): политика CSP
`script-src 'self'`, как у собранного сайта, встроенных скриптов и
обработчиков в разметке нет.

В образе HERON сервер слушает все интерфейсы контейнера, а порт публикуется
только на петлю машины: `-p 127.0.0.1:8000:8000`. На машине человека сервер
слушает только 127.0.0.1 — те же правила, что у `heron serve`.
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
COOKIE = "heron-studio"
ASSETS = {
    "/_studio/setup.js": ("setup", "application/javascript; charset=utf-8"),
    "/_studio/studio.js": ("studio.js", "application/javascript; charset=utf-8"),
    "/_studio/studio.css": ("studio.css", "text/css; charset=utf-8"),
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; frame-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors {frames}"
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

        def _cookie(self) -> bool:
            """Ключ в cookie студии: просмотр и картинки открываются обычной ссылкой."""
            given = ""
            for part in (self.headers.get("Cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == COOKIE:
                    given = value
            return self._local() and hmac.compare_digest(given.encode(), token.encode())

        def _send(
            self, code: int, body: bytes, kind: str, frames: str = "'none'", extra=()
        ) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP.format(frames=frames))
            for name, value in extra:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

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
            elif not self._cookie():
                self._json(403, {"error": say(lang, "srv_token")})
            elif route.startswith("/_studio/media/"):
                found = studio.media_file(root, route[len("/_studio/") :])
                if found is None:
                    self._json(404, {"error": say(lang, "srv_not_found")})
                else:
                    self._file(found)
            else:
                self._preview(route)

        def _file(self, path: Path, code: int = 200) -> None:
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
                kind += "; charset=utf-8"
            self._send(code, path.read_bytes(), kind, frames="'self'")

        def _preview(self, route: str) -> None:
            """Файл черновой сборки студии: страницы, справка темы, стили и картинки."""
            from heron.core import paths
            from heron.core.watch import not_found

            if not built.is_set():
                self._json(404, {"error": say(lang, "srv_not_found")})
                return
            target = dist / route.lstrip("/")
            if route.endswith("/") or target.is_dir():
                target = target / "index.html"
            if paths.inside(dist, target) and target.is_file():
                self._file(target)
                return
            page = not_found(dist, route)
            if page is not None:
                self._file(page, 404)
            else:
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
            if route == "/api/session":
                cookie = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"
                self._json(200, {"ok": True}, extra=[("Set-Cookie", cookie)])
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

    try:
        server = _Server((host, port), Handler)
    except OSError as error:
        raise HeronError(
            code="E031",
            message=say(lang, "srv_port", host=host, port=port, reason=error.strerror or error),
            hint=say(lang, "srv_port_hint", next=port + 1),
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


def _ui_lang(value: Any, fallback: str) -> str:
    """Язык ответа студии: язык страницы (ru, en), иначе язык запуска."""
    return value if value in ("ru", "en") else fallback


def _plain(error: ValueError, lang: str | None = None) -> str:
    """Ошибка проверки ответов человеческим языком: поле и что с ним не так.

    Язык не передан (так зовёт `heron setup --answers`) — язык запуска, как у
    сообщений терминала (`reasons.run_lang`).
    """
    return plain(error, lang)
