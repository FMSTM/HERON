"""Граница plugins/: имя плагина не уводит из папки сайта, ссылка тоже.

Ошибка схемы site.yaml — E011 (так отвечает loader.build); в спецификации задачи
стояло E002, но это код ошибок фронтматтера.
"""

from __future__ import annotations

import pytest

from heron.contracts.site import load_site
from heron.core import build as pipeline
from heron.core import paths, resolver
from heron.core.errors import HeronError
from heron.core.hooks import Hooks
from heron.scaffold import create

MARKER_CODE = (
    "from pathlib import Path\nPath(__MARK__).write_text('ran')\ndef register(hooks):\n    pass\n"
)


def _outside(tmp_path, name="outside"):
    """Плагин вне сайта, который оставляет маркер, если его исполнили."""
    folder = tmp_path / name
    folder.mkdir()
    marker = tmp_path / f"{name}.marker"
    (folder / "__init__.py").write_text(
        MARKER_CODE.replace("__MARK__", repr(str(marker))), encoding="utf-8"
    )
    return folder, marker


def _site(tmp_path, plugins):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    config = root / "site.yaml"
    config.write_text(
        config.read_text(encoding="utf-8") + f"\nplugins: {plugins}\n", encoding="utf-8"
    )
    return root


def test_traversal_name_in_site_yaml_is_e011(tmp_path):
    _, marker = _outside(tmp_path, "x")
    root = _site(tmp_path, "['../../x']")
    with pytest.raises(HeronError) as exc:
        load_site(root / "site.yaml")
    assert exc.value.code == "E011"
    with pytest.raises(HeronError) as exc:
        pipeline.run(root)
    assert exc.value.code == "E011"
    assert not marker.exists()


def test_duplicate_plugin_names_are_refused(tmp_path):
    root = _site(tmp_path, "[a, a]")
    with pytest.raises(HeronError) as exc:
        load_site(root / "site.yaml")
    assert exc.value.code == "E011"


@pytest.mark.parametrize("name", ["a_b", "seo-2", "a1"])
def test_good_names_are_accepted(tmp_path, name):
    root = _site(tmp_path, f"[{name}]")
    assert load_site(root / "site.yaml").plugins == [name]


@pytest.mark.parametrize("name", ["A", "a.b", "-a", "a/b", "..", "нет", ""])
def test_bad_names_are_refused_by_schema(tmp_path, name):
    root = _site(tmp_path, f"['{name}']")
    with pytest.raises(HeronError) as exc:
        load_site(root / "site.yaml")
    assert exc.value.code == "E011"


@pytest.mark.parametrize("name", ["../../x", "a/b", "нет", ".hidden", "A"])
def test_resolver_refuses_bad_name_directly(tmp_path, name):
    _, marker = _outside(tmp_path, "x")
    root = tmp_path / "site"
    (root / "plugins").mkdir(parents=True)
    with pytest.raises(HeronError) as exc:
        resolver.plugins(root, [name], Hooks())
    assert exc.value.code == "E014"
    assert not marker.exists()


def test_symlinked_plugin_folder_is_e024(tmp_path):
    folder, marker = _outside(tmp_path)
    root = tmp_path / "site"
    (root / "plugins").mkdir(parents=True)
    (root / "plugins" / "linked").symlink_to(folder, target_is_directory=True)
    with pytest.raises(HeronError) as exc:
        resolver.plugins(root, ["linked"], Hooks())
    assert exc.value.code == paths.CODE
    assert not marker.exists()


def test_symlinked_entry_file_is_e024(tmp_path):
    folder, marker = _outside(tmp_path)
    root = tmp_path / "site"
    real = root / "plugins" / "probe"
    real.mkdir(parents=True)
    (real / "__init__.py").symlink_to(folder / "__init__.py")
    with pytest.raises(HeronError) as exc:
        resolver.plugins(root, ["probe"], Hooks())
    assert exc.value.code == paths.CODE
    assert not marker.exists()


def test_real_plugin_still_loads(tmp_path):
    root = tmp_path / "site"
    real = root / "plugins" / "probe"
    real.mkdir(parents=True)
    (real / "__init__.py").write_text("def register(hooks):\n    pass\n", encoding="utf-8")
    found = resolver.plugins(root, ["probe"], Hooks())
    assert [f.name for f in found] == ["probe"]
