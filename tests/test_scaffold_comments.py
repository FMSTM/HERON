"""Язык комментариев новой папки сайта: ru или en во всех файлах скелета.

Спецификация: docs/spec/23-distribution.md, раздел 4.
"""

from __future__ import annotations

import re

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.core import build as pipeline
from heron.scaffold import adopt, create

CYRILLIC = re.compile(r"[а-яА-ЯёЁіїєІЇЄ]")
COMMENTED = ["site.yaml", "theme/theme.yaml", "content/en/index.md", "content/en/404.md"]


def _comments(path):
    return "\n".join(
        line.split("#", 1)[1]
        for line in path.read_text(encoding="utf-8").splitlines()
        if "#" in line
    )


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_scaffold_file_speaks_one_language(tmp_path, lang):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["en"], comments=lang)
    for rel in COMMENTED:
        text = _comments(root / rel)
        assert text.strip(), rel
        assert bool(CYRILLIC.search(text)) is (lang == "ru"), rel
    for note in root.rglob("heron-readme.md"):
        assert bool(CYRILLIC.search(note.read_text(encoding="utf-8"))) is (lang == "ru"), note
    assert (
        yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))["build"]["comments"]
        == lang
    )


def test_starter_site_builds_right_away(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk", "en"], comments="en")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (root / "dist" / "index.html").is_file()
    assert (root / "dist" / "en" / "index.html").is_file()
    assert (root / "dist" / "404.html").is_file()


def test_init_takes_comments_from_site_yaml(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"], comments="en")
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["site"]["languages"] = ["uk", "ru"]
    (root / "site.yaml").write_text(yaml.safe_dump(conf), encoding="utf-8")
    adopt(root)
    assert not CYRILLIC.search(_comments(root / "content" / "ru" / "index.md"))


def test_cli_new_and_page_use_the_language(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(main, ["new", "site", "--comments", "en"]).exit_code == 0
    result = runner.invoke(main, ["page", "page", "about", "site"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "site" / "content" / "uk" / "about.md").read_text(encoding="utf-8")
    assert "# ================= 1. BASICS" in text
    assert "# ================= 8. RELATIONS" in text
