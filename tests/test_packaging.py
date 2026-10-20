"""Всё, что pyproject.toml кладёт в пакет принудительно, доезжает до сборки образа.

Hatchling падает, если файла из force-include нет в контексте, — а контекст
сборки в Dockerfile собирается командами COPY. Новая запись в force-include
без COPY ломала сборку образа только в CI.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _copied() -> list[str]:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    build = text.split("\nFROM ", 2)[1]  # только сборочная стадия
    out: list[str] = []
    for line in build.splitlines():
        match = re.match(r"COPY\s+(?!--from)(.+)\s+\S+$", line.strip())
        if match:
            out.extend(match.group(1).split())
    return out


def test_force_include_is_copied_into_the_image():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    forced = data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    copied = _copied()
    for source in forced:
        assert (ROOT / source).exists(), source
        assert any(source == c or source.startswith(c.rstrip("/") + "/") for c in copied), (
            f"{source} есть в force-include, но Dockerfile его не копирует"
        )
