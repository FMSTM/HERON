"""Инструкция для агентов не расходится с движком.

Шаблоны из docs/<язык>/templates проходят валидацию моделей и JSON Schema из
heron.contracts.schemas, ссылки между документами ведут на существующие файлы,
README комплекта и корневой AGENTS.md называют все роли и образцы, тексты
агент-нейтральны, а сайт, собранный по шаблонам, собирается в прод без ошибок.

Спецификация: docs/ru/spec/23-distribution.md §4, §12; 20 §1; 21 §10.
docs/en/ может ещё отсутствовать: проверки идут по языкам, чья папка есть;
файл с `en_status: missing` в docs/translation.yaml — ещё не переведён (23 §10).
"""

from __future__ import annotations

import io
import json
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
from heron.scaffold import adopt, create

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


def _missing_translations() -> set[str]:
    """Пути внутри docs/<язык>/ с `en_status: missing` в docs/translation.yaml (23 §10)."""
    data = yaml.safe_load((ROOT / "docs" / "translation.yaml").read_text(encoding="utf-8"))
    return {e["path"] for e in data["files"] if e.get("en_status") == "missing"}


MISSING = _missing_translations()


def _untranslated(target: Path) -> bool:
    """Цель в дереве языка, перевода на который ещё нет.

    Либо нет всей папки языка (docs/en до перевода), либо нет одного файла:
    запись `en_status: missing`, а русский файл на месте. Такой файл комплект
    получает фолбэком по файлу (21 §10), поэтому в agents/ сайта ссылка жива;
    в дереве docs/en/ она оживает с переводом. Опечатка в пути сюда не попадает:
    русского файла с таким путём нет.
    """
    try:
        rel = target.resolve().relative_to(ROOT / "docs")
    except ValueError:
        return False
    if not rel.parts or rel.parts[0] not in docs.LANGS:
        return False
    if rel.parts[0] not in LANGS:
        return True
    inner = Path(*rel.parts[1:]).as_posix()
    return rel.parts[0] != "ru" and inner in MISSING and (ROOT / "docs" / "ru" / inner).is_file()


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


# Явный якорь заголовка (23 §10): `<a id="…"></a>` в конце строки. `{#…}` — синтаксис
# секций страниц сайта; GitHub его не понимает, поэтому в документации — `<a id>`.
_EXPLICIT = re.compile(r'^#{1,6} .*<a id="([^"]+)"></a>\s*$', re.M)


def _explicit_anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    return set(_EXPLICIT.findall(text))


def test_links_between_files_lead_to_explicit_anchors():
    """Ссылка `файл.md#якорь` ведёт на явный якорь заголовка: перевод заголовка её не ломает."""
    bad, checked = [], 0
    for doc in _docs_to_check():
        text = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)
        for path, anchor in re.findall(r"\]\(([^)\s#:]+)#([^)\s]+)\)", text):
            if path.startswith("/"):
                continue  # адрес страницы сайта в примере, не файл
            target = (doc.parent / path).resolve()
            if not target.is_file() and _untranslated(target):
                # комплект получит русский файл фолбэком — якорь должен быть в нём
                inner = target.relative_to(ROOT / "docs").parts[1:]
                target = ROOT / "docs" / "ru" / Path(*inner)
            checked += 1
            if anchor not in _explicit_anchors(target):
                bad.append(f"{doc.relative_to(ROOT)}: {path}#{anchor}")
    assert not bad, "\n".join(bad)
    assert checked > 30


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
def test_site_template_names_kit_language_and_level(lang):
    """Образец «со всеми ключами ядра» несёт build.notes и build.agents (20 §5)."""
    text = (_templates(lang) / "site.yaml").read_text(encoding="utf-8")
    data = yaml.load(text, Loader=_Yaml12)
    assert data["build"]["notes"] == lang
    assert data["build"]["agents"] is True
    config = SiteConfig.model_validate(yaml.safe_load(text))
    assert (config.build.notes, config.build.agents) == (lang, True)
    _schema_ok(schemas.site_schema(), text)


def _site_from_template(tmp_path: Path) -> Path:
    """Сайт ru с комплектом, site.yaml которого заменён образцом целиком (как советует README)."""
    root = tmp_path / "site"
    create(root, name="demo", languages=["en"], notes="ru")
    shutil.copy(TEMPLATES / "site.yaml", root / "site.yaml")
    return root


def _kit_lang(root: Path) -> str:
    return yaml.safe_load((root / "agents/heron-kit.yaml").read_text(encoding="utf-8"))["lang"]


def test_site_template_keeps_the_kit_language_on_init_agents(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site_from_template(tmp_path)
    readme = (root / "agents/README.md").read_bytes()
    plan = adopt(root, agents_only=True, agents_flag="true")
    assert plan.kit is not None and plan.kit.lang == "ru" and plan.kit.lang_from == ""
    assert _kit_lang(root) == "ru"
    assert (root / "agents/README.md").read_bytes() == readme
    assert (root / "AGENTS.md").read_text(encoding="utf-8").startswith("# Daybreak — для агентов")
    assert not plan.kit.edited and not plan.kit.forced


def test_init_agents_names_the_kit_language_change(tmp_path, monkeypatch):
    """Без build.notes язык комплекта — en: init --agents перекладывает его и говорит с какого."""
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site_from_template(tmp_path)
    text = (root / "site.yaml").read_text(encoding="utf-8")
    text = re.sub(r"^  notes: ru.*\n(?:\s+#.*\n)?", "", text, flags=re.M)
    assert "notes:" not in text.split("\nbuild:", 1)[1].split("\nplugins:", 1)[0]
    (root / "site.yaml").write_text(text, encoding="utf-8")
    plan = adopt(root, agents_only=True, agents_flag="true")
    assert plan.kit is not None and plan.kit.lang == "en" and plan.kit.lang_from == "ru"
    assert _kit_lang(root) == "en"
    assert "AGENTS.md" in plan.kit.updated
    # повторно — язык уже тот же, смены нет
    again = adopt(root, agents_only=True, agents_flag="true")
    assert again.kit is not None and again.kit.lang_from == ""


def test_site_from_template_passes_check(tmp_path, monkeypatch):
    """Образец после `init` проходит `heron check --json` без ошибок и сохраняет язык комплекта."""
    from click.testing import CliRunner

    from heron.cli import main

    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site_from_template(tmp_path)
    assert CliRunner().invoke(main, ["init", str(root), "-y"]).exit_code == 0
    head = "---\ntitle: {t} page title\nh1: {t}\ndescription: Description\n---\n\nText.\n"
    for lang in ("en", "ru"):
        for key in ("about", "services", "contacts"):  # nav.main образца
            (root / "content" / lang / f"{key}.md").write_text(
                head.format(t=f"{key} {lang}"), encoding="utf-8"
            )
    for name in ("default.png", "default-ru.png"):  # seo.og_default_image* образца
        _png(root / "media" / "og" / name)
    result = CliRunner().invoke(main, ["check", str(root), "--json"])
    data = json.loads(result.output)
    assert [e["message"] for e in data["errors"]] == []
    assert result.exit_code == 0 and data["ok"] is True
    assert data["kit"]["lang"] == "ru" and data["kit"]["current"] is True


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
    roles = {f"{r}.md" for r in (*ROLES, "capabilities")}
    # ещё не переведённая роль (en_status: missing) приходит в комплект фолбэком
    awaiting = {name for name in roles if _untranslated(base / "roles" / name)}
    for role in (*ROLES, "capabilities"):
        assert f"roles/{role}.md" in links, role
        assert (base / "roles" / f"{role}.md").is_file() or f"{role}.md" in awaiting, role
    assert {p.name for p in (base / "roles").glob("*.md")} == roles - awaiting
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

# Имена инструментов и их разработчиков. Разработчиков нет нигде (23 §12).
VENDORS = re.compile(r"claude|anthropic|openai|gemini|copilot|cursor", re.I)
COMPANIES = re.compile(r"anthropic|openai", re.I)
# Не упоминание инструмента: имена файлов-указателей и папки инструментов
# (`.claude/`, `.cursor/` и подобные, 20 §1).
_NOT_A_MENTION = re.compile(r"CLAUDE\.md|GEMINI\.md|(?<![\w.])\.[A-Za-z][\w-]*/")
# Ровно два места, где имена инструментов к месту (23 §12): файл комплекта
# (путь от docs/<язык>/ или от agents/ сайта) и начало строки в нём.
NEUTRAL_WHITELIST: dict[str, tuple[str, ...]] = {
    # перечень «Кто какой файл читает» README комплекта
    "README.md": ("- **Кто какой файл читает.**", "- **Who reads which file.**"),
    # описание корневых указателей в 20 §1: строки дерева и абзац
    "spec/20-data-contract.md": (
        "├── CLAUDE.md",
        "├── GEMINI.md",
        "**Корневые указатели.**",
        "**Root pointers.**",
    ),
}


def vendor_left(kit_path: str | None, line: str) -> bool:
    """Упоминает ли строка инструмент там, где 23 §12 этого не разрешает.

    `kit_path` — путь файла внутри комплекта (`spec/20-data-contract.md`),
    для файла вне комплекта — None: белого списка у него нет.
    """
    if COMPANIES.search(line):
        return True
    if line.strip() == "@AGENTS.md":
        return False
    if kit_path is not None and line.lstrip().startswith(NEUTRAL_WHITELIST.get(kit_path, ())):
        return False
    return bool(VENDORS.search(_NOT_A_MENTION.sub("", line)))


def _kit_path(path: Path) -> str | None:
    """Путь от docs/<язык>/ — так же он лежит в agents/ сайта."""
    for lang in LANGS:
        base = ROOT / "docs" / lang
        if path.is_relative_to(base):
            return path.relative_to(base).as_posix()
    return None


def _neutral_sources() -> list[Path]:
    found = _docs_to_check()
    found += sorted((ROOT / "skills").glob("*/SKILL.md"))
    found += sorted((ROOT / "heron" / "scaffold" / "agents-root").rglob("*.md"))
    return found


def test_texts_are_agent_neutral():
    """Имена инструментов — только в двух местах из 23 §12, разработчиков — нигде.

    Белый список (NEUTRAL_WHITELIST): строка «- **Кто какой файл читает.**»
    README комплекта и описание корневых указателей в 20 §1 — строки дерева
    `├── CLAUDE.md`, `├── GEMINI.md` и абзац «**Корневые указатели.**». Имена
    файлов `CLAUDE.md`/`GEMINI.md`, строка `@AGENTS.md` и папки инструментов
    (`.claude/`) — не упоминание.
    """
    bad = []
    for path in _neutral_sources():
        kit_path = _kit_path(path)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if VENDORS.search(line) and vendor_left(kit_path, line):
                bad.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}")
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize(
    ("kit_path", "line"),
    [
        # имя инструмента в другом файле — даже рядом с именем файла-указателя
        ("guide/01-concepts.md", "`CLAUDE.md` — Claude Code сам решает"),
        ("guide/01-concepts.md", "- **Кто какой файл читает.** `CLAUDE.md` — Claude Code"),
        # в README — только перечень, в 20 — только дерево и абзац
        ("README.md", "`GEMINI.md` читает Gemini CLI"),
        ("spec/20-data-contract.md", "`CLAUDE.md` — для Claude Code"),
        ("spec/20-data-contract.md", "The `CLAUDE.md` pointer is for Claude Code"),
        # английское начало разрешено только в 20, не в README и не в других файлах
        ("README.md", "**Root pointers.** Claude Code"),
        ("guide/01-concepts.md", "**Root pointers.** Claude Code"),
        ("spec/20-data-contract.md", "│   ├── CLAUDE.md   для Claude Code"),
        # вне комплекта белого списка нет
        (None, "- **Кто какой файл читает.** `CLAUDE.md` — Claude Code"),
        # разработчиков нет нигде, в том числе в разрешённых строках
        ("README.md", "- **Кто какой файл читает.** `CLAUDE.md` — Claude Code (Anthropic)"),
        ("spec/20-data-contract.md", "**Корневые указатели.** Codex от OpenAI"),
        ("spec/20-data-contract.md", "**Root pointers.** Codex from OpenAI"),
        ("guide/04-theme.md", "Copilot и Cursor"),
    ],
)
def test_neutrality_whitelist_is_exactly_23_12(kit_path, line):
    assert vendor_left(kit_path, line)


@pytest.mark.parametrize(
    ("kit_path", "line"),
    [
        ("README.md", "- **Кто какой файл читает.** `CLAUDE.md` — Claude Code; Cursor"),
        ("README.md", "- **Who reads which file.** `GEMINI.md` — Gemini CLI"),
        ("spec/20-data-contract.md", "├── CLAUDE.md      одна строка — для Claude Code"),
        ("spec/20-data-contract.md", "├── GEMINI.md      одна строка — для Gemini CLI"),
        ("spec/20-data-contract.md", "**Корневые указатели.** Cursor, Copilot; Claude Code"),
        ("spec/20-data-contract.md", "**Root pointers.** Cursor, Copilot; Claude Code"),
        # не упоминание — где угодно
        ("guide/01-concepts.md", "`CLAUDE.md` и `GEMINI.md` — по строке"),
        ("guide/01-concepts.md", "@AGENTS.md"),
        (None, "папки навыков (`.claude/`, `.cursor/`, `.gemini/`) движок не кладёт"),
    ],
)
def test_neutrality_whitelist_allows_23_12_places(kit_path, line):
    assert not vendor_left(kit_path, line)
