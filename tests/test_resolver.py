"""Поиск темы и плагинов: локальное сильнее установленного."""

import pytest
import yaml

from heron.core import resolver
from heron.core.errors import HeronError
from heron.core.hooks import Hooks


def make_theme(root, name="demo"):
    path = root / "theme"
    path.mkdir(parents=True, exist_ok=True)
    (path / "theme.yaml").write_text(yaml.safe_dump({"name": name}), encoding="utf-8")
    return path


def test_local_theme_found(tmp_path):
    make_theme(tmp_path)
    found = resolver.theme(tmp_path, "demo")
    assert found.path == tmp_path / "theme"
    assert found.source == "локальная"


def test_missing_theme_is_e013(tmp_path):
    with pytest.raises(HeronError) as exc:
        resolver.theme(tmp_path, "demo")
    assert exc.value.code == "E013"
    assert "heron-theme-demo" in str(exc.value)


def test_folder_without_paspоrt_is_not_a_theme(tmp_path):
    (tmp_path / "theme").mkdir()
    with pytest.raises(HeronError) as exc:
        resolver.theme(tmp_path, "demo")
    assert exc.value.code == "E013"


def local_plugin(root, name, body):
    path = root / "plugins" / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").write_text(body, encoding="utf-8")
    return path


def test_local_plugin_registers_hooks(tmp_path):
    local_plugin(
        tmp_path,
        "prices",
        "def register(hooks):\n    hooks.on('block:price', lambda section: [])\n",
    )
    hooks = Hooks()
    found = resolver.plugins(tmp_path, ["prices"], hooks)
    assert found[0].source == "локальный"
    assert hooks.block("price") is not None


def test_plugin_without_register_is_e014(tmp_path):
    local_plugin(tmp_path, "broken", "VALUE = 1\n")
    with pytest.raises(HeronError) as exc:
        resolver.plugins(tmp_path, ["broken"], Hooks())
    assert exc.value.code == "E014"
    assert "register" in str(exc.value)


def test_plugin_that_explodes_is_e014(tmp_path):
    local_plugin(tmp_path, "boom", "raise RuntimeError('дурная ошибка')\n")
    with pytest.raises(HeronError) as exc:
        resolver.plugins(tmp_path, ["boom"], Hooks())
    assert exc.value.code == "E014"
    assert "дурная ошибка" in str(exc.value)


def test_unknown_plugin_is_e014(tmp_path):
    with pytest.raises(HeronError) as exc:
        resolver.plugins(tmp_path, ["нет-такого"], Hooks())
    assert exc.value.code == "E014"


def test_empty_list_resolves_to_nothing(tmp_path):
    assert resolver.plugins(tmp_path, [], Hooks()) == []
