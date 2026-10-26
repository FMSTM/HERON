"""`heron page`: заготовка страницы целиком на языке пояснений сайта (E15.S1.T4: F03).

Тело заготовки — подсказки автору, как и SEO-блок над ним, поэтому оба на
языке `build.notes` (или HERON_NOTES), а не на языке страницы: страница
`content/en/` русскоязычного автора получает русские подсказки, которые он
заменит английским текстом.
"""

from __future__ import annotations

import re

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.scaffold import create
from heron.scaffold.page import BODY, write_page

CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")
# латиница в русской заготовке — только токены: TODO, имена ключей и типов
RU_TOKENS = {"TODO", "title", "h1", "description", "nav_title", "slug", "type", "about"}


def _site(tmp_path, notes, languages=("en",)):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=list(languages), notes=notes)
    return root


def _body(text):
    return text.split("---", 2)[2]


def test_body_tables_have_the_same_keys():
    assert set(BODY["ru"]) == set(BODY["en"])
    for words in BODY.values():
        assert words["heading"].startswith("TODO") and words["content"].startswith("TODO")


def test_english_site_gets_no_cyrillic(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site(tmp_path, "en")
    text = write_page(root, "page", "about").read_text(encoding="utf-8")
    assert not CYRILLIC.search(text), [line for line in text.splitlines() if CYRILLIC.search(line)]
    assert BODY["en"]["intro"] in text
    assert BODY["en"]["heading"] in text or "## " not in _body(text)


def test_russian_site_body_is_russian(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site(tmp_path, "ru")
    text = write_page(root, "page", "about").read_text(encoding="utf-8")
    body = _body(text)
    assert BODY["ru"]["intro"] in body
    for line in body.splitlines():
        plain = re.sub(r"\{#[\w-]+\}", " ", line)
        stray = [w for w in re.findall(r"[A-Za-z]{2,}", plain) if w not in RU_TOKENS]
        assert not stray, (line, stray)
    head = yaml.safe_load(text.split("---", 2)[1])
    assert head["description"] == BODY["ru"]["description"]


def test_page_of_another_language_keeps_the_notes_language(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site(tmp_path, "ru", languages=("ru", "en"))
    text = write_page(root, "page", "about", lang="en").read_text(encoding="utf-8")
    assert BODY["ru"]["intro"] in text
    assert BODY["en"]["intro"] not in text


@pytest.mark.parametrize("notes", ["ru", "en"])
def test_env_switches_the_body_with_the_seo_block(tmp_path, monkeypatch, notes):
    other = "en" if notes == "ru" else "ru"
    root = _site(tmp_path, other)
    monkeypatch.setenv("HERON_NOTES", notes)
    text = write_page(root, "page", "about").read_text(encoding="utf-8")
    assert BODY[notes]["intro"] in text
    assert BODY[other]["intro"] not in text
    assert bool(CYRILLIC.search(text)) is (notes == "ru")


def test_cli_page_in_english_site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(main, ["new", "site", "--notes", "en", "-y"]).exit_code == 0
    result = runner.invoke(main, ["page", "page", "about", "site"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "site" / "content" / "en" / "about.md").read_text(encoding="utf-8")
    assert "Вводный" not in text and not CYRILLIC.search(text)
