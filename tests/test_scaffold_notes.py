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
    assert f"/HERON/tree/prod/docs/{lang}/guide" in source and "/beta/" not in source
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
        assert f"https://github.com/FMSTM/HERON/tree/{want}/docs/{lang}/guide" in body
        assert f"https://github.com/FMSTM/HERON/blob/{want}/AGENTS.md" in body
        assert f"/HERON/tree/{other}/" not in body and f"/HERON/blob/{other}/" not in body
        assert f"ghcr.io/fmstm/heron:{want} serve ." in body
        assert f"ghcr.io/fmstm/heron:{other}" not in body
        if want == "prod":
            assert body == source  # в prod — байт в байт как исходник
        else:
            expected = source.replace("/prod/", f"/{want}/")
            assert body == expected.replace("heron:prod serve", f"heron:{want} serve")


# --- записка корня сайта: образ как основной путь, комплект agents (E12.S1.T2) --------

NOTES_SOURCE = Path(scaffold.__file__).parent / "notes"
H_LINE = (
    'H="docker run --rm -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"'
)


def _root_note(tmp_path, lang):
    root = tmp_path / f"s-{lang}"
    root.mkdir()
    create(root, name="My Site", languages=["en"], notes=lang, agents="false")
    return (root / "heron-readme.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_root_note_names_the_kit_and_the_pointers(tmp_path, lang):
    text = _root_note(tmp_path, lang)
    rows = [line for line in text.splitlines() if line.startswith("|")]
    assert any(line.startswith("| `agents/` |") and "agents/work/" in line for line in rows)
    assert any(
        all(name in line.split("|")[1] for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"))
        for line in rows
    )
    last = text.split("\n## ")[-1]  # последний раздел - про агента
    assert "AGENTS.md" in last and "`agents/work/`" in last


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_root_note_works_through_the_image(tmp_path, lang):
    text = _root_note(tmp_path, lang)
    assert H_LINE in text
    for command in ("$H init .", "$H check .", "$H serve .", "$H build . --env prod --strict"):
        assert command in text, command
    # путь через клон движка - одной строкой, не основной порядок работы
    assert text.count("scripts/site.sh") == 1
    assert "./scripts/site.sh my-site <" in text
    assert "site.sh my-site init" not in text  # старый порядок через клон ушёл


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_root_note_has_no_unfilled_placeholders(tmp_path, lang):
    text = _root_note(tmp_path, lang)
    assert "{" not in text and "}" not in text  # ни {name}, ни {slug}, ни фигурных скобок
    assert text.startswith("# My Site\n")
    assert "my-site" in text  # {slug} подставлен


def test_root_note_has_the_same_structure_in_both_languages():
    """ru и en: те же заголовки, строки таблицы, блоки кода и плейсхолдеры."""

    def shape(lang):
        text = (NOTES_SOURCE / lang / "root.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        return (
            len([line for line in lines if line.startswith("#")]),
            [line.count("|") for line in lines if line.startswith("|")],
            text.count("```"),
            sorted(re.findall(r"\{\w+\}", text)),
            len([line for line in lines if line.startswith("$H ")]),
        )

    assert shape("ru") == shape("en")
    en = (NOTES_SOURCE / "en" / "root.md").read_text(encoding="utf-8")
    assert not CYRILLIC.search(en)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_demo_docs_page_mentions_the_agent_kit_once(lang):
    text = (DEMO_SOURCE / lang / "docs.md").read_text(encoding="utf-8")
    assert text.count("agents/") == 1 and text.count("`AGENTS.md`") == 1
    commands, where = text.split("{#where}")[0], text.split("{#where}")[1]
    line = next(row for row in commands.splitlines() if "`agents/`" in row)
    assert commands.index("heron build . --env prod --strict") < commands.index(line)
    assert bool(CYRILLIC.search(line)) is (lang == "ru")
    assert "agents/" not in where


# --- комментарии стартовой темы и шапка site.yaml (E15.S1.T4: F07, F24) ---------

from heron import docs as library  # noqa: E402
from heron.scaffold import NOTE_MARK, TEMPLATES, theme_notes, with_notes  # noqa: E402
from heron.setup import HEADER  # noqa: E402

LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
# Комментарий темы: Jinja {# … #}, CSS /* … */, строка JS // …
THEME_COMMENT = re.compile(r"\{#.*?#\}|/\*.*?\*/|^\s*//.*$", re.S | re.M)
# Технические токены, которые в русском комментарии не переводятся
TOKENS = {
    "HERON",
    "CSS",
    "site",
    "yaml",
    "contact",
    "channels",
    "heron",
    "setup",
    "mark",
    "localStorage",
    "consent",
    "yes",
    "analytics",
    "tojson",
    "data",
    "theme",
    "checklist",
    "two",
    "lists",
    "timeline",
    "index",
    "mod",
    "faq",
}


def _theme_comments(root):
    for path in sorted((root / "theme").rglob("*")):
        if path.is_file() and path.suffix in (".html", ".css"):
            text = path.read_text(encoding="utf-8")
            for found in THEME_COMMENT.finditer(text):
                yield path.relative_to(root).as_posix(), found.group(0)


def test_theme_note_tables_have_the_same_keys_and_cover_every_mark():
    ru, en = theme_notes("ru"), theme_notes("en")
    assert set(ru) == set(en)
    used = set()
    for source in TEMPLATES.rglob("*"):
        if source.is_file():
            for found in NOTE_MARK.finditer(source.read_text(encoding="utf-8")):
                used.add(found.group(1) or found.group(2))
    assert used == set(ru), used ^ set(ru)
    # метка, которой нет в таблице, не уезжает в сайт молча
    with pytest.raises(KeyError):
        with_notes("{# heron:note no-such-note #}", "ru")


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_theme_comments_speak_the_notes_language(tmp_path, lang):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["en"], notes=lang)
    comments = list(_theme_comments(root))
    assert len(comments) >= 13
    for rel, text in comments:
        assert "heron:note" not in text, rel
        if lang == "en":
            assert not CYRILLIC.search(text), (rel, text)
        else:
            assert CYRILLIC.search(text), (rel, text)
            # латиница в русском комментарии — только токены: `код`, пути, имена ключей
            plain = re.sub(r"`[^`]*`|\{\{.*?\}\}|[\w.-]*[._/-][\w./*-]*|--[\w-]+", " ", text)
            stray = [w for w in LATIN_WORD.findall(plain) if w not in TOKENS]
            assert not stray, (rel, stray)
    # en-сайт: во всей теме, кроме i18n чужого языка, кириллицы нет вовсе
    if lang == "en":
        for path in (root / "theme").rglob("*"):
            if path.is_file() and "i18n" not in path.parts:
                assert not CYRILLIC.search(path.read_text(encoding="utf-8")), path


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_dist_carries_no_comment_of_the_other_language(tmp_path, lang):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["en"], notes=lang)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    pages = list(dist.rglob("*.html"))
    assert pages
    for page in pages:
        html = page.read_text(encoding="utf-8")
        # инлайн-скриптов нет: JSON-LD это данные, остальное только по src
        for attrs in re.findall(r"<script\b([^>]*)>", html):
            assert "src=" in attrs or 'type="application/ld+json"' in attrs, (page, attrs)
        if lang == "en":
            assert not CYRILLIC.search(html), page
    # скрипт темы без комментариев ни на каком языке; `//` в адресах счётчиков не комментарий
    script = (dist / "assets" / "site.js").read_text(encoding="utf-8")
    assert not re.search(r"(?<!:)//", script)
    css = (dist / "assets" / "site.css").read_text(encoding="utf-8")
    css_comments = re.findall(r"/\*.*?\*/", css, re.S)
    assert css_comments
    for comment in css_comments:
        assert bool(CYRILLIC.search(comment)) is (lang == "ru"), comment


def test_setup_header_names_an_existing_docs_topic():
    for lang, text in HEADER.items():
        names = re.findall(r"heron docs ([a-z][a-z-]*)", text)
        assert names, lang
        for name in names:
            assert library.topic(name) is not None, (lang, name)
        assert bool(CYRILLIC.search(text)) is (lang == "ru")


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_root_note_image_follows_the_channel(tmp_path, monkeypatch, lang):
    """Записка root.md: в beta образ канала, в prod - байт в байт как в шаблоне."""
    source = (scaffold.NOTES / lang / "root.md").read_text(encoding="utf-8")
    fields = {"name": "demo", "slug": "demo"}
    for channel in ("prod", "beta"):
        monkeypatch.setenv("HERON_CHANNEL", channel)
        root = tmp_path / f"{lang}-{channel}"
        root.mkdir()
        create(root, name="demo", languages=["en"], notes=lang)
        note = (root / scaffold.NOTE).read_text(encoding="utf-8")
        if channel == "prod":
            assert note == source.format(**fields)
            assert "heron:prod" in note
        else:
            assert "heron:beta" in note
            assert "heron:prod" not in note
