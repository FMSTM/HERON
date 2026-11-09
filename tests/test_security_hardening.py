"""Укрепление по внешнему аудиту: nginx, предел картинок, YAML-бомбы, медиа в SVG.

Спецификация: docs/ru/spec/21-engine.md, раздел 11 (коды и пределы).
"""

from __future__ import annotations

import io
import json
import struct
import tarfile
import time
import zlib
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageFile

from heron import studio
from heron.contracts.site import load_site
from heron.contracts.theme import ImagesSpec
from heron.core import build as pipeline
from heron.core import data as data_module
from heron.core import media, svg, tree, yamlsafe
from heron.core.errors import Collector, HeronError
from heron.core.parser import frontmatter
from heron.modules import nginx
from heron.modules.redirects import Plan
from heron.scaffold import create
from heron.themes import install, pack
from tests import sites

# --- SEC-HERON-01: quote() в конфиге nginx ------------------------------------------------


@pytest.mark.parametrize("char", ["\n", "\r", "\x00", "\x1b", "\x7f", "\x85", " ", " "])
def test_nginx_quote_refuses_control_characters(char):
    with pytest.raises(HeronError) as raised:
        nginx.quote(f"/old{char}path/")
    assert raised.value.code == "E022"
    assert "control character" in raised.value.message.text("en")


@pytest.mark.parametrize("path", ["/про-нас/", "/%D0%BF%D1%80%D0%BE/", '/a"b\\c/'])
def test_nginx_quote_keeps_normal_addresses(path):
    assert nginx.quote(path) == '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def test_nginx_config_with_a_control_character_past_the_checks_is_not_built():
    config = sites.config()
    assert "location = " in nginx.generate(config, Plan(gone=["/ok/"]))[nginx.NAME]
    for plan in (Plan(gone=["/a\nb/"]), Plan(moved={"/old/": "/new\r/"})):
        with pytest.raises(HeronError) as raised:
            nginx.generate(config, plan)
        assert raised.value.code == "E022"


def test_nginx_language_folders_are_validated_upstream():
    """Языки идут в location без quote(): их держит LANG_RE site.yaml."""
    site = {"domain": "example.com", "theme": "demo", "default_lang": "en"}
    sites.config(site={**site, "languages": ["en", "de"]})
    with pytest.raises(ValueError, match="languages"):
        sites.config(site={**site, "languages": ["en", "d;e"]})


# --- SEC-HERON-02: предел картинки в пикселях ---------------------------------------------


def _png(width: int, height: int) -> bytes:
    """PNG 1 бит на пиксель: килобайты на диске при любом размере кадра."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = (b"\x00" + b"\x00" * ((width + 7) // 8)) * height
    header = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


BIG = _png(10000, 6000)  # 60 Мп: под пределом Pillow, над пределом движка
BOMB = _png(20000, 20000)  # 400 Мп: над двойным пределом - отказ самого Pillow
SPEC = ImagesSpec(widths=[400], ratios=["1:1"], formats=["webp"])


@pytest.fixture
def no_decoding(monkeypatch):
    """Пиксели не декодируются: проверка - по заголовку."""

    def refuse(self, *args, **kwargs):
        raise AssertionError("pixels were decoded")

    monkeypatch.setattr(ImageFile.ImageFile, "load", refuse)


def test_one_limit_for_the_engine_and_pillow():
    assert media.MAX_PIXELS == 50_000_000
    assert Image.MAX_IMAGE_PIXELS == media.MAX_PIXELS


def test_limit_is_width_times_height():
    class Header:
        size = (10_000, 5_000)

    media.check_pixels(Header())  # ровно предел - можно
    Header.size = (10_000, 5_001)
    with pytest.raises(media.TooLarge):
        media.check_pixels(Header())


@pytest.mark.parametrize("data, size", [(BIG, "10000×6000"), (BOMB, "400000000")])
def test_master_over_the_limit_is_refused_before_decoding(tmp_path, no_decoding, data, size):
    path = tmp_path / "big.png"
    path.write_bytes(data)
    with pytest.raises(media.TooLarge) as raised:
        media.shape_of(path)
    assert raised.value.size == size


def _image_site(tmp_path: Path, data: bytes):
    content = sites.build(tmp_path, {"uk/index.md": sites.page("Головна", image="media/big.png")})
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "big.png").write_bytes(data)
    config = sites.config()
    site, _ = tree.scan(content, config)
    return site, config


def test_build_plan_and_check_give_e036_with_size_and_limit(tmp_path, no_decoding):
    site, config = _image_site(tmp_path, BIG)
    collector = Collector()
    manifest = media.plan(site, tmp_path, SPEC, collector, config=config)
    assert [e.code for e in collector.errors] == ["E036"]
    text = collector.errors[0].message.text("en")
    assert "media/big.png" in text and "10000×6000" in text and "50000000" in text
    assert "media/big.png" not in manifest.masters
    covers = Collector()
    media.verify_covers(site, tmp_path, covers, SPEC, config)  # heron check
    assert [e.code for e in covers.errors] == ["E036"]


def test_shape_from_an_old_cache_entry_is_held_to_the_limit(tmp_path):
    entry = tmp_path / "entry"
    entry.mkdir()
    (entry / "shape.json").write_text(json.dumps({"width": 12000, "height": 6000, "alpha": False}))
    with pytest.raises(media.TooLarge):
        media._shape(entry, tmp_path / "missing.png")


def test_normal_master_still_passes(tmp_path):
    buffer = io.BytesIO()
    Image.new("RGB", (1200, 900), (20, 60, 120)).save(buffer, "PNG")
    site, config = _image_site(tmp_path, buffer.getvalue())
    collector = Collector()
    manifest = media.plan(site, tmp_path, SPEC, collector, config=config)
    assert not collector.errors
    assert "media/big.png" in manifest.masters


@pytest.mark.parametrize("data", [BIG, BOMB])
def test_studio_upload_over_the_limit_is_refused(tmp_path, no_decoding, data):
    with pytest.raises(HeronError) as raised:
        studio.upload(tmp_path, "big.png", data)
    assert raised.value.code == "E039"
    assert "50000000" in raised.value.message.text("en")
    assert not (tmp_path / "media").exists() or not any((tmp_path / "media").iterdir())


# --- SEC-HERON-03: YAML-бомбы ---------------------------------------------------------------


def _laughs(levels: int = 9) -> str:
    """Billion laughs: десять ссылок на уровень."""
    lines = ['l0: &l0 ["lol","lol","lol","lol","lol","lol","lol","lol","lol","lol"]']
    for level in range(1, levels):
        refs = ",".join([f"*l{level - 1}"] * 10)
        lines.append(f"l{level}: &l{level} [{refs}]")
    return "\n".join(lines) + "\n"


LAUGHS = _laughs()


def _fast(call):
    start = time.monotonic()
    with pytest.raises(Exception) as raised:
        call()
    assert time.monotonic() - start < 1.0
    return raised.value


def test_site_mode_bounds_the_expansion_and_theme_mode_refuses_anchors():
    assert isinstance(_fast(lambda: yamlsafe.load(LAUGHS)), yamlsafe.Expands)
    assert isinstance(_fast(lambda: yamlsafe.load(LAUGHS, theme=True)), yamlsafe.Anchors)
    assert isinstance(_fast(lambda: yamlsafe.load("a: &a [*a]\n")), yamlsafe.Expands)
    assert yamlsafe.anchor_in(LAUGHS) == 1
    assert yamlsafe.anchor_in("a: 1\nb: [2]\n") is None


def test_site_mode_keeps_normal_documents():
    text = "base: &b {x: 1}\nother:\n  <<: *b\n  y: 2\nlist: [*b, *b]\n"
    assert yamlsafe.load(text) == {
        "base": {"x": 1},
        "other": {"x": 1, "y": 2},
        "list": [{"x": 1}, {"x": 1}],
    }
    # большой документ без ссылок не считается: узлов столько же, сколько в развёртке
    scalars = [yaml.ScalarNode("tag:yaml.org,2002:int", "1") for _ in range(150_000)]
    yamlsafe.bound(yaml.SequenceNode("tag:yaml.org,2002:seq", scalars))
    shared = yaml.ScalarNode("tag:yaml.org,2002:int", "1")
    with pytest.raises(yamlsafe.Expands):
        yamlsafe.bound(yaml.SequenceNode("tag:yaml.org,2002:seq", [shared] * 150_000))
    for text in ("", "# c\n", "x\n", "[1]\n", "~\n"):
        assert yamlsafe.load(text) == yaml.safe_load(text)


def _site_yaml(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "site.yaml"
    path.write_text(
        f'heron: "{sites._SPEC}"\nsite:\n  domain: example.com\n  theme: demo\n  default_lang: en\n'
        f"  languages: [en]\n{extra}",
        encoding="utf-8",
    )
    return path


def test_site_yaml_alias_bomb_is_e011_fast(tmp_path):
    path = _site_yaml(tmp_path, "x-bomb:\n" + "".join(f"  {line}\n" for line in LAUGHS.split("\n")))
    error = _fast(lambda: load_site(path))
    assert error.code == "E011"
    assert "expands too much" in error.message.text("en")


def test_site_yaml_with_a_couple_of_anchors_still_loads(tmp_path):
    path = _site_yaml(
        tmp_path,
        "gone: &old [/a/, /b/]\nbuild:\n  overrides: *old\n",
    )
    config = load_site(path)
    assert config.gone == ["/a/", "/b/"]


def test_front_matter_alias_bomb_is_e001_fast():
    text = "---\ntitle: x\n" + LAUGHS + "---\n\nbody\n"
    error = _fast(lambda: frontmatter.split(text, "en/index.md"))
    assert error.code == "E001"
    assert "expands too much" in error.message.text("en")


def test_data_file_alias_bomb_is_e011_fast(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "bomb.yaml").write_text(LAUGHS, encoding="utf-8")
    collector = Collector()
    start = time.monotonic()
    data_module.load(tmp_path, collector)
    assert time.monotonic() - start < 1.0
    assert [e.code for e in collector.errors] == ["E011"]


def _tar(entries: dict[str, bytes]) -> bytes:
    blob = io.BytesIO()
    with tarfile.open(fileobj=blob, mode="w:gz") as archive:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return blob.getvalue()


@pytest.fixture
def site(tmp_path, monkeypatch) -> Path:
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"], demo=True)
    return root


@pytest.mark.parametrize(
    "name, text",
    [
        ("theme/theme.yaml", "name: x\n" + LAUGHS),
        ("theme/i18n/en.yaml", "a: &a hi\nb: *a\n"),
        ("demo/content/en/index.md", "---\ntitle: &t x\nh1: *t\n---\n\nbody\n"),
        ("demo/data/team.yaml", LAUGHS),
        ("heron-theme.yaml", "name: x\nheron: &h '>=0.3'\nalso: *h\n"),
    ],
    ids=["theme-yaml", "i18n", "demo-front-matter", "demo-data", "manifest"],
)
def test_theme_get_refuses_anchors_before_unpacking(site, tmp_path, name, text):
    before = (site / "theme" / "theme.yaml").read_bytes()
    entries = {"heron-theme.yaml": b"name: x\n", "theme/theme.yaml": b"name: x\n"}
    entries[name] = text.encode()
    path = tmp_path / "bomb.tgz"
    path.write_bytes(_tar(entries))
    error = _fast(lambda: install(site, "file", archive=path))
    assert error.code == "E032"
    assert name in error.message.text("en") and "anchors" in error.message.text("en")
    assert (site / "theme" / "theme.yaml").read_bytes() == before  # тема сайта цела


def test_theme_with_anchors_builds_but_is_not_packed_or_passed_by_check_theme(site, tmp_path):
    theme_yaml = site / "theme" / "theme.yaml"
    theme_yaml.write_text(
        theme_yaml.read_text(encoding="utf-8") + "x-shared: &shared {a: 1}\nx-again: *shared\n",
        encoding="utf-8",
    )
    with pytest.raises(HeronError) as raised:
        pack(site, tmp_path / "t.tar.gz")
    assert raised.value.code == "E032"
    assert not (tmp_path / "t.tar.gz").exists()
    result = pipeline.check(site, notes_lang="en", theme_demo=True)
    assert [(e.code, e.path) for e in result.collector.errors] == [("E032", "theme/theme.yaml")]
    assert not pipeline.check(site, notes_lang="en").collector.errors  # сайт собирается


def test_theme_yaml_alias_bomb_at_build_is_refused_fast(site):
    theme_yaml = site / "theme" / "theme.yaml"
    theme_yaml.write_text(theme_yaml.read_text(encoding="utf-8") + LAUGHS, encoding="utf-8")
    error = _fast(lambda: pipeline.check(site, notes_lang="en"))
    assert error.code == "E041"


def test_the_starter_theme_has_no_anchors(site):
    theme = site / "theme"
    for path in sorted(theme.rglob("*")):
        if path.is_file() and path.suffix in (".yaml", ".yml", ".md"):
            assert yamlsafe.file_anchor(path.name, path.read_text(encoding="utf-8")) is None, path


# --- SEC-HERON-05: медиа HTML в SVG ---------------------------------------------------------

SVG = 'xmlns="http://www.w3.org/2000/svg"'
XHTML = 'xmlns:h="http://www.w3.org/1999/xhtml"'


@pytest.mark.parametrize(
    "inner",
    [
        '<video poster="https://x/p.png"/>',
        '<video xmlns="http://www.w3.org/1999/xhtml" poster="https://x/p.png"/>',
        '<h:video poster="https://x/p.png"/>',
        '<audio src="https://x/a.mp3"/>',
        '<h:audio><h:source src="https://x/a.mp3"/></h:audio>',
        '<track src="https://x/t.vtt"/>',
        '<g poster="https://x/p.png"/>',
        '<g poster="//x/p.png"/>',
    ],
)
def test_html_media_and_poster_in_svg_are_refused(inner):
    assert svg.problem(f"<svg {SVG} {XHTML}>{inner}</svg>".encode()) is not None


def test_check_gives_e043_for_video_poster_in_media(site):
    (site / "media").mkdir(exist_ok=True)
    (site / "media" / "clip.svg").write_bytes(
        f'<svg {SVG}><video poster="https://x/p.png"/></svg>'.encode()
    )
    result = pipeline.check(site, notes_lang="en")
    assert [e.path for e in result.collector.errors if e.code == "E043"] == ["media/clip.svg"]
