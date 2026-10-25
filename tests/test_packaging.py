"""Всё, что pyproject.toml кладёт в пакет принудительно, доезжает до сборки образа.

Hatchling падает, если файла из force-include нет в контексте, — а контекст
сборки в Dockerfile собирается командами COPY. Новая запись в force-include
без COPY ломала сборку образа только в CI.
"""

import re
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

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


# --- документация и навыки в пакете (23 §2, 21 §10) ---------------------------


def _forced() -> dict[str, str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]


def _shipped() -> list[str]:
    """Что обязано ехать в пакете: docs/<язык>/** (какие языки есть), translation.yaml, навыки."""
    out = ["docs/translation.yaml"]
    for lang in ("ru", "en"):
        tree = ROOT / "docs" / lang
        if tree.is_dir():
            out += [
                p.relative_to(ROOT).as_posix()
                for p in sorted(tree.rglob("*"))
                if p.is_file() and not p.name.startswith(".")
            ]
    out += [p.relative_to(ROOT).as_posix() for p in sorted(ROOT.glob("skills/*/SKILL.md"))]
    return out


def _covered(rel: str, sources) -> bool:
    return any(rel == s or rel.startswith(s.rstrip("/") + "/") for s in sources)


def test_docs_languages_and_skills_are_packed_and_copied():
    """Каждый файл docs/{ru,en}/**, translation.yaml и skills/*/SKILL.md — в force-include и в COPY.

    docs/en может ещё не быть: тогда проверяются только существующие файлы, а строку
    "docs/en" в force-include добавляют вместе с переводом (без неё этот тест упадёт).
    """
    forced, copied = _forced(), _copied()
    shipped = _shipped()
    assert "docs/ru/README.md" in shipped and "skills/heron/SKILL.md" in shipped
    for rel in shipped:
        assert _covered(rel, forced), f"{rel} не покрыт force-include"
        assert _covered(rel, copied), f"{rel} не копируется в Dockerfile"
    assert forced["docs/ru"] == "heron/_docs/docs/ru"
    assert forced["docs/translation.yaml"] == "heron/_docs/docs/translation.yaml"
    assert forced["skills"] == "heron/_docs/skills"
    if (ROOT / "docs" / "en").is_dir():
        assert forced.get("docs/en") == "heron/_docs/docs/en"


def test_dockerfile_copies_docs_languages_and_skills():
    copied = _copied()
    for rel in ("docs/ru", "docs/en", "docs/translation.yaml", "skills"):
        assert _covered(rel, copied), f"Dockerfile не копирует {rel}"
    assert "docs/brand/" in (ROOT / ".dockerignore").read_text(encoding="utf-8").split()


@pytest.mark.skipif(shutil.which("uv") is None, reason="нет uv: колесо собрать нечем")
def test_wheel_contains_docs_and_skills(tmp_path):
    """Настоящее колесо: документация и навыки внутри, бренда нет, текста меньше 2 МБ."""
    work = tmp_path / "src"
    shutil.copytree(
        ROOT,
        work,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".uvcache", "out", "dist", "__pycache__", ".*cache", "node_modules"
        ),
    )
    done = subprocess.run(
        ["uv", "build", "--wheel", "--offline", "-q", "-o", str(tmp_path / "dist")],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr
    (wheel,) = (tmp_path / "dist").glob("heron-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        infos = {i.filename: i for i in archive.infolist()}
    for name in (
        "heron/_docs/docs/ru/README.md",
        "heron/_docs/docs/translation.yaml",
        "heron/_docs/skills/heron/SKILL.md",
        "heron/_docs/AGENTS.md",
        "heron/_docs/README.md",
        "heron/_recipe/Dockerfile.site",
    ):
        assert name in infos, name
    for rel in _shipped():
        assert f"heron/_docs/{rel}" in infos, rel
    assert not any("/brand/" in name for name in infos)
    text = sum(i.file_size for name, i in infos.items() if name.startswith("heron/_docs/"))
    assert text < 2 * 1024 * 1024, text
