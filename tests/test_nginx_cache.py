"""Кэш браузера во внутреннем nginx: копии с хешем на год, прочее по nginx.cache (22 §5)."""

from __future__ import annotations

import re
import socket

import pytest

from heron.contracts.site import SiteConfig, duration, load_site
from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.modules import nginx
from heron.scaffold import create
from tests.nginx_server import needs_nginx, serve

BASE = {
    "heron": ">=0.1",
    "site": {
        "name": "x",
        "domain": "example.com",
        "languages": ["en"],
        "default_lang": "en",
        "theme": "main",
    },
}


def config(**cache) -> SiteConfig:
    return SiteConfig.model_validate({**BASE, "nginx": {"cache": cache}})


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("1y", 31536000), ("7d", 604800), ("12h", 43200), ("30m", 1800), ("3600", 3600), (90, 90)],
)
def test_duration_formats(value, seconds):
    assert duration(value) == seconds


@pytest.mark.parametrize("value", ["2x", "1.5d", "-1", "", "d", "1 d", True, None, "99999y"])
def test_duration_rejects(value):
    with pytest.raises(ValueError):
        duration(value)


def test_bad_cache_key_or_value_is_e011(tmp_path):
    path = tmp_path / "site.yaml"
    path.write_text(
        'heron: ">=0.1"\nsite: {name: x, domain: example.com, languages: [en], theme: main}\n'
        "nginx:\n  cache:\n    asets: 1d\n",
        encoding="utf-8",
    )
    with pytest.raises(HeronError) as typo:
        load_site(path)
    assert typo.value.code == "E011"
    path.write_text(path.read_text().replace("asets: 1d", "media: 1 week"), encoding="utf-8")
    with pytest.raises(HeronError) as bad:
        load_site(path)
    assert bad.value.code == "E011"
    assert "30m, 12h, 1d" in bad.value.render("en")


def _location(conf: str, prefix: str) -> str:
    start = conf.index(f"location ^~ {prefix} {{")
    depth, index = 0, start
    while True:
        if conf[index] == "{":
            depth += 1
        elif conf[index] == "}":
            depth -= 1
            if depth == 0:
                return conf[start : index + 1]
        index += 1


def test_default_headers_in_config():
    conf = nginx.generate(config())[nginx.NAME]
    for prefix in ("/assets/", "/media/"):
        block = _location(conf, prefix)
        assert 'add_header Cache-Control "public, max-age=86400" always;' in block
        assert 'location ~ "\\.[0-9a-f]{10}\\.[A-Za-z0-9]+$" {' in block
        inner = block[block.index('location ~ "') :]
        assert 'add_header Cache-Control "public, max-age=31536000, immutable" always;' in inner
        # add_header во вложенном location заменяет внешние: безопасность повторена
        assert inner.count("Content-Security-Policy") == 1
        assert inner.count("Strict-Transport-Security") == 1
        assert "X-Content-Type-Options" in inner and "Referrer-Policy" in inner
        # запрет скрытых файлов стоит раньше версии: регулярки проверяются по порядку
        assert block.index("location ~ /\\.") < block.index('location ~ "')
    assert 'add_header Cache-Control "no-cache" always;' in conf


def test_configured_times_in_config():
    conf = nginx.generate(config(versioned="30d", assets="2h", media="7d"))[nginx.NAME]
    assert 'max-age=7200" always;' in _location(conf, "/assets/")
    assert 'max-age=604800" always;' in _location(conf, "/media/")
    assert conf.count('"public, max-age=2592000, immutable"') == 2


@needs_nginx
def test_nginx_t_accepts_config():
    result = nginx.check(
        nginx.generate(config(versioned="30d", assets="0", media="12h"))[nginx.NAME]
    )
    assert result is not None and result[0], result


def _head(port, path):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(f"GET {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
        data = b""
        while chunk := sock.recv(65536):
            data += chunk
    lines = data.partition(b"\r\n\r\n")[0].decode("latin-1").split("\r\n")
    assert " 200 " in lines[0], (path, lines[0])
    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        key, _, value = line.partition(":")
        headers.setdefault(key.lower(), []).append(value.strip())
    return headers


@needs_nginx
def test_real_nginx_cache_headers(tmp_path):
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    page = (dist / "index.html").read_text(encoding="utf-8")
    css = re.search(r'href="(/assets/site\.[0-9a-f]{10}\.css)"', page).group(1)
    media = next(p for p in (dist / "media").iterdir() if re.search(r"\.[0-9a-f]{10}\.", p.name))
    work = tmp_path / "work"
    with serve(dist, work):
        port = int(re.search(r"listen\s+127\.0\.0\.1:(\d+)", (work / "nginx.conf").read_text())[1])
        for path in (css, f"/media/{media.name}"):
            got = _head(port, path)
            assert got["cache-control"] == ["public, max-age=31536000, immutable"], path
            assert got["content-security-policy"] and got["strict-transport-security"]
            assert got["x-content-type-options"] == ["nosniff"]
        for path in ("/assets/site.css", "/media/cover.png"):
            got = _head(port, path)
            assert got["cache-control"] == ["public, max-age=86400"], path
            assert got["content-security-policy"]
        got = _head(port, "/")
        assert got["cache-control"] == ["no-cache"]
        assert got["content-security-policy"]
