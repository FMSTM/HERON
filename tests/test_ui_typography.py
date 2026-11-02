"""Строки интерфейса cli.py, report.py и подписи сборки: без длинного и короткого тире.

AGENTS.md, «Типографика»: текст, который видит человек, пишется с дефисом "-".
Комментарии и docstring не проверяются: их человек не видит.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

import pytest

import heron
from heron.core.render import signature

DASHES = ("—", "–")
ROOT = Path(heron.__file__).resolve().parent
FILES = [ROOT / "cli.py", ROOT / "core" / "report.py", ROOT / "core" / "render" / "signature.py"]


def _docstring_lines(source: str) -> set[int]:
    import ast

    lines: set[int] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                first = body[0].value
                lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def dashed_literals(source: str) -> list[tuple[int, str]]:
    """Строки (номер, текст) литералов и f-строк с тире, без docstring."""
    skip = _docstring_lines(source)
    found: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.STRING:
            if tok.start[0] in skip:
                continue
        elif tok.type != getattr(tokenize, "FSTRING_MIDDLE", -1):
            continue
        if any(d in tok.string for d in DASHES):
            found.append((tok.start[0], tok.string))
    return found


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_string_literals_have_no_long_or_short_dash(path):
    bad = dashed_literals(path.read_text(encoding="utf-8"))
    assert not bad, f"{path.name}: тире в литералах: {bad}"


def test_detector_catches_dash_in_fstring_and_plain_string():
    src = '"""doc — ok"""\na = "x — y"\nb = f"{a} – z"\n'
    assert [line for line, _ in dashed_literals(src)] == [2, 3]


def test_signature_comment_uses_hyphen():
    assert "Built with HERON - a fast static site generator by FAMOUS.TEAM" in signature.COMMENT
    assert not any(d in signature.COMMENT for d in DASHES)


def test_signature_mutation_is_detected(monkeypatch):
    mutated = signature.COMMENT.replace("HERON - a", "HERON — a")
    monkeypatch.setattr(signature, "COMMENT", mutated)
    assert "Built with HERON - a fast" not in signature.COMMENT
    assert any(d in signature.COMMENT for d in DASHES)


def test_report_lines_use_hyphen():
    src = (ROOT / "core" / "report.py").read_text(encoding="utf-8")
    assert "{code} - {len(pages)}" in src
    assert "{kind_label(lang, kind)} - {len(batch)}" in src
