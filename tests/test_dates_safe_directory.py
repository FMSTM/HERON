"""Даты из гита: `safe.directory` - только репозиторий сайта, не `*` (аудит SEC-08)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from heron.core import dates


def _calls(monkeypatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def run(args, **_kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(dates.subprocess, "run", run)
    return seen


def test_safe_directory_is_the_repository_of_the_site(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    site = repo / "sites" / "one"
    site.mkdir(parents=True)
    (repo / ".git").mkdir()
    seen = _calls(monkeypatch)
    dates._git(site, "status")
    args = seen[0]
    assert "safe.directory=*" not in args
    assert f"safe.directory={repo.resolve().as_posix()}" in args


def test_no_repository_no_safe_directory(tmp_path, monkeypatch):
    site = tmp_path / "plain"
    site.mkdir()
    monkeypatch.setattr(dates, "_top", lambda _root: None)
    seen = _calls(monkeypatch)
    dates._git(site, "status")
    assert not any(arg.startswith("safe.directory") for arg in seen[0])


def test_git_worktree_file_counts_as_repository(tmp_path):
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    assert dates._top(repo / "missing" / "..") == repo.resolve()


def test_no_wildcard_left_in_the_module():
    source = Path(dates.__file__).read_text(encoding="utf-8")
    assert '"safe.directory=*"' not in source
