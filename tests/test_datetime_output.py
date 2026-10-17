"""Даты для машин — полной датой со временем и поясом.

Search Console не принимает `dateModified: 2026-10-14` у ProfilePage и
большинства типов: нужен ISO 8601 со временем и поясом. Время коммита
идёт как его отдаёт `git log --format=%cI`, день без времени — полночь
UTC. Подпись на странице остаётся днём.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core import build as pipeline
from heron.core import dates, tree
from heron.scaffold import create
from tests import sites

WHEN = "2026-10-17T11:30:12+02:00"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="нет git")


def site(tmp_path, front: str = "", updated_from: str = "manual"):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    if updated_from != "manual":
        with (root / "site.yaml").open("a", encoding="utf-8") as out:
            out.write(f"\nbuild:\n  updated_from: {updated_from}\n")
    (root / "content" / "en" / "a.md").write_text(
        "---\ntitle: A\nh1: About\ndescription: D\n"
        f"{front}schema:\n  Article:\n    headline: A\n---\n\nText.\n",
        encoding="utf-8",
    )
    return root


def commit(root, when: str = WHEN) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.org",
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
    }
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "x"]):
        subprocess.run(cmd, cwd=root, check=True, env=env, capture_output=True)


def graph(root, url: str = "a") -> list[dict]:
    html = (root / "dist" / url / "index.html").read_text(encoding="utf-8")
    out: list[dict] = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block)
        out += data.get("@graph", [data])
    return out


def article(root) -> dict:
    return next(n for n in graph(root) if n.get("@type") == "Article")


def stamps(value) -> list[str]:
    """Все значения ключей date* по всему дереву разметки."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.startswith("date") and isinstance(item, str):
                found.append(item)
            else:
                found += stamps(item)
    elif isinstance(value, list):
        for item in value:
            found += stamps(item)
    return found


@needs_git
def test_git_gives_commit_time_with_its_zone(tmp_path):
    root = site(tmp_path, updated_from="git")
    commit(root)
    expected = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", "content/en/a.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert expected == WHEN

    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert article(root)["dateModified"] == WHEN
    sitemap = (root / "dist" / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<lastmod>{WHEN}</lastmod>" in sitemap
    # подпись на странице — день, без времени
    assert result.site.page("a", "en").updated == date(2026, 10, 17)


def test_day_without_time_is_midnight_utc(tmp_path):
    root = site(tmp_path, "date: 2026-03-14\nupdated: 2026-09-02\n")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    node = article(root)
    assert node["datePublished"] == "2026-03-14T00:00:00+00:00"
    assert node["dateModified"] == "2026-09-02T00:00:00+00:00"


@needs_git
def test_every_date_in_the_build_is_a_full_moment(tmp_path):
    root = site(tmp_path, "date: 2026-03-14\n", updated_from="git")
    commit(root)
    built = datetime.now(UTC)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]

    found: list[str] = []
    for path in (root / "dist").rglob("index.html"):
        html = path.read_text(encoding="utf-8")
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            found += stamps(json.loads(block))
    for path in (root / "dist").glob("sitemap*.xml"):
        found += re.findall(r"<lastmod>([^<]+)</lastmod>", path.read_text(encoding="utf-8"))
    assert found
    for value in found:
        moment = datetime.fromisoformat(value)
        assert moment.tzinfo is not None, value
        assert moment <= built, value


def test_future_date_warns_and_strict_fails(tmp_path):
    later = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
    root = site(tmp_path, f"updated: {later}\n")
    result = pipeline.run(root)
    said = [w for w in result.collector.warnings if w.kind == "даты"]
    assert said and "позже сборки" in said[0].message
    assert said[0].path == "en/a.md"

    loose = CliRunner().invoke(main, ["build", str(root)])
    strict = CliRunner().invoke(main, ["build", str(root), "--strict"])
    assert loose.exit_code == 0, loose.output
    assert strict.exit_code != 0


def test_modified_before_published_warns(tmp_path):
    root = site(tmp_path, "date: 2026-09-02\nupdated: 2026-03-14\n")
    result = pipeline.run(root)
    said = [w.message for w in result.collector.warnings if w.kind == "даты"]
    assert any("раньше публикации" in m for m in said), said


@needs_git
def test_same_day_early_morning_commit_is_not_out_of_order(tmp_path):
    """Публикация днём, правка того же дня в 01:30 по Киеву — это 23:30 UTC
    накануне. Порядок сверяется по дням, а не по моментам."""
    root = site(tmp_path, "date: 2026-10-17\n", updated_from="git")
    commit(root, "2026-10-17T01:30:00+03:00")
    result = pipeline.run(root)
    assert [w.message for w in result.collector.warnings if w.kind == "даты"] == []


def test_check_takes_the_moment_of_the_build(tmp_path):
    files = {"uk/index.md": sites.page("H"), "uk/a.md": sites.page("A", updated="2026-10-17")}
    content = sites.build(tmp_path, files)
    built, collector = tree.scan(content, sites.config())
    before = datetime(2026, 10, 16, 23, 0, tzinfo=UTC)
    dates.check(built, collector, now=before)
    assert [w.path for w in collector.warnings if w.kind == "даты"] == ["uk/a.md"]

    _, collector = tree.scan(content, sites.config())
    dates.check(built, collector, now=datetime(2026, 10, 17, 0, 0, tzinfo=UTC))
    assert [w for w in collector.warnings if w.kind == "даты"] == []
