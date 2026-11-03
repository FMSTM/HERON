"""heron check: предупреждение об инлайн-скрипте в теме (E15.S1.T26)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from heron.cli import main
from heron.core import build as buildmod
from heron.scaffold import create


def site(tmp_path: Path, html: str | None = None) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True, notes="en")
    if html is not None:
        (root / "theme/partials").mkdir(parents=True, exist_ok=True)
        (root / "theme/partials/extra_inline.html").write_text(html, encoding="utf-8")
    return root


def found(root: Path, notes: str = "en") -> tuple[int, list[dict]]:
    result = CliRunner().invoke(main, ["check", str(root), "--json", "--notes", notes])
    data = json.loads(result.output)
    mine = [w for w in data["warnings"] if "extra_inline" in (w.get("path") or "")]
    return result.exit_code, mine


def test_inline_script_warns_with_file_and_line(tmp_path: Path) -> None:
    root = site(tmp_path, "<p>a</p>\n<script>var x = 1;</script>\n")
    code, warns = found(root)
    assert code == 0
    assert len(warns) == 1
    assert warns[0]["path"].endswith("theme/partials/extra_inline.html")
    assert warns[0]["line"] == 2
    assert "CSP" in warns[0]["message"]


def test_inline_script_ru(tmp_path: Path) -> None:
    root = site(tmp_path, "<script>var x = 1;</script>\n")
    _, warns = found(root, "ru")
    assert len(warns) == 1
    assert any("а" <= ch <= "я" for ch in warns[0]["message"].lower())


def test_src_and_non_executable_types_are_silent(tmp_path: Path) -> None:
    html = (
        '<script src="/a.js"></script>\n'
        '<script type="application/ld+json">{"a": 1}</script>\n'
        "<script type='application/json'>{}</script>\n"
    )
    _, warns = found(site(tmp_path, html))
    assert warns == []


def test_executable_types_warn(tmp_path: Path) -> None:
    html = '<script type="text/javascript">a()</script>\n<script type="module">b()</script>\n'
    _, warns = found(site(tmp_path, html))
    assert [w["line"] for w in warns] == [1, 2]


def test_commented_script_is_silent(tmp_path: Path) -> None:
    html = "{# <script>a()</script> #}\n<!-- <script>\nb()\n</script> -->\n"
    _, warns = found(site(tmp_path, html))
    assert warns == []


def test_scaffold_site_has_no_inline_warning(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, ["check", str(site(tmp_path)), "--json", "--notes", "en"])
    data = json.loads(result.output)
    assert not [w for w in data["warnings"] if "CSP" in w["message"]]


def test_mutation_without_call_is_silent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(buildmod.templates_check, "inline_scripts", lambda *a, **k: None)
    _, warns = found(site(tmp_path, "<script>a()</script>\n"))
    assert warns == []
