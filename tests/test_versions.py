"""Версии файлов темы и ресурсов по хешу содержимого (21 §4, 22 §5).

После обновления темы браузер не должен держать вчерашний site.css: страницы
ссылаются на копии `site.<hash>.css`, прежние имена остаются рядом. Ресурсы
`/media/` не копируются: ссылка на них несёт метку `?v=<hash>`.
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
    # у ресурсов копий нет: версия - метка ?v= в ссылке
    assert not [rel for rel in hashed(dist) if rel.startswith("media/")]


def test_media_is_not_duplicated_in_dist(tmp_path):
    root = make(tmp_path)
    for index in range(3):
        (root / "media" / f"doc{index}.pdf").write_bytes(b"%PDF-1.4 " + bytes([index]) * 4096)
    (root / "media" / "clip.0123456789.webm").write_bytes(b"\x1aE\xdf\xa3" + b"x" * 2048)
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "</body>",
            "".join(f'<img alt="" src="{{{{ asset(\'media/doc{i}.pdf\') }}}}">\n' for i in range(3))
            + '<video src="{{ asset(\'media/clip.0123456789.webm\') }}" poster="/media/cover.png">'
            + "</video>\n</body>",
        ),
        encoding="utf-8",
    )
    result = build(root)
    dist = root / "dist"
    files = [p for p in (dist / "media").rglob("*") if p.is_file()]
    # ни одной копии `<имя>.<хеш>.<расширение>` - кроме файла, который так и назван
    assert [p.name for p in files if versions.HASHED.search(p.name)] == ["clip.0123456789.webm"]
    # байты ресурсов в сборке - ровно байты исходников, без удвоения
    sources = {
        p.relative_to(root).as_posix(): p.stat().st_size
        for p in (root / "media").rglob("*")
        if p.is_file() and not p.name.startswith(".") and p.suffix not in (".md", ".txt")
    }
    built = {p.relative_to(dist).as_posix(): p.stat().st_size for p in files}
    assert built == sources
    assert sum(built.values()) == sum(sources.values())
    # имя, похожее на хеш, у ресурса ничего не значит: метка есть, предупреждения нет
    html = (dist / "index.html").read_text(encoding="utf-8")
    clip = sha10((root / "media" / "clip.0123456789.webm").read_bytes())
    assert f'src="/media/clip.0123456789.webm?v={clip}"' in html
    assert not [w for w in result.collector.warnings if "clip.0123456789" in str(w.message)]


def test_changed_media_changes_only_its_stamp(tmp_path):
    root = make(tmp_path)
    (root / "media" / "doc.pdf").write_bytes(b"%PDF-1.4 one")
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "</body>", '<img alt="" src="{{ asset(\'media/doc.pdf\') }}">\n</body>'
        ),
        encoding="utf-8",
    )
    build(root)
    before = html(root / "dist")
    (root / "media" / "doc.pdf").write_bytes(b"%PDF-1.4 two")
    build(root)
    after = html(root / "dist")
    assert before.keys() == after.keys()
    one, two = sha10(b"%PDF-1.4 one"), sha10(b"%PDF-1.4 two")
    changed = 0
    for rel, text in before.items():
        if text != after[rel]:
            changed += 1
            assert (
                text.replace(f"doc.pdf?v={one}".encode(), f"doc.pdf?v={two}".encode()) == after[rel]
            ), rel
    assert changed >= 1
    assert sorted(p.name for p in (root / "dist" / "media").glob("doc*")) == ["doc.pdf"]


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
        f'srcset="/media/cover.png?v={cover} 1x, https://demo.example/media/cover.png?v={cover} 2x"'
        in page
    )
    assert f'src="/media/cover.png?v={cover}"' in page
    assert f'style="background: url(&quot;/media/cover.png?v={cover}&quot;)"' in page
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
            "<meta name=a content=\"{{ asset('media/doc.pdf') }}\">"
            "<meta name=b content=\"{{ asset('/assets/site.js') }}\">"
            "<meta name=c content=\"{{ asset('fonts/a.woff2#x') }}\"></head>",
        ),
        encoding="utf-8",
    )
    build(root)
    dist = root / "dist"
    page = (dist / "index.html").read_text(encoding="utf-8")
    pdf = sha10(b"%PDF-1.4 x")
    js = sha10((root / "theme" / "assets" / "site.js").read_bytes())
    assert f'<meta name=a content="/media/doc.pdf?v={pdf}">' in page
    assert f'<meta name=b content="/assets/site.{js}.js">' in page
    assert f'<meta name=c content="/assets/fonts/a.{sha10(FONT)}.woff2#x">' in page
    # файл, названный только через asset(), доезжает до сборки - один раз
    assert (dist / "media/doc.pdf").is_file()
    assert not (dist / f"media/doc.{pdf}.pdf").exists()
    # и не числится в отчёте среди файлов, которых никто не ждёт
    assert "media/doc.pdf" not in pipeline.run(root).report.unused_media
    assert "media/doc.pdf" not in pipeline.check(root).report.unused_media


def test_asset_media_keeps_query_and_fragment(tmp_path):
    root = make(tmp_path)
    (root / "media" / "doc.pdf").write_bytes(b"%PDF-1.4 x")
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "</head>",
            '<link rel="preload" as="image" href="{{ asset(\'media/doc.pdf?w=1#p2\') }}"></head>',
        ),
        encoding="utf-8",
    )
    build(root)
    page = (root / "dist" / "index.html").read_text(encoding="utf-8")
    pdf = sha10(b"%PDF-1.4 x")
    # повторный проход по готовому HTML метку не удваивает
    assert f'href="/media/doc.pdf?w=1&amp;v={pdf}#p2"' in page


def test_css_import_cycle_is_cut_with_warning(tmp_path):
    folder = tmp_path / "assets"
    folder.mkdir()
    (folder / "a.css").write_text('@import "b.css";', encoding="utf-8")
    (folder / "b.css").write_text('@import "a.css";', encoding="utf-8")
    collector = Collector()
    plan = versions.plan(folder, collector=collector)
    assert set(plan.digests) == {"assets/a.css", "assets/b.css"}
    assert collector.warnings and "a.css" in str(collector.warnings[0].message)


def test_hash_like_name_in_assets_gets_no_second_copy(tmp_path):
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
        '<img src="/media/p.png?w=1&amp;h=2#top">'
        '<link href="/assets/a.css?x=1#y" rel=stylesheet>'
        '<div style="background:url(/media/p.png?k=1)"></div>'
    )
    out = versions.rewrite_html(text, table.get, ("https://example.com",))
    assert "href=/assets/a.aaaaaaaaaa.css>" in out
    assert "srcset='/media/p.png?v=bbbbbbbbbb 480w,/media/p.png?v=bbbbbbbbbb 800w'" in out
    assert 'imagesrcset="/media/p.png?v=bbbbbbbbbb 1x"' in out
    assert '<meta property="og:image" content="/media/p.png">' in out
    assert 'content="/media/p.png?v=bbbbbbbbbb">' in out
    assert "<!-- <img src=/media/p.png> -->" in out
    assert "var u = '/media/p.png';" in out
    assert "<textarea><img src=/media/p.png></textarea>" in out
    assert 'src="//other.example/media/p.png"' in out
    # ручная версия заменяется хешем, параметры и якорь остаются
    assert 'src="/media/p.png?v=bbbbbbbbbb"' in out
    assert 'src="/media/p.png?w=1&amp;h=2&amp;v=bbbbbbbbbb#top"' in out
    assert 'href="/assets/a.aaaaaaaaaa.css?x=1#y"' in out
    assert "url(/media/p.png?k=1&amp;v=bbbbbbbbbb)" in out
    # второй проход ничего не меняет
    assert versions.rewrite_html(out, table.get, ("https://example.com",)) == out


@pytest.mark.parametrize(
    ("tail", "escaped", "expected"),
    [
        ("", False, "?v=0123456789"),
        ("?", False, "?v=0123456789"),
        ("#x", False, "?v=0123456789#x"),
        ("?a=1", False, "?a=1&v=0123456789"),
        ("?a=1", True, "?a=1&amp;v=0123456789"),
        ("?a=1&v=old#f", False, "?a=1&v=0123456789#f"),
        ("?a=1&amp;v=old", True, "?a=1&amp;v=0123456789"),
        ("?v=2&b=3", False, "?v=0123456789&b=3"),
        ("?vv=1", False, "?vv=1&v=0123456789"),
        ("?a=1 ", False, "?a=1&v=0123456789 "),
    ],
)
def test_stamp_unit(tail, escaped, expected):
    assert versions.stamp(tail, "0123456789", escaped) == expected


def test_theme_css_links_media_with_stamp(tmp_path):
    root = make(tmp_path)
    (root / "theme" / "assets" / "bg.css").write_text(
        ".h { background: url(/media/cover.png); }\n"
        ".k { background: url('../media/cover.png?x=1#f'); }\n",
        encoding="utf-8",
    )
    build(root)
    dist = root / "dist"
    cover = sha10((root / "media" / "cover.png").read_bytes())
    [name] = [r for r in hashed(dist) if r.startswith("assets/bg.")]
    text = (dist / name).read_text(encoding="utf-8")
    assert f"url(/media/cover.png?v={cover})" in text
    assert f"url('../media/cover.png?x=1&v={cover}#f')" in text
    assert name == f"assets/bg.{sha10(text.encode())}.css"


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


def test_check_hardcoded_asset_inside_inline_script_has_own_message(tmp_path):
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            "</head>",
            '<script type="application/ld+json">{"logo": "/assets/logo.png"}</script>\n'
            '<link rel="icon" href="/assets/site.css">\n</head>',
        ),
        encoding="utf-8",
    )
    warnings = pipeline.check(root).collector.warnings
    script = [w for w in warnings if getattr(w.message, "key", "") == "theme_asset_in_script"]
    plain = [w for w in warnings if getattr(w.message, "key", "") == "theme_asset_hardcoded"]
    assert len(script) == 1 and len(plain) == 1
    assert script[0].line != plain[0].line
    text = str(script[0].message)
    assert "anyway" not in text and "data-" in text and "asset(" in text


# --- serve и просмотр ---------------------------------------------------------------


def test_dev_server_serves_hashed_names_and_stamped_media(tmp_path):
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
        src = re.search(r'src="(/media/cover\.png\?v=[0-9a-f]{10})"', page).group(1)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
        conn.request("GET", src)
        response = conn.getresponse()
        assert response.status == 200
        assert response.read() == (root / "media" / "cover.png").read_bytes()
    finally:
        server.shutdown()


def _serve_dist(dist: Path, handler_factory):
    import threading

    from heron.core import watch

    server = watch._Server(("127.0.0.1", 0), handler_factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_heron_serve_handler_ignores_media_query(tmp_path):
    """Просмотр `heron serve` отдаёт ресурс по адресу с меткой: параметр не читается."""
    import http.client

    from heron.core import watch

    root = make(tmp_path)
    dist = tmp_path / "preview"
    build(root, dist=dist)
    server = _serve_dist(dist, watch.handler_for(root, dist))
    try:
        page = (dist / "index.html").read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="(/(?:assets|media)/[^"]+)"', page):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
            conn.request("GET", ref.replace("&amp;", "&"))
            response = conn.getresponse()
            response.read()
            assert response.status == 200, ref
    finally:
        server.shutdown()


def test_plain_static_server_opens_every_versioned_reference(tmp_path):
    """Любой хостинг: `python -m http.server` над dist отдаёт все версии ссылок."""
    import http.client
    import subprocess
    import sys
    import time

    root = make(tmp_path)
    build(root)
    dist = root / "dist"
    with socket_port() as port:
        proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=dist,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    try:
        for _ in range(100):
            try:
                http.client.HTTPConnection("127.0.0.1", port, timeout=1).connect()
                break
            except OSError:
                time.sleep(0.05)
        page = (dist / "index.html").read_text(encoding="utf-8")
        refs = re.findall(r'(?:src|href)="(/(?:assets|media)/[^"]+)"', page)
        refs += [
            part.split()[0]
            for value in re.findall(r'srcset="([^"]+)"', page)
            for part in value.split(",")
            if part.strip().startswith("/")
        ]
        assert any("?v=" in ref for ref in refs) and any("/assets/" in ref for ref in refs)
        for ref in refs:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", ref.replace("&amp;", "&"))
            response = conn.getresponse()
            body = response.read()
            assert response.status == 200, ref
            plain = ref.split("?")[0].split("#")[0].lstrip("/")
            assert body == (dist / plain).read_bytes(), ref
    finally:
        proc.terminate()
        proc.wait(timeout=10)


class socket_port:
    """Свободный порт: занять и сразу отпустить."""

    def __enter__(self) -> int:
        import socket

        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        return self.sock.getsockname()[1]

    def __exit__(self, *exc) -> None:
        self.sock.close()


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
