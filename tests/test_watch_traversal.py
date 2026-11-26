"""Просмотр `heron serve`: адрес с `..` не выходит за dist (аудит SEC-07).

`no_slash_route()` и `not_found()` не смотрят на диск за пределами dist - даже
проверкой «есть ли там файл»; query-строка в путь не попадает.
"""

from __future__ import annotations

from pathlib import Path

from heron.core.watch import no_slash_route, not_found


def _tree(tmp_path: Path) -> Path:
    dist = tmp_path / "site" / "dist"
    for rel in ("404.html", "en/404/index.html", "en/page/index.html"):
        path = dist / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")
    # рядом с dist - чужое: папка со страницей и своя «404»
    outside = tmp_path / "site" / "secret"
    (outside / "404").mkdir(parents=True)
    (outside / "index.html").write_text("secret", encoding="utf-8")
    (outside / "404" / "index.html").write_text("secret 404", encoding="utf-8")
    (tmp_path / "site" / "notes.txt").write_text("x", encoding="utf-8")
    return dist


def test_no_slash_route_does_not_look_outside_dist(tmp_path):
    dist = _tree(tmp_path)
    for route in ("/../secret", "/../secret/", "/en/../../secret", "/../notes.txt/"):
        assert no_slash_route(dist, route) == ("missing", route), route
    # внутри dist - как раньше
    assert no_slash_route(dist, "/en/page") == ("file", "/en/page/index.html")
    assert no_slash_route(dist, "/en/page/") == ("redirect", "/en/page")


def test_not_found_does_not_take_a_page_outside_dist(tmp_path):
    dist = _tree(tmp_path)
    page = not_found(dist, "/../secret/x")
    assert page == dist / "404.html"
    assert page.read_text(encoding="utf-8") == "404.html"


def test_not_found_ignores_the_query(tmp_path):
    dist = _tree(tmp_path)
    assert not_found(dist, "/en/nope/?a=../../secret").read_text(encoding="utf-8") == (
        "en/404/index.html"
    )
    assert not_found(dist, "/?x=/en").read_text(encoding="utf-8") == "404.html"


def test_no_slash_route_collapses_double_leading_slashes(tmp_path):
    dist = _tree(tmp_path)
    assert no_slash_route(dist, "//en/page/") == ("redirect", "/en/page")
    assert no_slash_route(dist, "///en/page") == ("file", "/en/page/index.html")
    assert no_slash_route(dist, "///") is None
