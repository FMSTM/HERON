"""`heron docs`: документация этой версии движка по языкам — из образа, без клона и сети.

Спецификация: docs/ru/spec/21-engine.md, раздел 10 («heron docs»); 23 §2, §10, §12; 20 §1.
docs/en/ может ещё отсутствовать: проверки, зависящие от перевода, параметризованы по его наличию.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron import docs
from heron.cli import main
from heron.contracts.schemas import FILES as SCHEMA_FILES

ROOT = Path(__file__).resolve().parents[1]
HAS_EN = (docs.root() / "docs" / "en" / "README.md").is_file()


def run(*args):
    return CliRunner().invoke(main, list(args))


def repo_docs() -> set[str]:
    """Текст документации в репозитории: всё, кроме картинок бренда и скрытых файлов (.DS_Store)."""
    found = {"AGENTS.md", "README.md"}
    for path in (ROOT / "docs").rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        hidden = any(part.startswith(".") for part in path.relative_to(ROOT).parts)
        if path.is_file() and not hidden and not rel.startswith("docs/brand/"):
            found.add(rel)
    return found


def md_links(text: str) -> list[str]:
    """Относительные ссылки на .md (без якоря); примеры адресов (/, media/, пробел) — мимо."""
    out = []
    for link in re.findall(r"\]\(([^)]+)\)", text):
        if link.startswith(("http:", "https:", "#", "/", "media/", "mailto:")) or " " in link:
            continue
        path = link.split("#", 1)[0]
        if path.endswith(".md"):
            out.append(path)
    return out


# --- достижимость и упаковка ---------------------------------------------------


@pytest.mark.parametrize("lang", docs.LANGS)
def test_every_document_is_reachable(lang):
    """Новый файл не забыт: каждый файл docs/<язык>/** — тема или образец."""
    topic_paths = {t.path.format(lang=lang) for t in docs.TOPICS}
    for rel in docs.files(lang):
        inside = rel.removeprefix(f"docs/{lang}/")
        assert rel in topic_paths or inside.startswith("templates/"), rel


def test_files_lists_the_whole_tree():
    """Всё дерево docs/{ru,en}/, кроме файлов вне комплекта (глоссарий переводчика)."""
    expected = {rel for rel in repo_docs() if rel.startswith(("docs/ru/", "docs/en/"))}
    outside = {f"docs/{lang}/{rel}" for lang in docs.LANGS for rel in docs.NOT_IN_KIT}
    assert set(docs.files("ru")) | set(docs.files("en")) == expected - outside
    assert (ROOT / "docs" / "en" / "GLOSSARY.md").is_file() or not HAS_EN


def test_glossary_stays_out_of_the_kit():
    """GLOSSARY.md — инструмент перевода (23 §10): не тема, не файл agents/ (20 §1)."""
    for lang in docs.LANGS:
        assert not set(docs.tree(lang)) & docs.NOT_IN_KIT, lang


@pytest.mark.parametrize("lang", docs.LANGS)
def test_every_topic_resolves_on_every_language(lang):
    for item in docs.TOPICS:
        found = docs.resolve(item.name, lang)
        if found.path not in (docs.SKILLS, docs.SCHEMAS):
            assert (docs.root() / found.path).is_file(), item.name
        assert docs.read_topic(item.name, lang).strip(), item.name


def test_wheel_carries_every_document():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packed = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for rel in repo_docs():
        assert any(rel == src or rel.startswith(src.rstrip("/") + "/") for src in packed), rel
        assert not rel.startswith("docs/brand/")


def test_image_copies_every_document():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    copied = re.findall(r"^COPY (?!--)(.+?) \./", dockerfile, re.M)
    sources = " ".join(copied).split()
    for rel in repo_docs():
        assert any(rel == src or rel.startswith(src.rstrip("/") + "/") for src in sources), rel


# --- язык, фолбэк, пометка -----------------------------------------------------


def test_kit_on_english_marks_fallback_or_reads_translation():
    found = docs.resolve("kit", "en")
    if HAS_EN:
        assert found.path == "docs/en/README.md"
        assert found.lang_used == "en"
    else:
        assert found.path == "docs/ru/README.md"
        assert found.lang_used == "ru"
        assert found.note == "[ru: перевода на en пока нет]"
        text = docs.read_topic("kit", "en")
        first, blank, *_ = text.splitlines()
        assert first == found.note
        assert blank == ""


def test_kit_on_russian_has_no_note():
    found = docs.resolve("kit", "ru")
    assert found == docs.Resolved("docs/ru/README.md", "ru", None)
    assert docs.read_topic("kit", "ru").startswith("# HERON для агентов")


def fake_root(tmp_path: Path, monkeypatch, *, en: bool, status: str = "current") -> Path:
    (tmp_path / "docs" / "ru" / "guide").mkdir(parents=True)
    (tmp_path / "docs" / "ru" / "README.md").write_text("# ru kit\n", encoding="utf-8")
    (tmp_path / "docs" / "ru" / "guide" / "04-theme.md").write_text(
        "# ru theme\nпоиск-строка\n", encoding="utf-8"
    )
    if en:
        (tmp_path / "docs" / "en").mkdir(parents=True)
        (tmp_path / "docs" / "en" / "README.md").write_text("# en kit\n", encoding="utf-8")
    (tmp_path / "docs" / "translation.yaml").write_text(
        "files:\n"
        "  - path: README.md\n"
        '    ru_sha256: "0"\n'
        f"    en_status: {status}\n"
        "  - path: guide/04-theme.md\n"
        '    ru_sha256: "0"\n'
        "    en_status: missing\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(docs, "root", lambda: tmp_path)
    return tmp_path


def test_fallback_per_file(tmp_path, monkeypatch):
    fake_root(tmp_path, monkeypatch, en=True)
    assert docs.resolve("kit", "en") == docs.Resolved("docs/en/README.md", "en", None)
    theme = docs.resolve("theme", "en")
    assert theme.path == "docs/ru/guide/04-theme.md"
    assert theme.note == "[ru: перевода на en пока нет]"
    assert docs.tree("en") == {"README.md": "en", "guide/04-theme.md": "ru"}


def test_stale_translation_is_marked(tmp_path, monkeypatch):
    fake_root(tmp_path, monkeypatch, en=True, status="stale")
    found = docs.resolve("kit", "en")
    assert found.lang_used == "en"
    assert found.note == "[en: перевод отстаёт от ru]"
    assert docs.read_topic("kit", "en") == "[en: перевод отстаёт от ru]\n\n# en kit\n"
    assert docs.resolve("kit", "ru").note is None


def test_broken_translation_file_is_ignored(tmp_path, monkeypatch):
    fake_root(tmp_path, monkeypatch, en=True)
    (tmp_path / "docs" / "translation.yaml").write_text("files: [oops", encoding="utf-8")
    assert docs.translation() == {}
    assert docs.resolve("kit", "en").note is None


def test_unknown_topic_and_language():
    with pytest.raises(KeyError):
        docs.resolve("nonsense", "ru")
    with pytest.raises(ValueError):
        docs.resolve("kit", "de")


# --- оглавление ----------------------------------------------------------------


@pytest.mark.parametrize("lang", docs.LANGS)
def test_contents_lists_topics_on_language(lang):
    text = docs.contents(lang)
    for item in docs.TOPICS:
        assert item.name in text
        assert item.about(lang) in text
    for name in ("page.md", "structure.md", "site.yaml"):
        assert name in text


def test_contents_differ_by_language():
    ru, en = docs.contents("ru"), docs.contents("en")
    assert "Роли агентов" in ru and "Agent roles" not in ru
    assert "Agent roles" in en and "Роли агентов" not in en
    if not HAS_EN:
        assert en.startswith("[ru: перевода на en пока нет]")


# --- виртуальные темы ----------------------------------------------------------


def test_skills_topic_lists_every_skill():
    names = sorted(p.parent.name for p in (docs.root() / "skills").glob("*/SKILL.md"))
    assert len(names) == 5
    text = docs.read_topic("skills", "en")
    for name in names:
        assert f"`{name}`" in text
        assert f"skills/{name}/SKILL.md" in text


@pytest.mark.parametrize("lang", docs.LANGS)
def test_schemas_topic_names_every_file(lang):
    text = docs.read_topic("schemas", lang)
    assert len(SCHEMA_FILES) == 5
    for name in SCHEMA_FILES:
        assert name in text
    assert "heron schema --export" in text
    assert re.search(r"https://sitebuilder\.heron\.software/schema/\d+\.\d+/", text)


# --- поиск ---------------------------------------------------------------------


@pytest.mark.parametrize("lang", docs.LANGS)
def test_search_shows_file_line_and_context(lang):
    found = "\n".join(docs.search("page.meta.get", lang))
    # файл того языка, что отдаёт дерево: гайд без перевода — фолбэком (по файлу)
    path = f"docs/{docs.tree(lang)['guide/04-theme.md']}/guide/04-theme.md"
    assert re.search(rf"theme · {re.escape(path)}:\d+", found)
    assert "  > " in found


def test_search_covers_root_pointers():
    found = docs.search("npx skills add", "ru")
    assert any(line.startswith("agents · AGENTS.md:") for line in found)


def test_search_with_nothing_found():
    assert docs.search("такого-текста-нет-нигде", "ru") == []


def test_search_uses_fallback_files(tmp_path, monkeypatch):
    fake_root(tmp_path, monkeypatch, en=True)
    found = docs.search("поиск-строка", "en")
    assert found[0] == "theme · docs/ru/guide/04-theme.md:2"


# --- выгрузка ------------------------------------------------------------------


def test_export_lays_out_the_kit(tmp_path):
    target = tmp_path / "heron-docs"
    written = docs.export(target, "ru")
    for name in ("README.md", "architecture.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        assert (target / name).is_file(), name
    for folder in ("roles", "templates", "guide", "spec"):
        assert any((target / folder).iterdir()), folder
    assert sorted(p.name for p in (target / "schemas").iterdir()) == sorted(SCHEMA_FILES)
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (target / "GEMINI.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    for rel in docs.tree("ru"):
        assert (target / rel).read_bytes() == (docs.root() / "docs" / "ru" / rel).read_bytes()
    assert set(written) == {p.relative_to(target).as_posix() for p in target.rglob("*")} - {
        "roles",
        "templates",
        "guide",
        "spec",
        "schemas",
    }
    assert docs.start_hint(target, "ru") == f"Начать с {target / 'README.md'}"


@pytest.mark.parametrize("lang", docs.LANGS)
def test_export_links_resolve(tmp_path, lang):
    target = tmp_path / "out"
    docs.export(target, lang)
    checked = 0
    for path in target.rglob("*.md"):
        for link in md_links(path.read_text(encoding="utf-8")):
            assert (path.parent / link).exists(), f"{path.relative_to(target)} → {link}"
            checked += 1
    assert checked


def test_export_all_languages(tmp_path):
    target = tmp_path / "site"
    docs.export(target, all_langs=True)
    for lang in docs.LANGS:
        assert (target / lang / "README.md").is_file()
        assert (target / lang / "roles" / "architect.md").is_file()
        assert (target / lang / "templates" / "page.md").is_file()
    assert not (target / "AGENTS.md").exists()
    assert not (target / "schemas").exists()


def test_export_is_deterministic(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    docs.export(first, "en")
    docs.export(second, "en")
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()


# --- команда (текущий CLI без --lang: язык по умолчанию) -----------------------


def test_cli_contents_lists_topics():
    result = run("docs")
    assert result.exit_code == 0
    for item in docs.TOPICS:
        assert item.name in result.output


def test_cli_topic_prints_markdown():
    result = run("docs", "agents")
    assert result.exit_code == 0
    assert result.output.startswith("# HERON для агентов")


def test_cli_template_prints_the_sample():
    result = run("docs", "template", "page.md")
    assert result.exit_code == 0
    assert "1. ОСНОВНОЕ" in result.output or HAS_EN


def test_cli_unknown_topic_points_at_contents():
    result = run("docs", "nonsense")
    assert result.exit_code == 1
    assert "heron docs" in result.output


def test_cli_search_and_nothing_found():
    assert run("docs", "--search", "page.meta.get").exit_code == 0
    assert run("docs", "--search", "такого-текста-нет-нигде").exit_code == 1


def test_cli_export(tmp_path):
    target = tmp_path / "heron-docs"
    result = run("docs", "--export", str(target))
    assert result.exit_code == 0, result.output
    assert (target / "README.md").is_file()
    assert (target / "AGENTS.md").is_file()
