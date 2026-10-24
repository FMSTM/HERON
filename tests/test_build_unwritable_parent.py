"""Папка над --out недоступна на запись: E035 с путём, а не общее «denied»."""

import os

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core import build
from heron.core.errors import HeronError
from heron.scaffold import create

pytestmark = pytest.mark.skipif(os.geteuid() == 0, reason="root пишет в любую папку")


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"])
    parent = tmp_path / "ro"
    parent.mkdir()
    parent.chmod(0o555)
    yield root, parent
    parent.chmod(0o755)


def test_build_into_readonly_parent_is_e035(setup):
    root, parent = setup
    with pytest.raises(HeronError) as raised:
        build.run(root, dist=parent / "dist")
    error = raised.value
    assert error.code == "E035"
    assert str(parent / ".heron-cache") in error.path
    assert "доступна для записи" in error.hint
    assert not (parent / "dist").exists()  # dist не тронут
    assert list(parent.iterdir()) == []


def test_cli_exits_1_with_code_not_denied(setup):
    root, parent = setup
    result = CliRunner().invoke(main, ["build", str(root), "--out", str(parent / "dist")])
    assert result.exit_code == 1
    assert "E035" in result.output
    assert "No permission to write" not in result.output


def test_unwritable_lock_is_e035(tmp_path):
    from heron.core import output

    parent = tmp_path / "p"
    parent.mkdir()
    dist = parent / "dist"
    dist.mkdir()
    parent.chmod(0o555)
    try:
        with pytest.raises(HeronError) as raised:
            output.commit(dist, output.Outputs())
    finally:
        parent.chmod(0o755)
    assert raised.value.code == "E035"
    assert "heron-lock" in raised.value.path
