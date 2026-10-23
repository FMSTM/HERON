"""Инлайн-код через перенос строки — пример, а не ссылка на файл."""

from __future__ import annotations

from pathlib import Path

import pytest

from heron.core import build as pipeline
from heron.core.parser.markdown import without_code
from heron.scaffold import create


def _shape(text: str) -> list[int]:
    return [len(line) for line in text.split("\n")]


@pytest.mark.parametrize(
    "text",
    [
        "Write `an image like\n![x](media/missing.png)` in the text.",
        "- item with ``two\n  ![x](media/missing.png)`` ticks",
        "> quote `with\n> ![x](media/missing.png)` code",
        "| a | `b` |\n|---|---|\n| `![x](media/missing.png)` | d |",
    ],
)
def test_multiline_span_is_blanked_and_lines_are_kept(text):
    out = without_code(text)
    assert "media/missing.png" not in out
    assert _shape(out) == _shape(text)


def test_unclosed_backtick_does_not_hide_the_rest():
    text = "a ` lone\n\n![x](media/real.png)"
    assert "media/real.png" in without_code(text)


def test_span_does_not_cross_a_paragraph():
    text = "a `open\n\n![x](media/real.png) `close"
    assert "media/real.png" in without_code(text)


def test_build_does_not_ask_for_an_image_from_a_code_example(tmp_path: Path):
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True)
    index = root / "content" / "en" / "index.md"
    index.write_text(
        index.read_text("utf-8")
        + "\n\n## Example {#example}\n\nWrite `an image like\n![x](media/missing.png)` here.\n",
        encoding="utf-8",
    )
    result = pipeline.run(root, strict=True)
    assert not result.failed, [e.message for e in result.collector.errors]
    # а настоящая отсутствующая картинка по-прежнему ошибка
    index.write_text(
        index.read_text("utf-8") + "\n![y](media/really-missing.png)\n", encoding="utf-8"
    )
    result = pipeline.run(root, strict=True)
    assert "E007" in {e.code for e in result.collector.errors}
