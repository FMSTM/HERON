"""`heron page add` и `category add` не выходят за content/<язык>/: ни ключом, ни категорией."""

import os
import shutil

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core.errors import HeronError
from heron.edit import entity as ops
from heron.scaffold import create


@pytest.fixture
def root(tmp_path):
    site = tmp_path / "site"
    create(site, name="demo", languages=["en"], notes="en")
    return site


def snapshot(base):
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))


def run(*args):
    return CliRunner().invoke(main, list(args))


@pytest.mark.parametrize(
    "key", ["../../esc", "guides/../../x", ".git/hooks", "a//b/..", "/abs/../x", "UP"]
)
def test_bad_keys_are_refused_before_any_write(root, tmp_path, key):
    before = snapshot(tmp_path)
    with pytest.raises(HeronError) as caught:
        ops.norm_key(key)
    assert caught.value.code == "E005"
    result = run("page", "add", key, str(root))
    assert result.exit_code == 1 and "E005" in result.output, result.output
    result = run("category", "add", key, str(root))
    assert result.exit_code == 1 and "E005" in result.output, result.output
    assert snapshot(tmp_path) == before


def test_category_flag_escape_is_refused(root, tmp_path):
    before = snapshot(tmp_path)
    result = run("page", "add", "esc", "--category", "../../..", str(root))
    assert result.exit_code == 1 and "E005" in result.output
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("lang", ["../..", "zz", "en/../.."])
def test_lang_outside_site_languages_is_refused(root, tmp_path, lang):
    before = snapshot(tmp_path)
    result = run("page", "add", "esc", "--lang", lang, str(root))
    assert result.exit_code == 1 and "E005" in result.output, result.output
    assert snapshot(tmp_path) == before


def test_nested_category_still_works(root):
    result = run("page", "add", "x", "--category", "guides/intro", str(root))
    assert result.exit_code == 0, result.output
    assert (root / "content" / "en" / "guides" / "intro" / "x.md").is_file()
    assert (root / "content" / "en" / "guides" / "_index.md").is_file()
    assert (root / "content" / "en" / "guides" / "intro" / "_index.md").is_file()


def test_slashes_around_a_key_are_normalized(root):
    assert run("page", "add", "/sub/y/", str(root)).exit_code == 0
    assert (root / "content" / "en" / "sub" / "y.md").is_file()


@pytest.mark.skipif(os.name == "nt", reason="symlinks")
def test_language_folder_symlink_out_is_refused(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    lang_dir = root / "content" / "en"
    shutil.rmtree(lang_dir)
    lang_dir.symlink_to(outside, target_is_directory=True)
    result = run("page", "add", "x", str(root))
    assert result.exit_code == 1 and "E024" in result.output, result.output
    assert not list(outside.iterdir())
