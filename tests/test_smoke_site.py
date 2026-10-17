"""Дымовая проверка сайта ловит то, ради чего существует, — на настоящем nginx."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from heron.core import build as pipeline
from heron.scaffold import create
from tests.nginx_server import needs_nginx, serve

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smoke_site", ROOT / "scripts" / "smoke_site.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

PAGE = "---\ntitle: {t}\nh1: {t} page\ndescription: D\n{extra}---\n\nText.\n"


def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en", "ru"])
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["gone"] = ["/old-archive/"]
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (root / "content/en/about.md").write_text(
        PAGE.format(t="About", extra="redirect_from: [/about-us/, /старая/]\n"), encoding="utf-8"
    )
    (root / "content/ru/about.md").write_text(
        PAGE.format(t="О нас", extra="slug: o-nas\nredirect_from: [/ru/o-kompanii/]\n"),
        encoding="utf-8",
    )
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    return root / "dist"


def run(tmp_path: Path, dist: Path) -> tuple[int, smoke.Smoke]:
    with serve(dist, tmp_path / "nginx"):
        conf = (tmp_path / "nginx" / "nginx.conf").read_text(encoding="utf-8")
        port = int(conf.split("listen       127.0.0.1:")[1].split(";")[0])
        check = smoke.Smoke(f"http://127.0.0.1:{port}", dist)
        return check.run(), check


@needs_nginx
def test_green_on_a_correct_build(tmp_path):
    dist = site(tmp_path)
    code, check = run(tmp_path, dist)
    assert code == 0 and check.failed == 0
    assert smoke.Smoke("http://x", dist).languages() == ["ru"]


@needs_nginx
def test_catches_a_wrong_redirect_target(tmp_path):
    dist = site(tmp_path)
    redirects = dist / "redirects.map"
    redirects.write_text(
        redirects.read_text(encoding="utf-8").replace("/about/;", "/elsewhere/;", 1), "utf-8"
    )
    code, _ = run(tmp_path, dist)
    assert code == 1


@needs_nginx
def test_catches_a_redirect_chain(tmp_path):
    dist = site(tmp_path)
    conf = dist / ".heron-nginx.conf"
    text = conf.read_text(encoding="utf-8")
    # цель первого редиректа сама перенаправляет дальше
    text = text.replace(
        "    # 301 и 410: точные адреса, регистр важен\n",
        "    # 301 и 410: точные адреса, регистр важен\n"
        '    location = "/about/" { return 301 "/"; }\n',
    )
    conf.write_text(text, encoding="utf-8")
    code, _ = run(tmp_path, dist)
    assert code == 1


@needs_nginx
def test_catches_hidden_files_served_under_a_language(tmp_path):
    dist = site(tmp_path)
    (dist / "ru" / ".heron-smoke").write_text("secret", encoding="utf-8")
    conf = dist / ".heron-nginx.conf"
    conf.write_text(
        conf.read_text(encoding="utf-8").replace("        location ~ /\\. { return 404; }\n", ""),
        encoding="utf-8",
    )
    code, _ = run(tmp_path, dist)
    assert code == 1
