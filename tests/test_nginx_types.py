"""nginx отдаёт .md и .yaml текстом, остальные типы не меняются (23 §5).

Проверка настоящим nginx: `nginx -t` и заголовки ответов.
"""

from __future__ import annotations

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
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    return root / "dist"


def test_config_declares_types_over_stock_list(tmp_path):
    dist = make(tmp_path)
    conf = (dist / nginx.NAME).read_text(encoding="utf-8")
    assert "include /etc/nginx/mime.types;" in conf
    assert "text/markdown    md;" in conf
    assert "application/yaml yaml yml;" in conf
    assert "text/markdown application/yaml;" in conf


@needs_nginx
def test_content_types_on_real_nginx(tmp_path):
    dist = make(tmp_path)
    assert (dist / "x.md").exists(), "static/ должен лечь в корень dist"
    with serve(dist, tmp_path / "work") as get:
        # get() отдаёт только статус и Location: заголовки читаем сырым запросом
        port = _port(tmp_path / "work")

        def ctype(path):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                sock.sendall(f"GET {path} HTTP/1.0\r\nHost: x\r\n\r\n".encode())
                data = b""
                while chunk := sock.recv(65536):
                    data += chunk
            head = data.partition(b"\r\n\r\n")[0].decode("latin-1").split("\r\n")
            assert " 200 " in head[0], (path, head[0])
            return next(
                line.split(":", 1)[1].strip()
                for line in head
                if line.lower().startswith("content-type:")
            )

        assert ctype("/x.md") == "text/markdown; charset=utf-8"
        assert ctype("/x.yaml") == "application/yaml"
        assert ctype("/y.yml") == "application/yaml"
        assert ctype("/s.css") == "text/css"
        assert ctype("/s.svg") == "image/svg+xml"
        assert ctype("/index.html") == "text/html; charset=utf-8"
        assert get("/x.md")[0] == 200


def _port(work):
    # порт сервера записан в подставленной конфигурации nginx.conf
    import re

    text = (work / "nginx.conf").read_text(encoding="utf-8")
    return int(re.search(r"listen\s+127\.0\.0\.1:(\d+)", text).group(1))


@needs_nginx
def test_nginx_t_accepts_config(tmp_path):
    dist = make(tmp_path)
    with serve(dist, tmp_path / "work"):
        pass
    res = subprocess.run(
        [NGINX, "-t", "-p", str(tmp_path / "work"), "-c", str(tmp_path / "work" / "nginx.conf")],
        capture_output=True,
    )
    assert res.returncode == 0, res.stderr.decode()
