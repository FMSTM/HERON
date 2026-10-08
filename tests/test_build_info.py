"""`heron --version` показывает, какая именно сборка на руках."""

from __future__ import annotations

from click.testing import CliRunner

from heron import __version__, build_info


def test_label_from_image_variables(monkeypatch):
    monkeypatch.setenv("HERON_CHANNEL", "beta")
    monkeypatch.setenv("HERON_REVISION", "55249f02dffde477d4c8df3bdd3710e53d9c152d")
    monkeypatch.setenv("HERON_BUILT", "2026-10-08 19:12 UTC")
    assert build_info.label() == f"{__version__} (beta, 55249f0, 2026-10-08 19:12 UTC)"


def test_label_without_anything_is_just_the_version(monkeypatch):
    for name in ("HERON_CHANNEL", "HERON_REVISION", "HERON_BUILT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(build_info, "_from_git", lambda: "")
    assert build_info.label() == __version__


def test_label_from_source_checkout(monkeypatch):
    for name in ("HERON_CHANNEL", "HERON_REVISION", "HERON_BUILT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(build_info, "_from_git", lambda: "abc1234")
    assert build_info.label() == f"{__version__} (source, abc1234)"


def test_cli_version_prints_the_label():
    from heron.cli import main

    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith(f"heron, version {__version__}")
