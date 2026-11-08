"""Что ответы, опросник и студия могут записать в поле (приёмка 0.3.0, ошибки 3, 4, 6).

- Неизвестное поле в `--answers` - `E039` до записи, а не новая строка в SEO-блоке.
- Неосновной язык правит только поля со своим значением (тексты, подписи, пометку
  перевода, свои прежние адреса); общие поля (тип, порядок, обложка, флаги, даты,
  свои поля темы без текста) - только основной язык, и его правка пишет их во все
  файлы. `check` предупреждает, если файлы языков расходятся в общих полях.
- Значение поля не начинает новую секцию (заголовок с якорем `{#…}`), а в
  однострочном поле нет перевода строки.
"""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from heron import studio
from heron.cli import main
from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.edit import entity as ops
from heron.scaffold import create

LANGS = ["ru", "en", "de"]


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=LANGS, notes="ru", demo=True)
    return root


def run(*args):
    return CliRunner().invoke(main, [str(a) for a in args])


def answer(site, tmp_path, data, key="blocks"):
    path = tmp_path / "answers.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return run("page", "add", key, site, "--answers", path, "-y")


def files(site, key="blocks"):
    return {lang: (site / "content" / lang / f"{key}.md").read_bytes() for lang in LANGS}


# --- 3. неизвестное поле -------------------------------------------------------------


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_an_unknown_field_is_e039_before_any_write(site, tmp_path, lang):
    before = files(site)
    result = answer(site, tmp_path, {lang: {"h1": "Новый", "titel": "x"}})
    assert result.exit_code != 0
    assert "E039" in result.output and "titel" in result.output
    assert files(site) == before


def test_an_unknown_section_field_is_e039(site, tmp_path):
    before = files(site)
    result = answer(site, tmp_path, {"ru": {"sections.intro.titel": "x"}})
    assert result.exit_code != 0 and "E039" in result.output
    assert files(site) == before


# --- 4. общие поля -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [("order", 5), ("type", "page"), ("published", False), ("noindex", True), ("menu", True)],
)
def test_another_language_cannot_set_a_shared_field(site, tmp_path, name, value):
    before = files(site)
    current = ops.open_entity(ops.context(site, "ru"), "blocks")
    shown = {f.path: f.value for f in ops.fields_of(current, "ru")}
    if shown.get(name) == value:
        value = 7 if name == "order" else not value
    result = answer(site, tmp_path, {"en": {name: value}})
    assert result.exit_code != 0, result.output
    assert "E039" in result.output and "ru" in result.output
    assert files(site) == before


def test_another_language_still_translates_its_texts(site, tmp_path):
    result = answer(site, tmp_path, {"en": {"title": "Blocks of the theme", "translation": None}})
    assert result.exit_code == 0, result.output
    assert b"Blocks of the theme" in files(site)["en"]


def test_a_shared_field_on_the_main_language_goes_to_every_file(site, tmp_path):
    result = answer(site, tmp_path, {"ru": {"order": 42}})
    assert result.exit_code == 0, result.output
    for lang in LANGS:
        front = yaml.safe_load(files(site)[lang].decode("utf-8").split("---", 2)[1])
        assert front["order"] == 42, lang


def test_the_studio_refuses_a_shared_field_on_another_language(site):
    with pytest.raises(HeronError) as caught:
        studio.save(
            site,
            {"target": {"kind": "page", "key": "blocks"}, "answers": {"en": {"order": 3}}},
            "en",
        )
    assert caught.value.code == "E039"


def test_check_warns_when_languages_disagree_on_shared_fields(site):
    path = site / "content" / "en" / "blocks.md"
    text = path.read_text("utf-8")
    assert "\norder: 2\n" in text or "\norder:" in text
    lines = ["order: 77" if line.startswith("order:") else line for line in text.split("\n")]
    if not any(line.startswith("order:") for line in text.split("\n")):
        lines.insert(1, "order: 77")
    path.write_text("\n".join(lines), encoding="utf-8")
    result = pipeline.check(site, notes_lang="en")
    found = [w for w in result.collector.warnings if w.path == "en/blocks.md"]
    texts = [w.message.text("en") for w in found]
    assert any("order" in t and "ru" in t for t in texts), texts
    # на чистом сайте такого предупреждения нет
    clean = site.parent / "clean"
    create(clean, name="Demo", languages=LANGS, notes="ru", demo=True)
    again = pipeline.check(clean, notes_lang="en")
    assert not [w for w in again.collector.warnings if "shared by every" in w.message.text("en")]


# --- 6. структура из значения поля ----------------------------------------------------


INJECTED = "Абзац.\n\n## Чужой блок {#evil}\n\nТекст."


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_a_markdown_field_cannot_start_a_section(site, tmp_path, lang):
    before = files(site)
    result = answer(site, tmp_path, {lang: {"sections.intro.text": INJECTED}})
    assert result.exit_code != 0, result.output
    assert "E039" in result.output and "{#" in result.output
    assert files(site) == before


def test_a_heading_without_an_anchor_is_fine_in_markdown(site, tmp_path):
    result = answer(
        site, tmp_path, {"ru": {"sections.intro.text": "Абзац.\n\n### Подзаголовок\n\nТекст."}}
    )
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "path", ["title", "h1", "description", "nav_title", "image_alt", "og_title"]
)
def test_a_single_line_field_refuses_a_line_break(site, tmp_path, path):
    before = files(site)
    result = answer(site, tmp_path, {"ru": {path: "Первая\nвторая"}})
    assert result.exit_code != 0, result.output
    assert "E039" in result.output
    assert files(site) == before


def test_another_language_cannot_add_a_section(site, tmp_path):
    before = files(site)
    result = answer(site, tmp_path, {"en": {"sections.extra.text": "Only in English."}})
    assert result.exit_code != 0, result.output
    assert "E039" in result.output and "extra" in result.output
    assert files(site) == before
