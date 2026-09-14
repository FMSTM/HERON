"""Справочники из data/."""

from heron.core import data
from heron.core.errors import Collector


def test_missing_folder_is_empty(tmp_path):
    assert data.load(tmp_path / "data") == {}


def test_files_become_names(tmp_path):
    root = tmp_path / "data"
    (root / "prices").mkdir(parents=True)
    (root / "contacts.yaml").write_text("phone: '+1-555-0100'\n", encoding="utf-8")
    (root / "prices" / "base.yml").write_text("consult: 100\n", encoding="utf-8")
    loaded = data.load(root)
    assert loaded["contacts"]["phone"] == "+1-555-0100"
    assert loaded["prices"]["base"]["consult"] == 100


def test_broken_file_is_collected_not_raised(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "bad.yaml").write_text("a:\n  - b\n c\n", encoding="utf-8")
    collector = Collector()
    data.load(root, collector)
    assert collector.failed
