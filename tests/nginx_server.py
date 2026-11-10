"""Настоящий nginx над собранной папкой — для тестов 301, 410 и 404.

Конфиг берётся тот, что движок положил в `dist/.heron-nginx.conf`, меняются
только порт и корень. Нет nginx на машине — тест пропускается: проверять
поведение сервера его имитацией бессмысленно.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

NGINX = shutil.which("nginx") or ("/usr/sbin/nginx" if Path("/usr/sbin/nginx").exists() else None)

# В обязательном задании CI проверка nginx пропускаться не должна: там
# HERON_REQUIRE_NGINX=1, и отсутствие nginx — ошибка сбора тестов, а не
# тихий пропуск, после которого «всё зелёное».
if NGINX is None and os.environ.get("HERON_REQUIRE_NGINX"):
    raise RuntimeError("HERON_REQUIRE_NGINX=1, а nginx не установлен")

needs_nginx = pytest.mark.skipif(NGINX is None, reason="nginx не установлен")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def serve(dist: Path, work: Path):
    """Поднять nginx на свободном порту, отдать функцию запроса, погасить."""
    port = _free_port()
    site = (dist / ".heron-nginx.conf").read_text(encoding="utf-8")
    site = site.replace("listen       8080;", f"listen       127.0.0.1:{port};")
    site = site.replace("root   /usr/share/nginx/html;", f"root   {dist};")
    # журнал образа (stdout контейнера) - файлом рядом: его читают тесты журнала
    site = site.replace("access_log /var/log/nginx/access.log ", f"access_log {work}/access.log ")
    work.mkdir(parents=True, exist_ok=True)
    user = "user root;\n" if os.geteuid() == 0 else ""
    conf = work / "nginx.conf"
    conf.write_text(
        f"{user}worker_processes 1;\npid {work}/nginx.pid;\nerror_log {work}/error.log;\n"
        "events {}\nhttp {\n    access_log off;\n"
        f"    client_body_temp_path {work}/body;\n    proxy_temp_path {work}/proxy;\n"
        f"    fastcgi_temp_path {work}/fcgi;\n    uwsgi_temp_path {work}/uwsgi;\n"
        f"    scgi_temp_path {work}/scgi;\n{site}\n}}\n",
        encoding="utf-8",
    )
    test = subprocess.run([NGINX, "-t", "-p", str(work), "-c", str(conf)], capture_output=True)
    assert test.returncode == 0, test.stderr.decode()
    subprocess.run([NGINX, "-p", str(work), "-c", str(conf)], check=True)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.05)

        def get(
            path: str, method: str = "GET", headers: dict | None = None, version: str = "1.0"
        ) -> tuple[int, str]:
            """Код ответа и Location. Путь уходит байтами как есть: и
            percent-encoded, и сырой UTF-8 — так, как его шлют браузеры и боты.

            После вызова: `get.body` - тело текстом, `get.raw` - тело байтами,
            `get.headers` - заголовки ответа списком пар (имя в нижнем регистре).
            """
            # HTTP/1.1: gzip и gzip_static nginx отдаёт только ему (gzip_http_version)
            if version != "1.0":
                headers = {"Connection": "close", **(headers or {})}
            extra = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                sock.sendall(
                    method.encode()
                    + b" "
                    + path.encode("utf-8")
                    + f" HTTP/{version}\r\nHost: x\r\n".encode()
                    + extra.encode("latin-1")
                    + b"\r\n"
                )
                data = b""
                while chunk := sock.recv(65536):
                    data += chunk
            raw_head, _, body = data.partition(b"\r\n\r\n")
            get.raw = body
            get.body = body.decode("utf-8", errors="replace")
            head = raw_head.decode("latin-1").split("\r\n")
            get.headers = [
                (name.strip().lower(), value.strip())
                for name, _, value in (line.partition(":") for line in head[1:])
            ]
            status = int(head[0].split()[1])
            location = next(
                (
                    line.split(":", 1)[1].strip()
                    for line in head
                    if line.lower().startswith("location:")
                ),
                "",
            )
            return status, location

        get.port = port
        get.log = work / "access.log"
        yield get
    finally:
        subprocess.run([NGINX, "-p", str(work), "-c", str(conf), "-s", "stop"], check=False)
