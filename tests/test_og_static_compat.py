"""Картинка соцсетей сайта 0.1 в static/ (20 §5, совместимость).

Сайты 0.1 клали картинку соцсетей по умолчанию в `static/og/…` и писали в
site.yaml `seo.og_default_image: og/…` (и `og_default_image_<язык>`): static/
копируется в корень сборки, и og:image выходил `https://<домен>/og/…`. С 0.2
картинки берутся только из media/, и такой сайт падал с E024 - замена образа
движка ломала сайт, который никто не трогал.

Правило: путь вне media/ у этих полей (и у `og_image` страницы), файла которого
в media/ нет, ищется в static/. Нашёлся - принимается: адрес - сам файл из
static/, без нарезок и метки `?v=`; в сборку его везёт копирование static/.
Отчёт check и сборки пишет сведение (не предупреждение, `--strict` его не
считает) с точным путём в media/. Нет файла ни там, ни там, путь уходит из
сайта (`..`) или ссылкой наружу - прежний E024.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from click.testing import CliRunner
from PIL import Image

from heron.cli import main
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.core.errors import HeronError
from heron.scaffold import create

DOMAIN = "s.example"


def run(*args):
    return CliRunner().invoke(main, [str(a) for a in args])


def _png(path: Path, width: int = 1200, height: int = 630) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (40, 80, 120)).save(path)


def _seo(root: Path, **values) -> None:
    """Поменять ключи seo в site.yaml строкой, как их пишет человек."""
    path = root / "site.yaml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^  og_default_image:.*\n", "", text)
    lines = "".join(f"  {key}: {value}\n" for key, value in values.items())
    text = text.replace("seo:\n", "seo:\n" + lines, 1)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def old(tmp_path, monkeypatch):
    """Сайт в духе 0.1: картинки соцсетей в static/og/, в site.yaml - путь от static/."""
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.delenv("SITE_INDEXABLE", raising=False)
    root = tmp_path / "site"
    create(root, name="S", languages=["en", "ru"], demo=False)
    (root / "media" / "cover.png").unlink()
    _png(root / "static" / "og" / "s-en.png")
    _png(root / "static" / "og" / "s-ru.png")
    _seo(root, og_default_image="og/s-en.png", og_default_image_ru="og/s-ru.png")
    return root


def _meta(html: str, attr: str, name: str) -> str:
    found = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]+)"', html)
    assert found, name
    return found.group(1)


def _page(dist: Path, lang: str) -> str:
    folder = dist if lang == "en" else dist / lang
    return (folder / "index.html").read_text(encoding="utf-8")


def _codes(result) -> list[str]:
    return [error.code for error in result.collector.errors]


# --- сборка ----------------------------------------------------------------------------


def test_static_og_builds_in_prod_strict_with_the_01_address(old, tmp_path):
    dist = tmp_path / "dist"
    result = pipeline.run(old, dist=dist, env=BuildEnv.resolve("prod"), strict=True)
    assert not result.failed, [e.message for e in result.collector.errors]
    assert not result.collector.warnings, [w.message for w in result.collector.warnings]
    for lang in ("en", "ru"):
        html = _page(dist, lang)
        url = f"https://{DOMAIN}/og/s-{lang}.png"
        assert _meta(html, "property", "og:image") == url
        assert _meta(html, "name", "twitter:image") == url
    # файл везёт копирование static/: байт в байт, без нарезок рядом
    for lang in ("en", "ru"):
        built = dist / "og" / f"s-{lang}.png"
        assert built.read_bytes() == (old / "static" / "og" / f"s-{lang}.png").read_bytes()
    assert sorted(p.name for p in (dist / "og").iterdir()) == ["s-en.png", "s-ru.png"]
    assert not (dist / "media" / "og").exists()


def test_cli_build_prod_strict_passes_and_prints_the_note(old):
    result = run("build", old, "--env", "prod", "--strict", "--notes", "en")
    assert result.exit_code == 0, result.output
    assert "(not an error)" in result.output
    assert "og_default_image: og/s-en.png - better media/og/s-en.png" in result.output
    assert "og_default_image_ru: og/s-ru.png - better media/og/s-ru.png" in result.output
    # og-картинка - не «контент в static»: одно сведение, а не два
    assert "static/og/s-en.png" not in result.output


def test_theme_media_url_gives_the_static_address(old, tmp_path):
    """Тема 0.1 писала `absolute(media_url(site.seo.og_default_image))`: адрес тот же."""
    base = old / "theme" / "base.html"
    text = base.read_text(encoding="utf-8")
    probe = '<meta name="x-og" content="{{ absolute(media_url(site.seo.og_default_image)) }}">\n'
    base.write_text(text.replace("</head>", probe + "</head>", 1), encoding="utf-8")
    dist = tmp_path / "dist"
    result = pipeline.run(old, dist=dist, env=BuildEnv.resolve("prod"), strict=True)
    assert not result.failed, [e.message for e in result.collector.errors]
    for lang in ("en", "ru"):
        assert _meta(_page(dist, lang), "name", "x-og") == f"https://{DOMAIN}/og/s-{lang}.png"


@pytest.mark.parametrize("written", ["/og/s-en.png", "./og/s-en.png", "static/og/s-en.png"])
def test_other_spellings_of_the_static_path(old, tmp_path, written):
    _seo(old, og_default_image=written, og_default_image_ru="og/s-ru.png")
    dist = tmp_path / "dist"
    result = pipeline.run(old, dist=dist, env=BuildEnv.resolve("prod"), strict=True)
    assert not result.failed, [e.message for e in result.collector.errors]
    assert _meta(_page(dist, "en"), "property", "og:image") == f"https://{DOMAIN}/og/s-en.png"


def test_page_og_image_in_static(old, tmp_path):
    index = old / "content" / "en" / "index.md"
    text = index.read_text(encoding="utf-8")
    index.write_text(text.replace("---\n", "---\nog_image: og/s-ru.png\n", 1), encoding="utf-8")
    dist = tmp_path / "dist"
    result = pipeline.run(old, dist=dist, env=BuildEnv.resolve("prod"), strict=True)
    assert not result.failed, [e.message for e in result.collector.errors]
    assert _meta(_page(dist, "en"), "property", "og:image") == f"https://{DOMAIN}/og/s-ru.png"
    owners = {owner for owner, *_ in result.report.static_social}
    assert owners == {"site.yaml", "en/index.md"}


def test_page_twitter_image_in_static(old, tmp_path):
    """0.1 не проверял `twitter_image` на диске: путь от static/ собирался."""
    base = old / "theme" / "base.html"
    probe = (
        '{% if page.meta.extra.get(\'twitter_image\') %}<meta name="x-tw" content="{{ '
        "absolute(media_url(page.meta.extra.get('twitter_image'))) }}\">{% endif %}\n"
    )
    text = base.read_text(encoding="utf-8")
    base.write_text(text.replace("</head>", probe + "</head>", 1), encoding="utf-8")
    index = old / "content" / "en" / "index.md"
    text = index.read_text(encoding="utf-8")
    index.write_text(
        text.replace("---\n", "---\ntwitter_image: static/og/s-ru.png\n", 1), encoding="utf-8"
    )
    dist = tmp_path / "dist"
    result = pipeline.run(old, dist=dist, env=BuildEnv.resolve("prod"), strict=True)
    assert not result.failed, [e.message for e in result.collector.errors]
    assert _meta(_page(dist, "en"), "name", "x-tw") == f"https://{DOMAIN}/og/s-ru.png"
    assert ("en/index.md", "twitter_image", "static/og/s-ru.png", "media/og/s-ru.png") in (
        result.report.static_social
    )


def test_a_small_static_og_image_is_warned_like_a_media_one(old, tmp_path):
    _png(old / "static" / "og" / "s-en.png", width=600, height=315)
    result = pipeline.run(old, dist=tmp_path / "dist", env=BuildEnv.resolve("prod"))
    assert not result.failed
    texts = [w.message.text("en") for w in result.collector.warnings]
    assert any("og/s-en.png" in t and "1200" in t for t in texts), texts


# --- сведение не считается предупреждением --------------------------------------------


def test_the_note_does_not_count_under_strict_or_fail_on_warning(old, tmp_path):
    path = old / "site.yaml"
    path.write_text(
        path.read_text("utf-8").replace("fail_on_warning: false", "fail_on_warning: true"),
        "utf-8",
    )
    assert "fail_on_warning: true" in path.read_text("utf-8")
    checked = pipeline.check(old, strict=True, env=BuildEnv.resolve("prod"))
    assert not checked.failed, [e.message for e in checked.collector.errors]
    assert checked.report.static_social == [
        ("site.yaml", "og_default_image", "og/s-en.png", "media/og/s-en.png"),
        ("site.yaml", "og_default_image_ru", "og/s-ru.png", "media/og/s-ru.png"),
    ]
    rendered = checked.report.render("en")
    assert "A social image sits in static/ (not an error)" in rendered
    assert "better media/og/s-en.png" in rendered
    texts = [w.message.text("en") for w in checked.collector.warnings]
    assert not [t for t in texts if "og/s-" in t or "static" in t], texts

    built = pipeline.run(old, dist=tmp_path / "dist", env=BuildEnv.resolve("prod"))
    assert built.strict and not built.collector.warnings
    assert built.report.static_social == checked.report.static_social
    assert run("build", old, "--env", "prod", "--out", tmp_path / "out").exit_code == 0


# --- конфигуратор ----------------------------------------------------------------------


@pytest.mark.parametrize("written", ["og/s-en.png", "/og/s-en.png"])
def test_setup_dump_then_answers_keeps_the_value(old, tmp_path, written):
    _seo(old, og_default_image=written, og_default_image_ru="og/s-ru.png")
    before = (old / "site.yaml").read_text(encoding="utf-8")
    dumped = run("setup", old, "--dump")
    assert dumped.exit_code == 0, dumped.output
    assert yaml.safe_load(dumped.output)["search"]["og_image"] == written
    answers = tmp_path / "answers.yaml"
    answers.write_text(dumped.output, encoding="utf-8")
    applied = run("setup", old, "--answers", answers)
    assert applied.exit_code == 0, applied.output
    assert (old / "site.yaml").read_text(encoding="utf-8") == before
    # и сайт после сохранения собирается: значение принято, не только не тронуто
    built = run("build", old, "--env", "prod", "--strict", "--out", tmp_path / "out")
    assert built.exit_code == 0, built.output


# --- что по-прежнему E024 --------------------------------------------------------------


def _both(root: Path, tmp_path: Path):
    """Сборка и check; E024, поднятый исключением (обход static/), - тоже ответ."""
    out = []
    for call in (
        lambda: pipeline.run(root, dist=tmp_path / "dist", env=BuildEnv.resolve("prod")),
        lambda: pipeline.check(root, env=BuildEnv.resolve("prod")),
    ):
        try:
            out.append(call())
        except HeronError as error:
            out.append(SimpleNamespace(collector=SimpleNamespace(errors=[error])))
    return out


def test_a_missing_file_is_still_e024_in_build_and_check(old, tmp_path):
    _seo(old, og_default_image="og/nope.png", og_default_image_ru="og/s-ru.png")
    built, checked = _both(old, tmp_path)
    for result in (built, checked):
        assert "E024" in _codes(result)
        error = next(e for e in result.collector.errors if e.code == "E024")
        assert "og/nope.png" in error.message.text("en")
        assert "static/" in error.hint.text("en")
    assert not (tmp_path / "dist").exists()


def test_dot_dot_out_of_the_site_is_still_e024(old, tmp_path):
    _png(old.parent / "outside.png")
    _seo(old, og_default_image="../outside.png", og_default_image_ru="og/s-ru.png")
    built, checked = _both(old, tmp_path)
    assert "E024" in _codes(built) and "E024" in _codes(checked)
    _seo(old, og_default_image="og/../../outside.png", og_default_image_ru="og/s-ru.png")
    built, checked = _both(old, tmp_path)
    assert "E024" in _codes(built) and "E024" in _codes(checked)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="без символических ссылок")
def test_a_symlink_out_of_static_is_still_e024(old, tmp_path):
    outside = tmp_path / "outside.png"
    _png(outside)
    (old / "static" / "og" / "s-en.png").unlink()
    (old / "static" / "og" / "s-en.png").symlink_to(outside)
    built, checked = _both(old, tmp_path)
    assert "E024" in _codes(built) and "E024" in _codes(checked)
    assert not any(
        "s-en.png" in str(error.message.text("en"))
        for error in built.collector.errors
        if error.code != "E024"
    )
