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
FILES = [
    ROOT / "cli.py",
    ROOT / "core" / "report.py",
    ROOT / "core" / "render" / "signature.py",
    ROOT / "docs.py",
    ROOT / "contracts" / "schemas.py",
]


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


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_heron_docs_output_has_no_dash(lang):
    from click.testing import CliRunner

    from heron.cli import main

    result = CliRunner().invoke(main, ["docs", "--lang", lang])
    assert result.exit_code == 0, result.output
    printed = [ln for ln in result.output.splitlines() if "heron docs" in ln or ln.startswith("- `")]
    assert printed
    assert not [ln for ln in printed if any(d in ln for d in DASHES)]


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_frontmatter_schema_has_no_dash(lang):
    import json

    from heron.contracts import schemas

    dumped = json.dumps(schemas.frontmatter_schema(lang), ensure_ascii=False)
    assert "redirect_from" in dumped
    if lang == "ru":
        assert not any(d in dumped for d in DASHES)


def test_detector_catches_dash_in_docs_line_126_mutation():
    src = (ROOT / "docs.py").read_text(encoding="utf-8")
    mutated = src.replace("что движок уже умеет - по задачам", "что движок уже умеет — по задачам")
    assert mutated != src
    assert dashed_literals(mutated)


SETUP_FILES = [
    ROOT / "setup" / "answers.py",
    ROOT / "setup" / "reasons.py",
    ROOT / "setup" / "__init__.py",
]


@pytest.mark.parametrize("path", SETUP_FILES, ids=lambda p: p.name)
def test_setup_literals_have_no_dash_except_separators(path):
    src = path.read_text(encoding="utf-8")
    # SEPARATORS - разбор ввода автора: тире там остаются (исключение с причиной)
    bad = [(n, t) for n, t in dashed_literals(src) if not src.splitlines()[n - 1].startswith("SEPARATORS =")]
    assert not bad, f"{path.name}: тире в литералах: {bad}"


def test_setup_vocab_hints_and_labels_have_no_dash():
    import yaml

    data = yaml.safe_load((ROOT / "setup" / "vocab.yaml").read_text(encoding="utf-8"))
    found: list[str] = []

    def walk_all(node, in_text=False):
        if isinstance(node, dict):
            for k, v in node.items():
                walk_all(v, in_text or k in ("hint", "label"))
        elif isinstance(node, list):
            for v in node:
                walk_all(v, in_text)
        elif isinstance(node, str) and in_text and any(d in node for d in DASHES):
            found.append(node)

    walk_all(data)
    assert not found, found
