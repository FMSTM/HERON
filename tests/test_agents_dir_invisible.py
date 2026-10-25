"""Комплект для агентов невидим для сборки, просмотра и не попадает в dist (20 §1, 21 §4)."""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import heron
from heron.core import build as pipeline
from heron.core import notes, watch
from heron.core.report import KitStatus, kit_status
from heron.scaffold import create
from tests.sites import config

RESERVED = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")


def make_site(root: Path) -> Path:
    root.mkdir(parents=True)
    create(root, name="demo", languages=["en", "ru"])
    return root


def add_kit(root: Path, manifest: str | None = None) -> None:
    kit = root / "agents"
    for rel, text in {
        "README.md": "# kit\n",
        "roles/content.md": "role\n",
        "templates/page.md": "---\ntitle: x\n---\n",
        "guide/01.md": "guide\n",
        "spec/20.md": "spec\n",
        "schemas/site.schema.json": '{"произвольно": 1}',
        "work/.gitkeep": "",
    }.items():
        path = kit / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if manifest is None:
        manifest = f'heron_kit: 1\nengine: "{heron.__version__}"\nlang: ru\nfiles: []\n'
    (kit / "heron-kit.yaml").write_text(manifest, encoding="utf-8")
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (root / "GEMINI.md").write_text("@AGENTS.md\n", encoding="utf-8")


def same_tree(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(same_tree(a / d, b / d) for d in cmp.common_dirs)


def all_paths(dist: Path) -> list[str]:
    return [p.relative_to(dist).as_posix() for p in dist.rglob("*")]


@pytest.fixture
def pair(tmp_path):
    plain = make_site(tmp_path / "plain")
    with_kit = tmp_path / "kit"
    shutil.copytree(plain, with_kit)
    add_kit(with_kit)
    return plain, with_kit


def test_dist_is_byte_identical_with_and_without_kit(pair):
    plain, with_kit = pair
    a = pipeline.run(plain, strict=True)
    b = pipeline.run(with_kit, strict=True)
    assert not a.failed and not b.failed
    assert same_tree(plain / "dist", with_kit / "dist")
    assert (plain / "dist/.heron-nginx.conf").is_file()


def test_no_kit_paths_in_dist(pair):
    _, with_kit = pair
    pipeline.run(with_kit, strict=True)
    for rel in all_paths(with_kit / "dist"):
        assert not rel.startswith("agents/") and rel != "agents", rel
        assert rel not in RESERVED, rel


def test_reserved_names_only_in_root(tmp_path):
    root = make_site(tmp_path / "s")
    add_kit(root)
    page = "---\ntitle: Agents\nh1: Agents\ndescription: D\n---\n\nText.\n"
    (root / "content/en/agents.md").write_text(page, encoding="utf-8")
    (root / "static").mkdir(exist_ok=True)
    (root / "static/AGENTS.md").write_text("raw\n", encoding="utf-8")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (root / "dist/en/agents/index.html").is_file() or (
        root / "dist/agents/index.html"
    ).is_file()
    assert (root / "dist/AGENTS.md").read_text(encoding="utf-8") == "raw\n"


def test_is_reserved_root(tmp_path):
    assert notes.RESERVED_DIRS == ("agents",)
    assert notes.RESERVED_FILES == RESERVED
    for name in ("agents", *RESERVED):
        assert notes.is_reserved_root(tmp_path, tmp_path / name)
    assert not notes.is_reserved_root(tmp_path, tmp_path / "static" / "AGENTS.md")
    assert not notes.is_reserved_root(tmp_path, tmp_path / "content" / "en" / "agents.md")
    assert not notes.is_reserved_root(tmp_path, tmp_path / "agents.md")


def test_watch_ignores_kit(pair):
    plain, with_kit = pair
    snap = watch.snapshot(with_kit)
    for key in snap:
        assert key not in RESERVED
        assert not key.startswith("agents/")
    assert set(snap) == set(watch.snapshot(plain))
    (with_kit / "agents/README.md").write_text("# changed\n", encoding="utf-8")
    (with_kit / "AGENTS.md").write_text("# changed\n", encoding="utf-8")
    assert watch.changed(snap, watch.snapshot(with_kit)) == []
    assert "agents" not in watch.WATCHED


def test_kit_status_valid(tmp_path):
    add_kit(tmp_path)
    status = kit_status(tmp_path, config())
    assert (status.present, status.engine, status.lang, status.current) == (
        True,
        heron.__version__,
        "ru",
        True,
    )
    assert status.as_json() == {
        "present": True,
        "engine": heron.__version__,
        "lang": "ru",
        "current": True,
    }


def test_kit_status_outdated(tmp_path):
    add_kit(tmp_path, 'engine: "0.0.1"\nlang: en\n')
    status = kit_status(tmp_path, config())
    assert status.engine == "0.0.1" and status.current is False


def test_kit_status_broken_yaml(tmp_path):
    add_kit(tmp_path, "engine: [unclosed\n  : :\n")
    status = kit_status(tmp_path, config())
    assert status.present is True
    assert status.engine is None and status.lang is None and status.current is None


def test_kit_status_not_a_mapping(tmp_path):
    add_kit(tmp_path, "- just\n- a list\n")
    status = kit_status(tmp_path, config())
    assert status.present is True and status.engine is None


def test_kit_status_absent(tmp_path):
    assert kit_status(tmp_path, config()) == KitStatus(present=False)


def test_kit_status_disabled(tmp_path):
    # поле build.agents появится в S2.T5: до него читается мягко
    cfg = SimpleNamespace(build=SimpleNamespace(agents=False))
    assert kit_status(tmp_path, cfg).disabled is True
    cfg = SimpleNamespace(build=SimpleNamespace(agents=True))
    assert kit_status(tmp_path, cfg).disabled is False


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_check_text_has_kit_line(tmp_path, lang):
    root = make_site(tmp_path / "s")
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data.setdefault("build", {})["notes"] = lang
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    needle = "комплекта нет" if lang == "ru" else "no agent kit"
    assert needle in pipeline.check(root).report.render()
    add_kit(root)
    text = pipeline.check(root).report.render()
    assert "agents/" in text and heron.__version__ in text
