"""Дата публикации: разметка, лента, шаблон. И дата обновления из git.

Спецификация: docs/spec/20-data-contract.md, раздел 4.2.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date

import pytest

from heron.core import build as pipeline
from heron.core import links, tree
from heron.modules import feed
from heron.scaffold import create
from tests import sites


def _site(tmp_path, files, **over):
    content = sites.build(tmp_path, files)
    config = sites.config(**over)
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site, config, collector


def test_date_is_a_date_on_page(tmp_path):
    site, _, collector = _site(
        tmp_path, {"uk/index.md": sites.page("Г"), "uk/a.md": sites.page("A", date="2026-03-14")}
    )
    assert not collector.failed
    assert site.page("a", "uk").date == date(2026, 3, 14)
    assert site.page("/", "uk").date is None


def test_bad_date_is_e002(tmp_path):
    _, _, collector = _site(
        tmp_path, {"uk/index.md": sites.page("Г"), "uk/a.md": sites.page("A", date="березень")}
    )
    assert [e.code for e in collector.errors] == ["E002"]


def test_feed_sorted_by_date_then_updated(tmp_path):
    files = {
        "uk/index.md": sites.page("Г"),
        "uk/old.md": sites.page("Стара", type="article", date="2025-01-01", updated="2026-09-01"),
        "uk/new.md": sites.page("Нова", type="article", date="2026-05-01"),
        "uk/mid.md": sites.page("Без дати", type="article", updated="2026-02-01"),
    }
    site, config, _ = _site(tmp_path, files, seo={"feed": "article"})
    xml = feed.generate(site, config)["feed.xml"]
    order = re.findall(r"<title>([^<]+)</title>", xml)[1:]
    assert order == ["Нова", "Без дати", "Стара"]
    assert "<published>2026-05-01T00:00:00Z</published>" in xml
    assert xml.count("<published>") == 2


def _built(tmp_path, front: str, updated_from: str = "manual"):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    if updated_from != "manual":
        text = (root / "site.yaml").read_text(encoding="utf-8")
        (root / "site.yaml").write_text(
            text + f"\nbuild:\n  updated_from: {updated_from}\n", encoding="utf-8"
        )
    content = root / "content" / "uk"
    (content / "index.md").write_text(
        "---\ntitle: Г\nh1: Головна\ndescription: О\n---\n\nТекст.\n", encoding="utf-8"
    )
    (content / "a.md").write_text(
        f"---\ntitle: Стаття\nh1: Стаття про\ndescription: О\n{front}---\n\nТекст.\n",
        encoding="utf-8",
    )
    return root


def _ld(root) -> list[dict]:
    html = (root / "dist" / "a" / "index.html").read_text(encoding="utf-8")
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    out = []
    for block in blocks:
        data = json.loads(block)
        out += data.get("@graph", [data])
    return out


def test_jsonld_has_date_published_and_modified(tmp_path):
    root = _built(
        tmp_path,
        "date: 2026-03-14\nupdated: 2026-09-02\nschema:\n  Article:\n    headline: Стаття\n",
    )
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    article = next(n for n in _ld(root) if n.get("@type") == "Article")
    assert article["datePublished"] == "2026-03-14"
    assert article["dateModified"] == "2026-09-02"


@pytest.mark.skipif(shutil.which("git") is None, reason="нет git")
def test_updated_from_git_takes_commit_date(tmp_path):
    root = _built(tmp_path, "schema:\n  Article:\n    headline: Стаття\n", updated_from="git")
    env = {
        "GIT_AUTHOR_DATE": "2025-11-20T10:00:00Z",
        "GIT_COMMITTER_DATE": "2025-11-20T10:00:00Z",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.org",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "x"]):
        subprocess.run(cmd, cwd=root, check=True, env=env)
    result = pipeline.run(root)
    assert not result.failed
    assert result.site.page("a", "uk").updated == date(2025, 11, 20)
    article = next(n for n in _ld(root) if n.get("@type") == "Article")
    assert article["dateModified"] == "2025-11-20"
    assert "datePublished" not in article
