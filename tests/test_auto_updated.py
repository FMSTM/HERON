"""Дата обновления страницы: ручная, из истории репозитория, из времени файла."""

import os
import subprocess
import time
from datetime import UTC, date, datetime

from heron.core import dates, tree
from heron.modules import jsonld, sitemap
from tests import sites

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/bio.md": sites.page("Біографія"),
}


def git(root, *args):
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def repo(root, when: str):
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "первый",
        "--date",
        when,
    )


def scanned(root, **over):
    config = sites.config(**over)
    site, collector = tree.scan(root / "content", config)
    return site, config, collector


def resolve(tmp_path, mode, files=None, **over):
    sites.build(tmp_path, files or FILES)
    site, config, collector = scanned(tmp_path, **over)
    dates.resolve(site, tmp_path, mode, collector)
    return site, collector


def test_manual_mode_changes_nothing(tmp_path):
    site, collector = resolve(tmp_path, "manual")
    assert [p.updated for p in site.pages] == [None, None]
    assert [w for w in collector.warnings if w.kind == "даты"] == []


def test_git_history_gives_the_commit_date(tmp_path):
    sites.build(tmp_path, FILES)
    repo(tmp_path, "2026-03-14T10:00:00+00:00")
    site, config, collector = scanned(tmp_path)
    dates.resolve(site, tmp_path, "git", collector)
    assert {p.updated for p in site.pages} == {date(2026, 3, 14)}
    assert [w for w in collector.warnings if w.kind == "даты"] == []


def test_manual_date_beats_history(tmp_path):
    files = {**FILES, "uk/bio.md": sites.page("Біографія", updated="2020-01-02")}
    sites.build(tmp_path, files)
    repo(tmp_path, "2026-03-14T10:00:00+00:00")
    site, config, collector = scanned(tmp_path)
    dates.resolve(site, tmp_path, "git", collector)
    assert site.by_url["/bio/"].updated == date(2020, 1, 2)
    assert site.by_url["/"].updated == date(2026, 3, 14)


def test_uncommitted_file_falls_back_to_its_own_time(tmp_path):
    sites.build(tmp_path, FILES)
    repo(tmp_path, "2026-03-14T10:00:00+00:00")
    (tmp_path / "content/uk/bio.md").write_text(sites.page("Біографія оновлена"), encoding="utf-8")
    site, config, collector = scanned(tmp_path)
    dates.resolve(site, tmp_path, "git", collector)
    assert site.by_url["/bio/"].updated == datetime.now(UTC).date()
    said = [w for w in collector.warnings if w.kind == "даты"]
    assert [(w.path, "не закоммичен" in w.message) for w in said] == [("uk/bio.md", True)]


def test_no_repository_still_builds(tmp_path):
    site, collector = resolve(tmp_path, "git")
    said = [w for w in collector.warnings if w.kind == "даты"]
    assert said and "истории нет" in said[0].message
    # копирование файлов тестом идёт в одну секунду — это и есть подпись копии
    assert [p.updated for p in site.pages] == [None, None]


def test_file_mode_takes_file_time(tmp_path):
    sites.build(tmp_path, FILES)
    old = time.time() - 60 * 60 * 24 * 30
    os.utime(tmp_path / "content/uk/bio.md", (old, old))
    site, config, collector = scanned(tmp_path)
    dates.resolve(site, tmp_path, "file", collector)
    assert site.by_url["/bio/"].updated == datetime.fromtimestamp(old, UTC).date()
    assert site.by_url["/"].updated == datetime.now(UTC).date()


def test_all_files_at_once_looks_like_a_copy(tmp_path):
    sites.build(tmp_path, FILES)
    same = time.time() - 60 * 60
    for rel in FILES:
        os.utime(tmp_path / "content" / rel, (same, same))
    site, config, collector = scanned(tmp_path)
    dates.resolve(site, tmp_path, "file", collector)
    assert [p.updated for p in site.pages] == [None, None]
    said = [w for w in collector.warnings if w.kind == "даты"]
    assert said and "копирование" in said[0].message


def test_one_date_feeds_page_sitemap_and_schema(tmp_path):
    sites.build(tmp_path, FILES)
    repo(tmp_path, "2026-03-14T10:00:00+00:00")
    site, config, collector = scanned(tmp_path)
    dates.resolve(site, tmp_path, "git", collector)
    page = site.by_url["/bio/"]
    body = sitemap.generate(site, config)["sitemap-uk.xml"]
    assert f"<lastmod>{page.updated.isoformat()}</lastmod>" in body
    theme = sites.theme(types={"page": {"jsonld": ["Article"]}})
    graph = jsonld.build(page, config, theme, site)
    node = next(n for n in graph if n.get("@type") == "Article")
    assert node["dateModified"] == page.updated.isoformat()
