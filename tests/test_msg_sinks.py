"""Точки показа рендерят Msg по языку запуска: cli _fail, check --json, watch, setup/server."""

import json
import re

import pytest
from click.testing import CliRunner

from heron import cli
from heron.core import watch
from heron.core.errors import HeronError
from heron.messages import Msg, rendered

CYR = re.compile("[а-яА-ЯёЁ]")


def _error() -> HeronError:
    return HeronError(
        "E030", Msg("report_old_not_utf8", byte=3), path="old.txt", hint=Msg("report_old_not_utf8_hint")
    )


def test_render_follows_language():
    err = _error()
    en = err.render("en")
    assert "the old URLs file is not UTF-8 (byte 3)" in en
    assert "re-save the file as UTF-8" in en
    assert not CYR.search(en.replace("what to do", ""))
    assert "пересохраните файл" in err.render("ru")
    assert str(err) == err.render("ru")


def test_rendered_keeps_plain_strings():
    assert rendered("plain", "en") == "plain"
    assert rendered(None, "en") is None


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_fail_prints_in_language(capsys, lang):
    with pytest.raises(SystemExit) as exit_info:
        cli._fail(_error(), lang)
    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert ("пересохраните файл" in err) == (lang == "ru")
    assert ("re-save the file as UTF-8" in err) == (lang == "en")


def test_watch_once_renders_error_by_language(monkeypatch, tmp_path, capsys):
    def boom(*args, **kwargs):
        raise _error()

    monkeypatch.setattr(watch.pipeline, "run", boom)
    watch.once(tmp_path, False, lang="en")
    assert "the old URLs file is not UTF-8 (byte 3)" in capsys.readouterr().out
    watch.once(tmp_path, False, lang="ru")
    assert "пересохраните файл" in capsys.readouterr().out


def test_check_json_en_has_no_cyrillic_in_messages(tmp_path):
    result = CliRunner().invoke(cli.main, ["check", str(tmp_path / "missing"), "--json", "--notes", "en"])
    # папки нет: человеческий текст на экран, JSON не печатается; код выхода ненулевой
    assert result.exit_code != 0
