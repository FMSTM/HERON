"""Корень кэша сам по себе не может быть ссылкой.

Проверки записей и каталогов версий сравнивали путь с разрешённым корнем
кэша. Если `.heron-cache` или `.heron-cache/renditions` — ссылка наружу,
«внутри кэша» оказывалась чужая папка, и уборка удаляла её содержимое.
Все чужие файлы — только во временных папках.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from heron.core import build as pipeline
from heron.core import media
from heron.core.errors import HeronError
from heron.scaffold import create

SECRET = "чужое-содержимое"
LATER = time.time() + 400 * 86400


def bait(tmp_path: Path) -> Path:
    """Папка, похожая на кэш изнутри: renditions/<версия>/<запись>/файл."""
    outside = tmp_path / "outside"
    entry = outside / media.SLICES / f"v{media.CACHE_VERSION}-x" / ("0" * 64)
    entry.mkdir(parents=True)
    (entry / "keep.txt").write_text(SECRET, encoding="utf-8")
    (outside / "top.txt").write_text(SECRET, encoding="utf-8")
    return outside


def intact(outside: Path) -> bool:
    files = [p for p in outside.rglob("*") if p.is_file()]
    return len(files) == 2 and all(p.read_text(encoding="utf-8") == SECRET for p in files)


def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    return root


def test_sweep_refuses_cache_root_symlinked_out(tmp_path):
    outside = bait(tmp_path)
    cache = tmp_path / "site" / ".heron-cache"
    cache.parent.mkdir()
    os.symlink(outside, cache)
    with pytest.raises(HeronError) as error:
        media.sweep(cache, now=LATER)
    assert error.value.code == "E024"
    assert intact(outside)


def test_sweep_refuses_slices_symlinked_out(tmp_path):
    outside = bait(tmp_path)
    cache = tmp_path / "site" / ".heron-cache"
    cache.mkdir(parents=True)
    os.symlink(outside / media.SLICES, cache / media.SLICES)
    with pytest.raises(HeronError) as error:
        media.sweep(cache, now=LATER)
    assert error.value.code == "E024"
    assert intact(outside)


def test_using_refuses_dangling_cache_link_and_creates_nothing(tmp_path):
    target = tmp_path / "nowhere"
    cache = tmp_path / "site" / ".heron-cache"
    cache.parent.mkdir()
    os.symlink(target, cache)
    with pytest.raises(HeronError) as error, media.using(cache):
        pass
    assert error.value.code == "E024"
    assert not target.exists()


def test_build_with_cache_root_symlinked_out_is_e024_and_touches_nothing(tmp_path):
    root = site(tmp_path)
    outside = bait(tmp_path)
    os.symlink(outside, root / ".heron-cache")
    with pytest.raises(HeronError) as error:
        pipeline.run(root)
    assert error.value.code == "E024"
    assert intact(outside)
    assert "удалите" in (error.value.hint or "")


def test_cache_under_symlinked_parent_still_works(tmp_path):
    """Ссылка выше кэша (вся папка сайта — ссылкой) — законна."""
    real = site(tmp_path)
    alias = tmp_path / "alias"
    os.symlink(real, alias)
    result = pipeline.run(alias)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (real / ".heron-cache" / media.SLICES).is_dir()
    assert not (real / ".heron-cache").is_symlink()


def test_normal_cache_sweep_still_removes_stale_entries(tmp_path):
    cache = tmp_path / "site" / ".heron-cache"
    stale = media.store(cache) / ("1" * 64)
    stale.mkdir(parents=True)
    (stale / "x.webp").write_bytes(b"x")
    removed = media.sweep(cache, now=LATER)
    assert stale in removed and not stale.exists()
