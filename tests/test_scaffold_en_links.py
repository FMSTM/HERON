"""Английская заготовка не ведёт на русскую документацию (E15.S1.T24, F15)."""

from __future__ import annotations

from pathlib import Path

from heron import scaffold

SCAFFOLD_ROOT = Path(scaffold.__file__).parent
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt", ".html", ".css", ".js", ".json"}
NEEDLE = "docs/ru"


def _ru_files(root: Path) -> list[str]:
    """Текстовые файлы под root, где есть подстрока docs/ru."""
    bad = []
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix in TEXT_SUFFIXES
            and NEEDLE in path.read_text(encoding="utf-8")
        ):
            bad.append(str(path.relative_to(root)))
    return bad


def test_en_scaffold_files_have_no_docs_ru() -> None:
    checked = 0
    for sub in ("text/en", "demo/en", "notes/en", "agents-root/en"):
        base = SCAFFOLD_ROOT / sub
        assert base.is_dir(), base
        checked += sum(1 for p in base.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
        assert _ru_files(base) == [], sub
    assert checked > 0


def test_new_en_site_has_no_docs_ru_outside_agents(tmp_path: Path) -> None:
    root = tmp_path / "s"
    root.mkdir()
    scaffold.create(root, name="demo", languages=["en"], notes="en")
    assert (root / "site.yaml").is_file()
    assert (root / "content").is_dir()
    assert _ru_files(root / "content") == []
    skip = {"agents", "AGENTS.md", "CLAUDE.md", "GEMINI.md"}
    for path in sorted(root.iterdir()):
        if path.name in skip:
            continue
        files = [path] if path.is_file() else [f for f in path.rglob("*") if f.is_file()]
        for f in files:
            if f.suffix in TEXT_SUFFIXES:
                assert NEEDLE not in f.read_text(encoding="utf-8"), str(f.relative_to(root))


def test_mutation_docs_ru_in_copy_is_detected(tmp_path: Path) -> None:
    demo = tmp_path / "en"
    demo.mkdir()
    src = (SCAFFOLD_ROOT / "demo" / "en" / "docs.md").read_text(encoding="utf-8")
    (demo / "docs.md").write_text(src.replace("docs/en/guide", "docs/ru/guide"), encoding="utf-8")
    assert _ru_files(demo) == ["docs.md"]
