"""AGENTS.md публикуется на сайте движка как /AGENTS.md: ссылки только абсолютные."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from heron import docs

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://github.com/FMSTM/HERON/"
LINK = re.compile(r"\]\(([^)\s]+)\)")


def relative_targets(text: str) -> list[str]:
    """Цели ссылок вне кода, не http(s):// и не якорь."""
    out: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        line = re.sub(r"`[^`]*`", "", line)
        out += [t for t in LINK.findall(line) if not t.startswith(("http://", "https://", "#"))]
    return out


def test_agents_md_has_no_relative_links() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert relative_targets(text) == []


@pytest.mark.parametrize(
    "target",
    [
        BASE + "blob/prod/docs/ru/README.md",
        BASE + "blob/prod/docs/en/README.md",
        BASE + "tree/prod/skills",
    ],
)
def test_agents_md_has_absolute_target(target: str) -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert f"]({target})" in text


def test_stale_translation_notice_removed() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Пока английский перевод не завершён" not in text


def test_read_topic_agents_prod_has_no_relative_links(monkeypatch) -> None:
    monkeypatch.setenv("HERON_CHANNEL", "prod")
    assert relative_targets(docs.read_topic("agents")) == []


def test_mutation_relative_link_is_found() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    broken = text.replace(BASE + "blob/prod/docs/ru/README.md", "docs/ru/README.md")
    assert "](docs/ru/README.md)" in broken
    assert relative_targets(broken) == ["docs/ru/README.md"]
