"""Версии файлов темы и ресурсов: хеш содержимого в имени (21 §4, 22 §5).

После обновления темы браузер не должен держать вчерашний site.css: страницы
ссылаются на копии `site.<hash>.css`, прежние имена остаются рядом.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core import build as pipeline
from heron.core import versions
from heron.core.errors import Collector
from heron.scaffold import create

FONT = b"wOF2" + b"\x00" * 64


def sha10(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:10]


def make(tmp_path: Path, name: str = "site") -> Path:
    root = tmp_path / name
    create(root, name="demo", languages=["en"])
    assets = root / "theme" / "assets"
    (assets / "fonts").mkdir()
    (assets / "fonts" / "a.woff2").write_bytes(FONT)
    (assets / "css").mkdir()
    (assets / "css" / "extra.css").write_text(
        '@import "../site.css";\n'
        "@font-face { font-family: A; src: url(../fonts/a.woff2) format('woff2'); }\n"
        "body { background: url('/assets/fonts/a.woff2?x=1#frag'); }\n"
        "i { background: url(data:image/png;base64,AAAA); }\n"
        "b { background: url(https://cdn.example/assets/x.png); }\n",
        encoding="utf-8",
    )
    (assets / "m.js").write_text("export const x = 1;\n", encoding="utf-8")
    base = root / "theme" / "base.html"
    text = base.read_text(encoding="utf-8")
    text = text.replace(
        "</head>",
        '<link rel="stylesheet" href="{{ asset(\'css/extra.css\') }}">\n'
        '<link rel="preload" href="/assets/fonts/a.woff2" as="font" crossorigin>\n'
        '<link rel="modulepreload" href="/assets/m.js">\n'
        "<style>.x { background: url(/assets/fonts/a.woff2); }</style>\n"
        "</head>",
    )
    text = text.replace(
        "<body>",
        "<body>\n"
        '<img alt="" src="/media/cover.png" srcset="/media/cover.png 1x, '
        'https://demo.example/media/cover.png 2x">\n'
        '<a href="/media/cover.png">open</a>\n'
        '<div style="background: url(&quot;/media/cover.png&quot;)"></div>\n'
        '<img alt="" src="https://cdn.example/media/cover.png">\n'
        "<p>/assets/site.css stays text</p>\n"
        '<script type="application/ld+json">{"image": "/media/cover.png"}</script>\n',
        1,
    )
    base.write_text(text, encoding="utf-8")
    return root


def build(root: Path, dist: Path | None = None):
    result = pipeline.run(root, dist=dist)
    assert not result.failed, [str(e) for e in result.collector.errors]
    return result


def hashed(dist: Path) -> set[str]:
    return {
        p.relative_to(dist).as_posix()
        for p in dist.rglob("*")
        if p.is_file() and versions.HASHED.search(p.name)
    }


def html(dist: Path) -> dict[str, bytes]:
    return {p.relative_to(dist).as_posix(): p.read_bytes() for p in dist.rglob("*.html")}


def test_hashed_copies_next_to_plain_names(tmp_path):
    root = make(tmp_path)
    build(root)
    dist = root / "dist"
    css = (root / "theme" / "assets" / "site.css").read_bytes()
    assert (dist / f"assets/site.{sha10(css)}.css").read_bytes() == css
    # прежние имена остаются: старые страницы в кэше и чужие ссылки
    for rel in ("assets/site.css", "assets/site.js", "assets/fonts/a.woff2", "media/cover.png"):
        assert (dist / rel).is_file(), rel
    assert f"assets/fonts/a.{sha10(FONT)}.woff2" in hashed(dist)


def test_one_line_edit_changes_only_that_css_and_its_importers(tmp_path):
    root = make(tmp_path)
    build(root)
    before = hashed(root / "dist")
    css = root / "theme" / "assets" / "site.css"
    css.write_text(css.read_text(encoding="utf-8") + "\n.new { color: red; }\n", "utf-8")
    build(root)
    after = hashed(root / "dist")
    changed = {re.sub(r"\.[0-9a-f]{10}\.", ".", rel) for rel in before ^ after}
    # site.css и импортирующий его css/extra.css - больше ничего
    assert changed == {"assets/site.css", "assets/css/extra.css"}
    # старых копий с хешем в сборке нет: dist пересобирается
    assert len([r for r in after if r.startswith("assets/site.") and r.endswith(".css")]) == 1


def test_rebuild_without_changes_gives_identical_html(tmp_path):
    root = make(tmp_path)
    build(root)
    first = html(root / "dist")
    build(root)
    assert html(root / "dist") == first
    build(root, dist=tmp_path / "other")
    assert html(tmp_path / "other") == first


def test_font_url_in_css_is_rewritten_and_changes_css_hash(tmp_path):
    root = make(tmp_path)
    build(root)
    dist = root / "dist"
    [extra] = [r for r in hashed(dist) if r.startswith("assets/css/extra.")]
    text = (dist / extra).read_text(encoding="utf-8")
    font = sha10(FONT)
    assert f"url(../fonts/a.{font}.woff2)" in text
    assert f"url('/assets/fonts/a.{font}.woff2?x=1#frag')" in text
    [site_css] = [r for r in hashed(dist) if re.match(r"assets/site\.\w+\.css", r)]
    assert f'@import "../{site_css.split("/")[-1]}";' in text
    assert "url(data:image/png;base64,AAAA)" in text
    assert "url(https://cdn.example/assets/x.png)" in text
    # хеш стилей - по переписанным байтам
    assert extra == f"assets/css/extra.{sha10(text.encode())}.css"
    # шрифт поменялся - поменялось и имя стилей, которые на него ссылаются
    (root / "theme" / "assets" / "fonts" / "a.woff2").write_bytes(FONT + b"\x01")
    build(root)
    [extra2] = [r for r in hashed(dist) if r.startswith("assets/css/extra.")]
    assert extra2 != extra


def test_html_references_rewritten(tmp_path):
    root = make(tmp_path)
    build(root)
    dist = root / "dist"
    page = (dist / "index.html").read_text(encoding="utf-8")
    font, cover = sha10(FONT), sha10((root / "media" / "cover.png").read_bytes())
    m = sha10((root / "theme" / "assets" / "m.js").read_bytes())
    assert f'<link rel="preload" href="/assets/fonts/a.{font}.woff2"' in page
    assert f'<link rel="modulepreload" href="/assets/m.{m}.js">' in page
    assert f"<style>.x {{ background: url(/assets/fonts/a.{font}.woff2); }}</style>" in page
    assert (
        f'srcset="/media/cover.{cover}.png 1x, https://demo.example/media/cover.{cover}.png 2x"'
        in page
    )
    assert f'src="/media/cover.{cover}.png"' in page
    assert f'style="background: url(&quot;/media/cover.{cover}.png&quot;)"' in page
    # ссылки для людей, чужие адреса, текст и скрипты не трогаются
    assert '<a href="/media/cover.png">open</a>' in page
    assert 'src="https://cdn.example/media/cover.png"' in page
    assert "<p>/assets/site.css stays text</p>" in page
    assert '{"image": "/media/cover.png"}' in page
    # hand-written /assets/ и asset() дают одно и то же имя
    css = sha10((root / "theme" / "assets" / "site.css").read_bytes())
    assert f'href="/assets/site.{css}.css"' in page
    for ref in re.findall(r'(?:src|href)="(/(?:assets|media)/[^"]+)"', page):
        assert (dist / ref.lstrip("/").split("?")[0]).is_file(), ref


def test_social_images_keep_plain_names(tmp_path):
    root = make(tmp_path)
    build(root)
    page = (root / "dist" / "index.html").read_text(encoding="utf-8")
    og = re.search(r'<meta property="og:image" content="([^"]+)"', page).group(1)
    assert og == "https://demo.example/media/cover.png"
    tw = re.search(r'<meta name="twitter:image" content="([^"]+)"', page)
    if tw:
        assert not versions.HASHED.search(tw.group(1))
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    if ld:
        assert not re.search(r"\.[0-9a-f]{10}\.png", ld.group(1))


def test_asset_unknown_file_is_e045(tmp_path):
    root = make(tmp_path)
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text(encoding="utf-8").replace("</head>", "{{ asset('nope.css') }}</head>"),
        encoding="utf-8",
    )
    result = pipeline.run(root)
    assert result.failed
    assert [e for e in result.collector.errors if e.code == "E045"]
    assert "nope.css" in str(result.collector.errors[0])


def test_asset_media_and_theme_paths(tmp_path):
    root = make(tmp_path)
    (root / "media" / "doc.pdf").write_bytes(b"%PDF-1.4 x")
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "</head>",
            "<meta name=a content=\"{{ asset('media/doc.pdf') }}|{{ asset('/assets/site.js') }}"
            "|{{ asset('fonts/a.woff2#x') }}\"></head>",
        ),
        encoding="utf-8",
    )
    build(root)
    dist = root / "dist"
    page = (dist / "index.html").read_text(encoding="utf-8")
    pdf = sha10(b"%PDF-1.4 x")
    js = sha10((root / "theme" / "assets" / "site.js").read_bytes())
    assert (
        f"/media/doc.{pdf}.pdf|/assets/site.{js}.js|/assets/fonts/a.{sha10(FONT)}.woff2#x" in page
    )
    # файл, названный только через asset(), доезжает до сборки
    assert (dist / f"media/doc.{pdf}.pdf").is_file()
    assert (dist / "media/doc.pdf").is_file()


def test_css_import_cycle_is_cut_with_warning(tmp_path):
    folder = tmp_path / "assets"
    folder.mkdir()
    (folder / "a.css").write_text('@import "b.css";', encoding="utf-8")
    (folder / "b.css").write_text('@import "a.css";', encoding="utf-8")
    collector = Collector()
    plan = versions.plan(folder, collector=collector)
    assert set(plan.digests) == {"assets/a.css", "assets/b.css"}
    assert collector.warnings and "a.css" in str(collector.warnings[0].message)


def test_hash_like_name_gets_no_second_copy(tmp_path):
    root = make(tmp_path)
    (root / "theme" / "assets" / "chunk.0123456789.js").write_text("1;\n", encoding="utf-8")
    result = build(root)
    dist = root / "dist"
    assert (dist / "assets/chunk.0123456789.js").is_file()
    assert not [p for p in (dist / "assets").glob("chunk.0123456789.*.js")]
    assert any("chunk.0123456789.js" in str(w.message) for w in result.collector.warnings)


def test_rewrite_html_unit():
    table = {"assets/a.css": "aaaaaaaaaa", "media/p.png": "bbbbbbbbbb"}
    text = (
        "<link rel=stylesheet href=/assets/a.css>"
        "<img srcset='/media/p.png 480w,/media/p.png 800w' src=\"/media/p.png\">"
        '<link rel="preload" as="image" imagesrcset="/media/p.png 1x">'
        '<meta property="og:image" content="/media/p.png">'
        '<meta name="msapplication-TileImage" content="/media/p.png">'
        "<!-- <img src=/media/p.png> -->"
        "<script>var u = '/media/p.png';</script>"
        "<textarea><img src=/media/p.png></textarea>"
        '<img src="//other.example/media/p.png">'
        '<img src="/media/p.png?v=2">'
    )
    out = versions.rewrite_html(text, table.get, ("https://example.com",))
    assert "href=/assets/a.aaaaaaaaaa.css>" in out
    assert "srcset='/media/p.bbbbbbbbbb.png 480w,/media/p.bbbbbbbbbb.png 800w'" in out
    assert 'imagesrcset="/media/p.bbbbbbbbbb.png 1x"' in out
    assert '<meta property="og:image" content="/media/p.png">' in out
    assert 'content="/media/p.bbbbbbbbbb.png">' in out
    assert "<!-- <img src=/media/p.png> -->" in out
    assert "var u = '/media/p.png';" in out
    assert "<textarea><img src=/media/p.png></textarea>" in out
    assert 'src="//other.example/media/p.png"' in out
    assert 'src="/media/p.bbbbbbbbbb.png?v=2"' in out


# --- heron check ------------------------------------------------------------------


def test_starter_theme_has_no_asset_warnings(tmp_path):
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    keys = [getattr(w.message, "key", "") for w in pipeline.check(root).collector.warnings]
    assert "theme_asset_hardcoded" not in keys
    assert "theme_js_asset_path" not in keys


def test_check_warns_hardcoded_assets_in_templates_and_js(tmp_path):
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "</head>",
            '<link rel="icon" href="/assets/site.css">\n'
            "{# /assets/in-comment.css #}\n"
            '<img src="https://cdn.example/assets/x.png">\n</head>',
        ),
        encoding="utf-8",
    )
    (root / "theme" / "assets" / "app.js").write_text(
        "/* '/assets/in-comment.png' */\nconst img = '/media/photo.png';\n", encoding="utf-8"
    )
    result = pipeline.check(root)
    keys = [w.message for w in result.collector.warnings]
    hard = [w for w in keys if getattr(w, "key", "") == "theme_asset_hardcoded"]
    js = [w for w in keys if getattr(w, "key", "") == "theme_js_asset_path"]
    assert len(hard) == 1
    assert len(js) == 1 and "/media/photo.png" in str(js[0])
    assert [w.line for w in result.collector.warnings if w.message in js] == [2]


# --- serve и просмотр ---------------------------------------------------------------


def test_dev_server_serves_hashed_names(tmp_path):
    import http.client
    import threading

    from heron.core import watch

    root = make(tmp_path)
    dist = tmp_path / "preview"
    build(root, dist=dist)
    handler = type(
        "H",
        (watch.http.server.SimpleHTTPRequestHandler,),
        {
            "__init__": lambda self, *a, **kw: watch.http.server.SimpleHTTPRequestHandler.__init__(
                self, *a, directory=str(dist), **kw
            ),
            "log_message": lambda *a: None,
        },
    )
    server = watch._Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page = (dist / "index.html").read_text(encoding="utf-8")
        href = re.search(r'href="(/assets/site\.[0-9a-f]{10}\.css)"', page).group(1)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
        conn.request("GET", href)
        response = conn.getresponse()
        assert response.status == 200
        assert response.read() == (root / "theme" / "assets" / "site.css").read_bytes()
    finally:
        server.shutdown()


@pytest.mark.parametrize("value", ["2x", "-1", "1.5d", "", "yes"])
def test_cli_build_rejects_bad_cache_time(tmp_path, value):
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    with (root / "site.yaml").open("a", encoding="utf-8") as handle:
        handle.write(f'\nnginx:\n  cache:\n    assets: "{value}"\n')
    out = CliRunner().invoke(main, ["build", str(root)])
    assert out.exit_code != 0
    assert "E011" in out.output and "nginx.cache.assets" in out.output
    assert "1d" in out.output  # подсказка с примерами
