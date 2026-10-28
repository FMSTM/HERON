from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from heron.contracts.loader import build
from heron.contracts.site import SiteConfig
from heron.core.errors import HeronError

KEY = "SCH002:site.yaml:schema.entity.worksFor"


def _data(*exceptions: dict) -> dict:
    return {
        "heron": ">=0.1",
        "site": {"name": "S", "domain": "example.com", "theme": "base"},
        "schema_exceptions": list(exceptions),
    }


def _cfg(*exceptions: dict) -> SiteConfig:
    return SiteConfig.model_validate(_data(*exceptions))


def test_valid_exception() -> None:
    cfg = _cfg({"key": KEY, "reason": " причина ", "until": "2026-12-31"})
    exc = cfg.schema_exceptions[0]
    assert exc.reason == "причина" and exc.until == date(2026, 12, 31)
    assert "schema_exceptions" not in cfg.extras
    assert cfg.for_lang("en").schema_exceptions == cfg.schema_exceptions


def test_without_until_and_empty_list() -> None:
    assert _cfg({"key": KEY, "reason": "r"}).schema_exceptions[0].until is None
    assert _cfg().schema_exceptions == []


@pytest.mark.parametrize("key", ["SCH009:a:b", "SCH002:site.yaml", "SCH002::x"])
def test_bad_key(key: str) -> None:
    with pytest.raises(ValidationError, match="ожидается SCH00N"):
        _cfg({"key": key, "reason": "r"})


def test_blank_reason() -> None:
    with pytest.raises(ValidationError, match="нет причины"):
        _cfg({"key": KEY, "reason": "  "})


def test_bad_until() -> None:
    with pytest.raises(ValidationError):
        _cfg({"key": KEY, "reason": "r", "until": "завтра"})


def test_duplicate_key() -> None:
    with pytest.raises(ValidationError, match="задано дважды"):
        _cfg({"key": KEY, "reason": "a"}, {"key": KEY, "reason": "b"})


def test_json_schema_has_exceptions() -> None:
    from heron.contracts import schemas

    data = schemas.site_schema()
    assert "schema_exceptions" in data["properties"]
    defs = data["$defs"]["SchemaException"]
    assert set(defs["required"]) == {"key", "reason"}


def test_blank_reason_is_config_error_e011() -> None:
    with pytest.raises(HeronError) as info:
        build(SiteConfig, _data({"key": KEY, "reason": " "}), Path("site.yaml"))
    assert info.value.code == "E011"
    assert "у исключения нет причины" in info.value.message


def test_valid_exception_passes_loader() -> None:
    cfg = build(SiteConfig, _data({"key": KEY, "reason": "r"}), Path("site.yaml"))
    assert cfg.schema_exceptions[0].key == KEY
