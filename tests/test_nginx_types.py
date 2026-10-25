"""nginx отдаёт .md и .yaml текстом, остальные типы не меняются (23 §5).

Проверка настоящим nginx: `nginx -t` и заголовки ответов.
"""

from __future__ import annotations

import re
import socket
import subprocess

from heron.core import build as pipeline
from heron.modules import nginx
from heron.scaffold import create
from tests.nginx_server import NGINX, needs_nginx, serve


def make(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    static = root / "static"
    static.mkdir(exist_ok=True)
    (static / "x.md").write_text("# Hello\n" * 200, encoding="utf-8")
    (static / "x.yaml").write_text("key: value\n" * 200, encoding="utf-8")
    (static / "y.yml").write_text("a: b\n", encoding="utf-8")
    (static / "s.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (static / "s.css").write_text("a{color:red}", encoding="utf-8")
    (static / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 2000)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    return root / "dist"


def test_config_declares_types_over_stock_list(tmp_path):
    dist = make(tmp_path)
    conf = (dist / nginx.NAME).read_text(encoding="utf-8")
    assert nginx.MIME_INCLUDE in conf
    assert "text/markdown    md;" in conf
    assert "application/yaml yaml yml;" in conf
    assert "text/markdown application/yaml;" in conf
    # text/html nginx включает в charset_types сам, повтор даёт [warn]
    charset_line = re.search(r"charset_types[^;]*;", conf).group(0)
    assert "text/html" not in charset_line
    assert "text/markdown" in charset_line


def _head(port, path, gzip=False):
    extra = "Accept-Encoding: gzip\r\n" if gzip else ""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        # HTTP/1.1: nginx жмёт ответы только ему (gzip_http_version)
        sock.sendall(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n{extra}\r\n".encode())
        data = b""
        while chunk := sock.recv(65536):
            data += chunk
    lines = data.partition(b"\r\n\r\n")[0].decode("latin-1").split("\r\n")
    assert " 200 " in lines[0], (path, lines[0])
    return {k.lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:])}


def _port(work):
    text = (work / "nginx.conf").read_text(encoding="utf-8")
    return int(re.search(r"listen\s+127\.0\.0\.1:(\d+)", text).group(1))


@needs_nginx
def test_content_types_on_real_nginx(tmp_path):
    dist = make(tmp_path)
    assert (dist / "x.md").exists(), "static/ должен лечь в корень dist"
    with serve(dist, tmp_path / "work"):
        port = _port(tmp_path / "work")

        def ctype(path):
            return _head(port, path)["content-type"]

        assert ctype("/x.md") == "text/markdown; charset=utf-8"
        assert ctype("/x.yaml") == "application/yaml"
        assert ctype("/y.yml") == "application/yaml"
        assert ctype("/s.css") == "text/css"
        assert ctype("/s.svg") == "image/svg+xml"
        # html по-прежнему с charset, хотя text/html убран из charset_types
        assert ctype("/index.html") == "text/html; charset=utf-8"
        # у бинарных типов charset нет
        assert ctype("/p.png") == "image/png"
        assert "charset" not in ctype("/p.png")


@needs_nginx
def test_markdown_and_yaml_are_gzipped(tmp_path):
    dist = make(tmp_path)
    with serve(dist, tmp_path / "work"):
        port = _port(tmp_path / "work")
        for path in ("/x.md", "/x.yaml"):
            head = _head(port, path, gzip=True)
            assert head.get("content-encoding") == "gzip", path
            assert head.get("vary") == "Accept-Encoding", path
        assert "content-encoding" not in _head(port, "/p.png", gzip=True)


@needs_nginx
def test_nginx_t_has_no_warnings(tmp_path):
    dist = make(tmp_path)
    with serve(dist, tmp_path / "work"):
        pass
    work = tmp_path / "work"
    res = subprocess.run(
        [NGINX, "-t", "-p", str(work), "-c", str(work / "nginx.conf")], capture_output=True
    )
    out = (res.stderr + res.stdout).decode()
    assert res.returncode == 0, out
    assert "[warn]" not in out, out


@needs_nginx
def test_check_works_without_mime_types_in_etc_nginx(tmp_path, monkeypatch):
    """Система, где mime.types не в /etc/nginx (Homebrew, FreeBSD, из исходников)."""
    dist = make(tmp_path)
    conf = (dist / nginx.NAME).read_text(encoding="utf-8")
    monkeypatch.setattr(nginx, "_mime_types", lambda binary, sp: None)
    result = nginx.check(conf)
    assert result is not None and result[0], result
    # и с путём, которого нет: ложного предупреждения сборки быть не должно
    bad = conf.replace(nginx.MIME_INCLUDE, "include /nonexistent/mime.types;")
    assert nginx.check(bad)[0] is False  # настоящие ошибки по-прежнему ловятся


@needs_nginx
def test_check_passes_on_built_config(tmp_path):
    dist = make(tmp_path)
    conf = (dist / nginx.NAME).read_text(encoding="utf-8")
    result = nginx.check(conf)
    assert result is not None and result[0], result
