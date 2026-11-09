"""Нарезка только того, что просит сайт.

Раньше каждый мастер резался во все пропорции темы, а запасной формат — на
каждой ширине. На живом сайте с сотней мастеров это давало в сборке втрое
больше картинок, чем ссылалось из HTML. Теперь шаблоны берут план, а
кодируется и кладётся в сборку только то, на что есть ссылка.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import build as pipeline
from heron.core import media
from heron.scaffold import create

LINK = re.compile(r"""(?<=[/"'\s(,=])(media/[^\s"'<>()\\,]+)""")


def illustration(path: Path, size: int = 1600) -> None:
    """Рисунок на прозрачном фоне: его вписывают, а запасной формат — PNG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image.paste(
        Image.new("RGBA", (size // 2, size // 2), (200, 40, 40, 255)), (size // 4, size // 4)
    )
    image.save(path)


def photo(path: Path, width: int = 1600, height: int = 1200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (40, 90, 160)).save(path)


@pytest.fixture
def site(tmp_path) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    theme = root / "theme" / "theme.yaml"
    data = yaml.safe_load(theme.read_text(encoding="utf-8"))
    data["images"] = {
        "widths": [400, 800, 1200, 1600],
        "ratios": ["1:1", "16:9", "4:3"],
        "formats": ["avif", "webp"],
    }
    theme.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    # тема просит у карточки одну пропорцию — 16:9
    page = root / "theme" / "templates" / "page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "<h1>{{ page.h1 }}</h1>",
            "<h1>{{ page.h1 }}</h1>"
            "{% if page.meta.image %}{{ picture(page.meta.image, '16:9', alt='x') }}{% endif %}",
        ),
        encoding="utf-8",
    )
    illustration(root / "media" / "card.png")
    (root / "content" / "en" / "card.md").write_text(
        "---\ntitle: Card\nh1: Card\ndescription: D\n"
        "image: media/card.png\nimage_alt: x\n---\n\nText.\n",
        encoding="utf-8",
    )
    return root


# Метка версии ?v=<хеш> (core/versions.py) - тот же файл: здесь считаются
# только файлы.
STAMP = re.compile(r"\?v=[0-9a-f]{10}")


def unhash(text: str) -> str:
    return STAMP.sub("", text)


def built(root: Path) -> set[str]:
    media_dir = root / "dist" / "media"
    return {
        unhash(p.relative_to(root / "dist").as_posix()) for p in media_dir.rglob("*") if p.is_file()
    }


def links(root: Path) -> set[str]:
    found: set[str] = set()
    for path in (root / "dist").rglob("*"):
        # служебная справка темы черновой сборки (/_heron/theme/) пишет пути
        # картинок текстом - исходный markdown и подсказки, - а не ссылками
        if "_heron" in path.relative_to(root / "dist").parts:
            continue
        if path.is_file() and path.suffix in {".html", ".xml", ".txt", ".json", ".css"}:
            found.update(LINK.findall(unhash(path.read_text(encoding="utf-8"))))
    return found


def cover_variants(root: Path, src: str, fallback_width: int = 800) -> set[str]:
    """Файлы запасного формата, которые план обложки добавляет к запрошенным шаблоном.

    Имя считается через `plan_master(cover=True)`, а не строкой наугад.
    """
    data = yaml.safe_load((root / "theme" / "theme.yaml").read_text(encoding="utf-8"))
    spec = ImagesSpec(**{**data["images"], "fallback_width": fallback_width})
    plan = media.plan_master(src, root / src, spec, cover=True)
    return {f"{path}" for r in plan.values() for _, path in r.sources["origin"]}


def test_only_the_requested_ratio_lands_in_the_build(site):
    result = pipeline.run(site)
    assert not result.failed, [str(e) for e in result.collector.errors]
    files = built(site)
    # card.md - обложка страницы /card/: мастер едет в сборку целиком (E16.S1.T2)
    assert "media/card.png" in files
    # прочее: либо запрошенное шаблоном 16:9, либо вариант обложки (E16.S2.T3)
    cover = cover_variants(site, "media/card.png") & {n for n in files if n.endswith(".png")}
    # media/cover.png - обложка по умолчанию заготовки (E18.S1.T11) и её варианты
    default_cover = {"media/cover.png"} | cover_variants(site, "media/cover.png")
    extra = {n for n in files if "-16x9-" not in n} - {"media/card.png"} - default_cover
    assert extra <= cover, extra
    # пропорций, на которые никто не ссылается, нет
    assert not any(n for n in files if re.search(r"-(1x1|4x3)-", n) and n not in cover), files


def test_one_fallback_per_ratio_and_not_wider_than_fallback_width(site):
    pipeline.run(site)
    pngs = {name for name in built(site) if name.endswith(".png")}
    assert "media/card-16x9-800.png" in pngs
    # кроме запасного файла в <img> - мастер обложки и её вариант шириной cover_width
    assert pngs == {
        "media/card.png",
        "media/card-16x9-800.png",
        "media/card-16x9-1200.png",
        "media/cover.png",  # обложка по умолчанию заготовки (E18.S1.T11)
    }, pngs
    html = unhash((site / "dist" / "card" / "index.html").read_text(encoding="utf-8"))
    assert 'src="/media/card-16x9-800.png"' in html
    with Image.open(site / "dist" / "media" / "card-16x9-800.png") as out:
        assert out.width == 800


def test_html_and_media_folder_agree_both_ways(site):
    pipeline.run(site)
    files, referenced = built(site), links(site)
    assert referenced <= files, referenced - files  # ни одной битой ссылки
    assert files <= referenced, files - referenced  # ни одного файла без ссылки


def test_fallback_width_comes_from_the_theme(site):
    theme = site / "theme" / "theme.yaml"
    data = yaml.safe_load(theme.read_text(encoding="utf-8"))
    data["images"]["fallback_width"] = 400
    theme.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    pipeline.run(site)
    pngs = {n for n in built(site) if n.endswith(".png")}
    html = unhash((site / "dist" / "card" / "index.html").read_text(encoding="utf-8"))
    assert 'src="/media/card-16x9-400.png"' in html
    # прочие .png - мастер обложки и её вариант шириной max(fallback_width, cover_width)
    assert pngs == {
        "media/card.png",
        "media/card-16x9-400.png",
        "media/card-16x9-1200.png",
        "media/cover.png",  # обложка по умолчанию заготовки (E18.S1.T11)
    }, pngs


def test_fallback_width_defaults_to_800():
    assert ImagesSpec().fallback_width == 800


def test_media_url_with_width_gets_exactly_that_file(site):
    page = site / "theme" / "templates" / "page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "</h1>",
            "</h1>{% if page.meta.image %}"
            "<i data-og=\"{{ media_url(page.meta.image, '16:9', 1200) }}\"></i>{% endif %}",
            1,
        ),
        encoding="utf-8",
    )
    pipeline.run(site)
    assert "media/card-16x9-1200.png" in built(site)


def test_raw_references_bring_the_master(site):
    """Картинка из текста страницы и обложка для соцсетей нужны целиком."""
    photo(site / "media" / "inline.jpg")
    photo(site / "media" / "og.jpg")
    (site / "content" / "en" / "inline.md").write_text(
        "---\ntitle: I\nh1: I\ndescription: D\nog_image: media/og.jpg\n---\n\n"
        "![Picture](media/inline.jpg)\n",
        encoding="utf-8",
    )
    pipeline.run(site)
    files = built(site)
    assert "media/inline.jpg" in files
    assert "media/og.jpg" in files
    # inline.jpg не обложка и шаблон его не режет; у og.jpg (обложка /inline/)
    # допустим только вариант шириной cover_width
    assert not any(name.startswith("media/inline-") for name in files)
    og = {n for n in files if n.startswith("media/og-")}
    assert og <= cover_variants(site, "media/og.jpg"), og
    assert all(n.endswith("-1200.jpg") for n in og), og


def test_cache_keeps_what_the_build_did_not_take(site, tmp_path):
    """Правка шаблона, вернувшая пропорцию, не должна кодировать её заново."""
    pipeline.run(site)
    page = site / "theme" / "templates" / "page.html"
    page.write_text(page.read_text(encoding="utf-8").replace("'16:9'", "'1:1'"), encoding="utf-8")
    import shutil

    shutil.rmtree(site / "dist")  # dist расходный: его стирают перед сборкой
    pipeline.run(site)
    slices = site / ".heron-cache" / media.SLICES
    cached = {p.name for p in slices.rglob("*") if p.is_file()}
    assert any("-16x9-" in name for name in cached)
    # нарезки карточки - 1:1; исключение - мастер и вариант обложки
    cover = cover_variants(site, "media/card.png")
    assert all(
        "-1x1-" in name or name in {"media/card.png", "media/cover.png"} or name in cover
        for name in built(site)
    ), built(site)


def test_build_without_templates_still_cuts_everything(tmp_path):
    """`media.build` режет весь план — для проверки нарезки без шаблонов."""
    from heron.core import tree
    from heron.core.errors import Collector
    from tests import sites

    content = sites.build(
        tmp_path, {"uk/a.md": sites.page("A", image="media/a.png", image_alt="a")}
    )
    illustration(tmp_path / "media" / "a.png", size=900)
    site_model, collector = tree.scan(content, sites.config())
    spec = ImagesSpec(widths=[400, 800], ratios=["1:1"], formats=["webp"])
    media.build(site_model, tmp_path, tmp_path / "dist", spec, Collector())
    names = {p.name for p in (tmp_path / "dist" / "media").iterdir()}
    assert {"a-1x1-400.webp", "a-1x1-800.webp", "a-1x1-800.png", "a.png"} <= names
