"""Сообщения blocks, hooks, data: ru прежний, en без кириллицы."""

import re
from types import SimpleNamespace

import pytest

from heron.core import data, hooks
from heron.core.errors import Collector, HeronError
from heron.core.parser import blocks
from heron.messages import Msg

CYR = re.compile("[а-яА-Я]")


def test_hook_unknown() -> None:
    with pytest.raises(ValueError) as ei:
        hooks.Hooks().on("nope", lambda: None)
    msg = ei.value.args[0]
    assert isinstance(msg, Msg)
    assert not CYR.search(msg.text("en"))
    assert msg.text("ru").startswith("неизвестный хук 'nope'; доступны: ")
    assert msg.text("ru").endswith("block:<имя>")


def test_data_symlink_outside(tmp_path) -> None:
    out = tmp_path / "outside.yaml"
    out.write_text("a: 1\n")
    root = tmp_path / "data"
    root.mkdir()
    (root / "x.yaml").symlink_to(out)
    with pytest.raises(HeronError) as ei:
        data.load(root)
    assert ei.value.message.text("ru") == "символическая ссылка ведёт за пределы data/"
    assert not CYR.search(ei.value.message.text("en"))
    col = Collector()
    data.load(root, col)
    err = col.errors[0]
    assert not CYR.search(err.message.text("en")) and not CYR.search(err.hint.text("en"))
    assert err.hint.text("ru") == "положите сам файл в data/ вместо ссылки на него"


def test_data_unreadable(tmp_path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "bad.yaml").write_text("a: [\n")
    col = Collector()
    data.load(root, col)
    msg = col.errors[0].message
    assert msg.text("ru").startswith("справочник не читается: ")
    assert msg.text("en").startswith("the data file cannot be read: ")


def test_blocks_messages_ru_and_en() -> None:
    cases = [
        (Msg("blocks_unknown_class", section="'a'", name="'z'"),
         "секция 'a': неизвестный класс 'z', определяю по содержимому"),
        (Msg("blocks_stray_lines", section="'a'", stray=2),
         "секция 'a': строки без разделителя «|» пропущены (2)"),
        (Msg("blocks_class_mismatch", section="'a'", name="'z'"),
         "секция 'a': класс 'z' не подходит к содержимому, вывожу прозой"),
        (Msg("blocks_intro_long", count=3),
         "вводный блок длиннее двух абзацев: третий и далее (3) не попадут в шаблон"),
    ]
    for msg, ru in cases:
        assert msg.text("ru") == ru == str(msg)
        assert not CYR.search(msg.text("en"))


def test_no_cyrillic_literals_left() -> None:
    import ast
    import inspect

    for mod in (blocks, hooks, data):
        src = inspect.getsource(mod)
        tree = ast.parse(src)
        docs = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
        }
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                if CYR.search(n.value):
                    assert n.value == "контент" or "noqa" in src.splitlines()[n.lineno - 1], n.value
