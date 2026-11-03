"""Msg, MsgError, rendered и say с позиционными lang и key (E15.S2, раздел 2 плана)."""

import copy
import pickle
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from heron import messages
from heron.messages import LINES_JOIN, Msg, MsgError, rendered, say

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def table(monkeypatch):
    """Тестовые шаблоны, не задевающие настоящий словарь."""
    ru = {
        "t_plain": "ссылка {url} не ведёт",
        "t_outer": "не прошло: {inner}",
        "t_list": "жалобы:\n    {lines}",
        "t_meta": "язык {lang}, ключ {key}",
        "t_n": "{n} {n:файл|файла|файлов}",
    }
    en = {
        "t_plain": "link {url} leads nowhere",
        "t_outer": "failed: {inner}",
        "t_list": "complaints:\n    {lines}",
        "t_meta": "lang {lang}, key {key}",
        "t_n": "{n} {n:file|files}",
    }
    monkeypatch.setitem(messages.TEXT, "ru", {**messages.TEXT["ru"], **ru})
    monkeypatch.setitem(messages.TEXT, "en", {**messages.TEXT["en"], **en})


def test_msg_is_russian_string_with_key_and_fields(table):
    msg = Msg("t_plain", url="/a")
    assert isinstance(msg, str)
    assert msg == "ссылка /a не ведёт"
    assert msg.key == "t_plain" and msg.fields == {"url": "/a"}
    assert msg.text("en") == "link /a leads nowhere"
    assert msg.text("ru") == "ссылка /a не ведёт"


def test_unknown_key_raises(table):
    with pytest.raises(KeyError):
        Msg("t_no_such_key")


def test_nested_msg_field_rendered_in_both_languages(table):
    outer = Msg("t_outer", inner=Msg("t_plain", url="/x"))
    assert outer == "не прошло: ссылка /x не ведёт"
    assert outer.text("en") == "failed: link /x leads nowhere"


def test_list_field_joined_with_lines_join(table):
    lines = [Msg("t_plain", url="/a"), Msg("t_plain", url="/b")]
    msg = Msg("t_list", lines=lines)
    assert msg == "жалобы:\n    " + LINES_JOIN.join(["ссылка /a не ведёт", "ссылка /b не ведёт"])
    assert msg.text("en") == "complaints:\n    link /a leads nowhere\n    link /b leads nowhere"
    assert Msg("t_list", lines=tuple(lines)) == msg


def test_plural_form_follows_language(table):
    assert Msg("t_n", n=2).text("ru") == "2 файла"
    assert Msg("t_n", n=2).text("en") == "2 files"


@pytest.mark.parametrize(
    "clone", [copy.copy, copy.deepcopy, lambda m: pickle.loads(pickle.dumps(m))]
)
def test_copy_and_pickle_keep_key_and_fields(table, clone):
    msg = Msg("t_outer", inner=Msg("t_plain", url="/x"))
    other = clone(msg)
    assert isinstance(other, Msg)
    assert other.key == "t_outer"
    assert other == msg
    assert other.text("en") == "failed: link /x leads nowhere"
    assert isinstance(other.fields["inner"], Msg)


def test_fields_named_lang_and_key_in_say(table):
    assert say("en", "t_meta", lang="ru", key="x") == "lang ru, key x"
    assert say("ru", "t_meta", lang="en", key="y") == "язык en, ключ y"


def test_fields_named_lang_and_key_in_msg(table):
    msg = Msg("t_meta", lang="uk", key="k1")
    assert msg == "язык uk, ключ k1"
    assert msg.text("en") == "lang uk, key k1"
    assert msg.key == "t_meta"
    assert msg.fields == {"lang": "uk", "key": "k1"}


@pytest.mark.parametrize("clone", [copy.copy, lambda m: pickle.loads(pickle.dumps(m))])
def test_copy_and_pickle_keep_lang_and_key_fields(table, clone):
    other = clone(Msg("t_meta", lang="uk", key="k1"))
    assert other.key == "t_meta"
    assert other.fields == {"lang": "uk", "key": "k1"}
    assert other.text("en") == "lang uk, key k1"


def test_msg_error_carries_msg(table):
    error = MsgError("t_plain", url="/e")
    assert isinstance(error, ValueError)
    assert isinstance(error.args[0], Msg)
    assert str(error) == "ссылка /e не ведёт"
    assert error.args[0].text("en") == "link /e leads nowhere"


def test_msg_error_accepts_lang_and_key_fields(table):
    error = MsgError("t_meta", lang="ru", key="z")
    assert error.args[0].fields == {"lang": "ru", "key": "z"}
    assert error.args[0].text("en") == "lang ru, key z"


def test_rendered(table):
    msg = Msg("t_plain", url="/r")
    assert rendered(msg, "en") == "link /r leads nowhere"
    assert rendered(msg, "ru") == "ссылка /r не ведёт"
    assert rendered("plain", "en") == "plain"
    assert rendered(None, "en") is None


def test_kinds_has_redirects():
    assert messages.kind("en", "редиректы") == "redirects"


def test_existing_say_is_unchanged():
    assert say("ru", "sandbox_mutation", call="x.y") == messages.TEXT["ru"][
        "sandbox_mutation"
    ].format(call="x.y")


def test_texts_package_found_by_pkgutil():
    import pkgutil

    import heron.texts

    assert heron.texts.__name__ == "heron.texts"
    assert isinstance(heron.texts.load(), dict)
    names = {m.name for m in pkgutil.iter_modules(heron.texts.__path__)}
    assert set(heron.texts.groups()) == names


@pytest.mark.skipif(shutil.which("uv") is None, reason="нет uv: колесо собрать нечем")
def test_wheel_contains_texts(tmp_path):
    work = tmp_path / "src"
    shutil.copytree(
        ROOT,
        work,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".uvcache", "out", "dist", "__pycache__", ".*cache", "node_modules"
        ),
    )
    done = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "-q", "-o", str(tmp_path / "dist")],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr
    (wheel,) = (tmp_path / "dist").glob("heron-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert "heron/texts/__init__.py" in names
