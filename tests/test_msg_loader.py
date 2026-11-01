"""Сообщения contracts/loader.py и frontmatter.py на ключах heron/texts/loader.py (E15.S2.T11)."""

import re

import pytest
from pydantic import BaseModel, ConfigDict

from heron.contracts.frontmatter import PageMeta
from heron.contracts.loader import build, read_yaml
from heron.core.errors import HeronError
from heron.messages import Msg

CYRILLIC = re.compile("[А-Яа-яЁё]")


class Site(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    port: int = 1


def _fail(tmp_path, data):
    with pytest.raises(HeronError) as caught:
        build(Site, data, tmp_path / "site.yaml")
    return caught.value


def test_build_one_complaint_ru_is_old_text_en_has_no_cyrillic(tmp_path):
    err = _fail(tmp_path, {})
    assert isinstance(err.message, Msg)
    assert err.message.text("ru") == "не проходит проверку:\n    name: поле обязательно, его нет в файле"
    assert err.message.text("en") == (
        "failed validation:\n    name: the field is required and is missing from the file"
    )
    assert not CYRILLIC.search(err.message.text("en"))


def test_build_many_complaints_two_at_once(tmp_path):
    err = _fail(tmp_path, {"typo": 1})
    ru = err.message.text("ru")
    assert ru == (
        "не проходит проверку (2):\n"
        "    name: поле обязательно, его нет в файле\n"
        "    typo: такого поля нет в контракте — опечатка в имени?"
    )
    en = err.message.text("en")
    assert en.startswith("failed validation (2):\n")
    assert not CYRILLIC.search(en)
    assert str(err.message) == ru


def test_read_yaml_errors_bilingual(tmp_path):
    cases = {
        "missing.yaml": None,
        "empty.yaml": b"",
        "list.yaml": b"- a\n- b\n",
        "bad.yaml": b"a: [1,\n",
        "binary.yaml": b"\xff\xfe\x00\xc3\x28",
    }
    ru_expected = {
        "missing.yaml": "файл не найден",
        "empty.yaml": "файл пуст",
        "list.yaml": "ожидался набор ключей, а в файле list",
        "binary.yaml": "файл не в кодировке UTF-8",
    }
    for name, body in cases.items():
        path = tmp_path / name
        if body is not None:
            path.write_bytes(body)
        with pytest.raises(HeronError) as caught:
            read_yaml(path)
        err = caught.value
        assert isinstance(err.message, Msg)
        assert not CYRILLIC.search(err.message.text("en")), name
        if err.hint is not None:
            assert not CYRILLIC.search(err.hint.text("en")), name
        if name in ru_expected:
            assert err.message.text("ru") == ru_expected[name]
        if name == "bad.yaml":
            assert err.message.text("ru").startswith("битый YAML: ")
            assert err.message.text("en").startswith("broken YAML: ")
            assert err.line is not None
            assert err.hint.text("ru").startswith("проверьте отступы")
        if name == "binary.yaml":
            assert err.hint.text("ru").startswith("пересохраните файл в UTF-8")


def test_frontmatter_validator_messages_keep_ru_and_translate(tmp_path):
    data = {"title": " ", "h1": "h", "description": "d", "slug": "Bad_Slug", "redirect_from": ["x"]}
    with pytest.raises(HeronError) as caught:
        build(PageMeta, data, tmp_path / "a.md")
    msg = caught.value.message
    ru = msg.text("ru")
    assert "title: Value error, поле не может быть пустым" in ru
    assert "slug: Value error, слаг — латиница, цифры и дефис, без слешей и подчёркиваний" in ru
    assert "redirect_from: Value error, 'x' — ожидается путь от корня, например /services/old/" in ru
    en = msg.text("en")
    assert "title: the field must not be empty" in en
    assert "'x' - a path from the root is expected" in en
    assert not CYRILLIC.search(en)


def test_lint_warnings_are_msg(tmp_path):
    meta = PageMeta(title="t" * 70, h1="t" * 70, description="d" * 160, image="a.png")
    out = meta.lint("a.md")
    assert len(out) == 4
    for warning in out:
        assert isinstance(warning.message, Msg)
        assert not CYRILLIC.search(warning.message.text("en"))
    assert out[0].message.text("ru") == "title длиннее 60 знаков (70)"
    assert out[1].message.text("ru") == "description длиннее 155 знаков (160)"
    assert out[2].message.text("ru") == "картинка задана, а image_alt нет"
