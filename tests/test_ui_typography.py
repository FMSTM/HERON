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
    printed = [
        ln for ln in result.output.splitlines() if "heron docs" in ln or ln.startswith("- `")
    ]
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
    bad = [
        (n, t)
        for n, t in dashed_literals(src)
        if not src.splitlines()[n - 1].startswith("SEPARATORS =")
    ]
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


# --- Весь пакет heron/: обход всех *.py ---------------------------------------------------

# Исключения: файл (путь от heron/) -> причина. Тире там не видит человек как текст сайта.
WHOLE_FILE_EXCEPTIONS = {
    "modules/nginx.py": "комментарии генерируемого nginx-конфига",
    "setup/files.py": "комментарии генерируемых скриптов и workflow",
}
# Исключения по строке: (файл, начало строки) -> причина.
LINE_EXCEPTIONS = {
    ("core/parser/blocks.py", "LEAD_END"): "разбор: LEAD_END распознаёт тире в тексте автора",
    ("setup/answers.py", "SEPARATORS"): "разбор ввода: SEPARATORS распознаёт тире в ответах автора",
}


def _package_findings(root: Path = ROOT) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in WHOLE_FILE_EXCEPTIONS:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for n, _text in dashed_literals("\n".join(lines) + "\n"):
            line = lines[n - 1].lstrip()
            if any(rel == f and line.startswith(start) for (f, start) in LINE_EXCEPTIONS):
                continue
            found.append(f"{rel}:{n}")
    return found


def test_whole_package_literals_have_no_dash_except_listed():
    bad = _package_findings()
    assert not bad, "тире в литералах вне списка исключений: " + ", ".join(bad)


def test_exception_list_points_to_existing_files():
    for rel in WHOLE_FILE_EXCEPTIONS:
        assert (ROOT / rel).is_file(), rel
    for rel, start in LINE_EXCEPTIONS:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        assert any(ln.lstrip().startswith(start) for ln in lines), (rel, start)


def test_schemaorg_dictionary_is_not_walked():
    # schemaorg-29.3.json - словарь schema.org как есть, обход смотрит только *.py
    assert (ROOT / "schemaorg" / "schemaorg-29.3.json").is_file()


def test_messages_tables_and_groups_have_no_dash():
    from heron import messages
    from heron.texts import groups

    bad: list[str] = []
    for name in ("TEXT", "TITLES", "KINDS"):
        for lang, table in getattr(messages, name, {}).items():
            bad += [f"{name}.{lang}.{k}" for k, v in table.items() if any(d in v for d in DASHES)]
    for group, tables in groups().items():
        for lang, table in tables.items():
            bad += [f"{group}.{lang}.{k}" for k, v in table.items() if any(d in v for d in DASHES)]
    assert not bad, bad


def test_mutation_dash_in_cli_literal_is_found():
    src = (ROOT / "cli.py").read_text(encoding="utf-8")
    mutated = src + '\nBROKEN = "a — b"\n'
    assert dashed_literals(mutated)[-1][1].count("—") == 1


def test_mutation_dash_in_lead_end_is_allowed(tmp_path):
    (tmp_path / "core" / "parser").mkdir(parents=True)
    (tmp_path / "core" / "parser" / "blocks.py").write_text('LEAD_END = "—"\n', encoding="utf-8")
    assert _package_findings(tmp_path) == []
    (tmp_path / "cli.py").write_text('X = "—"\n', encoding="utf-8")
    assert _package_findings(tmp_path) == ["cli.py:1"]
