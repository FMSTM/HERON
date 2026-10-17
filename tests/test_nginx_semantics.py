"""nginx отвечает так, как обещает модель адресов движка.

Адреса в движке различают регистр. Строковые ключи `map` nginx сравнивает
без учёта регистра — отсюда редирект страницы на саму себя, 410 на живой
странице и конфиг, который не стартует. Плюс скрытые файлы под `^~`.
Всё проверяется настоящим nginx: `nginx -t` и HTTP-ответами.
"""

from __future__ import annotations

import yaml

from heron.core import build as pipeline
from heron.modules import nginx
from heron.scaffold import create
from tests.nginx_server import needs_nginx, serve

PAGE = "---\ntitle: {t}\nh1: {t}\ndescription: D\n{extra}---\n\nText.\n"
LONG = "/" + "старая-страница-с-очень-длинным-адресом-" * 3 + "/"


def make(tmp_path, gone=None):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en", "ru"])
    if gone:
        conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
        conf["gone"] = gone
        (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), "utf-8")
    pages = {
        "en/page.md": PAGE.format(t="Page", extra="redirect_from: [/Page/]\n"),
        "en/gone.md": PAGE.format(t="Gone", extra=""),
        "en/first.md": PAGE.format(t="First", extra="redirect_from: [/A/]\n"),
        "en/second.md": PAGE.format(t="Second", extra=f"redirect_from: [/a/, {LONG}]\n"),
    }
    for rel, text in pages.items():
        (root / "content" / rel).write_text(text, encoding="utf-8")
    return root


def test_config_has_exact_locations_and_no_string_maps(tmp_path):
    root = make(tmp_path, gone=["/Gone/"])
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    conf = (root / "dist" / nginx.NAME).read_text(encoding="utf-8")
    assert 'location = "/Page/" { return 301 "/page/"; }' in conf
    assert 'location = "/Gone/" { return 410; }' in conf
    assert "map $uri" not in conf
    assert "map_hash" not in conf


@needs_nginx
def test_case_matters_in_301_and_410(tmp_path):
    root = make(tmp_path, gone=["/Gone/"])
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:  # serve сам делает nginx -t
        assert get("/Page/") == (301, "/page/")
        assert get("/page/")[0] == 200  # не редирект на самого себя
        assert get("/Gone/")[0] == 410
        assert get("/gone/")[0] == 200  # живая страница не закрыта
        assert get("/A/") == (301, "/first/")
        assert get("/a/") == (301, "/second/")
        assert get("/PAGE/")[0] == 404  # ни 301, ни 410: такого адреса нет
        assert get(LONG) == (301, "/second/")  # длинный кириллический — без map_hash


@needs_nginx
def test_hidden_files_are_404_everywhere_except_well_known(tmp_path):
    root = make(tmp_path)
    assert not pipeline.run(root).failed
    dist = root / "dist"
    hidden = [
        ".audit-secret",
        "ru/.audit-secret",
        "ru/page/.audit-secret",
        "media/.audit-secret",
        "assets/.audit-secret",
        "page/.audit-secret",
        "ru/.git/config",
    ]
    for rel in hidden:
        (dist / rel).parent.mkdir(parents=True, exist_ok=True)
        (dist / rel).write_text("secret", encoding="utf-8")
    (dist / ".well-known").mkdir()
    (dist / ".well-known" / "security.txt").write_text("Contact: x", encoding="utf-8")
    with serve(dist, tmp_path / "nginx") as get:
        for rel in hidden:
            assert get("/" + rel)[0] == 404, rel
        assert get("/" + nginx.NAME)[0] == 404
        assert get("/.well-known/security.txt")[0] == 200
        assert get("/ru/")[0] == 200


def test_gone_on_a_service_prefix_is_e022(tmp_path):
    root = make(tmp_path, gone=["/media/*"])
    result = pipeline.run(root)
    assert "E022" in [e.code for e in result.collector.errors]
