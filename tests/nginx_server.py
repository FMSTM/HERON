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

        def get(path: str) -> tuple[int, str]:
            """Код ответа и Location. Путь уходит байтами как есть: и
            percent-encoded, и сырой UTF-8 — так, как его шлют браузеры и боты."""
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                sock.sendall(b"GET " + path.encode("utf-8") + b" HTTP/1.0\r\nHost: x\r\n\r\n")
                data = b""
                while chunk := sock.recv(65536):
                    data += chunk
            raw_head, _, body = data.partition(b"\r\n\r\n")
            get.body = body.decode("utf-8", errors="replace")
            head = raw_head.decode("latin-1").split("\r\n")
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

        yield get
    finally:
        subprocess.run([NGINX, "-p", str(work), "-c", str(conf), "-s", "stop"], check=False)
