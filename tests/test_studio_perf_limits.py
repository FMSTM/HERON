"""Студия 0.3.3: без многосекундного обхода словаря и без чтения больших тел в память.

PERF-01: `props_by_spec()` и запросы к словарю schema.org (`ancestors`,
`properties_of`) считаются один раз; `state()` типичного сайта - доли секунды,
повтор не обходит граф.
PERF-02: JSON-запрос - не больше MAX_JSON, загрузки пишутся на диск кусками по
64 КБ (общий потолок прежний); `0.0.0.0` - не локальное имя хоста.
"""

from __future__ import annotations

import http.client
import io
import json
import socket
import threading
import time

import pytest
from click.testing import CliRunner

from heron import setup
from heron.cli import main
from heron.schemaorg import Vocab, vocab
from heron.setup import server

# --- PERF-01 ---------------------------------------------------------------------------


def test_props_by_spec_walks_the_graph_once(monkeypatch):
    setup._props_by_spec.cache_clear()
    first = setup.props_by_spec()
    calls = {"n": 0}
    real = Vocab.allows

    def counting(self, types, prop):
        calls["n"] += 1
        return real(self, types, prop)

    monkeypatch.setattr(Vocab, "allows", counting)
    again = setup.props_by_spec()
    assert again == first and calls["n"] == 0
    # наружу - копия: правка ответа кэш не портит
    key = next(iter(again))
    again[key].append("x")
    assert setup.props_by_spec()[key] == first[key]


def test_vocab_answers_are_memoised():
    v = vocab()
    assert v.ancestors("MedicalClinic") is v.ancestors("MedicalClinic")
    assert v.properties_of(["Organization"]) == v.properties_of("Organization")
    assert "name" in v.properties_of("Organization")


def test_state_of_a_typical_site_is_fast(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    root = tmp_path / "demo"
    setup.state(root, lang="en")  # прогрев: данные пакета читаются один раз
    started = time.perf_counter()
    for _ in range(3):
        setup.state(root, lang="en")
    assert (time.perf_counter() - started) / 3 < 0.5


# --- PERF-02 ---------------------------------------------------------------------------


class _Reader(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.sizes.append(size)
        return super().read(size)


def test_spool_reads_in_64k_chunks(tmp_path):
    data = bytes(range(256)) * 1024  # 256 КБ
    reader = _Reader(data)
    path = server.spool(reader, len(data), tmp_path)
    assert path.read_bytes() == data
    assert max(reader.sizes) <= server.CHUNK == 64 * 1024


def test_spool_short_body_leaves_nothing(tmp_path):
    with pytest.raises(ValueError):
        server.spool(io.BytesIO(b"abc"), 10, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_limits():
    assert 5 * 1024 * 1024 <= server.MAX_JSON <= 10 * 1024 * 1024
    assert server.MAX_BODY == 210 * 1024 * 1024
    assert "0.0.0.0" not in server.LOCAL_HOSTS


@pytest.fixture
def running(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    root = tmp_path / "demo"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    box: dict[str, str] = {}
    thread = threading.Thread(
        target=server.run,
        args=(root, "127.0.0.1", port),
        kwargs={"on_ready": lambda token: box.update(token=token)},
        daemon=True,
    )
    thread.start()
    while "token" not in box:
        time.sleep(0.01)
    yield port, box["token"], root
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(
        "POST",
        "/api/stop",
        body=b"{}",
        headers={"X-Heron-Token": box["token"], "Host": "localhost"},
    )
    conn.getresponse().read()
    thread.join(timeout=5)


def _post(port, token, path, body: bytes, length: int | None = None, host="localhost"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", f"{host}:{port}")
    conn.putheader("X-Heron-Token", token)
    conn.putheader("Content-Length", str(len(body) if length is None else length))
    conn.endheaders()
    if body:
        conn.send(body)
    response = conn.getresponse()
    return response.status, response.read()


def test_json_over_the_limit_is_413_without_reading_it(running):
    port, token, _ = running
    status, body = _post(port, token, "/api/save", b"", length=server.MAX_JSON + 1)
    assert status == 413 and json.loads(body)["error"]


def test_upload_is_streamed_and_kept(running):
    port, token, _ = running
    data = b"PK\x03\x04" + b"\0" * (300 * 1024)
    status, body = _post(port, token, "/api/upload", data)
    assert status == 200 and json.loads(body)["upload"]


def test_image_upload_over_its_limit_is_413(running):
    from heron import studio

    port, token, _ = running
    status, _ = _post(
        port, token, "/api/studio/upload?name=a.png", b"", length=studio.MAX_IMAGE + 1
    )
    assert status == 413


def test_host_0000_is_not_local(running):
    port, token, _ = running
    status, _ = _post(port, token, "/api/save", b"{}", host="0.0.0.0")
    assert status == 403
    ok, _ = _post(port, token, "/api/save", b'{"answers": {}}', host="localhost")
    assert ok != 403


def test_preview_port_refuses_host_0000(running):
    port, _, _ = running
    conn = http.client.HTTPConnection("127.0.0.1", port + 1, timeout=5)
    conn.putrequest("GET", "/", skip_host=True)
    conn.putheader("Host", f"0.0.0.0:{port + 1}")
    conn.endheaders()
    assert conn.getresponse().status == 403
