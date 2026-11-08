"""Вывод в терминал без управляющих последовательностей из текста темы и сайта (ошибка 5).

Подсказка темы или заголовок страницы с `ESC ] 52 ; c ; … BEL` (запись в буфер
обмена) или `ESC [ 2 J` (стереть экран) печатается видимым `\\x1b`, а не
исполняется - во всех командах сразу (`heron.term`, поток вывода команды).
Своё оформление движка (жирный, цвет) в терминале остаётся. `check --theme`
называет такие символы в тексте темы ошибкой `E044`.
"""

from __future__ import annotations

import io
import os
import pty
import re
import subprocess
import sys

import click
import pytest
from click.testing import CliRunner

from heron import term
from heron.cli import main
from heron.core import build as pipeline
from heron.scaffold import create

OSC52 = "\x1b]52;c;SGVsbG8=\x07"
CLEAR = "\x1b[2J"


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    create(root, name="Demo", languages=["ru", "en"], notes="en", demo=True)
    theme = root / "theme" / "theme.yaml"
    text = theme.read_text("utf-8")
    hint = '"The intro block - the text before the first ## heading with an anchor"'
    assert hint in text
    theme.write_text(text.replace(hint, '"Intro \\e]52;c;SGVsbG8=\\a block \\e[2J"', 1), "utf-8")
    page = root / "content" / "ru" / "blocks.md"
    words = page.read_text("utf-8")
    owned = 'nav_title: "Blocks \\e]0;owned\\a"'
    page.write_text(re.sub(r"(?m)^nav_title: .*$", lambda _m: owned, words, count=1), "utf-8")
    return root


def run(*args):
    return CliRunner().invoke(main, [str(a) for a in args])


def test_clean_shows_controls_instead_of_running_them():
    assert term.clean(f"a{OSC52}b") == "a\\x1b]52;c;SGVsbG8=\\x07b"
    assert term.clean("tab\tline\r\nnext\x9b2J") == "tab\tline\nnext\\x9b2J"
    assert term.controls(f"{OSC52}{CLEAR}") == ["\\x1b", "\\x07"]


class Tty(io.StringIO):
    def __init__(self, tty: bool) -> None:
        super().__init__()
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


@pytest.mark.parametrize("tty", [True, False])
def test_the_stream_keeps_only_the_engines_own_styling(tty):
    inner = Tty(tty)
    stream = term.Stream(inner)
    with term.guarded():
        styled = click.style("bold", bold=True)
    stream.write(styled + " " + click.style(f"theme {OSC52}", fg="red") + term.CR + term.EL)
    out = inner.getvalue()
    assert "\x1b]52" not in out and "\x07" not in out
    assert "\\x1b]52" in out
    if tty:
        assert "\x1b[1mbold" in out and out.endswith("\r\x1b[K")
    else:
        assert "\x1b" not in out and "\r" not in out


@pytest.mark.parametrize(
    "args",
    [("describe",), ("describe", "page"), ("page", "list"), ("page", "add", "blocks")],
)
def test_commands_print_theme_and_content_text_without_controls(site, monkeypatch, args):
    monkeypatch.chdir(site)
    result = run(*args)
    assert result.exit_code == 0, result.output
    assert "\x1b" not in result.output and "\x07" not in result.output
    if args == ("describe",):
        assert "\\x1b]52" in result.output


def test_a_real_terminal_gets_colors_but_not_the_themes_sequences(site):
    """Настоящий терминал (pty): жирный заголовок движка есть, ESC из текста - видимый."""
    leader, follower = pty.openpty()
    env = dict(os.environ, HERON_NOTES="en", TERM="xterm", COLUMNS="160")
    code = "from heron.cli import main; main()"
    done = subprocess.run(
        [sys.executable, "-c", code, "page", "list", str(site)],
        stdin=follower,
        stdout=follower,
        stderr=follower,
        env=env,
        timeout=120,
        check=False,
    )
    os.close(follower)
    chunks = []
    while True:
        try:
            chunk = os.read(leader, 65536)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    os.close(leader)
    out = b"".join(chunks).decode("utf-8", "replace")
    assert done.returncode == 0, out
    assert "\x1b[1m" in out  # оформление движка
    assert "\x1b]0;" not in out and "\\x1b]0;owned\\x07" in out


def test_check_theme_reports_controls_in_theme_text(site):
    result = pipeline.check(site, theme_demo=True, notes_lang="en")
    found = [e for e in result.collector.errors if e.code == "E044"]
    paths = {e.path for e in found}
    assert "theme/theme.yaml" in paths, [e.message.text("en") for e in found]
    assert "content/ru/blocks.md" in paths
    text = " ".join(e.message.text("en") for e in found)
    assert "\\x1b" in text and "\\x07" in text and "hint_en" in text
    # без --theme - не ошибка: терминал защищает сам движок
    plain = pipeline.check(site, notes_lang="en")
    assert not [e for e in plain.collector.errors if e.code == "E044"]


def test_a_clean_theme_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "clean"
    create(root, name="Demo", languages=["ru", "en", "uk"], notes="ru", demo=True)
    result = pipeline.check(root, theme_demo=True, notes_lang="en")
    assert not [e for e in result.collector.errors if e.code == "E044"]
