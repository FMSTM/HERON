"""Браузерное задание CI берёт все браузерные тесты, а не один по имени (аудит TEST-02)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
E2E = ROOT / "tests" / "test_studio_e2e.py"


def _tests(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]


def test_ci_selects_by_marker_not_by_name():
    text = CI.read_text(encoding="utf-8")
    assert "pytest tests -m browser" in text
    runs = [line for line in text.splitlines() if line.strip().startswith("run:")]
    assert not any("-k browser" in line for line in runs)


def test_all_studio_e2e_tests_are_browser_tests():
    text = E2E.read_text(encoding="utf-8")
    assert "pytestmark = pytest.mark.browser" in text
    assert len(_tests(E2E)) >= 6


def test_studio_e2e_honours_require_browser():
    text = E2E.read_text(encoding="utf-8")
    # без браузера - не тихий пропуск: _no_browser() падает при HERON_REQUIRE_BROWSER=1
    assert 'pytest.skip("нет Playwright' not in text
    assert 'pytest.skip("Chromium' not in text
    assert "pytest.fail(" in text


def test_marker_is_registered():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"browser:' in text
