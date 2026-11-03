"""Негодное требование heron у темы: E008 с адресом, установка - E032."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.contracts.theme import ThemeConfig
from heron.contracts.wiring import verify_engine
from heron.core.errors import HeronError
from heron.scaffold import create
from heron.themes import install


@pytest.mark.parametrize("spec", [">=x", "0.4", "~=1", ","])
def test_bad_spec_is_e008_with_path(spec: str):
    with pytest.raises(HeronError) as err:
        verify_engine(ThemeConfig(name="t", heron=spec), "/x/theme.yaml")
    assert err.value.code == "E008"
    assert err.value.path == "/x/theme.yaml"
    assert err.value.hint


def test_too_new_theme_is_still_e012():
    with pytest.raises(HeronError) as err:
        verify_engine(ThemeConfig(name="t", heron=">=99.0"), "/x/theme.yaml")
    assert err.value.code == "E012"


@pytest.mark.parametrize("spec", [">=0.1", None])
def test_good_spec_passes(spec):
    verify_engine(ThemeConfig(name="t", heron=spec), "/x/theme.yaml")


def test_cli_build_names_e008_and_theme_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(main, ["new", "demo"]).exit_code == 0
    theme_yaml = tmp_path / "demo" / "theme" / "theme.yaml"
    text = theme_yaml.read_text(encoding="utf-8")
    theme_yaml.write_text(text + '\nheron: ">=x"\n', encoding="utf-8")
    result = runner.invoke(main, ["build", "demo"])
    assert result.exit_code != 0
    assert "E008" in result.output
    assert "theme.yaml" in result.output
    assert "MsgError" not in result.output


def test_install_bad_heron_is_e032(tmp_path: Path):
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"])
    theme_yaml = (root / "theme" / "theme.yaml").read_bytes()
    entries = {
        "theme/theme.yaml": theme_yaml,
        "heron-theme.yaml": b'heron: ">=x"\n',
    }
    blob = io.BytesIO()
    with tarfile.open(fileobj=blob, mode="w:gz") as archive:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    archive_path = tmp_path / "t.tar.gz"
    archive_path.write_bytes(blob.getvalue())
    with pytest.raises(HeronError) as err:
        install(root, "file", archive=archive_path, languages=["en"])
    assert err.value.code == "E032"
