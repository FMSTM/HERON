"""Навыки в skills/: правильная шапка и ссылки только на существующие темы документации."""

import re
from pathlib import Path

import yaml

from heron import docs

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))


def test_five_skills():
    assert {p.parent.name for p in SKILLS} == {
        "heron",
        "heron-architect",
        "heron-content",
        "heron-designer",
        "heron-builder",
    }


def test_frontmatter_and_docs_topics():
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        head = yaml.safe_load(text.split("---", 2)[1])
        assert head["name"] == path.parent.name
        assert 20 < len(head["description"]) <= 1024
        for topic in re.findall(r"\$H docs ([a-z][a-z0-9-]*)", text):
            assert docs.topic(topic) is not None, f"{path.parent.name}: нет темы {topic}"
