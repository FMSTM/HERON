"""Какой именно движок запущен: версия, ветка, коммит, время сборки.

Номер версии один на всю ветку разработки: и вчерашняя бета, и сегодняшняя
отвечают 0.1.0. Чтобы по `heron --version` было видно, какой образ на руках,
CI вписывает в образ ветку, коммит и время сборки (HERON_CHANNEL,
HERON_REVISION, HERON_BUILT). Запуск из исходников берёт коммит у git.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from heron import __version__


def _from_git() -> str:
    """Короткий коммит, если движок запущен из клона репозитория."""
    root = Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        return ""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def label() -> str:
    """`0.1.0 (beta, 55249f0, 2026-10-05 19:12 UTC)` — или просто `0.1.0`."""
    channel = os.environ.get("HERON_CHANNEL", "").strip()
    revision = os.environ.get("HERON_REVISION", "").strip()[:7]
    built = os.environ.get("HERON_BUILT", "").strip()
    if not revision:
        revision = _from_git()
        channel = channel or ("source" if revision else "")
    parts = [part for part in (channel, revision, built) if part]
    return f"{__version__} ({', '.join(parts)})" if parts else __version__
