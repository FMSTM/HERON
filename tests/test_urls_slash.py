"""Адреса для переезда: подчёркивание в сегменте и `urls.trailing_slash: never` (20 §2).

Сайт, который переезжает с Nuxt, Next или WordPress, сохраняет адреса как
были: `/ru/cases/landing_page`, без слеша на конце, без 301 на каждой
странице. Поведение сервера проверяется настоящим nginx (`tests/nginx_server`).
"""

from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.contracts.site import load_site
from heron.core import build as pipeline
from heron.core import links, report, tree, urls, versions
from heron.core.errors import Collector, HeronError
from heron.edit import entity as ops
from heron.modules import nginx
from heron.scaffold import create
from heron.setup import apply, current_answers, load_answers
from heron.setup.answers import Answers
from tests import sites
from tests.nginx_server import needs_nginx, serve

PAGE = "---\ntitle: {t}\nh1: {t}\ndescription: D\n{extra}---\n\n{body}\n"


def _write(root: Path, rel: str, title: str, extra: str = "", body: str = "Text.") -> None:
    path = root / "content" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGE.format(t=title, extra=extra, body=body), encoding="utf-8")


def _site(tmp_path: Path, mode: str | None, gone=None) -> Path:
    """Сайт на двух языках: раздел `cases`, страница с `_` в имени, старые адреса."""
    root = tmp_path / "site"
    create(root, name="demo", languages=["en", "ru"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    if mode is not None:
        conf["urls"] = {"trailing_slash": mode}
    conf["gone"] = gone or ["/old_gone/", "/wp/*"]
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    for lang in ("en", "ru"):
        _write(root, f"{lang}/cases/_index.md", "Cases")
        extra = "redirect_from: [/old_case/, /legacy]\n" if lang == "en" else ""
        body = "See [the case](/cases/landing_page/) and ![a](media/cover.png)."
        _write(root, f"{lang}/cases/landing_page.md", "Landing", extra, body)
    return root


def _built(root: Path):
    result = pipeline.run(root)
    assert not result.failed, [e.render("en") for e in result.collector.errors]
    return result


def _head(port: int, path: str) -> dict[str, list[str]]:
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


# --- подчёркивание в сегменте адреса --------------------------------------------------


def test_segment_rule_allows_underscore_and_still_rejects_the_rest():
    for good in ("landing_page", "a_b-c", "0_x", "a-", "a__b"):
        assert tree.SLUG.match(good), good
    # первый знак - буква или цифра; $, пробел, точка, кавычки, скобки, ; nginx
    # прочёл бы как переменную или конец директивы; заглавные - другой адрес
    for bad in ("_draft", "-a", "a$b", "a b", "a.b", "a;b", "a{b}", "a'b", 'a"b', "A", "aB", "a/b"):
        assert not tree.SLUG.match(bad), bad


@pytest.mark.parametrize("name", ["a$b.md", "a b.md", "a;b.md", "a{b}.md", "Upper.md", "-a.md"])
def test_dangerous_characters_in_url_stay_e005(tmp_path, name):
    content = sites.build(tmp_path, {"uk/index.md": sites.page("Г"), f"uk/{name}": sites.page("X")})
    _, collector = tree.scan(content, sites.config(), collector=Collector())
    assert [e.code for e in collector.errors] == ["E005"], name


def test_underscore_in_file_folder_slug_and_relations(tmp_path):
    files = {
        "uk/index.md": sites.page("Г"),
        "uk/cases_old/_index.md": sites.page("Кейси"),
        "uk/cases_old/landing_page.md": sites.page("Ф", related=["my_page"]),
        "uk/page.md": sites.page("С", slug="my_slug"),
        "uk/my_page.md": sites.page("М", related=["landing_page"]),
        "uk/_draft.md": sites.page("Чернетка"),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    assert not collector.errors, [e.render("en") for e in collector.errors]
    found = {page.url for page in site.pages}
    assert {"/cases_old/", "/cases_old/landing_page/", "/my_slug/", "/my_page/"} <= found
    assert not any("draft" in url for url in found)  # `_draft.md` страницей не бывает
    links.resolve(site, config, sites.theme(links=[{"field": "related"}]), collector)
    assert not collector.errors
    fit = site.page("cases_old/landing_page", "uk")
    assert [p.url for p in fit.related["related"]] == ["/my_page/"]


def test_underscore_in_folder_name_with_leading_underscore_is_not_a_page(tmp_path):
    files = {"uk/index.md": sites.page("Г"), "uk/_drafts/x.md": sites.page("X")}
    site, collector = tree.scan(sites.build(tmp_path, files), sites.config())
    assert "/_drafts/x/" not in site.by_url and "E005" in [e.code for e in collector.errors]


def test_keys_with_underscore_in_editor_and_frontmatter():
    assert ops.norm_key("/cases/landing_page/") == "cases/landing_page"
    with pytest.raises(HeronError) as caught:
        ops.norm_key("cases/_draft")
    assert caught.value.code == "E005"
    from heron.contracts.frontmatter import PageMeta

    meta = PageMeta.model_validate(
        {"title": "T", "h1": "H", "description": "D", "slug": "old_slug"}
        | {"redirect_from": ["/ru/cases/landing_page"]}
    )
    assert meta.slug == "old_slug"


@needs_nginx
def test_underscore_page_and_folder_get_200_on_real_nginx(tmp_path):
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["gone"] = ["/old_gone/"]
    (root / "site.yaml").write_text(yaml.safe_dump(conf), "utf-8")
    _write(root, "en/cases_old/_index.md", "Cases")
    _write(root, "en/cases_old/landing_page.md", "Fit", "redirect_from: [/old_case/]\n")
    _write(root, "en/page.md", "Slug", "slug: my_slug\n")
    _built(root)
    conf_text = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    assert 'location = "/old_case/" { return 301 "/cases_old/landing_page/"; }' in conf_text
    with serve(root / "dist", tmp_path / "nginx") as get:  # serve сам делает nginx -t
        assert get("/cases_old/landing_page/")[0] == 200
        assert get("/cases_old/")[0] == 200
        assert get("/my_slug/")[0] == 200
        assert get("/old_case/") == (301, "/cases_old/landing_page/")
        assert get("/old_gone/")[0] == 410


def test_new_key_with_underscore_gets_a_soft_hint(tmp_path):
    root = tmp_path / "s"
    create(root, name="Demo", languages=["en"])
    runner = CliRunner()
    out = runner.invoke(main, ["page", "add", "landing_page", str(root), "-y", "--notes", "en"])
    assert out.exit_code == 0, out.output
    assert "hyphen is better for new addresses" in out.output
    assert (root / "content" / "en" / "landing_page.md").is_file()
    out = runner.invoke(main, ["category", "add", "old_cases", str(root), "-y", "--notes", "en"])
    assert out.exit_code == 0, out.output
    assert "hyphen is better" in out.output
    # имя без подчёркивания и уже существующая страница - без подсказки
    out = runner.invoke(main, ["page", "add", "about-us", str(root), "-y", "--notes", "en"])
    assert out.exit_code == 0 and "hyphen is better" not in out.output
    out = runner.invoke(main, ["page", "add", "landing_page", str(root), "-y", "--notes", "en"])
    assert out.exit_code == 0 and "hyphen is better" not in out.output


def test_studio_accepts_underscore_names():
    script = (Path(__file__).parents[1] / "heron" / "studio" / "studio.js").read_text("utf-8")
    assert "const NAME = /^[a-z0-9][a-z0-9_-]*$/;" in script
    assert script.count("d_underscore:") == 2  # ru и en


# --- urls.trailing_slash ------------------------------------------------------------


def test_trailing_slash_key_is_validated(tmp_path):
    path = tmp_path / "site.yaml"
    head = 'heron: ">=0.1"\nsite: {name: x, domain: example.com, languages: [en], theme: main}\n'
    path.write_text(head + "urls:\n  trailing_slash: never\n", encoding="utf-8")
    assert load_site(path).urls.slash is False
    path.write_text(head, encoding="utf-8")
    assert load_site(path).urls.slash is True
    for bad in ("urls:\n  trailing_slash: sometimes\n", "urls:\n  trailing_slsh: never\n"):
        path.write_text(head + bad, encoding="utf-8")
        with pytest.raises(HeronError) as caught:
            load_site(path)
        assert caught.value.code == "E011"


def test_url_helpers():
    assert urls.page_url("ru", "en", ["cases", "x"], slash=False) == "/ru/cases/x"
    assert urls.page_url("ru", "en", [], slash=False) == "/ru"
    assert urls.page_url("en", "en", [], slash=False) == "/"
    assert urls.page_url("ru", "en", ["x"]) == "/ru/x/"
    assert urls.shape("/x/", False) == "/x" and urls.shape("/x", True) == "/x/"
    assert urls.relative("pic.jpg") and urls.relative("./x/") and urls.relative("../y")
    for fine in ("/media/x.png", "https://a.b/", "//cdn.x/a.js", "#top", "?a=1", "mailto:a@b.c"):
        assert not urls.relative(fine), fine
    assert not urls.relative("tel:+100")


def _absolute_and_rooted(text: str, domain: str) -> list[str]:
    found = re.findall(rf"https://{re.escape(domain)}(/[^\"'\s<>)]*)", text)
    found += re.findall(r'(?:href|src)="(/[^"]*)"', text)
    return found


def _page_like(path: str) -> bool:
    """Адрес страницы, а не файла: последний сегмент без точки."""
    last = path.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    return "." not in last


def test_never_writes_no_slash_everywhere(tmp_path):
    root = _site(tmp_path, "never")
    result = _built(root)
    dist = root / "dist"
    domain = result.config.site.domain
    page = (dist / "ru" / "cases" / "landing_page" / "index.html").read_text("utf-8")
    base = f"https://{domain}"
    assert f'<link rel="canonical" href="{base}/ru/cases/landing_page">' in page
    assert f'<meta property="og:url" content="{base}/ru/cases/landing_page">' in page
    assert f'hreflang="en" href="{base}/cases/landing_page"' in page
    assert f'hreflang="x-default" href="{base}/cases/landing_page"' in page
    assert 'href="/ru/cases/landing_page"' in page  # ссылка из markdown - по-русски, без слеша
    assert 'class="logo" href="/ru"' in page
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1)
    assert f'"{base}/ru/cases/landing_page"' in ld and f'"{base}/ru"' in ld
    # ни одного адреса страницы со слешем на конце, кроме корня сайта
    texts = [p for p in dist.rglob("*") if p.is_file() and p.suffix in (".html", ".xml", ".txt")]
    texts = [p for p in texts if "_heron" not in p.parts]
    for path in texts:
        for found in _absolute_and_rooted(path.read_text("utf-8"), domain):
            clean = found.split("?", 1)[0].split("#", 1)[0]
            if clean != "/" and _page_like(clean):
                assert not clean.endswith("/"), (path.relative_to(dist).as_posix(), found)
    sitemap = (dist / "sitemap-ru.xml").read_text("utf-8")
    assert f"<loc>{base}/ru/cases/landing_page</loc>" in sitemap
    assert f"<loc>{base}/ru</loc>" in sitemap
    assert "/cases/landing_page" in (dist / "redirects.map").read_text("utf-8")
    assert "/old_case/  /cases/landing_page;" in (dist / "redirects.map").read_text("utf-8")
    site = result.site
    assert site.page("/", "ru").url == "/ru" and site.page("/", "en").url == "/"
    assert site.page("404", "ru").url == "/ru/404"
    assert [p.url for p in site.page("cases/landing_page", "ru").breadcrumbs] == [
        "/ru",
        "/ru/cases",
    ]
    # служебная справка темы и 404 - там же, где всегда
    assert (dist / "ru" / "404" / "index.html").is_file() and (dist / "404.html").is_file()
    # копии с хешем и метки на месте, адреса страниц не тронуты
    assert re.search(r'href="/assets/site\.[0-9a-f]{10}\.css"', page)
    assert re.search(r'src="/media/cover\.png\?v=[0-9a-f]{10}"', page)


def test_always_is_unchanged(tmp_path):
    root = _site(tmp_path, None)
    result = _built(root)
    domain = result.config.site.domain
    page = (root / "dist" / "ru" / "cases" / "landing_page" / "index.html").read_text("utf-8")
    assert f'<link rel="canonical" href="https://{domain}/ru/cases/landing_page/">' in page
    assert 'class="logo" href="/ru/"' in page
    assert result.site.page("/", "ru").url == "/ru/"
    conf = (root / "dist" / nginx.NAME).read_text("utf-8")
    assert "try_files $uri $uri/ =404;" in conf and "$uri/index.html" not in conf
    assert "location = /ru {" not in conf and "rewrite" not in conf


def test_versions_rewriter_ignores_no_slash_page_addresses():
    html = (
        '<link rel="prefetch" href="/ru/cases/x"><link rel="preload" href="/media">'
        '<img src="/media/a.png"><a href="/assets/x.css">x</a>'
    )
    out = versions.rewrite_html(html, lambda rel: "0123456789" if rel == "media/a.png" else None)
    assert out == html.replace("/media/a.png", "/media/a.png?v=0123456789")


def test_never_nginx_config_text():
    from heron.contracts.site import SiteConfig

    config = SiteConfig.model_validate(
        {
            "heron": ">=0.1",
            "site": {
                "name": "x",
                "domain": "example.com",
                "languages": ["en", "ru"],
                "theme": "main",
            },
            "urls": {"trailing_slash": "never"},
        }
    )
    conf = nginx.generate(config)[nginx.NAME]
    assert "try_files $uri $uri/index.html =404;" in conf
    assert "try_files $uri $uri/ =404;" not in conf  # `$uri/` - это 301 nginx на /x/
    assert "location = /ru {" in conf and "location ^~ /ru/ {" in conf
    assert conf.count("rewrite ^(.+)/$ $1 permanent;") == 2
    assert "absolute_redirect off;" in conf
    assert 'location ~ "\\.[0-9a-f]{10}\\.[A-Za-z0-9]+$" {' in conf


@needs_nginx
def test_never_on_real_nginx(tmp_path):
    root = _site(tmp_path, "never")
    _built(root)
    dist = root / "dist"
    css = re.search(
        r'href="(/assets/site\.[0-9a-f]{10}\.css)"', (dist / "index.html").read_text("utf-8")
    ).group(1)
    landing = (dist / "cases" / "landing_page" / "index.html").read_text("utf-8")
    stamped = re.search(r'src="(/media/cover\.png\?v=[0-9a-f]{10})"', landing).group(1)
    work = tmp_path / "nginx"
    with serve(dist, work) as get:
        assert get("/")[0] == 200
        assert get("/ru")[0] == 200
        assert get("/ru/") == (301, "/ru")
        assert get("/cases/landing_page")[0] == 200
        assert get("/ru/cases/landing_page")[0] == 200
        assert "Landing" in get.body
        assert get("/ru/cases")[0] == 200
        assert get("/ru/cases/landing_page/") == (301, "/ru/cases/landing_page")
        assert get("/cases/landing_page/?utm=1&x=2") == (
            301,
            "/cases/landing_page?utm=1&x=2",
        )
        assert get("/cases/") == (301, "/cases")
        # старые адреса: обе формы - 301 сразу на адрес без слеша
        for old in ("/old_case/", "/old_case", "/legacy", "/legacy/"):
            assert get(old) == (301, "/cases/landing_page"), old
        for old in ("/old_gone/", "/old_gone", "/wp/x", "/wp/x/"):
            assert get(old)[0] == 410, old
        # 404 на языке адреса
        status = get("/ru/nope")
        assert status[0] == 404
        assert get.body == (dist / "ru" / "404" / "index.html").read_text("utf-8")
        assert get("/nope")[0] == 404
        assert get.body == (dist / "404.html").read_text("utf-8")
        assert get("/ru/.git/config")[0] == 404 and get("/.secret")[0] == 404
        # служебные адреса и файлы - как всегда
        assert get("/sitemap.xml")[0] == 200 and get("/robots.txt")[0] == 200
        assert get("/media/cover.png")[0] == 200
        assert get(stamped)[0] == 200
        # папка ресурсов и темы без страницы - 404 без 301 (heron serve повторяет)
        for path in ("/assets/", "/media/"):
            assert get(path)[0] in (403, 404), path
        port = int(re.search(r"listen\s+127\.0\.0\.1:(\d+)", (work / "nginx.conf").read_text())[1])
        for path in (css, stamped):
            got = _head(port, path)
            assert got["cache-control"] == ["public, max-age=31536000, immutable"], path


@needs_nginx
def test_always_on_real_nginx_is_unchanged(tmp_path):
    root = _site(tmp_path, None)
    _built(root)
    with serve(root / "dist", tmp_path / "nginx") as get:
        assert get("/ru/")[0] == 200
        assert get("/ru") == (301, "/ru/")
        assert get("/cases/landing_page/")[0] == 200
        assert get("/cases/landing_page") == (301, "/cases/landing_page/")
        assert get("/old_case") == (301, "/cases/landing_page/")
        assert get("/old_gone")[0] == 410


# --- относительные ссылки -----------------------------------------------------------


def _relative_site(tmp_path, mode):
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    if mode:
        path = root / "site.yaml"
        path.write_text(
            path.read_text("utf-8") + f"\nurls:\n  trailing_slash: {mode}\n", encoding="utf-8"
        )
    body = (
        "Fine: [a](/x), [b](#top), [c](?q=1), [d](mailto:a@b.c), [e](https://x.org/a),\n"
        "![f](media/cover.png), ![g](./media/cover.png).\n\n"
        "Bad: [h](pic.jpg) and [i](../y/).\n"
    )
    _write(root, "en/x.md", "X", body=body)
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text("utf-8").replace("<body", '<link rel="icon" href="favicon.ico">\n<body', 1),
        encoding="utf-8",
    )
    return root


def _e046(result) -> list[tuple[str, int | None, str]]:
    return [
        (str(e.path), e.line, e.render("en")) for e in result.collector.errors if e.code == "E046"
    ]


def test_relative_links_are_e046_under_never(tmp_path):
    root = _relative_site(tmp_path, "never")
    for result in (pipeline.check(root), pipeline.run(root)):
        found = _e046(result)
        assert [(p, line) for p, line, _ in found if p == "en/x.md"] == [("en/x.md", 10)] * 2
        texts = " ".join(text for _, _, text in found)
        assert "pic.jpg" in texts and "../y/" in texts and "favicon.ico" in texts
        assert "/media/" in texts  # как поправить
        assert any(p == "theme/base.html" for p, _, _ in found)
        assert result.failed
        assert not [t for _, _, t in found if "media/cover.png" in t.split(" - ")[0]]


def test_relative_css_urls_are_e046_and_scripts_are_skipped(tmp_path):
    """url() в style и <style> - тоже адреса; содержимое <script> - код, не ссылки."""
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["urls"] = {"trailing_slash": "never"}
    conf.setdefault("build", {})["allow_raw_html"] = True
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    body = (
        'Raw: <span style="background:url(bg.png)">x</span>\n\n'
        "<style>.q{background:url('img/q.png')} .r{background:url(/media/ok.png)}</style>\n"
    )
    _write(root, "en/x.md", "X", body=body)
    base = root / "theme" / "base.html"
    base.write_text(
        base.read_text("utf-8").replace(
            "<body",
            '<div style="background:url(&quot;t-bg.png&quot;)"></div>\n'
            "<style>@import 't.css'; .z{background:url(data:image/png;base64,AA)}</style>\n"
            '<script>/* el.src = "loader.gif" */ const a = "<img src=x.gif>";</script>\n<body',
            1,
        ),
        encoding="utf-8",
    )
    for result in (pipeline.check(root), pipeline.run(root)):
        found = _e046(result)
        texts = " ".join(text for _, _, text in found)
        for bad in ("bg.png", "img/q.png", "t-bg.png", "t.css"):
            assert bad in texts, (bad, found)
        for fine in ("loader.gif", "x.gif", "data:image", "/media/ok.png"):
            assert fine not in texts, (fine, found)
        assert {p for p, _, _ in found} == {"en/x.md", "theme/base.html"}


def test_attr_urls_unit():
    html = (
        '<a href="a.html"><i style="background:url(b.png)"></i>'
        "<style>.x{background:url('c.png')}</style>"
        '<script>var s = "<img src=d.png>"; // url(e.png)\n</script><img src="f.png">'
    )
    assert [v for _, v in urls.attr_urls(html)] == ["a.html", "b.png", "c.png", "f.png"]


def test_relative_links_are_fine_under_always(tmp_path):
    root = _relative_site(tmp_path, None)
    assert not _e046(pipeline.check(root))
    assert not _e046(pipeline.run(root))


# --- check --old-urls -----------------------------------------------------------------


def test_old_urls_without_slash_match_pages(tmp_path):
    root = _site(tmp_path, "never")
    result = pipeline.check(root)
    listed = [
        "https://example.com/ru/cases/landing_page",
        "/cases/landing_page",
        "/ru",
        "/legacy",
        "/old_gone",
        "/ru/cases/landin_page",
    ]
    lost, _ = report.old_urls(listed, result.site, result.config)
    assert len(lost) == 1
    text = lost[0].message.text("en")
    assert "/ru/cases/landin_page" in text and "301 to /ru/cases/landing_page:" in text
    old = tmp_path / "old.txt"
    old.write_text("\n".join(listed) + "\n", encoding="utf-8")
    out = CliRunner().invoke(main, ["check", str(root), "--old-urls", str(old), "--notes", "en"])
    assert "landin_page" in out.output
    assert out.output.count("leads nowhere") == 1


# --- конфигуратор и просмотр --------------------------------------------------------


def test_setup_answers_round_trip(tmp_path):
    root = tmp_path / "s"
    create(root, name="Example", languages=["en"])
    path = root / "site.yaml"
    apply(root, load_answers(current_answers(root)))
    assert "urls" not in yaml.safe_load(path.read_text("utf-8"))  # умолчание не пишется
    path.write_text(path.read_text("utf-8") + "\n# адреса старого сайта\n", encoding="utf-8")
    data = yaml.safe_load(current_answers(root))
    assert data["urls"] == {"trailing_slash": "always"}
    data["urls"]["trailing_slash"] = "never"
    apply(root, load_answers(yaml.safe_dump(data)))
    text = path.read_text("utf-8")
    assert yaml.safe_load(text)["urls"] == {"trailing_slash": "never"}
    assert "# адреса старого сайта" in text
    assert load_site(path).urls.slash is False
    dumped = current_answers(root)
    assert yaml.safe_load(dumped)["urls"]["trailing_slash"] == "never"
    assert apply(root, load_answers(dumped)).written == []
    with pytest.raises(ValueError, match="urls.trailing_slash"):
        Answers.model_validate({"urls": {"trailing_slash": "maybe"}})
    runner = CliRunner()
    answers = tmp_path / "answers.yaml"
    data["urls"]["trailing_slash"] = "always"
    answers.write_text(yaml.safe_dump(data), encoding="utf-8")
    out = runner.invoke(main, ["setup", str(root), "--answers", str(answers)])
    assert out.exit_code == 0, out.output
    assert yaml.safe_load(path.read_text("utf-8"))["urls"] == {"trailing_slash": "always"}
    assert yaml.safe_load(runner.invoke(main, ["setup", str(root), "--dump"]).output)["urls"] == {
        "trailing_slash": "always"
    }


def test_setup_page_has_the_field():
    page = (Path(__file__).parents[1] / "heron" / "setup" / "page.js").read_text("utf-8")
    assert '"urls.trailing_slash"' in page
    for key in ("urls_t", "urls_about", "urls_always_s", "urls_never_s"):
        assert page.count(f"{key}:") == 2, key  # ru и en
    assert "E046" in page


def test_preview_routes_follow_the_mode(tmp_path):
    from heron.core.watch import no_slash_route, trailing_slash

    root = _site(tmp_path, "never")
    _built(root)
    dist = root / "dist"
    assert trailing_slash(root) is False
    assert no_slash_route(dist, "/ru/cases/landing_page/") == (
        "redirect",
        "/ru/cases/landing_page",
    )
    assert no_slash_route(dist, "/ru/") == ("redirect", "/ru")
    assert no_slash_route(dist, "/ru") == ("file", "/ru/index.html")
    assert no_slash_route(dist, "/ru/cases/landing_page") == (
        "file",
        "/ru/cases/landing_page/index.html",
    )
    assert no_slash_route(dist, "/") is None
    assert no_slash_route(dist, "/sitemap.xml") is None
    # папка без страницы - 404, а не 301 туда-обратно
    (dist / "media" / "demo").mkdir(parents=True, exist_ok=True)
    (dist / "media" / "demo" / "x.txt").write_text("x", encoding="utf-8")
    assert no_slash_route(dist, "/assets/") == ("missing", "/assets/")
    assert no_slash_route(dist, "/assets") == ("missing", "/assets")
    assert no_slash_route(dist, "/media/demo/") == ("missing", "/media/demo/")
    assert no_slash_route(dist, "/media/demo") == ("missing", "/media/demo")
    assert no_slash_route(dist, "/media/demo/x.txt/") == ("missing", "/media/demo/x.txt/")
    assert no_slash_route(dist, "/ru/nope/") == ("missing", "/ru/nope/")
    assert no_slash_route(dist, "/sitemap.xml/") == ("redirect", "/sitemap.xml")
    path = root / "site.yaml"
    path.write_text(path.read_text("utf-8").replace("never", "always"), encoding="utf-8")
    assert trailing_slash(root) is True


def test_serve_answers_like_nginx(tmp_path):
    """`heron serve`: адрес без слеша открывается, со слешем - 301, как на проде."""
    import http.client
    import threading

    from heron.core import watch

    root = _site(tmp_path, "never")
    _built(root)
    dist = root / "dist"
    server = watch._Server(("127.0.0.1", 0), watch.handler_for(root, dist))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def get(path: str) -> tuple[int, str]:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        response.read()
        conn.close()
        return response.status, response.getheader("Location") or ""

    try:
        assert get("/ru")[0] == 200
        assert get("/ru/") == (301, "/ru")
        assert get("/ru/cases/landing_page")[0] == 200
        assert get("/ru/cases/landing_page/?a=1") == (301, "/ru/cases/landing_page?a=1")
        assert get("/")[0] == 200 and get("/sitemap.xml")[0] == 200
        assert get("/ru/nope")[0] == 404
        # папка без страницы: 404 сразу, без 301 - ни своего, ни на папку (петля)
        (dist / "media" / "demo").mkdir(parents=True, exist_ok=True)
        (dist / "media" / "demo" / "x.txt").write_text("x", encoding="utf-8")
        for path in ("/assets/", "/assets", "/media/demo/", "/media/demo", "/media/", "/ru/nope/"):
            assert get(path) == (404, ""), path
        assert get("/media/demo/x.txt")[0] == 200
        path = root / "site.yaml"
        path.write_text(path.read_text("utf-8").replace("never", "always"), encoding="utf-8")
        assert get("/ru")[0] == 301  # обычный каталог без слеша - как раньше
    finally:
        server.shutdown()
        server.server_close()


def test_llms_full_links_follow_mode_and_language(tmp_path):
    """llms-full: ссылки текста - адресом страницы на языке файла и в форме режима."""
    root = _site(tmp_path, "never")
    for lang in ("en", "ru"):
        body = (
            "See [the case](/cases/landing_page/#top), [ref][r] and "
            "[home](/?a=1), `[code](/cases/)`, [file](/media/cover.png), [nope](/nope/).\n\n"
            "```\n[fenced](/cases/)\n```\n\n[r]: /cases/\n"
        )
        _write(root, f"{lang}/cases/landing_page.md", "Landing", "", body)
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf.setdefault("seo", {})["llms_txt"] = True
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    _built(root)
    dist = root / "dist"
    en = (dist / "llms-full-en.txt").read_text("utf-8")
    ru = (dist / "llms-full-ru.txt").read_text("utf-8")
    assert "[the case](/cases/landing_page#top)" in en
    assert "[the case](/ru/cases/landing_page#top)" in ru
    assert "[r]: /cases\n" in en and "[r]: /ru/cases\n" in ru
    assert "[home](/?a=1)" in en and "[home](/ru?a=1)" in ru
    for text in (en, ru):
        # код, файлы и ссылки в никуда - как написаны
        assert "`[code](/cases/)`" in text and "[fenced](/cases/)" in text
        assert "[file](/media/cover.png)" in text and "[nope](/nope/)" in text
        assert "/cases/landing_page/" not in text


def test_llms_full_links_always_mode_keep_slash(tmp_path):
    root = _site(tmp_path, None)
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf.setdefault("seo", {})["llms_txt"] = True
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    _built(root)
    ru = (root / "dist" / "llms-full-ru.txt").read_text("utf-8")
    assert "[the case](/ru/cases/landing_page/)" in ru


def test_e009_shows_the_address_in_the_mode_form(tmp_path):
    root = _site(tmp_path, "never")
    _write(root, "en/other.md", "Other", "redirect_from: [/cases/]\n")
    result = pipeline.run(root)
    [error] = [e for e in result.collector.errors if e.code == "E009"]
    text = error.render("en")
    assert "existing address /cases" in text and "existing address /cases/" not in text
