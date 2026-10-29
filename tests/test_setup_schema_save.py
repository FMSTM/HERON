"""Анкета: проверка разметки перед записью, режимы check, drop, except (E17.S3.T2)."""

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.scaffold import create
from heron.setup import SchemaFindings, apply, current_answers, load_answers
from heron.setup.answers import field_for

KEY = "SCH002:site.yaml:schema.entity.worksFor"
ENTITY = {"@type": "IndividualPhysician", "@id": "#me", "worksFor": "Клиника"}


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"], demo=True)
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["schema"] = {**(data.get("schema") or {}), "entity": dict(ENTITY)}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return root


def _data(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))


def _answers(root: Path):
    return load_answers(current_answers(root))


def _backups(root: Path) -> list[Path]:
    folder = root / ".heron-cache" / "setup"
    return sorted(folder.glob("site.yaml.*")) if folder.is_dir() else []


def test_check_refuses_and_writes_nothing(site: Path):
    before = (site / "site.yaml").read_text(encoding="utf-8")
    with pytest.raises(SchemaFindings) as caught:
        apply(site, _answers(site))
    assert caught.value.findings[0]["key"] == KEY
    assert caught.value.findings[0]["field"] in ("works_for", None)
    assert isinstance(caught.value, ValueError)
    assert (site / "site.yaml").read_text(encoding="utf-8") == before
    assert _backups(site) == []


def test_drop_removes_value_and_makes_backup(site: Path):
    result = apply(site, _answers(site), schema={"mode": "drop"})
    assert any("worksFor" in label or "Works for" in label for label in result.dropped)
    assert "worksFor" not in _data(site)["schema"]["entity"]
    assert _backups(site)


def test_drop_only_listed_keys(site: Path):
    with pytest.raises(SchemaFindings):
        apply(
            site,
            _answers(site),
            schema={"mode": "drop", "drop": ["SCH002:site.yaml:schema.entity.nope"]},
        )
    assert "worksFor" in _data(site)["schema"]["entity"]


def test_drop_type_is_refused(site: Path):
    data = _data(site)
    data["schema"]["entity"] = {"@type": "NoSuchType"}
    (site / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    answers = _answers(site)
    with pytest.raises(ValueError) as caught:
        apply(site, answers, schema={"mode": "drop"})
    if not isinstance(caught.value, SchemaFindings):
        assert "не удаляется" in str(caught.value) or "cannot be removed" in str(caught.value)


def test_except_needs_reason(site: Path):
    with pytest.raises(ValueError, match="reason"):
        apply(site, _answers(site), schema={"mode": "except", "reason": "   "})
    assert "schema_exceptions" not in _data(site)


def test_except_writes_and_updates_without_duplicates(site: Path):
    first = apply(site, _answers(site), schema={"mode": "except", "reason": "так надо"})
    assert first.excepted == [KEY]
    assert _data(site)["schema_exceptions"] == [{"key": KEY, "reason": "так надо"}]
    # исключение действует: без режима находок уже нет
    apply(site, _answers(site))
    apply(site, _answers(site), schema={"mode": "except", "reason": "новая причина"})
    assert _data(site)["schema_exceptions"] == [{"key": KEY, "reason": "так надо"}]


def test_except_replaces_reason_of_existing_key(site: Path):
    data = _data(site)
    data["schema_exceptions"] = [{"key": KEY, "reason": "старая", "until": "2000-01-01"}]
    (site / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    apply(site, _answers(site), schema={"mode": "except", "reason": "новая"})
    assert _data(site)["schema_exceptions"] == [{"key": KEY, "reason": "новая"}]


def test_bad_mode(site: Path):
    with pytest.raises(ValueError, match="mode"):
        apply(site, _answers(site), schema={"mode": "force"})


def test_answers_file_schema_key(site: Path):
    text = current_answers(site) + "schema:\n  mode: drop\n"
    result = apply(site, load_answers(text))
    assert result.dropped
    assert "worksFor" not in _data(site)["schema"]["entity"]


def test_cli_without_schema_fails_with_key(site: Path, tmp_path: Path):
    answers = tmp_path / "answers.yaml"
    answers.write_text(current_answers(site), encoding="utf-8")
    run = CliRunner().invoke(main, ["setup", str(site), "--answers", str(answers)])
    assert run.exit_code != 0
    assert KEY in run.output


def test_field_for_rules():
    assert field_for("schema.entity.address.addressLocality") == "city"
    assert field_for("schema.entity.worksFor") == "works_for"
    assert field_for("schema.entity.telephone") == "contacts"
    assert field_for("schema.entity.hasOccupation") == "specialization"
    assert field_for("schema.entity.@type") == "type"
    assert field_for("schema.entity.unknownProp") is None
    assert field_for("schema.Person.name") is None


def test_clean_site_apply_unchanged(tmp_path: Path):
    root = tmp_path / "clean"
    create(root, name="Example", languages=["en"], demo=True)
    result = apply(root, _answers(root))
    assert result.dropped == [] and result.excepted == []


# --- HTTP ------------------------------------------------------------------------


@pytest.fixture
def server(site: Path):
    import socket

    from heron.setup import server as srv

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    box: dict = {}
    thread = threading.Thread(
        target=srv.run, args=(site, "127.0.0.1", port, lambda t: box.update(token=t)), daemon=True
    )
    thread.start()
    for _ in range(100):
        if "token" in box:
            break
        time.sleep(0.05)

    def call(path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(body).encode(),
            headers={"X-Heron-Token": box["token"], "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    yield call
    call("/api/stop", {})
    thread.join(timeout=5)


def test_http_flow(site: Path, server):
    answers = json.loads(json.dumps(yaml.safe_load(current_answers(site))))
    before = (site / "site.yaml").read_text(encoding="utf-8")
    code, body = server("/api/save", {"answers": answers})
    assert code == 409 and body["ok"] is False
    assert body["schema"]["findings"][0]["key"] == KEY
    assert (site / "site.yaml").read_text(encoding="utf-8") == before

    code, body = server("/api/save", {"answers": answers, "schema": {"mode": "except"}})
    assert code == 400 and "reason" in body["error"].lower() or "причин" in body["error"]

    code, body = server(
        "/api/save", {"answers": answers, "schema": {"mode": "except", "reason": "ok"}}
    )
    assert code == 200 and body["excepted"] == [KEY]
    assert _data(site)["schema_exceptions"][0]["reason"] == "ok"


def test_http_drop(site: Path, server):
    answers = json.loads(json.dumps(yaml.safe_load(current_answers(site))))
    code, body = server("/api/save", {"answers": answers, "schema": {"mode": "drop"}})
    assert code == 200 and body["dropped"]
    assert "worksFor" not in _data(site)["schema"]["entity"]
    assert _backups(site)
