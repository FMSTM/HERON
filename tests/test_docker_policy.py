"""Одна политика запуска движка: scripts/site.sh, site-image.yml и помощники анкеты.

Помощники анкеты писали свой `docker run`: с сетью, с обычными правами и с
папкой сайта на запись. Политика теперь одна (`files.POLICY`), и этот тест
не даёт трём местам разойтись снова.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from heron.setup import files
from heron.setup.answers import Answers

ROOT = Path(__file__).resolve().parents[1]
FLAGS = {"--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges"}


def _flags(text: str) -> set[str]:
    found = set(re.findall(r"--(?:network=none|read-only|cap-drop=ALL|security-opt=[\w-]+)", text))
    if re.search(r"--tmpfs /tmp", text):
        found.add("--tmpfs /tmp")
    if re.search(r'--user "\$\(id -u\):\$\(id -g\)"', text):
        found.add("--user")
    return found


WANTED = FLAGS | {"--tmpfs /tmp", "--user"}


def test_policy_constant_has_every_flag():
    assert _flags(files.POLICY) == WANTED


def test_site_sh_uses_the_same_policy():
    text = (ROOT / "scripts" / "site.sh").read_text("utf-8")
    body = text[text.index("run_engine() {") : text.index("strict_flag()")]
    assert _flags(body) == WANTED
    assert '"$SITE_PATH":/site:ro' in body


def test_site_image_workflow_uses_the_same_policy():
    data = yaml.safe_load((ROOT / ".github" / "workflows" / "site-image.yml").read_text("utf-8"))
    (step,) = [s for s in data["jobs"]["image"]["steps"] if s.get("name") == "сборка сайта"]
    assert _flags(step["run"]) == WANTED
    assert '"$PWD":/site:ro' in step["run"]


def _generated(**publish) -> dict[str, str]:
    answers = Answers.model_validate({"publish": publish})
    return {item.rel: item.text for item in files.plan(answers, "en")}


def test_helpers_and_pages_use_the_same_policy_and_a_read_only_site():
    sets = [
        _generated(way="dockerhub", dockerhub_user="user", image="site"),
        _generated(way="static", static_target="pages"),
        _generated(way="static", server="user@host.test"),
    ]
    runs = 0
    for rel, text in [item for texts in sets for item in texts.items()]:
        for block in re.findall(r"docker run --rm(?:[^\n]*\\\n)*[^\n]*", text):
            runs += 1
            assert _flags(block) == WANTED, (rel, block)
            assert not re.search(r'"\$PWD":/site(?!:ro)\b(?!/)', block), (rel, block)
    assert runs >= 4
