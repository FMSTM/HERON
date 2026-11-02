"""Сообщения редиректов и nginx.check на ключах texts/redirects.py: ru прежний, en без кириллицы."""

import re
import shutil
import subprocess
from types import SimpleNamespace

from heron.core.errors import Collector
from heron.messages import Msg
from heron.modules import nginx, redirects
from heron.texts import redirects as texts

CYR = re.compile("[а-яА-ЯёЁ]")


def _en_ok(item) -> str:
    for part in (item.message, getattr(item, "hint", None)):
        if part is None:
            continue
        assert isinstance(part, Msg)
        assert not CYR.search(part.text("en"))
    return item.message.text("en")


def _page(source, url, redirect_from=(), gone=()):
    meta = SimpleNamespace(redirect_from=list(redirect_from), gone=list(gone))
    return SimpleNamespace(source=source, url=url, meta=meta)


def _site(*pages):
    return SimpleNamespace(pages=list(pages), by_url={p.url: p for p in pages})


def test_keys_parity_and_en_clean():
    assert texts.TEXT["ru"].keys() == texts.TEXT["en"].keys()
    assert not any(CYR.search(v) for v in texts.TEXT["en"].values())
    assert not any("—" in v or "–" in v for v in texts.TEXT["en"].values())


def test_redirect_from_exists_and_chain():
    a = _page("a.md", "/a/", ["/b/"])
    b = _page("b.md", "/b/")
    c = _page("c.md", "/c/", ["/a/"])
    collector = Collector()
    redirects.collect(_site(a, b, c), collector)
    ens = [_en_ok(e) for e in collector.errors]
    assert any("matches the existing address /b/" in t for t in ens)
    ru = [e.message.text("ru") for e in collector.errors]
    assert "redirect_from '/b/' совпадает с существующим адресом /b/" in ru
    assert any(e.hint.text("ru") == "страница по этому адресу уже есть, редирект перекрыл бы её" for e in collector.errors)


def test_two_targets_and_chain():
    a = _page("a.md", "/a/", ["/old/"])
    b = _page("b.md", "/b/", ["/old/"])
    c = _page("c.md", "/c/", ["/a"])
    collector = Collector()
    redirects.collect(_site(a, b, c), collector)
    ru = [e.message.text("ru") for e in collector.errors]
    assert any("ведёт сразу в два места: /a/ и /b/" in t for t in ru)
    for e in collector.errors:
        _en_ok(e)


def test_gone_errors_and_warnings():
    page = _page("p.md", "/p/", gone=["/dead/"])
    cfg = SimpleNamespace(
        gone=["/p/", "/x/", "/x/", "/dead/\x01", "/media/*"],
        site=SimpleNamespace(languages=["ru", "en"], default_lang="ru"),
    )
    collector = Collector()
    redirects.collect(_site(page), collector, cfg)
    assert collector.errors and collector.warnings
    texts_en = [_en_ok(w) for w in collector.warnings + collector.errors]
    assert any("is deprecated" in t for t in texts_en)
    assert any("is listed twice" in t for t in texts_en)
    assert any("covers the existing page /p/" in t for t in texts_en)
    assert any("covers a reserved site path" in t for t in texts_en)
    ru = [e.message.text("ru") for e in collector.errors]
    assert any("gone '/p/' закрывает существующую страницу /p/" == t for t in ru)


def test_nginx_check_rejected(monkeypatch):
    done = SimpleNamespace(returncode=1, stderr="nginx: [emerg] bad directive in x:1\n", stdout="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: done)
    monkeypatch.setattr(shutil, "which", lambda *_: "/usr/sbin/nginx")
    collector = Collector()
    res = nginx.check("events {}", collector)
    assert res is not None
    assert res[0] is False
    (w,) = collector.warnings
    assert w.message.text("ru") == "nginx -t не принял собранный конфиг: nginx: [emerg] bad directive in x:1"
    assert w.message.text("en") == "nginx -t rejected the built config: nginx: [emerg] bad directive in x:1"
