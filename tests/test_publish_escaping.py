"""Ветка и путь публикации не становятся командами оболочки.

Скрипты публикации запускаются с заглушками git, rsync и docker в PATH:
заглушка записывает свои аргументы, ничего никуда не отправляется.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from heron.setup import files
from heron.setup.answers import Answers

STUB = '#!/bin/sh\nprintf "%s\\n" "$(basename "$0")" "$@" >> "$HERON_STUB_LOG"\n'


def _stubs(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("git", "rsync", "docker"):
        path = bin_dir / name
        path.write_text(STUB, encoding="utf-8")
        path.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HERON_STUB_LOG"] = str(tmp_path / "calls.log")
    return env


def _run(tmp_path: Path, answers: Answers) -> list[str]:
    site = tmp_path / "site"
    site.mkdir()
    for item in files.plan(answers, "en"):
        path = site / item.rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.text, encoding="utf-8")
        if item.executable:
            path.chmod(0o755)
    subprocess.run(["bash", str(site / files.PUBLISH)], cwd=site, env=_stubs(tmp_path), check=True)
    return (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize(
    "branch",
    [
        "main; touch MARKER",
        "main$(touch MARKER)",
        "main`touch MARKER`",
        "-main",
        "main]\n  pull_request:",
        "a..b",
        "main.lock",
    ],
)
def test_harmful_branch_is_refused(branch):
    with pytest.raises(ValueError):
        Answers.model_validate({"publish": {"way": "github", "branch": branch}})


@pytest.mark.parametrize(
    "path",
    ["/var/www/$(touch MARKER)", "/var/www/`touch MARKER`", '/var/www/"; touch MARKER; "', "/a b"],
)
def test_harmful_path_is_refused(path):
    with pytest.raises(ValueError):
        Answers.model_validate(
            {"publish": {"way": "static", "server": "user@host.test", "path": path}}
        )


def test_server_cannot_be_an_option():
    with pytest.raises(ValueError):
        Answers.model_validate({"publish": {"way": "static", "server": "-e"}})


def test_branch_reaches_git_as_one_argument(tmp_path):
    answers = Answers.model_validate(
        {"publish": {"way": "github", "auto": False, "branch": "release/v1.2-x"}}
    )
    calls = _run(tmp_path, answers)
    assert calls[-3:] == ["git", "push", "origin", "release/v1.2-x"][-3:]
    assert "release/v1.2-x" in calls
    assert not (tmp_path / "site" / "MARKER").exists()


def test_path_reaches_rsync_as_one_argument(tmp_path):
    answers = Answers.model_validate(
        {"publish": {"way": "static", "server": "user@host.test", "path": "/srv/site-1/www"}}
    )
    calls = _run(tmp_path, answers)
    assert calls[0] == "docker"  # сборка — заглушкой
    assert calls[-1] == "user@host.test:/srv/site-1/www/"


def test_workflow_branch_is_a_yaml_string():
    answers = Answers.model_validate({"publish": {"way": "github", "branch": "release/v1"}})
    (image,) = [g for g in files.plan(answers, "en") if g.rel.endswith("image.yml")]
    data = yaml.safe_load(image.text)
    trigger = data.get("on", data.get(True))  # PyYAML читает голый on как True
    assert trigger["push"]["branches"] == ["release/v1"]
