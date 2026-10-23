"""Подмена .heron-nginx.conf, которую нельзя проверить, — ошибка до записи dist."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from heron.core import build as pipeline
from heron.scaffold import create

NAME = ".heron-nginx.conf"


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True)
    assert not pipeline.run(root, strict=True).failed
    data = yaml.safe_load((root / "site.yaml").read_text("utf-8"))
    data.setdefault("build", {})["overrides"] = [NAME]
    (root / "site.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


def _dist(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root / "dist").as_posix(): p.read_bytes()
        for p in (root / "dist").rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("data", [b"server {\xff\xfe broken", b"", b"  \n\t\n"])
def test_bad_override_fails_before_dist_changes(tmp_path, data):
    root = _site(tmp_path)
    before = _dist(root)
    (root / "static" / NAME).write_bytes(data)
    result = pipeline.run(root)  # и без --strict: это ошибка, а не предупреждение
    assert result.failed
    assert "E034" in {e.code for e in result.collector.errors}
    assert _dist(root) == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root читает всё; права не проверить")
def test_unreadable_override_fails_before_dist_changes(tmp_path):
    root = _site(tmp_path)
    before = _dist(root)
    conf = root / "static" / NAME
    conf.write_text("server { listen 8080; }\n", encoding="utf-8")
    conf.chmod(0)
    try:
        result = pipeline.run(root)
    finally:
        conf.chmod(0o644)
    assert result.failed
    assert {e.code for e in result.collector.errors} & {"E034", "E030"}
    assert _dist(root) == before
