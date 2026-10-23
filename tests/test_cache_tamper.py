"""Подменённый кэш нарезок не приносит чужие файлы в dist.

Кэш могут восстановить из чужого архива или положить в репозиторий сайта:
ссылка на месте готовой нарезки — частный случай. Корректный кэш при этом
должен использоваться как прежде, без перекодирования.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.scaffold import create

SECRET = b"SECRET-MARKER-cache"


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True)
    Image.new("RGB", (640, 480), (200, 30, 30)).save(root / "media" / "pic.png")
    index = root / "content" / "en" / "index.md"
    index.write_text(
        index.read_text("utf-8") + "\n\n## Pic {#pic}\n\n![A picture](media/pic.png)\n",
        encoding="utf-8",
    )
    home = root / "theme" / "templates" / "home.html"
    home.write_text(
        home.read_text("utf-8").replace(
            "{% block content %}",
            "{% block content %}{{ picture('media/pic.png', '16:9', alt='x') }}",
            1,
        ),
        encoding="utf-8",
    )
    return root


def _slices(root: Path) -> list[Path]:
    return sorted(
        p
        for p in (root / ".heron-cache").rglob("*")
        if p.suffix in (".avif", ".webp", ".png") and (p.is_file() or p.is_symlink())
    )


def _leaks(root: Path) -> list[Path]:
    return [p for p in (root / "dist").rglob("*") if p.is_file() and SECRET in p.read_bytes()]


@pytest.mark.parametrize("warm_dist", [False, True])
def test_symlinked_slice_is_recreated_not_published(tmp_path, warm_dist):
    root = _site(tmp_path)
    assert not pipeline.run(root).failed
    good = {p.name: p.read_bytes() for p in _slices(root)}
    secret = tmp_path / "secret.bin"
    secret.write_bytes(SECRET)
    victim = _slices(root)[0]
    victim.unlink()
    victim.symlink_to(secret)
    if not warm_dist:
        shutil.rmtree(root / "dist")

    result = pipeline.run(root)

    assert not result.failed, [e.message for e in result.collector.errors]
    assert not _leaks(root)
    assert not victim.is_symlink() and victim.read_bytes() == good[victim.name]
    assert secret.read_bytes() == SECRET  # внешний файл не тронут


def test_directory_in_place_of_a_slice_is_an_error(tmp_path):
    root = _site(tmp_path)
    assert not pipeline.run(root).failed
    victim = _slices(root)[0]
    victim.unlink()
    victim.mkdir()
    (victim / "keep").write_bytes(b"x")
    before = {p: p.read_bytes() for p in (root / "dist").rglob("*") if p.is_file()}

    with pytest.raises(HeronError) as error:
        pipeline.run(root)

    assert error.value.code == "E024"
    assert (victim / "keep").exists()
    after = {p: p.read_bytes() for p in (root / "dist").rglob("*") if p.is_file()}
    assert after == before  # dist при ошибке не тронут


def test_valid_cache_is_reused_without_encoding(tmp_path, monkeypatch):
    root = _site(tmp_path)
    assert not pipeline.run(root).failed
    stamps = {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in _slices(root)}
    shutil.rmtree(root / "dist")

    from heron.core import media

    def boom(*args, **kwargs):
        raise AssertionError("кэш корректен — кодировать нечего")

    monkeypatch.setattr(media, "slice_master", boom)
    assert not pipeline.run(root).failed
    assert {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in _slices(root)} == stamps
    linked = [p for p in (root / "dist" / "media").glob("pic-*") if os.stat(p).st_nlink > 1]
    assert linked  # нарезки в dist — те же файлы, что в кэше
