"""Граница доступа анкеты: ключ из терминала, а не заголовок Host.

Сервер поднимается по-настоящему, запросы идут по сети. Сетевой сценарий —
клиент с другого интерфейса машины, который подделал Host и получил страницу:
он не должен ни прочитать настройки, ни записать site.yaml.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from heron.setup import server

MARKER = "MARKER-7f3a"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _outer_ip() -> str | None:
    """Не-петлевой адрес этой машины, если он есть."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 9))
            ip = sock.getsockname()[0]
        except OSError:
            return None
    return None if ip.startswith("127.") else ip


def _site(root: Path) -> Path:
    (root / "content" / "en").mkdir(parents=True)
    (root / "site.yaml").write_text(
        "site:\n  name: Before\n  domain: example.test\n  languages: [en]\n  default_lang: en\n"
        "theme:\n  name: theme\n",
        encoding="utf-8",
    )
    return root


def _start(root: Path, host: str):
    port = _free_port()
    ready = threading.Event()
    box: dict[str, str] = {}

    def on_ready(token: str) -> None:
        box["token"] = token
        ready.set()

    thread = threading.Thread(
        target=server.run, args=(root, host, port, False), kwargs={"on_ready": on_ready}
    )
    thread.daemon = True
    thread.start()
    assert ready.wait(10)
    return port, box["token"], thread


def _call(url: str, *, data: dict | None = None, token: str = "", host: str = "localhost"):
    headers = {"Host": host}
    if token:
        headers["X-Heron-Token"] = token
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def _stop(port: int, token: str, thread) -> None:
    _call(f"http://127.0.0.1:{port}/api/stop", data={}, token=token)
    thread.join(10)


SAVE = {"answers": {"site": {"name": MARKER, "domain": "example.test", "languages": ["en"]}}}


def test_local_client_with_the_printed_key_reads_and_saves(tmp_path):
    root = _site(tmp_path)
    port, token, thread = _start(root, "127.0.0.1")
    try:
        base = f"http://127.0.0.1:{port}"
        status, page = _call(base + "/")
        assert status == 200
        assert token not in page  # страница одинакова для всех: ключа в ней нет
        status, body = _call(base + "/api/state", token=token)
        assert status == 200 and json.loads(body)["answers"]["site"]["name"] == "Before"
        status, body = _call(base + "/api/save", data=SAVE, token=token)
        assert status == 200, body
        assert MARKER in (root / "site.yaml").read_text("utf-8")
    finally:
        _stop(port, token, thread)


def test_without_the_key_nothing_is_read_or_written(tmp_path):
    root = _site(tmp_path)
    before = (root / "site.yaml").read_bytes()
    port, token, thread = _start(root, "127.0.0.1")
    try:
        base = f"http://127.0.0.1:{port}"
        assert _call(base + "/api/state")[0] == 403
        assert _call(base + "/api/state", token="wrong")[0] == 403
        assert _call(base + "/api/save", data=SAVE)[0] == 403
        assert _call(base + "/api/upload", data={})[0] == 403
        assert _call(base + "/api/stop", data={})[0] == 403
        assert (root / "site.yaml").read_bytes() == before
    finally:
        _stop(port, token, thread)


def test_network_client_with_spoofed_host_gets_no_key_and_no_access(tmp_path):
    ip = _outer_ip()
    if ip is None:
        pytest.skip("у машины нет не-петлевого адреса")
    root = _site(tmp_path)
    before = (root / "site.yaml").read_bytes()
    # Как в контейнере: слушаем все интерфейсы.
    port, token, thread = _start(root, "0.0.0.0")
    try:
        base = f"http://{ip}:{port}"
        status, page = _call(base + "/", host="localhost")
        assert status == 200 and token not in page
        assert _call(base + "/api/state", host="localhost")[0] == 403
        assert _call(base + "/api/save", data=SAVE, host="localhost")[0] == 403
        assert (root / "site.yaml").read_bytes() == before
        # Чужое имя в Host не проходит даже с ключом: защита от подмены DNS.
        assert _call(base + "/api/state", token=token, host="attacker.test")[0] == 403
    finally:
        _stop(port, token, thread)


def test_outside_a_container_other_interfaces_cannot_connect(tmp_path):
    ip = _outer_ip()
    if ip is None:
        pytest.skip("у машины нет не-петлевого адреса")
    from heron.core.watch import default_host

    root = _site(tmp_path)
    port, token, thread = _start(root, default_host(False))
    try:
        time.sleep(0.1)
        with pytest.raises(OSError):
            socket.create_connection((ip, port), timeout=2).close()
    finally:
        _stop(port, token, thread)
