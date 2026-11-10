"""Внутренний nginx: заголовки безопасности, методы, готовый gzip, адрес в журнале (22 §5).

- HSTS настраивается (nginx.hsts), preload - по правилам hstspreload.org;
- Permissions-Policy (nginx.permissions), X-Frame-Options, Cross-Origin-Opener-Policy;
- только GET и HEAD, остальное - 405 с Allow и теми же заголовками;
- `.gz` рядом с текстовыми файлами (gzip_static), детерминированно;
- адрес посетителя от внешнего прокси (realip) и в журнале - по nginx.log_ip;
- open_file_cache.

Ответы проверяет настоящий nginx (tests/nginx_server.py) в обоих режимах адресов.
"""

from __future__ import annotations

import gzip
import re
import zlib
from pathlib import Path

import pytest
import yaml

from heron.contracts.site import (
    PERMISSION_DEFAULTS,
    HstsBlock,
    SiteConfig,
    load_site,
    permission_header,
)
from heron.core import build as pipeline
from heron.core import output, precompress
from heron.core.errors import Collector, HeronError
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
SECURITY = (
    "x-content-type-options",
    "referrer-policy",
    "content-security-policy",
    "strict-transport-security",
    "permissions-policy",
    "x-frame-options",
    "cross-origin-opener-policy",
)
DEFAULT_POLICY = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), encrypted-media=(), "
    "fullscreen=(self), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), "
    "midi=(), payment=(), picture-in-picture=(), publickey-credentials-get=(), "
    "screen-wake-lock=(), sync-xhr=(), usb=(), xr-spatial-tracking=()"
)
PAGE = "---\ntitle: {t}\nh1: {t}\ndescription: D\n{extra}---\n\n{body}\n"


def config(**nginx_block) -> SiteConfig:
    return SiteConfig.model_validate({**BASE, "nginx": nginx_block})


def conf_of(**nginx_block) -> str:
    return nginx.generate(config(**nginx_block))[nginx.NAME]


def _site_yaml(tmp_path: Path, block: str) -> Path:
    path = tmp_path / "site.yaml"
    path.write_text(
        'heron: ">=0.1"\nsite: {name: x, domain: example.com, languages: [en], theme: main}\n'
        + block,
        encoding="utf-8",
    )
    return path


# --- HSTS ---------------------------------------------------------------------------------


def test_hsts_default_is_the_old_header():
    assert HstsBlock().header() == "max-age=31536000; includeSubDomains"
    conf = conf_of()
    assert (
        'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;' in conf
    )


def test_hsts_is_configurable_and_zero_turns_it_off():
    conf = conf_of(hsts={"max_age": "180d", "subdomains": False})
    assert 'Strict-Transport-Security "max-age=15552000" always;' in conf
    conf = conf_of(hsts={"max_age": "2y", "preload": True})
    assert 'Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"' in conf
    assert "Strict-Transport-Security" not in conf_of(hsts={"max_age": 0})


@pytest.mark.parametrize(
    "block",
    [
        "nginx:\n  hsts:\n    preload: true\n    max_age: 180d\n",
        "nginx:\n  hsts:\n    preload: true\n    subdomains: false\n",
        "nginx:\n  hsts:\n    max_age: 1 year\n",
        "nginx:\n  hsts:\n    maxage: 1y\n",
    ],
)
def test_bad_hsts_is_e011(tmp_path, block):
    with pytest.raises(HeronError) as caught:
        load_site(_site_yaml(tmp_path, block))
    assert caught.value.code == "E011"
    if "preload" in block:
        assert "hstspreload.org" in caught.value.render("en")
        assert "1y" in caught.value.render("ru")


# --- Permissions-Policy, X-Frame-Options, COOP ----------------------------------------------


def test_permissions_default_and_overrides():
    assert permission_header({}) == DEFAULT_POLICY
    assert "interest-cohort" not in DEFAULT_POLICY  # Chromium: «Unrecognized feature»
    got = permission_header(
        {
            "geolocation": "self",
            "fullscreen": "*",
            "autoplay": "self https://player.example.com",
            "clipboard-write": "self",
        }
    )
    assert "geolocation=(self)" in got and "fullscreen=*" in got
    assert 'autoplay=(self "https://player.example.com")' in got
    assert got.endswith("clipboard-write=(self)")  # новые - после умолчаний
    conf = conf_of(permissions={"autoplay": ["self", "https://player.example.com"]})
    assert 'autoplay=(self \\"https://player.example.com\\")' in conf  # кавычки экранированы


@pytest.mark.parametrize(
    ("block", "words"),
    [
        ("geolocaton: self", "'geolocation'"),
        ("interest-cohort: none", "interest-cohort"),
        ("camera: maybe", "camera"),
        ("camera: self none", "self none"),
        ('camera: "* self"', "* self"),
        ("camera: http://a.example.com", "http://a.example.com"),
        ('camera: "https://a.example.com/path"', "https://a.example.com/path"),
    ],
)
def test_bad_permission_is_e011(tmp_path, block, words):
    with pytest.raises(HeronError) as caught:
        load_site(_site_yaml(tmp_path, f"nginx:\n  permissions:\n    {block}\n"))
    assert caught.value.code == "E011"
    assert words in caught.value.render("en")


def test_frame_and_opener_headers_everywhere_security_is():
    conf = conf_of()
    count = conf.count("add_header X-Content-Type-Options")
    assert count == 5  # server, healthz, media, assets, копии с хешем
    for line in (
        f"add_header Permissions-Policy {nginx.quote(DEFAULT_POLICY)} always;",
        'add_header X-Frame-Options "SAMEORIGIN" always;',
        'add_header Cross-Origin-Opener-Policy "same-origin" always;',
    ):
        assert conf.count(line) == count, line
    assert "frame-ancestors 'self'" in conf  # то же, что X-Frame-Options: SAMEORIGIN
    assert "Cross-Origin-Resource-Policy" not in conf
    assert "Cross-Origin-Embedder-Policy" not in conf


# --- журнал -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "mode"), [("masked", "masked"), ("full", "full"), ("off", "off"), ('"off"', "off")]
)
def test_log_ip_values(tmp_path, raw, mode):
    # `off` без кавычек YAML читает как false - это тоже off
    config = load_site(_site_yaml(tmp_path, f"nginx:\n  log_ip: {raw}\n"))
    assert config.nginx.log_ip == mode


@pytest.mark.parametrize("raw", ["half", "true", "on", "1"])
def test_bad_log_ip_is_e011(tmp_path, raw):
    with pytest.raises(HeronError) as caught:
        load_site(_site_yaml(tmp_path, f"nginx:\n  log_ip: {raw}\n"))
    assert caught.value.code == "E011"


def test_log_directives():
    conf = conf_of()
    head, server = conf.split("server {", 1)
    assert "map $remote_addr $heron_log_ip_masked {" in head
    name = re.search(r"^log_format (heron_masked_[0-9a-f]{10}) '\$heron_log_ip_masked ", head, re.M)
    assert name, head
    assert f"    access_log /var/log/nginx/access.log {name[1]};\n" in server
    assert "$http_x_forwarded_for" not in conf  # иначе полный адрес уходил бы в журнал
    for net in ("127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"):
        assert f"    set_real_ip_from {net};\n" in server
    assert "real_ip_header X-Forwarded-For;" in server and "real_ip_recursive on;" in server
    full = conf_of(log_ip="full")
    assert "heron_log_ip_masked" not in full
    assert re.search(r"^log_format heron_full_[0-9a-f]{10} '\$remote_addr ", full, re.M)
    off = conf_of(log_ip="off")
    assert re.search(r"^log_format heron_off_[0-9a-f]{10} '- - \$remote_user ", off, re.M)
    assert "$remote_addr" not in off.split("server {")[0]


@needs_nginx
def test_two_sites_in_one_http_do_not_clash():
    """Имя формата журнала разное у разных конфигов: два log_format с одним именем - emerg."""
    a = conf_of()
    b = conf_of(cache={"media": "1h"}).replace("listen       8080;", "listen       8081;")
    result = nginx.check(a + "\n" + b)
    assert result is not None and result[0], result
    # одни и те же исходники - одно имя
    assert conf_of() == a


def test_server_level_directives():
    conf = conf_of()
    server = conf.split("server {", 1)[1]
    for line in (
        "open_file_cache          max=10000 inactive=60s;",
        "open_file_cache_valid    60s;",
        "open_file_cache_min_uses 2;",
        "open_file_cache_errors   on;",
        "gzip_static on;",
        "if ($heron_method_denied) { return 405; }",
        "add_header Allow $heron_allow always;",
    ):
        assert f"    {line}\n" in server, line
    assert server.index("return 405") < server.index("\n    location ")
    types = re.search(r"gzip_types[^;]*;", conf)[0]
    for kind in (
        "image/svg+xml",
        "application/xml",
        "application/manifest+json",
        "font/ttf",
        "font/otf",
        "application/vnd.ms-fontobject",
        "text/javascript",
    ):
        assert kind in types, kind


@needs_nginx
@pytest.mark.parametrize("log_ip", ["masked", "full", "off"])
def test_nginx_t_accepts_every_mode(log_ip):
    for slash in ("always", "never"):
        model = SiteConfig.model_validate(
            {
                **BASE,
                "nginx": {"log_ip": log_ip, "permissions": {"geolocation": "self"}},
                "urls": {"trailing_slash": slash},
            }
        )
        result = nginx.check(nginx.generate(model)[nginx.NAME])
        assert result is not None and result[0], result


# --- готовый gzip ---------------------------------------------------------------------------


def _outputs(files: dict[str, str | bytes]) -> output.Outputs:
    out = output.Outputs()
    for rel, value in files.items():
        if isinstance(value, bytes):
            entry = output.Entry(owner=rel, kind="static", data=value)
        else:
            entry = output.Entry(owner=rel, kind="page", text=value)
        out.add(rel, entry, Collector())
    return out


def test_precompress_picks_text_files_of_size():
    big = "<p>" + "heron " * 400 + "</p>"
    out = _outputs(
        {
            "index.html": big,
            "small.html": "<p>tiny</p>",
            "assets/site.css": big,
            "assets/site.0123456789.css": big,
            "assets/font.ttf": big,
            "assets/font.woff2": big,
            "media/x.svg": big,
            "media/x.jpg": big,
            "media/x.pdf": big,
            "app.webmanifest": big,
            "favicon.ico": big,
            ".well-known/security.txt": big,
            "ru/.hidden/x.html": big,
            "noise.txt": bytes(range(256)) * 8,  # повторы: сжимается
        }
    )
    assert precompress.add(out) == 8
    made = sorted(rel for rel in out.entries if rel.endswith(".gz"))
    assert made == [
        "app.webmanifest.gz",
        "assets/font.ttf.gz",
        "assets/site.0123456789.css.gz",
        "assets/site.css.gz",
        "favicon.ico.gz",
        "index.html.gz",
        "media/x.svg.gz",
        "noise.txt.gz",
    ]
    packed = out.entries["index.html.gz"].data
    assert gzip.decompress(packed) == big.encode()
    # детерминированно: время 0, без имени файла (флаги 0), уровень 9 (XFL=2)
    assert packed[3] == 0 and packed[4:8] == b"\0\0\0\0" and packed[8] == 2
    assert precompress.compress(big.encode()) == packed


def test_precompress_skips_files_that_do_not_shrink_and_foreign_gz():
    noise = bytes((i * 7919 + 13) % 256 for i in range(4096))
    out = _outputs({"a.txt": noise, "b.css": "x" * 5000, "b.css.gz": b"own"})
    precompress.add(out)
    if len(precompress.compress(noise)) >= len(noise):
        assert "a.txt.gz" not in out.entries
    assert out.entries["b.css.gz"].data == b"own"  # свой .gz сайта не перекрывается


def _gz_site(tmp_path: Path, slash: str = "always") -> Path:
    root = tmp_path / "site"
    create(root, name="demo", languages=["en", "ru"])
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["gone"] = ["/old-gone/"]
    data["urls"] = {"trailing_slash": slash}
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), "utf-8")
    body = "Long text. " * 300
    (root / "content" / "en" / "page.md").write_text(
        PAGE.format(t="Page", extra="redirect_from: [/old-page/]\n", body=body), "utf-8"
    )
    return root


def test_build_writes_gz_and_two_builds_are_identical(tmp_path):
    root = _gz_site(tmp_path)
    first = pipeline.run(root, dist=tmp_path / "one")
    assert not first.failed, [str(e) for e in first.collector.errors]
    second = pipeline.run(root, dist=tmp_path / "two")
    assert not second.failed
    one = {
        p.relative_to(tmp_path / "one"): p.read_bytes()
        for p in (tmp_path / "one").rglob("*")
        if p.is_file()
    }
    two = {
        p.relative_to(tmp_path / "two"): p.read_bytes()
        for p in (tmp_path / "two").rglob("*")
        if p.is_file()
    }
    assert one == two
    gz = sorted(str(p) for p in one if p.suffix == ".gz")
    assert "index.html.gz" in gz and "page/index.html.gz" in gz
    assert any(re.fullmatch(r"assets/site\.[0-9a-f]{10}\.css\.gz", p) for p in gz), gz
    for rel in gz:
        assert gzip.decompress(one[Path(rel)]) == one[Path(rel[:-3])], rel
    assert not any(
        p.endswith((".woff2.gz", ".jpg.gz", ".webp.gz", ".avif.gz", ".png.gz")) for p in gz
    )
    sitemap = one[Path("sitemap.xml")].decode()
    assert ".gz" not in sitemap
    assert ".gz" not in one[Path("llms.txt")].decode()
    manifest = (tmp_path / "one" / output.MANIFEST).read_text(encoding="utf-8")
    assert '"index.html.gz"' in manifest  # своё: уберётся, когда страница исчезнет


def test_rebuild_keeps_unchanged_gz_and_drops_stale(tmp_path):
    root = _gz_site(tmp_path)
    assert not pipeline.run(root).failed
    dist = root / "dist"
    packed = dist / "page" / "index.html.gz"
    inode = packed.stat().st_ino
    again = pipeline.run(root)
    assert "page/index.html.gz" in again.applied.kept
    assert packed.stat().st_ino == inode
    (root / "content" / "en" / "page.md").unlink()
    assert not pipeline.run(root).failed
    assert not packed.exists()


def test_reuse_needs_the_same_bytes(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    text = "<p>" + "x y " * 600 + "</p>"
    (dist / "index.html.gz").write_bytes(gzip.compress(b"other", mtime=0))
    (dist / output.MANIFEST).write_text('{"format": 1, "files": ["index.html.gz"]}', "utf-8")
    out = _outputs({"index.html": text})
    precompress.add(out, dist)
    entry = out.entries["index.html.gz"]
    assert entry.data is not None and gzip.decompress(entry.data) == text.encode()
    (dist / "index.html.gz").write_bytes(zlib.compress(text.encode(), 9, wbits=31))
    out = _outputs({"index.html": text})
    precompress.add(out, dist)
    assert out.entries["index.html.gz"].source == dist / "index.html.gz"


# --- настоящий nginx --------------------------------------------------------------------------


def _counts(headers: list[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, _ in headers:
        counts[name] = counts.get(name, 0) + 1
    return counts


def _value(headers, name):
    return [v for k, v in headers if k == name]


def _check_security(get, path, status, method="GET"):
    got = get(path, method=method)[0]
    assert got == status, (method, path, got)
    counts = _counts(get.headers)
    for name in SECURITY:
        assert counts.get(name) == 1, (method, path, name, get.headers)
    assert _value(get.headers, "x-frame-options") == ["SAMEORIGIN"]
    assert _value(get.headers, "cross-origin-opener-policy") == ["same-origin"]
    assert _value(get.headers, "permissions-policy") == [DEFAULT_POLICY]
    return get.headers


@needs_nginx
@pytest.mark.parametrize("slash", ["always", "never"])
def test_headers_once_on_every_kind_of_answer(tmp_path, slash):
    root = _gz_site(tmp_path, slash)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    page = (dist / "index.html").read_text(encoding="utf-8")
    css = re.search(r'href="(/assets/site\.[0-9a-f]{10}\.css)"', page)[1]
    media = next(p.name for p in (dist / "media").iterdir() if p.is_file() and p.suffix != ".gz")
    tail = "/" if slash == "always" else ""
    with serve(dist, tmp_path / "nginx") as get:
        _check_security(get, "/", 200)
        _check_security(get, f"/page{tail}", 200)
        _check_security(get, "/old-page/", 301)
        _check_security(get, f"/page{'' if tail else '/'}", 301)
        _check_security(get, f"/no-such-page{tail}", 404)
        _check_security(get, f"/ru/no-such-page{tail}", 404)
        _check_security(get, "/old-gone/", 410)
        _check_security(get, css, 200)
        _check_security(get, "/assets/site.css", 200)
        _check_security(get, f"/media/{media}", 200)
        _check_security(get, f"/media/{media}?v=0123456789", 200)
        _check_security(get, "/healthz", 200)
        _check_security(get, "/", 200, method="HEAD")
        assert not _value(get.headers, "allow")
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "PATCH", "TRACE"):
            for path in ("/", f"/page{tail}", css, f"/media/{media}", "/healthz", "/nowhere"):
                headers = _check_security(get, path, 405, method=method)
                assert _value(headers, "allow") == ["GET, HEAD"], (method, path)


@needs_nginx
def test_gzip_static_serves_the_file_next_to_it(tmp_path):
    root = _gz_site(tmp_path)
    assert not pipeline.run(root).failed
    dist = root / "dist"
    # подменённый .gz отличим от сжатого на лету: значит, отдан именно файл
    marker = b"<!doctype html><p>served from page/index.html.gz</p>"
    (dist / "page" / "index.html.gz").write_bytes(gzip.compress(marker, mtime=0))
    with serve(dist, tmp_path / "nginx") as get:
        for path in ("/page/", "/page/index.html"):
            assert get(path, headers={"Accept-Encoding": "gzip"}, version="1.1")[0] == 200
            assert _value(get.headers, "content-encoding") == ["gzip"]
            assert _value(get.headers, "vary") == ["Accept-Encoding"]
            assert gzip.decompress(get.raw) == marker, path
        assert get("/page/", version="1.1")[0] == 200
        assert not _value(get.headers, "content-encoding")
        assert get.raw == (dist / "page" / "index.html").read_bytes()


def _logged(get, xff):
    get("/", headers={"X-Forwarded-For": xff})
    lines = get.log.read_text(encoding="utf-8").strip().splitlines()
    return lines[-1]


@needs_nginx
@pytest.mark.parametrize(
    ("mode", "want4", "want6"),
    [
        ("masked", "203.0.113.0 ", "2001:db8:abcd:: "),
        ("full", "203.0.113.45 ", "2001:db8:abcd:12::1 "),
        ("off", "- - ", "- - "),
    ],
)
def test_real_ip_in_log(tmp_path, mode, want4, want6):
    root = _gz_site(tmp_path)
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["nginx"] = {"log_ip": mode}
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), "utf-8")
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:
        # nginx видит петлю: внешний прокси на той же машине, адрес - в X-Forwarded-For
        line = _logged(get, "198.51.100.7, 203.0.113.45")
        assert line.startswith(want4), line
        assert "198.51.100" not in line and "127.0.0.1" not in line
        line = _logged(get, "2001:db8:abcd:12::1")
        assert line.startswith(want6), line
        # частная сеть за прокси тоже доверенная: берётся первый чужой справа
        line = _logged(get, "203.0.113.45, 10.1.2.3")
        assert line.startswith(want4), line
        get("/healthz")
        assert "/healthz" not in get.log.read_text(encoding="utf-8")


def test_engine_defaults_for_page_permissions_match_engine():
    page = (Path(__file__).parents[1] / "heron" / "setup" / "page.js").read_text("utf-8")
    table = re.search(r"const PERMISSIONS = \{([^}]*)\}", page)[1]
    pairs = dict(re.findall(r'"?([a-z-]+)"?: "([^"]+)"', table))
    assert pairs == {k: PERMISSION_DEFAULTS[k] for k in pairs}
    assert set(pairs) == {
        "fullscreen",
        "autoplay",
        "picture-in-picture",
        "geolocation",
        "camera",
        "microphone",
        "payment",
    }
