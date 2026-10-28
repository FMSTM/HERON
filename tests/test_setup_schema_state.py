"""Анкета: находки текущего site.yaml в state() (E17.S3.T3)."""

from pathlib import Path

import pytest
import yaml

from heron.scaffold import create
from heron.setup import state

KEY = "SCH002:site.yaml:schema.entity.worksFor"
ENTITY = {"@type": "IndividualPhysician", "@id": "#me", "worksFor": "Клиника"}
EMPTY = {"active": [], "excepted": [], "expired": []}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "site"
    create(path, name="Example", languages=["en"], demo=True)
    return path


def _edit(root: Path, fn) -> None:
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _entity(data: dict) -> None:
    data["schema"] = {**(data.get("schema") or {}), "entity": dict(ENTITY)}


def test_fresh_site_has_no_findings(root: Path) -> None:
    assert state(root)["schema"]["findings"] == EMPTY


def test_manual_worksfor_is_active(root: Path) -> None:
    _edit(root, _entity)
    active = state(root)["schema"]["findings"]["active"]
    item = next(x for x in active if x["key"] == KEY)
    assert item["code"] == "SCH002"
    assert item["path"] == "schema.entity.worksFor"
    assert item["field"] == "works_for"


def test_excepted_finding_has_reason(root: Path) -> None:
    def edit(data: dict) -> None:
        _entity(data)
        data["schema_exceptions"] = [{"key": KEY, "reason": "так надо"}]

    _edit(root, edit)
    found = state(root)["schema"]["findings"]
    assert all(x["key"] != KEY for x in found["active"])
    item = next(x for x in found["excepted"] if x["key"] == KEY)
    assert item["reason"] == "так надо"
    assert item["until"] is None


def test_broken_config_gives_empty_findings(root: Path) -> None:
    _edit(root, lambda d: d.update(site="не словарь"))
    assert state(root)["schema"]["findings"] == EMPTY
