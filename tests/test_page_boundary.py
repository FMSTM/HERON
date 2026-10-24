"""`heron page` не выходит за content/<lang>/ ни через --folder, ни через --lang."""

import os
import shutil

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core.errors import HeronError
from heron.scaffold import create
from heron.scaffold.page import write_page

TYPE = "page"


@pytest.fixture
def root(tmp_path):
    site = tmp_path / "site"
    create(site, name="demo", languages=["en"], notes="en")
    return site


def snapshot(base):
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))


def test_folder_escape_is_refused(root, tmp_path):
    before = snapshot(tmp_path)
    with pytest.raises(HeronError) as caught:
        write_page(root, TYPE, "esc", folder="../../..")
    assert caught.value.code == "E024"
    assert snapshot(tmp_path) == before


def test_folder_dot_segment_is_refused(root):
    with pytest.raises(HeronError) as caught:
        write_page(root, TYPE, "esc", folder="guides/../../x")
    assert caught.value.code == "E024"


def test_hidden_folder_is_refused(root):
    with pytest.raises(HeronError) as caught:
        write_page(root, TYPE, "esc", folder=".git/hooks")
    assert caught.value.code == "E024"


@pytest.mark.parametrize("lang", ["../..", "zz", "en/../.."])
def test_lang_outside_site_languages_is_refused(root, tmp_path, lang):
    before = snapshot(tmp_path)
    with pytest.raises(HeronError) as caught:
        write_page(root, TYPE, "esc", lang=lang)
    assert caught.value.code == "E005"
    assert snapshot(tmp_path) == before


def test_nested_folder_still_works(root):
    made = write_page(root, TYPE, "x", folder="guides/intro")
    assert made == root / "content" / "en" / "guides" / "intro" / "x.md"
    assert made.is_file()


def test_trailing_slash_and_dot_prefix_are_normalized(root):
    made = write_page(root, TYPE, "y", folder="./sub/")
    assert made == root / "content" / "en" / "sub" / "y.md"


def test_empty_folder_and_dot_mean_language_root(root):
    assert write_page(root, TYPE, "a", folder=".").parent == root / "content" / "en"
    assert write_page(root, TYPE, "b").parent == root / "content" / "en"


@pytest.mark.skipif(os.name == "nt", reason="symlinks")
def test_language_folder_symlink_out_is_refused(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    lang_dir = root / "content" / "en"
    shutil.rmtree(lang_dir)
    lang_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(HeronError) as caught:
        write_page(root, TYPE, "x")
    assert caught.value.code == "E024"
    assert not list(outside.iterdir())


def test_cli_folder_escape_fails(root, tmp_path):
    before = snapshot(tmp_path)
    result = CliRunner().invoke(main, ["page", TYPE, "esc", "--folder", "../../..", str(root)])
    assert result.exit_code == 1
    assert "E024" in result.output
    assert snapshot(tmp_path) == before
