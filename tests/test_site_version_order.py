"""Порядок проверок site.yaml: версия движка раньше строгой схемы (E012 раньше E011)."""

import re

import pytest
import yaml

from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.scaffold import create

HOME_MD = "---\ntitle: Демо\nh1: Демо\ndescription: Описание\n---\n\nТекст.\n"


def _site(tmp_path, heron: str | None):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    (root / "content" / "uk" / "index.md").write_text(HOME_MD, encoding="utf-8")
    path = root / "site.yaml"
    text = path.read_text(encoding="utf-8")
    if heron is not None:
        text = re.sub(r"^heron: .*$", f'heron: "{heron}"', text, count=1, flags=re.M)
    # Неизвестный ключ в блоке build: схема build закрытая (extra=forbid).
    data = yaml.safe_load(text)
    assert isinstance(data.get("build"), dict) or "build" not in data
    text += "\nbuild:\n  brand_new_key: 1\n" if "build" not in data else ""
    if "build" in data:
        text = re.sub(r"^build:[ \t]*\n", "build:\n  brand_new_key: 1\n", text, count=1, flags=re.M)
    path.write_text(text, encoding="utf-8")
    assert "brand_new_key" in yaml.safe_load(text)["build"]
    return root


def test_new_key_with_newer_heron_gives_version_error(tmp_path):
    root = _site(tmp_path, ">=9.0")
    with pytest.raises(HeronError) as exc:
        pipeline.run(root)
    assert exc.value.code == "E012"


def test_unknown_key_with_suitable_heron_still_e011(tmp_path):
    root = _site(tmp_path, None)
    with pytest.raises(HeronError) as exc:
        pipeline.run(root)
    assert exc.value.code == "E011"
