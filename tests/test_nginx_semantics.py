"""nginx отвечает так, как обещает модель адресов движка.

Адреса в движке различают регистр. Строковые ключи `map` nginx сравнивает
без учёта регистра — отсюда редирект страницы на саму себя, 410 на живой
странице и конфиг, который не стартует. Плюс скрытые файлы под `^~`.
Всё проверяется настоящим nginx: `nginx -t` и HTTP-ответами.
"""

from __future__ import annotations

import socket

import pytest
import yaml

from heron.core import build as pipeline
from heron.modules import nginx
from heron.scaffold import create
from tests import nginx_server
from tests.nginx_server import needs_nginx, serve

PAGE = "---\ntitle: {t}\nh1: {t}\ndescription: D\n{extra}---\n\nText.\n"
LONG = "/" + "старая-страница-с-очень-длинным-адресом-" * 3 + "/"


def make(tmp_path, gone=None):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en", "ru"])
    if gone:
        conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
        conf["gone"] = gone
        (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    pages = {
        "en/page.md": PAGE.format(t="Page", extra="redirect_from: [/Page/]\n"),
        "en/gone.md": PAGE.format(t="Gone", extra=""),
        "en/first.md": PAGE.format(t="First", extra="redirect_from: [/A/]\n"),
        "en/second.md": PAGE.format(t="Second", extra=f"redirect_from: [/a/, {LONG}]\n"),
    }
    for rel, text in pages.items():
        (root / "content" / rel).write_text(text, encoding="utf-8")
    return root


def test_config_has_exact_locations_and_no_string_maps(tmp_path):
    root = make(tmp_path, gone=["/Gone/"])
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    conf = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    assert 'location = "/Page/" { return 301 "/page/"; }' in conf
    assert 'location = "/Gone/" { return 410; }' in conf
    assert "map $uri" not in conf
    assert "map_hash" not in conf


@needs_nginx
def test_case_matters_in_301_and_410(tmp_path):
    root = make(tmp_path, gone=["/Gone/"])
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:  # serve сам делает nginx -t
        assert get("/Page/") == (301, "/page/")
        assert get("/page/")[0] == 200  # не редирект на самого себя
        assert get("/Gone/")[0] == 410
        assert get("/gone/")[0] == 200  # живая страница не закрыта
        assert get("/A/") == (301, "/first/")
        assert get("/a/") == (301, "/second/")
        assert get("/PAGE/")[0] == 404  # ни 301, ни 410: такого адреса нет
        assert get(LONG) == (301, "/second/")  # длинный кириллический — без map_hash


@needs_nginx
def test_hidden_files_are_404_everywhere_except_well_known(tmp_path):
    root = make(tmp_path)
    assert not pipeline.run(root).failed
    dist = root / "dist"
    hidden = [
        ".audit-secret",
        "ru/.audit-secret",
        "ru/page/.audit-secret",
        "media/.audit-secret",
        "assets/.audit-secret",
        "page/.audit-secret",
        "ru/.git/config",
    ]
    for rel in hidden:
        (dist / rel).parent.mkdir(parents=True, exist_ok=True)
        (dist / rel).write_text("secret", encoding="utf-8")
    (dist / ".well-known").mkdir()
    (dist / ".well-known" / "security.txt").write_text("Contact: x", encoding="utf-8")
    with serve(dist, tmp_path / "nginx") as get:
        for rel in hidden:
            assert get("/" + rel)[0] == 404, rel
        assert get("/" + nginx.NAME)[0] == 404
        assert get("/.well-known/security.txt")[0] == 200
        assert get("/ru/")[0] == 200


def test_gone_on_a_service_prefix_is_e022(tmp_path):
    root = make(tmp_path, gone=["/media/*"])
    result = pipeline.run(root)
    assert "E022" in [e.code for e in result.collector.errors]


# --- комментарии конфига на языке пояснений сайта (E15.S1.T4: F17) -------------

import re  # noqa: E402

CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")


def _with_notes(tmp_path, lang):
    root = make(tmp_path / lang, gone=["/Gone/", "/old/*"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf.setdefault("build", {})["notes"] = lang
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    return root, (root / "dist" / nginx.NAME).read_text(encoding="utf-8")


def _split(conf):
    comments = [line for line in conf.splitlines() if line.lstrip().startswith("#")]
    directives = [line for line in conf.splitlines() if not line.lstrip().startswith("#")]
    return comments, directives


def test_config_comments_follow_build_notes_and_directives_do_not(tmp_path, monkeypatch):
    (tmp_path / "ru").mkdir()
    (tmp_path / "en").mkdir()
    monkeypatch.delenv("HERON_NOTES", raising=False)
    _, ru = _with_notes(tmp_path, "ru")
    _, en = _with_notes(tmp_path, "en")
    ru_comments, ru_directives = _split(ru)
    en_comments, en_directives = _split(en)
    # семантика одна: те же директивы в том же порядке, меняются только комментарии
    assert ru_directives == en_directives
    assert len(ru_comments) == len(en_comments) >= 19
    assert all(CYRILLIC.search(line) for line in ru_comments), ru_comments
    assert not any(CYRILLIC.search(line) for line in en_comments), en_comments
    assert "#@" not in ru and "#@" not in en
    assert ru.startswith("# " + nginx.COMMENTS["ru"]["built"] + "\n")
    assert en.startswith("# " + nginx.COMMENTS["en"]["built"] + "\n")
    assert "    # " + nginx.COMMENTS["en"]["exact"] + "\n" in en


def test_config_does_not_depend_on_the_environment(tmp_path, monkeypatch):
    """HERON_NOTES — язык сообщений одного запуска, сборку он не меняет."""
    (tmp_path / "ru").mkdir()
    monkeypatch.setenv("HERON_NOTES", "en")
    _, first = _with_notes(tmp_path, "ru")
    assert CYRILLIC.search(first.splitlines()[0])
    monkeypatch.delenv("HERON_NOTES")
    root = tmp_path / "ru" / "site"
    assert pipeline.run(root).failed is False
    assert (root / "dist" / nginx.NAME).read_text(encoding="utf-8") == first


def test_comment_tables_match():
    assert set(nginx.COMMENTS["ru"]) == set(nginx.COMMENTS["en"])
    templates = nginx.HEAD + nginx.VERSIONED + nginx.TAIL + nginx.LANG_NEVER + nginx.TAIL_NEVER
    templates += nginx.MEDIA_MAP + nginx.METHOD_CHECK + nginx.REAL_IP
    used = set(nginx.MARK.findall(templates))
    used |= {("    ", "exact"), ("", "built"), ("", "logformat")}
    assert {key for _, key in used} == set(nginx.COMMENTS["en"])


@needs_nginx
def test_both_languages_pass_nginx(tmp_path):
    for lang in ("ru", "en"):
        (tmp_path / lang).mkdir()
        root, _ = _with_notes(tmp_path, lang)
        with serve(root / "dist", tmp_path / lang / "nginx") as get:  # serve сам делает nginx -t
            assert get("/Page/") == (301, "/page/")
            assert get("/Gone/")[0] == 410
            assert get("/old/x/")[0] == 410


def test_config_has_security_headers_and_healthz(tmp_path):
    root = make(tmp_path)
    assert not pipeline.run(root).failed
    conf = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    assert "server_tokens off;" in conf
    assert 'add_header X-Content-Type-Options "nosniff" always;' in conf
    assert "add_header Referrer-Policy" in conf
    assert "add_header Content-Security-Policy" in conf
    assert "script-src 'self';" in conf
    assert "add_header Strict-Transport-Security" in conf
    assert "location = /healthz {" in conf
    # add_header в location заменяет server-уровень: заголовки повторены везде,
    # где задан свой add_header (healthz, media, assets и копии с хешем темы)
    assert conf.count("add_header X-Content-Type-Options") == 5


@needs_nginx
def test_security_headers_and_healthz_are_served(tmp_path):
    root = make(tmp_path)
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:  # serve сам делает nginx -t
        assert get("/healthz")[0] == 200


# --- заголовки на живом ответе (E15.S1.T20) --------------------------------------


def _headers(port, path):
    """Код и заголовки ответа: `get` из nginx_server отдаёт только код и Location."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(f"GET {path} HTTP/1.0\r\nHost: x\r\n\r\n".encode())
        data = b""
        while chunk := sock.recv(65536):
            data += chunk
    head = data.partition(b"\r\n\r\n")[0].decode("latin-1").split("\r\n")
    pairs = (line.split(":", 1) for line in head[1:])
    return int(head[0].split()[1]), {k.strip().lower(): v.strip() for k, v in pairs}


def _directive(csp, name):
    """Значения директивы CSP, без её имени."""
    for part in csp.split(";"):
        words = part.split()
        if words and words[0] == name:
            return words[1:]
    raise AssertionError(f"{name} нет в {csp}")


@pytest.fixture
def spy_port(monkeypatch):
    """Порт, который `serve` выбрал для nginx: самому `serve` он не нужен снаружи."""
    ports = []
    real = nginx_server._free_port

    def spy():
        ports.append(real())
        return ports[-1]

    monkeypatch.setattr(nginx_server, "_free_port", spy)
    return ports


@needs_nginx
def test_live_response_has_strict_csp_and_security_headers(tmp_path, spy_port):
    root = make(tmp_path)
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:
        assert get("/healthz")[0] == 200
        for path in ("/", "/assets/site.js"):
            status, headers = _headers(spy_port[0], path)
            assert status == 200, path
            csp = headers["content-security-policy"]
            assert _directive(csp, "script-src") == ["'self'"], path
            assert "unsafe-inline" not in " ".join(_directive(csp, "script-src"))
            assert headers["x-content-type-options"] == "nosniff"
            assert "max-age=" in headers["strict-transport-security"]
            assert headers["server"] == "nginx"  # без версии
        # при nosniff браузер не исполнит скрипт с другим типом
        assert "javascript" in _headers(spy_port[0], "/assets/site.js")[1]["content-type"]


@needs_nginx
def test_live_csp_allows_only_the_enabled_counter(tmp_path, spy_port):
    root = make(tmp_path)
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["analytics"] = {"metrika": 10000001}
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx"):
        csp = _headers(spy_port[0], "/")[1]["content-security-policy"]
    for name in ("script-src", "connect-src", "img-src"):
        assert "https://mc.yandex.ru" in _directive(csp, name), name
    assert "unsafe-inline" not in " ".join(_directive(csp, "script-src"))
    assert "google" not in csp
