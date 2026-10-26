"""Инструкция для агентов не расходится с движком.

Шаблоны из docs/<язык>/templates проходят валидацию моделей и JSON Schema из
heron.contracts.schemas, ссылки между документами ведут на существующие файлы,
README комплекта и корневой AGENTS.md называют все роли и образцы, тексты
агент-нейтральны, а сайт, собранный по шаблонам, собирается в прод без ошибок.

Спецификация: docs/ru/spec/23-distribution.md §4, §12; 20 §1; 21 §10.
docs/en/ может ещё отсутствовать: проверки идут по языкам, чья папка есть.
"""

from __future__ import annotations

import io
import re
import shutil
from pathlib import Path

import jsonschema
import pytest
import yaml
from PIL import Image

from heron import docs
from heron.contracts import schemas
from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.core.parser import blocks, frontmatter, markdown, sections
from heron.scaffold import create

ROOT = Path(__file__).resolve().parents[1]
LANGS = [lang for lang in docs.LANGS if (ROOT / "docs" / lang / "README.md").is_file()]
TEMPLATES = ROOT / "docs" / "ru" / "templates"  # сценарий сборки — на русском образце
ROLES = ("architect", "content", "designer", "builder")
TEMPLATE_FILES = ("structure.md", "site.yaml", "theme.yaml", "page.md", "report.md", "questions.md")


def _templates(lang: str) -> Path:
    return ROOT / "docs" / lang / "templates"


class _Yaml12(yaml.SafeLoader):
    """Как читает YAML редактор со схемой (YAML 1.2): булевы — только true/false.

    Движок прощает YAML 1.1 (`on:` → true, theme.py); схема пишется для 1.2, и
    образец проверяется так, как его увидит редактор.
    """


_Yaml12.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in value if tag != "tag:yaml.org,2002:bool"]
    for key, value in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Yaml12.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)


def _schema_ok(schema: dict, text: str) -> None:
    jsonschema.Draft202012Validator(schema).validate(yaml.load(text, Loader=_Yaml12))


def test_russian_tree_is_present():
    assert "ru" in LANGS


# --- образцы проходят свои модели и схемы -------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_site_template_is_valid(lang):
    text = (_templates(lang) / "site.yaml").read_text(encoding="utf-8")
    config = SiteConfig.model_validate(yaml.safe_load(text))
    assert config.for_lang("ru").site.name != config.site.name
    assert config.gone
    _schema_ok(schemas.site_schema(), text)


@pytest.mark.parametrize("lang", LANGS)
def test_theme_template_is_valid(lang):
    text = (_templates(lang) / "theme.yaml").read_text(encoding="utf-8")
    theme = ThemeConfig.model_validate(yaml.safe_load(text))
    assert {"home", "service", "article", "404"} <= set(theme.types)
    _schema_ok(schemas.theme_schema(), text)


@pytest.mark.parametrize("lang", LANGS)
def test_page_template_parses_into_expected_forms(lang):
    text = (_templates(lang) / "page.md").read_text(encoding="utf-8")
    data, body, line = frontmatter.split(text, "page.md")
    _schema_ok(schemas.frontmatter_schema(), text.split("---\n", 2)[1])
    meta = frontmatter.parse_meta(data, "page.md")
    if lang == "ru":
        assert meta.redirect_from == ["/старый-адрес/"]
    else:
        assert meta.redirect_from and all(a.startswith("/") for a in meta.redirect_from)
    md = markdown.make()
    intro, found = sections.split(md, body, "page.md", offset=line)
    blocks.apply(md, found)
    assert {k: s.kind for k, s in found.items()} == {
        "includes": "list",
        "how": "steps",
        "faq": "faq",
    }


@pytest.mark.parametrize("lang", LANGS)
def test_report_template_has_every_section(lang):
    """Отчёт: восемь пронумерованных разделов по порядку, команды проверки, ссылка на вопросы."""
    text = (_templates(lang) / "report.md").read_text(encoding="utf-8")
    numbers = [int(n) for n in re.findall(r"^## (\d+)\. \S", text, re.M)]
    assert numbers == list(range(1, 9))
    assert re.search(r"^# \S", text, re.M)
    assert "heron check . --strict --json" in text
    assert "heron build . --env prod --strict" in text
    assert "work/questions.md" in text


@pytest.mark.parametrize("lang", LANGS)
def test_questions_template_is_a_filled_table(lang):
    """Вопросы: таблица в семь колонок, у каждой строки примера — все семь ячеек."""
    text = (_templates(lang) / "questions.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("|")]
    assert len(rows) >= 3, "заголовок, разделитель и хотя бы один пример"
    cells = [row.strip("|").split("|") for row in rows]
    assert all(len(c) == 7 for c in cells), [len(c) for c in cells]
    assert set("".join(cells[1]).replace(" ", "")) <= {"-", ":"}


# --- ссылки --------------------------------------------------------------------


def _docs_to_check() -> list[Path]:
    found = [ROOT / "AGENTS.md", ROOT / "README.md"]
    for lang in LANGS:
        found += sorted((ROOT / "docs" / lang).rglob("*.md"))
    return found


def _links(text: str) -> list[str]:
    """Относительные ссылки; примеры адресов (/, media/, пробел) и внешние — мимо."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)  # пример разметки в коде — не ссылка
    out = []
    for link in re.findall(r"\]\(([^)]+)\)", text):
        if link.startswith(("http:", "https:", "#", "/", "media/", "mailto:")) or " " in link:
            continue
        out.append(link.split("#", 1)[0])
    return out


def _untranslated(target: Path) -> bool:
    """Ссылка в дерево языка, перевода на который ещё нет (docs/en до перевода)."""
    try:
        rel = target.resolve().relative_to(ROOT / "docs")
    except ValueError:
        return False
    return rel.parts[0] in docs.LANGS and rel.parts[0] not in LANGS


def test_links_between_agent_docs_resolve():
    checked = 0
    for doc in _docs_to_check():
        for target in _links(doc.read_text(encoding="utf-8")):
            path = doc.parent / target
            if _untranslated(path):
                continue
            checked += 1
            assert path.exists(), f"{doc.relative_to(ROOT)}: битая ссылка {target}"
    assert checked > 50


# --- сборка по образцам ----------------------------------------------------------


def _png(path: Path) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (1200, 630), (20, 40, 60)).save(buf, "PNG")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


def test_site_built_from_templates_passes_prod_strict_checks(tmp_path):
    """Сценарий А на шаблонах: new → site.yaml → init → тема → контент → prod."""
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    shutil.copy(TEMPLATES / "site.yaml", root / "site.yaml")
    create(root, name="demo", languages=["en", "ru"])  # то, что делает init
    shutil.copy(TEMPLATES / "theme.yaml", root / "theme" / "theme.yaml")

    templates = root / "theme" / "templates"
    page_tpl = (templates / "page.html").read_text(encoding="utf-8")
    for kind in ("service", "category", "article"):
        (templates / f"{kind}.html").write_text(page_tpl, encoding="utf-8")
    for name in ("default.png", "default-ru.png"):
        _png(root / "media" / "og" / name)

    head = "---\ntitle: {t}\nh1: {h}\ndescription: Description\n{x}---\n\nText.\n"
    service = (TEMPLATES / "page.md").read_text(encoding="utf-8")
    files = {
        "en/index.md": head.format(t="Site home", h="Home", x=""),
        "ru/index.md": head.format(t="Главная сайта", h="Главная", x=""),
        "en/404.md": head.format(t="Not found", h="No such page", x=""),
        "ru/404.md": head.format(t="Не найдено", h="Страницы нет", x=""),
        "en/services/_index.md": head.format(
            t="Catalog", h="Our catalog", x="children_type: service\n"
        ),
        "en/services/design.md": service,
        "en/services/planning.md": head.format(t="Planning", h="Space planning", x=""),
    }
    for rel, text in files.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    assert (dist / "services" / "design" / "index.html").is_file()
    assert "/старый-адрес/  /services/design/;" in (dist / "redirects.map").read_text(
        encoding="utf-8"
    )
    assert "/wp-*  1;" in (dist / "gone.map").read_text(encoding="utf-8")
    design = result.site.page("services/design", "en")
    assert [p.url for p in design.related["related"]] == ["/services/planning/"]


@pytest.mark.parametrize("lang", LANGS)
def test_page_template_has_the_same_seo_groups_as_scaffold(lang):
    """Образец страницы и блок, который кладёт движок, — одни и те же восемь групп."""
    group = re.compile(r"^# =+ (.+?) =+$", re.M)
    template = (_templates(lang) / "page.md").read_text(encoding="utf-8")
    scaffold = (ROOT / "heron" / "scaffold" / "text" / lang / "seo-block.md").read_text(
        encoding="utf-8"
    )
    assert group.findall(template) == group.findall(scaffold)
    assert len(group.findall(template)) == 8


# --- точки входа называют роли и образцы -----------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_agents_prompt_names_every_role_document(lang):
    """README комплекта ссылается на каждую роль и каждый образец; лишних файлов нет."""
    base = ROOT / "docs" / lang
    text = (base / "README.md").read_text(encoding="utf-8")
    links = set(_links(text))
    for role in (*ROLES, "capabilities"):
        assert f"roles/{role}.md" in links, role
        assert (base / "roles" / f"{role}.md").is_file(), role
    assert {p.name for p in (base / "roles").glob("*.md")} == {
        f"{r}.md" for r in (*ROLES, "capabilities")
    }
    for name in TEMPLATE_FILES:
        assert f"`{name}`" in text, name
        assert (base / "templates" / name).is_file(), name
    assert {p.name for p in (base / "templates").iterdir() if not p.name.startswith(".")} == set(
        TEMPLATE_FILES
    )


def test_repository_pointer_names_every_language_role_and_template():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for lang in docs.LANGS:
        assert f"docs/{lang}/README.md" in text, lang
    for word in ("архитектор", "контент и SEO", "дизайнер", "сборщик"):
        assert word in text, word
    for word in ("architect", "content and SEO", "designer", "builder"):
        assert word in text, word
    assert "docs/<lang>/roles/" in text
    for name in TEMPLATE_FILES:
        assert f"`{name}`" in text, name
    for name in ("CLAUDE.md", "GEMINI.md"):
        assert (ROOT / name).read_text(encoding="utf-8").strip() == "@AGENTS.md", name


# --- агент-нейтральность (23 §12) -------------------------------------------------

# Имя файла-указателя и папки инструмента — не упоминание инструмента.
_FILE_NAMES = re.compile(r"CLAUDE\.md|\.claude/")
_VENDOR = re.compile(r"claude|anthropic", re.I)


def _neutral_sources() -> list[Path]:
    found = _docs_to_check()
    found += sorted((ROOT / "skills").glob("*/SKILL.md"))
    found += sorted((ROOT / "heron" / "scaffold" / "agents-root").rglob("*.md"))
    return found


def test_texts_are_agent_neutral():
    """Claude/Anthropic — только имя файла CLAUDE.md и строка «кто какой файл читает».

    Белый список: «Claude Code» допустим лишь в строке, которая называет файл
    `CLAUDE.md` (перечень «какой файл какой агент читает», 20 §1, README комплекта).
    «Anthropic» не допускается нигде.
    """
    bad = []
    for path in _neutral_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not _VENDOR.search(line):
                continue
            rest = _FILE_NAMES.sub("", line)
            if "CLAUDE.md" in line:
                rest = rest.replace("Claude Code", "")
            if _VENDOR.search(rest):
                bad.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}")
    assert not bad, "\n".join(bad)
