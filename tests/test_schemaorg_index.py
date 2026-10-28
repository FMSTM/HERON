"""Индекс schema.org: сборка из образца, детерминизм, ошибки источника, факты релиза 29.3."""

import hashlib
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MINI = ROOT / "tests" / "fixtures" / "schemaorg-mini.jsonld"
INDEX = ROOT / "heron" / "schemaorg" / "schemaorg-29.3.json"

_spec = importlib.util.spec_from_file_location(
    "schemaorg_index", ROOT / "scripts" / "schemaorg_index.py"
)
assert _spec and _spec.loader
si = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(si)

# точный ожидаемый индекс образца: класс, подкласс, двойной термин в двух перечислениях,
# свойства pending, attic и с supersededBy, значение attic с supersededBy, DataType и URL
EXPECTED_MINI = (
    '{"classes":{"Blue":{"attic":false,"dual":true,"ext":"core","parents":["Place"],"supersed'
    'ed_by":[]},"Color":{"attic":false,"ext":"core","parents":["Enumeration"],"superseded_by"'
    ':[]},"DataType":{"attic":false,"ext":"core","parents":["rdfs:Class"],"superseded_by":[]}'
    ',"Enumeration":{"attic":false,"ext":"core","parents":["Thing"],"superseded_by":[]},"Plac'
    'e":{"attic":false,"ext":"core","parents":["Thing"],"superseded_by":[]},"Shade":{"attic":'
    'false,"ext":"pending","parents":["Enumeration"],"superseded_by":[]},"Text":{"attic":fals'
    'e,"ext":"core","parents":[],"superseded_by":[]},"Thing":{"attic":false,"ext":"core","par'
    'ents":[],"superseded_by":[]},"URL":{"attic":false,"ext":"core","parents":["Text"],"super'
    'seded_by":[]}},"counts":{"attic":2,"classes":9,"enums":2,"members":4,"properties":4,"sup'
    'erseded":2},"datatypes":{"Text":[],"URL":["Text"]},"enums":{"Color":["Blue","Grey","Red"'
    '],"Shade":["Blue"]},"license":{"attribution":"Schema.org vocabulary, release t, https://'
    'schema.org; compacted into an index by HERON","name":"CC BY-SA 3.0","url":"https://creat'
    'ivecommons.org/licenses/by-sa/3.0/"},"member_meta":{"Grey":{"attic":true,"ext":"attic","'
    'superseded_by":["Red"]},"Red":{"attic":false,"ext":"core","superseded_by":[]}},"members"'
    ':{"Blue":["Color","Shade"],"Grey":["Color"],"Red":["Color"]},"properties":{"name":{"atti'
    'c":false,"domain":["Thing"],"ext":"core","range":["Text","URL"],"superseded_by":[]},"nea'
    'rby":{"attic":false,"domain":["Place"],"ext":"pending","inverse":"nearby","range":["Plac'
    'e"],"superseded_by":[]},"oldColor":{"attic":true,"domain":["Thing"],"ext":"attic","range'
    '":["Color"],"superseded_by":[]},"title":{"attic":false,"domain":["Thing"],"ext":"core","'
    'range":["Text"],"superseded_by":["name"]}},"release":"t","source":{"bytes":2137,"commit"'
    ':"c","sha256":"h","url":"u"}}'
    "\n"
)


def _mini() -> str:
    return si.dump(si.build(MINI.read_bytes(), release="t", commit="c", sha256="h", url="u"))


def test_mini_exact_and_deterministic():
    first = _mini()
    assert first == EXPECTED_MINI
    assert _mini().encode() == first.encode()


def test_cli_writes_same_bytes_twice(tmp_path):
    sha = hashlib.sha256(MINI.read_bytes()).hexdigest()
    out = tmp_path / "idx.json"
    assert si.main(["--source", str(MINI), "--sha256", sha, "--out", str(out)]) == 0
    first = out.read_bytes()
    assert si.main(["--source", str(MINI), "--sha256", sha, "--out", str(out)]) == 0
    assert out.read_bytes() == first
    assert json.loads(first)["source"]["sha256"] == sha


def test_wrong_sha256_exits_2_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "idx.json"
    with pytest.raises(SystemExit) as exc:
        si.main(["--source", str(MINI), "--sha256", "0" * 64, "--out", str(out)])
    assert exc.value.code == 2
    assert "sha256 не совпадает: ожидался " + "0" * 64 in capsys.readouterr().err
    assert not out.exists()


def test_no_network_no_source_exits_2(tmp_path, monkeypatch, capsys):
    def offline(*_a, **_k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(si.urllib.request, "urlopen", offline)
    out = tmp_path / "idx.json"
    with pytest.raises(SystemExit) as exc:
        si.main(["--out", str(out)])
    assert exc.value.code == 2
    assert "укажите --source <файл>" in capsys.readouterr().err
    assert not out.exists()


def test_broken_json_exits_2(tmp_path):
    bad = tmp_path / "bad.jsonld"
    bad.write_bytes(b"{not json")
    sha = hashlib.sha256(bad.read_bytes()).hexdigest()
    with pytest.raises(SystemExit) as exc:
        si.main(["--source", str(bad), "--sha256", sha, "--out", str(tmp_path / "o.json")])
    assert exc.value.code == 2


def test_real_index_facts():
    assert INDEX.stat().st_size < 400 * 1024
    d = json.loads(INDEX.read_text(encoding="utf-8"))
    c, p, e, m = d["classes"], d["properties"], d["enums"], d["members"]
    assert c["IndividualPhysician"]["parents"] == ["Physician"]
    assert p["practicesAt"]["range"] == ["MedicalOrganization"]
    assert "acceptsNewPatients" not in p
    assert p["isAcceptingNewPatients"]["range"] == ["Boolean"]
    assert "MusicSchool" not in json.dumps(d)
    assert len(e["MedicalSpecialty"]) == 42
    assert m["Physiotherapy"] == ["MedicalSpecialty"]
    assert c["Physiotherapy"]["dual"] is True
    assert sum(1 for v in c.values() if v.get("dual")) == 20


def test_real_counts_and_deprecation():
    d = json.loads(INDEX.read_text(encoding="utf-8"))
    counts = d["counts"]
    assert counts["classes"] == 924 + 20
    assert counts["properties"] == 1518
    assert counts["enums"] == 80
    assert counts["members"] == 524
    assert counts["superseded"] == 92
    assert counts["attic"] == 16
    assert len(d["datatypes"]) == 12 and d["datatypes"]["URL"] == ["Text"]
    # значения перечислений сохраняют признак устаревания
    assert any(v["attic"] for v in d["member_meta"].values())


def test_real_license_and_source():
    d = json.loads(INDEX.read_text(encoding="utf-8"))
    assert d["release"] == "29.3"
    assert d["license"]["name"] == "CC BY-SA 3.0"
    assert d["source"]["sha256"] == si.SHA256
    assert d["source"]["commit"] == si.COMMIT
    assert d["source"]["bytes"] == 1500091
