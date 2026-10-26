"""Язык пояснений новой папки сайта: ru или en во всех файлах скелета.

Спецификация: docs/spec/23-distribution.md, раздел 4.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron import scaffold
from heron.cli import main
from heron.core import build as pipeline
from heron.scaffold import adopt, create

CYRILLIC = re.compile(r"[а-яА-ЯёЁіїєІЇЄ]")
COMMENTED = ["site.yaml", "theme/theme.yaml", "content/en/index.md", "content/en/404.md"]


def _comments(path):
    """Комментарии файла; у страницы — только из SEO-блока: якоря секций
    `{#about}` в тексте — не комментарии."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".md" and text.startswith("---"):
        text = text.split("---", 2)[1]
    return "\n".join(line.split("#", 1)[1] for line in text.splitlines() if "#" in line)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_scaffold_file_speaks_one_language(tmp_path, lang):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["en"], notes=lang)
    for rel in COMMENTED:
        text = _comments(root / rel)
        assert text.strip(), rel
        assert bool(CYRILLIC.search(text)) is (lang == "ru"), rel
    for note in root.rglob("heron-readme.md"):
        assert bool(CYRILLIC.search(note.read_text(encoding="utf-8"))) is (lang == "ru"), note
    assert (
        yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))["build"]["notes"] == lang
    )


def test_starter_site_builds_right_away(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk", "en"], notes="en")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (root / "dist" / "index.html").is_file()
    assert (root / "dist" / "en" / "index.html").is_file()
    assert (root / "dist" / "404.html").is_file()


def test_init_takes_comments_from_site_yaml(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"], notes="en")
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["site"]["languages"] = ["uk", "ru"]
    (root / "site.yaml").write_text(yaml.safe_dump(conf), encoding="utf-8")
    adopt(root)
    assert not CYRILLIC.search(_comments(root / "content" / "ru" / "index.md"))


def test_cli_new_and_page_use_the_language(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(main, ["new", "site", "--notes", "en"]).exit_code == 0
    result = runner.invoke(main, ["page", "page", "about", "site"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "site" / "content" / "en" / "about.md").read_text(encoding="utf-8")
    assert "# ================= 1. BASICS" in text
    assert "# ================= 8. RELATIONS" in text


def test_default_is_english(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    assert not CYRILLIC.search(_comments(root / "site.yaml"))


def test_env_variable_switches_language(tmp_path, monkeypatch):
    monkeypatch.setenv("HERON_NOTES", "ru")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["new", "site"])
    assert result.exit_code == 0, result.output
    assert "Сайт создан: site" in result.output
    assert CYRILLIC.search(_comments(tmp_path / "site" / "site.yaml"))


def test_flag_beats_env_and_site_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("HERON_NOTES", "ru")
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"], notes="ru")
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["site"]["languages"] = ["uk", "en"]
    (root / "site.yaml").write_text(yaml.safe_dump(conf), encoding="utf-8")
    adopt(root, notes="en")
    assert not CYRILLIC.search(_comments(root / "content" / "en" / "index.md"))


def test_english_cli_messages(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["new", "site"])
    assert "Site created: site" in result.output
    assert not CYRILLIC.search(result.output)


# --- демо-страница: ветка канала образа (E13.S1.T22) -------------------------------

DEMO_SOURCE = Path(scaffold.__file__).parent / "demo"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_demo_page_points_at_the_channel_branch(tmp_path, monkeypatch, lang):
    """Из beta-образа демо-страница ведёт на beta, вне образа и из prod — на prod.

    Ссылки и образ в готовой команде — по тому же правилу, что комплект (23 §12).
    """
    source = (DEMO_SOURCE / lang / "docs.md").read_text(encoding="utf-8")
    assert "/HERON/tree/prod/docs/ru/guide" in source and "/beta/" not in source
    assert "ghcr.io/fmstm/heron:prod serve ." in source and "heron:beta" not in source
    for channel, want in ((None, "prod"), ("  ", "prod"), ("prod", "prod"), ("beta", "beta")):
        if channel is None:
            monkeypatch.delenv("HERON_CHANNEL", raising=False)
        else:
            monkeypatch.setenv("HERON_CHANNEL", channel)
        root = tmp_path / f"s-{want}-{len(channel or '')}"
        root.mkdir()
        create(root, name="S", languages=[lang], demo=True, agents="false")
        page = (root / "content" / lang / "docs.md").read_text(encoding="utf-8")
        body = page.split("\n---\n", 1)[1].removeprefix("\n")
        other = "beta" if want == "prod" else "prod"
        assert f"https://github.com/FMSTM/HERON/tree/{want}/docs/ru/guide" in body
        assert f"https://github.com/FMSTM/HERON/blob/{want}/AGENTS.md" in body
        assert f"/HERON/tree/{other}/" not in body and f"/HERON/blob/{other}/" not in body
        assert f"ghcr.io/fmstm/heron:{want} serve ." in body
        assert f"ghcr.io/fmstm/heron:{other}" not in body
        if want == "prod":
            assert body == source  # в prod — байт в байт как исходник
        else:
            expected = source.replace("/prod/", f"/{want}/")
            assert body == expected.replace("heron:prod serve", f"heron:{want} serve")
