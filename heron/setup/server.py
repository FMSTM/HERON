"""Локальная страница конфигуратора `heron setup` и студии `heron studio`.

Сервер живёт ровно столько, сколько открыта страница. Граница доступа — токен,
который видит только тот, кто запустил команду: движок печатает его в терминале
в адресе страницы (`http://localhost:8000/#ключ`). В саму страницу токен не
вшивается: её может получить любой, кто дотянулся до порта, а читать
настройки, загружать тему и записывать site.yaml без токена нельзя — каждый
запрос `/api/*` несёт его в заголовке X-Heron-Token. Часть после `#` браузер
на сервер не отправляет, поэтому ключ не попадает ни в журналы, ни в Referer.

Просмотр черновой сборки, справка темы и картинки из `media/` - на втором
порту (`--preview-port`, по умолчанию `--port` + 1, то есть 8001), на другом
источнике (origin) браузера. Там работают скрипты темы, и они не должны дотянуться до ключа и до
`/api/*`: со своего источника скрипт не читает адрес страницы студии (ключ в нём
после `#`, и страница сразу убирает его из адресной строки) и не шлёт запросы
с заголовком ключа - браузер не пускает их без CORS, которого у сервера нет.
Второй порт пускает по своему ключу просмотра (`?k=` в адресе, затем cookie
`heron-preview`): с ним можно только смотреть, писать на этом порту нечем.
Рамка студии с просмотром и справкой - `<iframe sandbox>` без выхода наверх.

Адрес порта просмотра страница строит из своего же адреса: схема и имя - как в
адресной строке, порт - `location.port - порт студии + порт просмотра` (оба
внутренних порта сервер отдаёт в `/api/studio/start`). Так `docker run -p
9000:8000 -p 9001:8001` работает без настроек. CSP (`frame-src`, `img-src`,
`frame-ancestors`) считается так же - из порта в заголовке Host запроса, а не из
внутренних портов: иначе политика назвала бы источник, которого браузер не видит.

Заголовок Host дополнительно обязан быть локальным: это закрывает подмену DNS
(чужой сайт, имя которого вдруг указывает на 127.0.0.1), но границей доступа
не является — его подделывает любой клиент.

Скрипты страницы — отдельными файлами (`/_studio/*.js`): политика CSP
`script-src 'self'`, как у собранного сайта, встроенных скриптов и
обработчиков в разметке нет.

В образе HERON сервер слушает все интерфейсы контейнера, а порты публикуются
только на петлю машины: `-p 127.0.0.1:8000:8000 -p 127.0.0.1:8001:8001`
(другие `--port` и `--preview-port` - те же номера в `-p`). На
машине человека сервер слушает только 127.0.0.1 — те же правила, что у `heron serve`.
"""

from __future__ import annotations

import hmac
import http.server
import json
import mimetypes
import re
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
# Скрипт порта просмотра: убирает ключ ?k= из адресной строки страницы (`history.replaceState`).
PREVIEW_SCRIPT = "/_studio/preview.js"
# Начало документа до первого содержимого: пробелы, BOM, комментарии, <!doctype>, <?…?>.
_PROLOG = re.compile(rb"(?:\s+|\xef\xbb\xbf|<!--.*?-->|<![^>]*>|<\?.*?\?>)*", re.S)
_OPEN = {name: re.compile(rb"<" + name + rb"(?:\s[^>]*)?>", re.I) for name in (b"html", b"head")}


def with_preview_script(html: bytes) -> bytes:
    """Страница просмотра с `<script src="/_studio/preview.js">` первым в `<head>`.

    Свой файл, а не встроенный код: политика просмотра - `script-src 'self'`.
    Место ищется по строению документа, а не первым `<head` в тексте: тот мог
    оказаться в комментарии в начале или в строке скрипта. После пролога
    (комментарии, `<!doctype>`) и открывающих `<html>` и `<head>`, если они идут
    первыми; иначе - туда, где начинается содержимое (браузер сам отнесёт скрипт
    в `<head>`).
    """
    tag = f'<script src="{PREVIEW_SCRIPT}"></script>'.encode()
    at = _PROLOG.match(html).end()  # type: ignore[union-attr]
    for name in (b"html", b"head"):
        found = _OPEN[name].match(html, at)
        if found is None:
            continue
        at = found.end()
        at = _PROLOG.match(html, at).end()  # type: ignore[union-attr]
    return html[:at] + tag + html[at:]


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run(
    root: Path,
    host: str,
    port: int,
    on_ready=None,
    start: dict[str, Any] | None = None,
    preview_port: int | None = None,
) -> None:
    """Поднять страницу. `on_ready(token)` вызывается, когда порт открыт.

    `preview_port` - порт просмотра, по умолчанию `port + 1` (`preview_port_for`).

    `start` - с чего открыться: `{"tab": "site"|"pages"|"ref", "target": {...},
    "answers": {...}}` (`heron studio`, `page add --web`, `category add --web`).
    """
    from heron import setup, studio

    token = secrets.token_urlsafe(24)
    # Ключ второго порта: только смотреть просмотр, справку и картинки (не ключ API).
    preview_key = secrets.token_urlsafe(24)
    lang = run_lang(root)
    preview_port = preview_port_for(port, preview_port, lang)
    # Язык ответов сервера — язык запуска (--notes, HERON_NOTES, build.notes);
    # причины отказа при сохранении — на языке, который выбран на странице.
    uploads: dict[str, Path] = {}
    workdir = tempfile.TemporaryDirectory(prefix="heron-setup-")
    dist = Path(workdir.name) / "preview"
    built = threading.Event()
    lock = threading.Lock()
    done = threading.Event()
    opening = dict(start or {"tab": "site"})
    # Внутренние порты: страница пересчитает порт просмотра от своего адреса (remap в docker).
    opening["preview"] = {"port": preview_port, "studio": port, "key": preview_key}

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
            seen = _peer(self.headers.get("Host"), port, preview_port)
            policy = CSP.format(preview=seen)
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
            seen = _peer(self.headers.get("Host"), preview_port, port)
            policy = PREVIEW_CSP.format(studio=seen)
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
            if route == PREVIEW_SCRIPT:
                # общий файл без секретов: убирает ?k= из адреса страницы просмотра
                body = studio.asset("preview.js")
                self._send(200, body, "application/javascript; charset=utf-8")
                return
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
            self._preview(route, extra, parsed.query)

        def _file(self, path: Path, code: int = 200, extra=()) -> None:
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            body = path.read_bytes()
            if kind == "text/html":
                body = with_preview_script(body)
            if kind.startswith("text/") or kind in ("application/javascript", "image/svg+xml"):
                kind += "; charset=utf-8"
            self._send(code, body, kind, extra)

        def _preview(self, route: str, extra, query: str = "") -> None:
            from heron.core import paths
            from heron.core.watch import no_slash_route, not_found, trailing_slash

            if not built.is_set():
                self._json(404, {"error": say(lang, "srv_not_found")})
                return
            # адреса без слеша (urls.trailing_slash: never) - как у nginx прода
            found = None if trailing_slash(root) else no_slash_route(dist, route)
            if found is not None and found[0] == "redirect":
                where = urllib.parse.quote(found[1]) + (f"?{query}" if query else "")
                self._send(301, b"", "text/plain; charset=utf-8", [*extra, ("Location", where)])
                return
            if found is not None:
                route = found[1]
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
            if number == port:
                hint = say(lang, "srv_port_hint", next=_spare(port, preview_port))
            else:
                hint = say(lang, "srv_preview_hint", next=_spare(preview_port, port))
            raise HeronError(
                code="E031",
                message=say(
                    lang,
                    "srv_port" if number == port else "srv_preview_port",
                    host=host,
                    port=number,
                    reason=error.strerror or error,
                ),
                hint=hint,
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


def preview_port_for(port: int, preview: int | None, lang: str = "en") -> int:
    """Порт просмотра: заданный `--preview-port` или `port + 1`; проверка до открытия портов."""
    if preview is None:
        if port < 65535:
            return port + 1
        raise HeronError(
            code="E031",
            message=say(lang, "srv_preview_range", port=port),
            hint=say(lang, "srv_preview_range_hint"),
        )
    if not 1 <= preview <= 65535:
        raise HeronError(code="E031", message=say(lang, "srv_preview_range", port=preview))
    if preview == port:
        raise HeronError(code="E031", message=say(lang, "srv_preview_same", port=port))
    return preview


def _spare(busy: int, other: int) -> int:
    """Свободный на вид номер для подсказки: следующий за занятым, мимо второго порта."""
    for value in (*range(busy + 1, busy + 10), *range(busy - 1, busy - 10, -1)):
        if 1024 <= value <= 65535 and value != other:
            return value
    return busy


def _split_host(host: str | None) -> tuple[str, int | None]:
    """Заголовок Host: имя (`localhost`, `127.0.0.1`, `[::1]`) и порт, если он есть."""
    host = (host or "").strip().lower()
    if host.startswith("["):
        name, _, rest = host.partition("]")
        name += "]"
        port = rest[1:] if rest.startswith(":") else ""
    elif host.count(":") == 1:
        name, _, port = host.partition(":")
    else:
        name, port = host, ""
    return name, int(port) if port.isdigit() and 0 < int(port) <= 65535 else None


def _hostname(host: str | None) -> str:
    """Имя из заголовка Host без порта: `localhost`, `127.0.0.1`, `[::1]`."""
    return _split_host(host)[0]


def _shift(seen: int, own: int, other: int) -> int:
    """Порт второго сервера так, как его видит браузер: тот же сдвиг, что у этого порта.

    Та же формула - в studio.js (`pvOrigin`): `location.port - studio + preview`.
    Вышло за пределы портов - внутренний номер.
    """
    value = seen - own + other
    return value if 1 <= value <= 65535 else other


def _peer(host: str | None, own: int, other: int) -> str:
    """Источник второго порта для CSP - из заголовка Host, а не из внутренних портов.

    Браузер открыл этот порт по адресу из Host. Если docker пробросил порты со
    сдвигом (`-p 9000:8000 -p 9001:8001`), второй порт для браузера - тот же сдвиг
    (`_shift`). Порта в Host нет - адрес на 80 (http) или 443 (https): оба варианта,
    как их считает страница. Имя не локальное (такой запрос получит 403) - localhost.
    """
    name, seen = _split_host(host)
    if name not in LOCAL_HOSTS or name == "0.0.0.0":
        name = "localhost"
    if seen is not None:
        return f"http://{name}:{_shift(seen, own, other)}"
    return f"http://{name}:{_shift(80, own, other)} https://{name}:{_shift(443, own, other)}"


def _write(handler, code: int, body: bytes, kind: str, policy: str, extra=()) -> None:
    handler.send_response(code)
    handler.send_header("Content-Type", kind)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Content-Security-Policy", policy)
    # Порт студии в рамку не встаёт вовсе (frame-ancestors 'none') - то же для
    # браузеров без CSP 2, и окна, открытые со страницы, её не видят. Порт
    # просмотра этого не получает: его рамка - на другом источнике, в студии,
    # а X-Frame-Options чужой источник разрешить не умеет.
    if "frame-ancestors 'none'" in policy:
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Cross-Origin-Opener-Policy", "same-origin")
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
