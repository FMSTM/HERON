"""Отдача 404, метка сборки и мягкие предупреждения о переводах.

Страница 404 нарисована темой, но её никто не увидит, если сервер отдаёт
свою. Проверяем выбор файла по языку адреса и то, что метка сборки
появляется только вне прода.
"""

from __future__ import annotations

from pathlib import Path

from heron.core import links, report, tree
from heron.core.environment import BuildEnv
from heron.core.errors import Collector
from heron.core.render import env as render_env
from heron.core.watch import not_found
from tests import sites


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    for rel in ("404.html", "ru/404/index.html", "en/404/index.html"):
        path = dist / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")
    return dist


def test_404_choosen_by_language_of_path(tmp_path):
    dist = _dist(tmp_path)
    assert not_found(dist, "/ru/нет-такой/").read_text(encoding="utf-8") == "ru/404/index.html"
    assert not_found(dist, "/en/nope/").read_text(encoding="utf-8") == "en/404/index.html"


def test_404_falls_back_to_root_page(tmp_path):
    dist = _dist(tmp_path)
    assert not_found(dist, "/нет-языка/").read_text(encoding="utf-8") == "404.html"
    assert not_found(dist, "/uk/nope/").read_text(encoding="utf-8") == "404.html"


def test_no_404_page_at_all(tmp_path):
    assert not_found(tmp_path / "dist", "/nope/") is None


def test_stamp_only_outside_prod(tmp_path):
    dev = BuildEnv.named("dev").stamped(tmp_path)
    prod = BuildEnv.named("prod").stamped(tmp_path)
    assert dev.stamp and not dev.is_prod
    assert prod.is_prod  # метку в теме прячет сама тема, но версия есть у обоих
    assert dev.version and dev.built_at


def test_boolean_key_in_strings_is_reported(tmp_path):
    theme_dir = tmp_path / "theme"
    (theme_dir / "i18n").mkdir(parents=True)
    (theme_dir / "i18n" / "uk.yaml").write_text('off: "Вимкнено"\nyes_word: "Так"\n', "utf-8")
    collector = Collector()
    strings = render_env.load_strings(theme_dir, "uk", collector)
    assert any(w.kind == "переводы" for w in collector.warnings)
    assert strings["yes_word"] == "Так"


def test_missing_translation_is_not_a_menu_typo(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "ru/index.md": sites.page("Главная"),
        "ru/bio.md": sites.page("Врач"),
    }
    content = sites.build(tmp_path, files)
    config = sites.config(nav={"main": ["bio"]})
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    kinds = {w.kind for w in collector.warnings}
    assert "нет перевода" in kinds
    assert "меню" not in kinds


def test_language_home_is_not_orphan(tmp_path):
    files = {"uk/index.md": sites.page("Головна"), "ru/index.md": sites.page("Главная")}
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    assert report.build(site, config, sites.theme()).orphans == []


def test_built_site_is_readable_by_any_server(tmp_path):
    """Собранное должно читаться чужим процессом: nginx работает не под root."""
    import os

    from heron.core import build as pipeline
    from heron.scaffold import create

    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(sites.page("Головна"), encoding="utf-8")
    closed = root / "static" / "closed"
    closed.mkdir(parents=True, exist_ok=True)
    (closed / "a.txt").write_text("текст", encoding="utf-8")
    os.chmod(closed, 0o700)

    pipeline.run(root)
    for path in (root / "dist").rglob("*"):
        mode = path.stat().st_mode & 0o777
        assert mode & 0o044, path
        if path.is_dir():
            assert mode & 0o011, path


def test_nginx_conf_follows_site_languages():
    """Основной язык живёт в корне, остальные — в своих папках."""
    from heron.modules import nginx

    conf = nginx.generate(sites.config())[nginx.NAME]
    assert "location ^~ /ru/ {" in conf
    assert "/uk/" not in conf  # основной язык, папки с таким именем нет
    assert "error_page 404 /404.html;" in conf
    assert conf.count("internal;") == 2


def test_nginx_conf_when_default_language_changes():
    from heron.modules import nginx

    config = sites.config(
        site={
            "domain": "example.com",
            "theme": "demo",
            "default_lang": "ru",
            "languages": ["uk", "ru"],
        }
    )
    conf = nginx.generate(config)[nginx.NAME]
    assert "location ^~ /uk/ {" in conf
    assert "/ru/" not in conf
