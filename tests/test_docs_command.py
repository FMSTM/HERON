"""`heron docs`: документация этой версии движка — из образа, без клона и сети."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from click.testing import CliRunner

from heron import docs
from heron.cli import main

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return CliRunner().invoke(main, list(args))


def repo_docs() -> set[str]:
    """Текст документации в репозитории: всё, кроме картинок бренда."""
    found = {"AGENTS.md", "README.md"}
    for path in (ROOT / "docs").rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        if path.is_file() and not rel.startswith("docs/brand/"):
            found.add(rel)
    return found


def test_every_document_is_reachable():
    """Новый гайд не забыт: каждый файл — тема или образец."""
    assert set(docs.files()) == repo_docs()


def test_wheel_carries_every_document():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packed = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for rel in repo_docs():
        assert any(rel == src or rel.startswith(src.rstrip("/") + "/") for src in packed), rel
        assert not rel.startswith("docs/brand/")


def test_image_copies_every_document():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    copied = re.findall(r"^COPY (?!--)(.+?) \./", dockerfile, re.M)
    sources = " ".join(copied).split()
    for rel in repo_docs():
        assert any(rel == src or rel.startswith(src.rstrip("/") + "/") for src in sources), rel


def test_contents_lists_topics():
    result = run("docs")
    assert result.exit_code == 0
    for topic in docs.TOPICS:
        assert topic.name in result.output


def test_topic_prints_markdown():
    result = run("docs", "agents")
    assert result.exit_code == 0
    assert result.output.startswith("# HERON для агентов")


def test_template_prints_the_sample():
    result = run("docs", "template", "page.md")
    assert result.exit_code == 0
    assert "1. ОСНОВНОЕ" in result.output


def test_unknown_topic_points_at_contents():
    result = run("docs", "nonsense")
    assert result.exit_code == 1
    assert "heron docs" in result.output


def test_search_shows_file_line_and_context():
    result = run("docs", "--search", "page.meta.get")
    assert result.exit_code == 0
    assert re.search(r"theme · docs/guide/04-theme\.md:\d+", result.output)
    assert "  > " in result.output


def test_search_with_nothing_found():
    result = run("docs", "--search", "такого-текста-нет-нигде")
    assert result.exit_code == 1


def test_export_keeps_links_between_files(tmp_path):
    target = tmp_path / "heron-docs"
    result = run("docs", "--export", str(target))
    assert result.exit_code == 0, result.output
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\((docs/[^)#\s]+)\)", agents)
    assert links
    for link in links:
        assert (target / link).exists(), link
