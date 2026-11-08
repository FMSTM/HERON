"""Навыки в skills/: правильная шапка и ссылки только на существующие темы документации.

Темы — `docker run … ghcr.io/fmstm/heron:<канал> docs [--lang <язык>] <тема>` из
heron.docs.TOPICS; `template <файл>` — образец из docs/<язык>/templates. Команды в
навыках пишутся целиком, без переменных оболочки вроде `$H` (их не скопировать как есть).
"""

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
        assert "heron:beta docs agents" not in text, f"{path.parent.name}: вместо agents — kit"
        assert not re.search(r"\$H\b|\$HP\b|\bH=", text), f"{path.parent.name}: команда переменной"
        found = re.findall(
            r"ghcr\.io/fmstm/heron:\w+ docs (?:--lang (\w+) )?([a-z][a-z0-9-]*)(?: ([\w.-]+))?",
            text,
        )
        assert found, path.parent.name
        for lang, topic, arg in found:
            if lang:
                assert lang in docs.LANGS, f"{path.parent.name}: нет языка {lang}"
            if topic == "theme-ref":  # справка темы сайта, не тема документации (21 §10)
                continue
            if topic == "template":
                assert arg in docs.templates(lang or "en"), f"{path.parent.name}: нет образца {arg}"
                continue
            assert docs.topic(topic) is not None, f"{path.parent.name}: нет темы {topic}"


def test_skills_point_to_the_kit_and_the_site_folder():
    """Каждый навык читает README комплекта и знает, где тот же текст лежит в сайте (23 §2)."""
    line = (
        "Inside a HERON site the same documentation sits in `agents/` "
        "(start with `AGENTS.md`); your deliverables go to `agents/work/`."
    )
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        full = 'docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)"'
        assert f"`{full} ghcr.io/fmstm/heron:beta docs --lang en kit`" in text, path.parent.name
        assert line in text, path.parent.name
        assert "ghcr.io/fmstm/heron:beta" in text, path.parent.name
