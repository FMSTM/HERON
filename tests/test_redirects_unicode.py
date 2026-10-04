"""Старые адреса с кириллицей: UTF-8 и percent-encoding — один адрес.

Спецификация: docs/spec/20-data-contract.md, раздел 2, «Старые адреса».
"""

from __future__ import annotations

import pytest
import yaml

from heron.core import build as pipeline
from heron.core import tree
from heron.core.urls import canonical_path
from heron.modules import redirects
from heron.scaffold import create
from tests import sites
from tests.nginx_server import needs_nginx, serve

CYR = "/новини/"
ENC_UP = "/%D0%BD%D0%BE%D0%B2%D0%B8%D0%BD%D0%B8/"
ENC_LOW = ENC_UP.lower()
# «й» двумя кодовыми точками: и + комбинирующая бреве
NFD = "/й/"
NFC = "/й/"
# слаг, обрезанный старой системой посреди буквы: последний байт без пары
CUT = "/%d0%bd%d0%be%d0/"


@pytest.mark.parametrize(
    ("written", "form", "ok"),
    [
        (CYR, CYR, True),
        (ENC_UP, CYR, True),
        (ENC_LOW, CYR, True),
        ("/новини", CYR, True),
        (NFD, NFC, True),
        ("/About", "/About/", True),
        ("/index.php", "/index.php", True),
        (CUT, "/%D0%BD%D0%BE%D0/", False),
    ],
)
def test_canonical_form(written, form, ok):
    assert canonical_path(written) == (form, ok)


def _collect(tmp_path, files, gone=()):
    content = sites.build(tmp_path, files)
    config = sites.config(gone=list(gone))
    site, collector = tree.scan(content, config)
    return redirects.collect(site, collector, config), collector


def test_both_forms_are_one_address_for_e009(tmp_path):
    _, collector = _collect(
        tmp_path,
        {
            "uk/index.md": sites.page("Г"),
            "uk/a.md": sites.page("A", redirect_from=[CYR]),
            "uk/b.md": sites.page("B", redirect_from=[ENC_LOW]),
        },
    )
    assert [e.code for e in collector.errors] == ["E009"]
    assert "два места" in str(collector.errors[0])


def test_encoded_old_address_of_existing_page_is_e009(tmp_path):
    # /%62/ — это /b/, а страница /b/ существует
    _, collector = _collect(
        tmp_path,
        {
            "uk/index.md": sites.page("Г"),
            "uk/b.md": sites.page("B"),
            "uk/c.md": sites.page("C", redirect_from=["/%62"]),
        },
    )
    assert [e.code for e in collector.errors] == ["E009"]
    assert "/b/" in str(collector.errors[0])


def test_gone_and_redirect_meet_in_canonical_form(tmp_path):
    _, collector = _collect(
        tmp_path,
        {"uk/index.md": sites.page("Г"), "uk/a.md": sites.page("A", redirect_from=[CYR])},
        gone=[ENC_UP],
    )
    assert [e.code for e in collector.errors] == ["E022"]


def test_map_file_holds_decoded_form(tmp_path):
    plan, collector = _collect(
        tmp_path,
        {"uk/index.md": sites.page("Г"), "uk/a.md": sites.page("A", redirect_from=[ENC_UP])},
    )
    assert not collector.failed
    assert redirects.files(plan)["redirects.map"] == f"{CYR}  /a/;\n"


def _site(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["gone"] = ["/архів/*", "/%D1%82%D0%B5%D0%B3/", "/%d1%81%d1%82%d0/"]
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), encoding="utf-8")
    page = (
        "---\ntitle: Новини\nh1: Новини\ndescription: Опис\n"
        f"redirect_from: ['{ENC_UP}', '{NFD}', '{CUT}', '/пробел%20тут/']\n---\n\nТекст.\n"
    )
    for rel, text in {
        "uk/index.md": "---\ntitle: Г\nh1: Головна\ndescription: О\n---\n\nТекст.\n",
        "uk/news.md": page,
    }.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@needs_nginx
def test_nginx_redirects_every_spelling(tmp_path):
    root = _site(tmp_path)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    with serve(root / "dist", tmp_path / "nginx") as get:
        for path in (ENC_UP, ENC_LOW, CYR, "/новини", ENC_UP.rstrip("/")):
            assert get(path) == (301, "/news/"), path
        # «й» одной точкой — так шлют браузеры, хотя в файле две
        assert get("/%D0%B9/") == (301, "/news/")
        assert get(NFC) == (301, "/news/")
        # обрезанный слаг: оба регистра, со слешем и без, с параметрами
        for path in (CUT, CUT.upper(), CUT.rstrip("/"), CUT + "?x=1"):
            assert get(path) == (301, "/news/"), path
        assert get("/пробел%20тут/") == (301, "/news/")
        # 410 в любой форме
        assert get("/%D0%B0%D1%80%D1%85%D1%96%D0%B2/2019/")[0] == 410
        assert get("/архів/x/")[0] == 410
        assert get("/тег/")[0] == 410
        assert get("/тег")[0] == 410
        assert get("/%D1%81%D1%82%D0/")[0] == 410
        assert get("/news/")[0] == 200
