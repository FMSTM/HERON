"""Обложка у каждого языка своя, нет своей - как на основном языке (20 §4.2, 21 §10).

- `image`, `image_alt`, `og_image` - своё значение у языка; язык без своего `image`
  получает обложку основного языка при сборке, одним местом (`build.inherit`): её видят
  `og:image`, `twitter:image`, разметка, карта сайта и шаблоны.
- Правка обложки на основном языке не пишет её в другие файлы; на другом языке её можно
  задать (не E039) и очистить (снова как на основном).
- Новая копия языка не копирует обложку; `--dump` показывает обложку другого языка,
  только если она в файле есть.
- `check`: обложки нет в «общие поля расходятся»; своя обложка языка проверяется теми
  же правилами; подпись - у каждого языка.
- Своё поле типа с `translatable: true` без текста - так же; у поля с текстом флаг
  лишний - предупреждение.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from PIL import Image

from heron import studio
from heron.cli import main
from heron.contracts.fields import SHARED
from heron.core import build as pipeline
from heron.core import describe
from heron.core.environment import BuildEnv
from heron.edit import console
from heron.edit import entity as ops
from heron.scaffold import create
from tests import sites

LANGS = ["en", "ru", "de"]


def run(*args):
    return CliRunner().invoke(main, [str(a) for a in args])


def _png(path: Path, width: int = 1600, height: int = 900) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (120, 80, 40)).save(path)


def _md(title: str, **fields) -> str:
    head = {"title": title, "h1": title + " h1", "description": "D " + title, **fields}
    lines = [f"{k}: {v}" for k, v in head.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\nText.\n"


def _theme(root: Path, change) -> None:
    path = root / "theme" / "theme.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8")


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Три языка, основной en: у страницы case обложка en, своя у ru, у de - нет."""
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="S", languages=LANGS, demo=False)
    sites.clear_content(root)
    for name in ("case-en", "case-ru", "home"):
        _png(root / "media" / f"{name}.png")
    content = root / "content"
    files = {
        "en/index.md": _md("Home", image="media/home.png", image_alt="Home"),
        "ru/index.md": _md("Glavnaya", image="media/home.png", image_alt="Glavnaya"),
        "de/index.md": _md("Start", image="media/home.png", image_alt="Start"),
        "en/case.md": _md("Case", image="media/case-en.png", image_alt="Slide en"),
        "ru/case.md": _md("Keis", image="media/case-ru.png", image_alt="Slide ru"),
        "de/case.md": _md("Fall", image_alt="Folie de"),
    }
    for rel, text in files.items():
        (content / rel).write_text(text, encoding="utf-8")
    return root


def _rel(root: Path, lang: str, name: str = "case") -> str:
    return f"{lang}/{name}.md"


def _warnings(result, path: str) -> list[str]:
    return [w.message.text("en") for w in result.collector.warnings if w.path == path]


def _no_cover_mismatch(result, path: str) -> None:
    """Своя обложка языка - не «общее поле расходится»."""
    texts = [t for t in _warnings(result, path) if "other values" in t and "image" in t]
    assert not texts, texts


# --- 1. списки полей -------------------------------------------------------------------


def test_cover_fields_are_not_shared():
    from heron.contracts.fields import FALLBACK

    assert {"image", "og_image"} <= FALLBACK
    assert not set(SHARED) & {"image", "image_alt", "og_image"}
    assert pipeline.SHARED_FIELDS is SHARED


# --- 2. сборка: одно место подстановки ---------------------------------------------------


def _jsonld(html: str) -> list[dict]:
    out = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block)
        out.extend(data.get("@graph", [data]) if isinstance(data, dict) else data)
    return out


def test_build_gives_each_language_its_cover(site, tmp_path, monkeypatch):
    monkeypatch.delenv("SITE_INDEXABLE", raising=False)
    _theme(site, lambda data: data["types"]["page"].update(jsonld=["WebPage"]))
    dist = tmp_path / "dist"
    result = pipeline.run(site, dist=dist, env=BuildEnv.resolve("prod"))
    assert not result.failed, [e.message for e in result.collector.errors]
    expected = {"en": "case-en", "ru": "case-ru", "de": "case-en"}
    for lang, name in expected.items():
        folder = dist / ("case" if lang == "en" else f"{lang}/case")
        html = (folder / "index.html").read_text(encoding="utf-8")
        og = re.search(r'<meta property="og:image" content="([^"]+)"', html).group(1)
        tw = re.search(r'<meta name="twitter:image" content="([^"]+)"', html).group(1)
        assert f"/media/{name}" in og and og == tw, (lang, og, tw)
        nodes = [n for n in _jsonld(html) if "primaryImageOfPage" in n]
        assert nodes, lang
        assert f"/media/{name}" in nodes[0]["primaryImageOfPage"]["url"], lang
        alt = re.search(r'<meta property="og:image:alt" content="([^"]+)"', html).group(1)
        assert alt == {"en": "Slide en", "ru": "Slide ru", "de": "Folie de"}[lang]
    for lang, name in expected.items():
        sitemap = (dist / f"sitemap-{lang}.xml").read_text(encoding="utf-8")
        entries = re.findall(r"<url>(.*?)</url>", sitemap, re.S)
        entry = next(e for e in entries if e.split("</loc>")[0].endswith("/case/"))
        images = re.findall(r"<image:loc>([^<]+)</image:loc>", entry)
        assert images and f"/media/{name}" in images[0], (lang, entry)


def test_inherited_cover_is_visible_to_templates(site):
    result = pipeline.check(site, notes_lang="en")
    pages = {(p.lang, p.key): p for p in result.site.pages}
    de, ru = pages[("de", "case")], pages[("ru", "case")]
    assert de.meta.image == "media/case-en.png" and "image" in de.inherited
    assert de.meta.image_alt == "Folie de" and "image_alt" not in de.inherited
    assert ru.meta.image == "media/case-ru.png" and not ru.inherited
    assert de.cover_source(result.config)[0] == "media/case-en.png"


def test_inherited_cover_brings_the_main_alt_when_the_language_has_none(site):
    path = site / "content" / "de" / "case.md"
    path.write_text(_md("Fall"), encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    de = next(p for p in result.site.pages if (p.lang, p.key) == ("de", "case"))
    assert de.meta.image_alt == "Slide en" and "image_alt" in de.inherited
    assert not [t for t in _warnings(result, "de/case.md") if "image_alt" in t]


# --- 3. check ----------------------------------------------------------------------------


def test_check_does_not_call_an_own_cover_a_mismatch(site):
    result = pipeline.check(site, notes_lang="en")
    for lang in ("ru", "de"):
        texts = [t for t in _warnings(result, _rel(site, lang)) if "image" in t]
        assert not texts, (lang, texts)


def test_check_still_warns_about_shared_fields(site):
    path = site / "content" / "ru" / "case.md"
    path.write_text(path.read_text(encoding="utf-8").replace("---\n\n", "order: 3\n---\n\n"))
    result = pipeline.check(site, notes_lang="en")
    texts = [t for t in _warnings(result, "ru/case.md") if "order" in t]
    assert texts and "image" not in texts[0]


def test_check_validates_the_own_cover_of_a_language(site):
    path = site / "content" / "ru" / "case.md"
    path.write_text(_md("Keis", image="media/nope-ru.png", image_alt="x"), encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    errors = [e for e in result.collector.errors if e.code == "E007"]
    assert errors and errors[0].path == "ru/case.md", errors
    assert "nope-ru" in errors[0].message.text("en")
    _no_cover_mismatch(result, "ru/case.md")


def test_check_validates_the_width_of_the_own_cover(site):
    _png(site / "media" / "narrow-ru.png", 600, 400)
    path = site / "content" / "ru" / "case.md"
    path.write_text(_md("Keis", image="media/narrow-ru.png", image_alt="x"), encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    assert any("narrow-ru" in t for t in _warnings(result, "ru/case.md"))
    _no_cover_mismatch(result, "ru/case.md")


def test_check_rejects_an_own_cover_outside_media(site):
    path = site / "content" / "ru" / "case.md"
    path.write_text(_md("Keis", image="media/../site.yaml", image_alt="x"), encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    assert any(e.code == "E024" and e.path == "ru/case.md" for e in result.collector.errors)
    _no_cover_mismatch(result, "ru/case.md")


def test_missing_alt_is_per_language(site):
    # своя обложка ru без своей подписи - замечание ru; de берёт обложку en без подписи
    (site / "content" / "ru" / "case.md").write_text(
        _md("Keis", image="media/case-ru.png"), encoding="utf-8"
    )
    (site / "content" / "en" / "case.md").write_text(
        _md("Case", image="media/case-en.png"), encoding="utf-8"
    )
    (site / "content" / "de" / "case.md").write_text(_md("Fall"), encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    for lang in ("en", "ru", "de"):
        assert any("image_alt" in t for t in _warnings(result, f"{lang}/case.md")), lang


def test_inherited_cover_points_the_missing_file_at_the_main_language(site):
    for lang, text in (("en", _md("Case", image="media/gone.png", image_alt="a")),):
        (site / "content" / lang / "case.md").write_text(text, encoding="utf-8")
    (site / "content" / "ru" / "case.md").write_text(_md("Keis"), encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    errors = [e for e in result.collector.errors if e.code == "E007"]
    # одна ошибка на файл, первым назван файл основного языка, где обложка объявлена;
    # ru и de взяли её у основного - они следом
    assert len(errors) == 1 and errors[0].path.startswith("en/case.md"), errors
    assert "2" in errors[0].path, errors


# --- 4. правка ---------------------------------------------------------------------------


def _ctx(root: Path):
    return ops.context(root, "en")


def _bytes(root: Path) -> dict[str, bytes]:
    return {lang: (root / "content" / lang / "case.md").read_bytes() for lang in LANGS}


def test_editing_the_main_cover_leaves_other_files_alone(site):
    _png(site / "media" / "case-en-2.png")
    # ru уже с копией той же обложки - остаётся как есть, байт в байт
    ru = site / "content" / "ru" / "case.md"
    ru.write_text(_md("Keis", image="media/case-en.png", image_alt="Slide ru"), "utf-8")
    before = _bytes(site)
    entity = ops.open_entity(_ctx(site), "case")
    ops.set_value(entity, "en", "image", "media/case-en-2.png")
    saved = ops.save(entity)
    after = _bytes(site)
    assert saved.written == ["content/en/case.md"]
    assert after["ru"] == before["ru"] and after["de"] == before["de"]
    assert b"case-en-2.png" in after["en"]
    result = pipeline.check(site, notes_lang="en")
    de = next(p for p in result.site.pages if (p.lang, p.key) == ("de", "case"))
    assert de.meta.image == "media/case-en-2.png"


def test_editing_the_main_cover_with_answers_leaves_other_files_alone(site, tmp_path):
    _png(site / "media" / "case-en-2.png")
    before = _bytes(site)
    answers = tmp_path / "a.yaml"
    answers.write_text("en:\n  image: media/case-en-2.png\n", encoding="utf-8")
    result = run("page", "add", "case", site, "--answers", answers)
    assert result.exit_code == 0, result.output
    after = _bytes(site)
    assert after["ru"] == before["ru"] and after["de"] == before["de"]
    assert after["en"] != before["en"]


def test_a_language_may_set_its_own_cover(site):
    _png(site / "media" / "case-de.png")
    entity = ops.open_entity(_ctx(site), "case")
    ops.set_value(entity, "de", "image", "media/case-de.png")  # не E039
    ops.save(entity)
    text = (site / "content" / "de" / "case.md").read_text(encoding="utf-8")
    assert "image: media/case-de.png" in text
    assert (site / "content" / "en" / "case.md").read_text("utf-8").count("case-en.png") == 1


def test_clearing_the_cover_of_a_language_returns_to_the_main_one(site):
    entity = ops.open_entity(_ctx(site), "case")
    ops.set_value(entity, "ru", "image", None)
    ops.save(entity)
    text = (site / "content" / "ru" / "case.md").read_text(encoding="utf-8")
    assert not re.search(r"^image:", text, re.M) and "image_alt: Slide ru" in text
    result = pipeline.check(site, notes_lang="en")
    ru = next(p for p in result.site.pages if (p.lang, p.key) == ("ru", "case"))
    assert ru.meta.image == "media/case-en.png"


def test_shared_fields_still_go_to_every_file(site):
    entity = ops.open_entity(_ctx(site), "case")
    ops.set_value(entity, "en", "order", 5)
    ops.save(entity)
    for lang in LANGS:
        assert "order: 5" in (site / "content" / lang / "case.md").read_text("utf-8"), lang
    with pytest.raises(Exception) as caught:
        ops.set_value(ops.open_entity(_ctx(site), "case"), "de", "order", 6)
    assert getattr(caught.value, "code", None) == "E039"


def test_new_translation_does_not_copy_the_cover(site, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text(
        "en:\n  title: Fresh\n  h1: Fresh page\n  description: About it\n"
        "  image: media/case-en.png\n  image_alt: Slide\n"
        "ru:\n  title: Svezh\n  h1: Svezhaya\n  description: O nei\n",
        encoding="utf-8",
    )
    result = run("page", "add", "fresh", site, "--answers", answers)
    assert result.exit_code == 0, result.output
    for lang in ("ru", "de"):
        head = (site / "content" / lang / "fresh.md").read_text("utf-8").split("---")[1]
        assert not re.search(r"^image(_alt)?:", head, re.M), (lang, head)
    checked = pipeline.check(site, drafts=True, notes_lang="en")
    pages = {(p.lang, p.key): p for p in checked.site.pages}
    assert pages[("de", "fresh")].meta.image == "media/case-en.png"
    # ru не перевёл подпись: копия с пометкой, подпись основного - при сборке
    assert pages[("ru", "fresh")].meta.translation == "pending"


def test_translation_asks_alt_for_an_inherited_cover(site):
    entity = ops.open_entity(_ctx(site), "case")
    (site / "content" / "de" / "case.md").unlink()
    entity = ops.open_entity(_ctx(site), "case")
    io, out = _io([])
    console.Console(entity, io, "en").translate("de")
    asked = [line.strip() for line in out]
    assert any(line.startswith("image -") for line in asked), out
    assert any(line.startswith("image_alt") for line in asked), out
    assert "Enter - as on the main language" in " ".join(out)
    assert not re.search(r"^image(_alt)?:", ops.page_of(entity, "de").text, re.M)


def _io(answers: list[str]):
    out: list[str] = []
    feed = iter(answers)
    return console.Io(
        lambda prompt: (out.append(prompt), next(feed, ""))[1],
        lambda *a, **k: out.append(str(a[0]) if a else ""),
    ), out


def test_console_shows_the_main_cover_as_the_default(site):
    (site / "content" / "de" / "case.md").write_text(_md("Fall"), encoding="utf-8")
    entity = ops.open_entity(ops.context(site, "ru"), "case")
    item = next(f for f in ops.fields_of(entity, "de") if f.path == "image")
    assert ops.inherits(item) and ops.own_value(item) and not ops.shared(item)
    assert item.default == "media/case-en.png"
    io, out = _io([""])
    assert console.Console(entity, io, "ru").field("de", item) is False
    assert "Enter - как на основном языке" in [line.strip() for line in out]
    assert any("[media/case-en.png]" in line for line in out), out


# --- 5. --dump и --answers ----------------------------------------------------------------


def test_dump_shows_the_cover_of_a_language_only_from_its_file(site, tmp_path):
    result = run("page", "add", "case", site, "--dump")
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(result.output)
    assert data["en"]["image"] == "media/case-en.png"
    assert data["ru"]["image"] == "media/case-ru.png"
    assert "image" not in data["de"] and data["de"]["image_alt"] == "Folie de"


def test_dump_then_answers_changes_nothing(site, tmp_path):
    before = _bytes(site)
    result = run("page", "add", "case", site, "--dump")
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(result.output)
    assert data["ru"]["image"] == "media/case-ru.png" and "image" not in data["de"]
    answers = tmp_path / "dump.yaml"
    answers.write_text(result.output, encoding="utf-8")
    again = run("page", "add", "case", site, "--answers", answers)
    assert again.exit_code == 0, again.output
    assert _bytes(site) == before


# --- 6. студия ----------------------------------------------------------------------------


def test_studio_shows_the_cover_on_other_languages(site):
    entity = ops.open_entity(studio.context(site, "ru"), "case")
    state = studio.state(entity, "ru")
    de = {f["path"]: f for f in state["fields"]["de"]}
    assert de["image"]["inherits"] is True
    assert de["image"]["value"] is None and de["image"]["default"] == "media/case-en.png"
    assert "image_alt" in de and "order" not in de
    js = (Path(studio.__file__).parent / "studio.js").read_text(encoding="utf-8")
    assert "пусто - как на основном языке" in js and "f.inherits" in js


# --- 7. describe -------------------------------------------------------------------------


def test_describe_marks_the_cover_as_own_per_language(site):
    theme, config = describe.load(site)
    data = describe.contract(theme, config, "en")
    service = {f["name"]: f for f in data["service"]["page"]}
    assert service["image"]["inherits"] and service["og_image"]["inherits"]
    assert not service["image_alt"]["inherits"] and not service["order"]["inherits"]


# --- 8. своё поле типа с translatable ------------------------------------------------------


def _own_field(data, **extra):
    field = {"name": "slide", "type": "image", "hint_ru": "Слайд", "hint_en": "Slide"}
    field.update(extra)
    data["types"]["page"].setdefault("fields", []).append(field)


def test_theme_field_translatable_image_inherits(site, tmp_path):
    _theme(site, lambda data: _own_field(data, translatable=True))
    for name in ("slide-en", "slide-ru"):
        _png(site / "media" / f"{name}.png")
    content = site / "content"
    for lang, extra in (("en", "slide-en"), ("ru", "slide-ru")):
        path = content / lang / "case.md"
        path.write_text(
            path.read_text("utf-8").replace("---\n\n", f"slide: media/{extra}.png\n---\n\n")
        )
    result = pipeline.check(site, notes_lang="en")
    assert not result.collector.errors, [e.message for e in result.collector.errors]
    pages = {(p.lang, p.key): p for p in result.site.pages}
    assert pages[("de", "case")].meta.get("slide") == "media/slide-en.png"
    assert "slide" in pages[("de", "case")].inherited
    assert pages[("ru", "case")].meta.get("slide") == "media/slide-ru.png"
    assert not [t for t in _warnings(result, "ru/case.md") if "slide" in t]
    # describe, редактор, --dump
    theme, config = describe.load(site)
    page_type = next(
        t for t in describe.contract(theme, config, "en")["types"] if t["name"] == "page"
    )
    slide = next(f for f in page_type["fields"] if f["name"] == "slide")
    assert slide["translatable"] is True
    entity = ops.open_entity(_ctx(site), "case")
    item = next(f for f in ops.fields_of(entity, "de") if f.path == "slide")
    assert ops.inherits(item) and item.default == "media/slide-en.png"
    ops.set_value(entity, "de", "slide", "media/slide-ru.png")  # не E039
    dumped = yaml.safe_load(run("page", "add", "case", site, "--dump").output)
    assert dumped["ru"]["slide"] == "media/slide-ru.png" and "slide" not in dumped["de"]
    # новая копия языка поле не копирует
    answers = tmp_path / "a.yaml"
    answers.write_text(
        "en:\n  title: Fresh\n  h1: Fresh page\n  description: About it\n"
        "  slide: media/slide-en.png\n",
        encoding="utf-8",
    )
    assert run("page", "add", "fresh", site, "--answers", answers).exit_code == 0
    head = (content / "de" / "fresh.md").read_text("utf-8").split("---")[1]
    assert not re.search(r"^slide:", head, re.M), head


def test_theme_field_without_the_flag_stays_shared(site):
    _theme(site, lambda data: _own_field(data))
    _png(site / "media" / "slide-en.png")
    _png(site / "media" / "slide-ru.png")
    for lang, name in (("en", "slide-en"), ("ru", "slide-ru"), ("de", "slide-en")):
        path = site / "content" / lang / "case.md"
        path.write_text(
            path.read_text("utf-8").replace("---\n\n", f"slide: media/{name}.png\n---\n\n")
        )
    result = pipeline.check(site, notes_lang="en")
    assert any("slide" in t for t in _warnings(result, "ru/case.md"))
    entity = ops.open_entity(_ctx(site), "case")
    item = next(f for f in ops.fields_of(entity, "en") if f.path == "slide")
    assert ops.shared(item) and not ops.inherits(item)


@pytest.mark.parametrize("kind", ["number", "enum", "date", "flag", "ref"])
def test_theme_field_translatable_other_types_inherit(site, kind):
    values = {
        "number": (3, 4),
        "enum": ("a", "b"),
        "date": ("2025-01-02", "2025-02-03"),
        "flag": (True, False),
        "ref": ("case", "index"),
    }[kind]
    extra = {"values": ["a", "b"]} if kind == "enum" else {}
    _theme(site, lambda data: _own_field(data, type=kind, translatable=True, **extra))
    for lang, value in (("en", values[0]), ("ru", values[1])):
        path = site / "content" / lang / "case.md"
        text = path.read_text("utf-8").replace("---\n\n", f"slide: {json.dumps(value)}\n---\n\n")
        path.write_text(text, encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    pages = {(p.lang, p.key): p for p in result.site.pages}
    assert str(pages[("de", "case")].meta.get("slide")) == str(values[0])
    assert str(pages[("ru", "case")].meta.get("slide")) == str(values[1])
    assert not [t for t in _warnings(result, "ru/case.md") if "slide" in t]


def test_translatable_on_a_text_field_is_a_warning_not_an_error(site):
    _theme(site, lambda data: _own_field(data, type="text", translatable=True))
    result = pipeline.check(site, notes_lang="en")
    assert not result.collector.errors, [e.message for e in result.collector.errors]
    texts = [w.message.text("en") for w in result.collector.warnings]
    assert any("types.page.fields.slide" in t and "translatable" in t for t in texts), texts
    entity = ops.open_entity(_ctx(site), "case")
    item = next(f for f in ops.fields_of(entity, "de") if f.path == "slide")
    assert ops.translatable(item) and not ops.inherits(item)
