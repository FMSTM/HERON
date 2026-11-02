"""Сообщения output и paths на ключах texts/output.py: ru прежний, en без кириллицы."""

import os
import re
from pathlib import Path

import pytest

from heron.core import output, paths
from heron.core.errors import Collector, HeronError
from heron.messages import Msg

CYR = re.compile("[а-яА-ЯёЁ]")


def _en_ok(error: HeronError) -> str:
    for part in (error.message, error.hint):
        if part is None:
            continue
        assert isinstance(part, Msg)
        assert not CYR.search(part.text("en"))
    return error.message.text("en")


def test_source_escape(tmp_path):
    with pytest.raises(HeronError) as info:
        paths.source(tmp_path, "../x")
    assert info.value.message == f"путь '../x' выходит за пределы {tmp_path.name}/"
    assert _en_ok(info.value) == f"path '../x' goes outside {tmp_path.name}/"
    assert info.value.hint.text("ru").startswith("файлы сайта берутся")


def test_target_escape_and_link(tmp_path):
    with pytest.raises(HeronError) as info:
        paths.target(tmp_path, "../x")
    assert info.value.message == "результат '../x' оказался бы вне папки сборки"
    assert _en_ok(info.value) == "output '../x' would end up outside the build folder"
    outside = tmp_path / "outside"
    outside.mkdir()
    dist = tmp_path / "dist"
    dist.mkdir()
    os.symlink(outside, dist / "a")
    with pytest.raises(HeronError) as info:
        paths.target(dist, "a/f.txt")
    assert info.value.message == "результат a/f.txt ведёт за пределы папки сборки через ссылку"
    _en_ok(info.value)


def test_in_site_link(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    os.symlink(tmp_path, site / "ln")
    with pytest.raises(HeronError) as info:
        paths.in_site(site, "ln/x")
    assert info.value.message == "ln/x ведёт за пределы папки сайта через символическую ссылку"
    assert _en_ok(info.value).endswith("outside the site folder through a symbolic link")


def test_unreadable_and_layout(tmp_path):
    error = paths.unreadable(tmp_path / "d", PermissionError(13, "Permission denied"))
    assert error.message == f"не читается {tmp_path / 'd'}: Permission denied"
    assert _en_ok(error) == f"cannot read {tmp_path / 'd'}: Permission denied"
    site = tmp_path / "site"
    (site / "content").mkdir(parents=True)
    with pytest.raises(HeronError) as info:
        paths.layout(site, site, tmp_path / "cache", [site / "content"])
    assert info.value.message == "папка сборки совпадает с папкой сайта или содержит её"
    _en_ok(info.value)
    with pytest.raises(HeronError) as info:
        paths.layout(site, site / "content", tmp_path / "cache", [site / "content"])
    assert info.value.message == "папка сборки пересекается с исходниками: content/"
    assert _en_ok(info.value) == "the build folder overlaps the sources: content/"


def test_outputs_conflict_and_reserved():
    outs = output.Outputs()
    collector = Collector()
    outs.add("a.txt", output.Entry(owner="X", kind="page", text="1"), collector)
    outs.add("a.txt", output.Entry(owner="Y", kind="page", text="2"), collector)
    outs.add(".heron-manifest.json", output.Entry(owner="Z", kind="page", text="3"), collector)
    outs.add("../b", output.Entry(owner="W", kind="page", text="4"), collector)
    texts = [e.message for e in collector.errors]
    assert "два источника дают один файл сборки a.txt: X и Y" in texts
    assert "Z: .heron-manifest.json - служебное имя сборки, его пишет сам движок" in texts
    assert "W: выходной путь '../b' вне папки сборки" in texts
    for e in collector.errors:
        _en_ok(e)
    conflict = next(e for e in collector.errors if e.hint.text("ru") == "переименуйте один из них")
    assert conflict.message.text("en") == "two sources give one build file a.txt: X and Y"


def test_override_unused_and_tree():
    outs = output.Outputs(overrides={"robots.txt"})
    collector = Collector()
    outs.check_overrides(collector)
    (warning,) = collector.warnings
    assert warning.message == (
        "build.overrides: robots.txt ничего не подменяет - "
        "нет ни генерированного файла, ни файла в static/"
    )
    assert not CYR.search(warning.message.text("en"))
    outs.overrides = set()
    outs.entries = {
        "a": output.Entry(owner="P", kind="page", text=""),
        "a/index.html": output.Entry(owner="Q", kind="page", text=""),
    }
    collector = Collector()
    outs.check_tree(collector)
    (error,) = collector.errors
    assert error.message == "a - и файл (P), и папка для a/index.html (Q)"
    assert _en_ok(error) == "a is both a file (P) and a folder for a/index.html (Q)"


def test_text_of_not_utf8(tmp_path):
    bad = tmp_path / "f.bin"
    bad.write_bytes(b"\xff\xfe")
    outs = output.Outputs()
    outs.entries["f"] = output.Entry(owner="own", kind="static", source=bad)
    with pytest.raises(HeronError) as info:
        outs.text_of("f")
    assert info.value.message == "f из own: не UTF-8 (байт 0)"
    assert _en_ok(info.value) == "f from own: not UTF-8 (byte 0)"


def test_unwritable():
    error = output.unwritable(Path("/x/y"), OSError(13, "Permission denied"))
    assert error.message == "не удалось создать /x/y: Permission denied"
    assert _en_ok(error) == "could not create /x/y: Permission denied"
