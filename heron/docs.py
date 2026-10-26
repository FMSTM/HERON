"""Документация движка — внутри самого движка.

Агент сайта часто работает только с образом: клона репозитория рядом нет,
а документация в сети может быть новее или старее его образа. Поэтому
текст документации едет в образе (без картинок) и читается командой
`heron docs --lang ru|en` — ровно той версии, что и движок (21 §10).

Источник — `docs/<язык>/` репозитория движка: README комплекта, роли,
образцы, гайды, спецификации, architecture.md. Нет файла на нужном языке —
отдаётся файл другого языка с пометкой первой строкой; отстающий перевод
(`docs/translation.yaml`, 23 §10) помечается так же.

В установленном пакете файлы лежат в `heron/_docs/` (их кладёт сборка
колеса, см. pyproject.toml): `_docs/docs/<язык>/…`, `_docs/docs/translation.yaml`,
`_docs/skills/`, `_docs/AGENTS.md`, `_docs/README.md`. Из исходников — прямо
из репозитория.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKED = Path(__file__).parent / "_docs"
SOURCE = Path(__file__).resolve().parent.parent

LANGS = ("ru", "en")
# Язык по умолчанию, если вызывающий его не назвал (21 §10: «иначе en»).
DEFAULT_LANG = "en"

# Виртуальные темы: собираются из файлов, своего markdown у них нет.
SKILLS = "@skills"
SCHEMAS = "@schemas"


@dataclass(frozen=True, slots=True)
class Topic:
    name: str
    path: str
    about_ru: str
    about_en: str
    group: str
    per_lang: bool = True

    def about(self, lang: str) -> str:
        return self.about_ru if lang == "ru" else self.about_en


@dataclass(frozen=True, slots=True)
class Resolved:
    """Какой файл отдать: путь от root(), язык, на котором он на самом деле, пометка."""

    path: str
    lang_used: str
    note: str | None


def _t(name: str, path: str, ru: str, en: str, group: str, *, per_lang: bool = True) -> Topic:
    return Topic(name, path, ru, en, group, per_lang)


# Имя темы → файл. Порядок — порядок оглавления.
TOPICS: tuple[Topic, ...] = (
    _t(
        "agents",
        "AGENTS.md",
        "указатель репозитория движка (двуязычный)",
        "pointer of the engine repository (bilingual)",
        "start",
        per_lang=False,
    ),
    _t(
        "kit",
        "docs/{lang}/README.md",
        "с чего начинать агенту: роли, правила, границы, «готово»",
        "where an agent starts: roles, rules, limits, done criteria",
        "start",
    ),
    _t(
        "readme",
        "README.md",
        "что такое HERON, быстрый старт, несколько сайтов",
        "what HERON is, quick start, several sites",
        "start",
        per_lang=False,
    ),
    _t(
        "architect",
        "docs/{lang}/roles/architect.md",
        "роль: структура сайта по отчёту о старом",
        "role: site structure from the report on the old site",
        "roles",
    ),
    _t(
        "content",
        "docs/{lang}/roles/content.md",
        "роль: страницы, SEO-блок, переводы, переезд",
        "role: pages, SEO block, translations, migration",
        "roles",
    ),
    _t(
        "designer",
        "docs/{lang}/roles/designer.md",
        "роль: тема, шаблоны, модули",
        "role: theme, templates, modules",
        "roles",
    ),
    _t(
        "builder",
        "docs/{lang}/roles/builder.md",
        "роль: сборка, проверка, выкладка",
        "role: build, check, deploy",
        "roles",
    ),
    _t(
        "capabilities",
        "docs/{lang}/roles/capabilities.md",
        "что движок уже умеет — по задачам",
        "what the engine already does — by task",
        "roles",
    ),
    _t(
        "concepts",
        "docs/{lang}/guide/01-concepts.md",
        "01 · понятия: страница, ключ, адрес, тема",
        "01 · concepts: page, key, address, theme",
        "guide",
    ),
    _t(
        "first-site",
        "docs/{lang}/guide/02-first-site.md",
        "02 · первый сайт от пустой папки",
        "02 · the first site from an empty folder",
        "guide",
    ),
    _t(
        "pages",
        "docs/{lang}/guide/03-content.md",
        "03 · страницы, секции, ссылки, картинки",
        "03 · pages, sections, links, images",
        "guide",
    ),
    _t(
        "theme",
        "docs/{lang}/guide/04-theme.md",
        "04 · тема: theme.yaml, шаблоны, модули",
        "04 · theme: theme.yaml, templates, modules",
        "guide",
    ),
    _t(
        "seo",
        "docs/{lang}/guide/05-seo.md",
        "05 · SEO и переезд со старого сайта",
        "05 · SEO and moving from the old site",
        "guide",
    ),
    _t(
        "deploy",
        "docs/{lang}/guide/06-deploy.md",
        "06 · сборка, образ, несколько сайтов",
        "06 · build, image, several sites",
        "guide",
    ),
    _t(
        "contract",
        "docs/{lang}/spec/20-data-contract.md",
        "20 · контракт: папка, URL, поля, ключи",
        "20 · contract: folder, URL, fields, keys",
        "spec",
    ),
    _t(
        "engine",
        "docs/{lang}/spec/21-engine.md",
        "21 · движок: конвейер, модель, CLI, ошибки",
        "21 · engine: pipeline, model, CLI, errors",
        "spec",
    ),
    _t(
        "deploy-spec",
        "docs/{lang}/spec/22-deploy.md",
        "22 · развёртывание: nginx, CI, переезд",
        "22 · deployment: nginx, CI, migration",
        "spec",
    ),
    _t(
        "distribution",
        "docs/{lang}/spec/23-distribution.md",
        "23 · поставка: образ, команды, теги",
        "23 · distribution: image, commands, tags",
        "spec",
    ),
    _t(
        "architecture",
        "docs/{lang}/architecture.md",
        "архитектура одной страницей",
        "the architecture on one page",
        "spec",
    ),
    _t(
        "skills",
        SKILLS,
        "навыки skills/*: имя, описание, путь",
        "skills/*: name, description, path",
        "machine",
        per_lang=False,
    ),
    _t(
        "schemas",
        SCHEMAS,
        "JSON Schema контрактов: какие есть и как получить",
        "JSON Schema of the contracts: which exist and how to get them",
        "machine",
        per_lang=False,
    ),
)

TEMPLATES = "docs/{lang}/templates"

# Группы оглавления по порядку; заголовки — ключи messages.py docs_group_<группа>.
GROUPS = ("start", "roles", "guide", "spec", "machine")

# Строки оглавления и виртуальных тем. Пометки фолбэка и подсказка «Начать с» —
# в messages.py (docs_*), общие с командной строкой.
_TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "head": "Документация HERON этой версии движка ({code}). Читать: heron docs <тема>",
        "samples": "Образцы: heron docs template <файл> — {names}",
        "search": "Поиск:   heron docs --search <текст>",
        "export": "Папкой:  heron docs --export <папка> — со ссылками между файлами",
        "lang": "Язык:    heron docs --lang ru|en",
        "skills_head": "# Навыки HERON",
        "skills_about": (
            "Навыки — тонкие английские указатели на те же темы heron docs. "
            "Ставятся из репозитория движка: npx skills add FMSTM/HERON. В сайт не кладутся."
        ),
        "schemas_head": "# Схемы HERON",
        "schemas_about": (
            "Машиночитаемые схемы контрактов этой версии движка (JSON Schema draft 2020-12) "
            "и реестр кодов ошибок:"
        ),
        "schemas_export": "Получить файлами: heron schema --export <папка>",
        "schemas_url": "В сети, версия контракта {contract}: {url}",
        "schemas_kit": "В сайте они лежат в agents/schemas/ (heron new, heron init --agents).",
    },
    "en": {
        "head": "HERON documentation of this engine version ({code}). Read: heron docs <topic>",
        "samples": "Samples: heron docs template <file> — {names}",
        "search": "Search:  heron docs --search <text>",
        "export": "Folder:  heron docs --export <folder> — links between files kept",
        "lang": "Language: heron docs --lang ru|en",
        "skills_head": "# HERON skills",
        "skills_about": (
            "Skills are thin English pointers to the same heron docs topics. "
            "Install them from the engine repository: npx skills add FMSTM/HERON. "
            "They are not placed in a site."
        ),
        "schemas_head": "# HERON schemas",
        "schemas_about": (
            "Machine-readable schemas of the contracts of this engine version "
            "(JSON Schema draft 2020-12) and the error code registry:"
        ),
        "schemas_export": "As files: heron schema --export <folder>",
        "schemas_url": "Online, contract version {contract}: {url}",
        "schemas_kit": "In a site they sit in agents/schemas/ (heron new, heron init --agents).",
    },
}


def _text(lang: str, key: str, **fields: object) -> str:
    """Строка: ключи `docs_*` — из messages.py, прочие — из своей таблицы."""
    if key.startswith("docs_"):
        from heron.messages import say

        return say(lang, key, **fields)
    table = _TEXT.get(lang, _TEXT["en"])
    return table.get(key, _TEXT["en"][key]).format(**fields)


def _group_title(group: str, lang: str) -> str:
    from heron.messages import say

    return say(lang, f"docs_group_{group}")


def _lang(lang: str | None) -> str:
    if lang is None:
        return DEFAULT_LANG
    if lang not in LANGS:
        raise ValueError(f"unknown documentation language: {lang!r}")
    return lang


def _other(lang: str) -> str:
    return next(item for item in LANGS if item != lang)


def root() -> Path:
    """Где лежит документация: в пакете или в репозитории рядом."""
    if (PACKED / "docs" / "ru" / "README.md").is_file():
        return PACKED
    return SOURCE


def topic(name: str) -> Topic | None:
    return next((t for t in TOPICS if t.name == name), None)


# --- состояние перевода --------------------------------------------------------


def translation() -> dict[str, str]:
    """`docs/translation.yaml`: путь внутри docs/<язык>/ → en_status. Читается мягко."""
    path = root() / "docs" / "translation.yaml"
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — нет файла или он битый: просто без пометок
        return {}
    out: dict[str, str] = {}
    entries = data.get("files") if isinstance(data, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            out[entry["path"]] = str(entry.get("en_status") or "")
    return out


# --- дерево docs/<язык>/ -------------------------------------------------------


def _tree_files(lang: str) -> list[str]:
    """Пути внутри docs/<lang>/ (без префикса), только файлы, без скрытых."""
    base = root() / "docs" / lang
    if not base.is_dir():
        return []
    out = []
    for path in base.rglob("*"):
        rel = path.relative_to(base)
        if path.is_file() and not any(part.startswith(".") for part in rel.parts):
            out.append(rel.as_posix())
    return sorted(out)


def files(lang: str | None = None) -> list[str]:
    """Все файлы docs/<lang>/** — пути от root(), например `docs/ru/guide/04-theme.md`."""
    lang = _lang(lang)
    return [f"docs/{lang}/{rel}" for rel in _tree_files(lang)]


def tree(lang: str | None = None) -> dict[str, str]:
    """Дерево комплекта на языке: путь внутри docs/<язык>/ → язык, чей файл берётся.

    Нет файла на `lang` — берётся файл другого языка (фолбэк по файлу).
    """
    lang = _lang(lang)
    out = {rel: _other(lang) for rel in _tree_files(_other(lang))}
    out.update({rel: lang for rel in _tree_files(lang)})
    return dict(sorted(out.items()))


def _note(rel: str, want: str, have: str) -> str | None:
    """Пометка для файла `rel` дерева: фолбэк или отстающий перевод."""
    if have != want:
        return _text(want, "docs_fallback", have=have, want=want)
    if want == "en" and translation().get(rel) == "stale":
        return _text(want, "docs_stale", have="ru", want="en")
    return None


def localize(rel: str, lang: str | None = None) -> Resolved | None:
    """Файл `rel` дерева docs/<язык>/ на языке `lang` или с фолбэком; нет нигде — None."""
    lang = _lang(lang)
    for have in (lang, _other(lang)):
        if (root() / "docs" / have / rel).is_file():
            return Resolved(f"docs/{have}/{rel}", have, _note(rel, lang, have))
    return None


def _tree_rel(path: str) -> str | None:
    """`docs/{lang}/guide/04-theme.md` → `guide/04-theme.md`; не из дерева — None."""
    prefix = "docs/{lang}/"
    return path[len(prefix) :] if path.startswith(prefix) else None


def resolve(name: str, lang: str | None = None) -> Resolved:
    """Тема → файл. Неизвестная тема — KeyError; файла нет ни на одном языке — FileNotFoundError."""
    lang = _lang(lang)
    item = topic(name)
    if item is None:
        raise KeyError(name)
    if item.path in (SKILLS, SCHEMAS):
        return Resolved(item.path, lang, None)
    rel = _tree_rel(item.path)
    if rel is None:
        path = item.path
        if name == "readme" and lang == "ru" and (root() / "README.ru.md").is_file():
            path = "README.ru.md"
        if not (root() / path).is_file():
            raise FileNotFoundError(root() / path)
        return Resolved(path, lang, None)
    found = localize(rel, lang)
    if found is None:
        raise FileNotFoundError(root() / item.path.format(lang=lang))
    return found


def read_topic(name: str, lang: str | None = None) -> str:
    """Текст темы; при фолбэке или отстающем переводе — пометка первой строкой."""
    lang = _lang(lang)
    found = resolve(name, lang)
    if found.path == SKILLS:
        body = skills_text(lang)
    elif found.path == SCHEMAS:
        body = schemas_text(lang)
    else:
        body = (root() / found.path).read_text(encoding="utf-8")
    return body if found.note is None else f"{found.note}\n\n{body}"


def templates(lang: str | None = None) -> list[str]:
    """Имена образцов в docs/<lang>/templates/ (с фолбэком на другой язык)."""
    return sorted(
        rel.removeprefix("templates/") for rel in tree(lang) if rel.startswith("templates/")
    )


def read(rel: str, lang: str | None = None) -> str:
    """Файл документации по пути от root(); `{lang}` в пути — язык с фолбэком.

    Путь темы (`Topic.path`) читается как тема — с пометкой языка.
    """
    lang = _lang(lang)
    item = next((t for t in TOPICS if t.path == rel), None)
    if item is not None:
        return read_topic(item.name, lang)
    inner = _tree_rel(rel)
    if inner is not None:
        found = localize(inner, lang)
        if found is None:
            raise FileNotFoundError(root() / rel.format(lang=lang))
        rel = found.path
    return (root() / rel).read_text(encoding="utf-8")


# --- виртуальные темы ----------------------------------------------------------


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    head, sep, _ = text[3:].partition("\n---")
    if not sep:
        return {}
    try:
        import yaml

        data = yaml.safe_load(head)
    except Exception:  # noqa: BLE001 — битая шапка навыка: без описания
        return {}
    return data if isinstance(data, dict) else {}


def skills() -> list[tuple[str, str, str]]:
    """Навыки: (имя, описание, путь от root()) по алфавиту папок."""
    base = root() / "skills"
    out = []
    for path in sorted(base.glob("*/SKILL.md")) if base.is_dir() else []:
        head = _frontmatter(path.read_text(encoding="utf-8"))
        name = str(head.get("name") or path.parent.name)
        about = " ".join(str(head.get("description") or "").split())
        out.append((name, about, path.relative_to(root()).as_posix()))
    return out


def skills_text(lang: str | None = None) -> str:
    lang = _lang(lang)
    lines = [_text(lang, "skills_head"), "", _text(lang, "skills_about"), ""]
    for name, about, path in skills():
        lines.append(f"- `{name}` — {about}" if about else f"- `{name}`")
        lines.append(f"  {path}")
    return "\n".join(lines) + "\n"


def schemas_text(lang: str | None = None) -> str:
    lang = _lang(lang)
    import heron
    from heron.contracts.schemas import BASE, FILES

    major, minor, *_ = heron.__version__.split(".")
    contract = f"{major}.{minor}"
    lines = [_text(lang, "schemas_head"), "", _text(lang, "schemas_about"), ""]
    lines += [f"- `{name}`" for name in FILES]
    lines += [
        "",
        _text(lang, "schemas_export"),
        _text(lang, "schemas_url", contract=contract, url=f"{BASE}/{contract}/"),
        _text(lang, "schemas_kit"),
    ]
    return "\n".join(lines) + "\n"


# --- оглавление и поиск --------------------------------------------------------


def contents(lang: str | None = None) -> str:
    """Оглавление: темы по группам с одной строкой описания на языке `lang`."""
    lang = _lang(lang)
    lines = []
    if not (root() / "docs" / lang).is_dir():
        lines += [_text(lang, "docs_fallback", have=_other(lang), want=lang), ""]
    lines += [_text(lang, "head", code=lang), ""]
    for group in GROUPS:
        lines.append(f"{_group_title(group, lang)}:")
        for item in (t for t in TOPICS if t.group == group):
            lines.append(f"  {item.name:<14} {item.about(lang)}")
        lines.append("")
    lines.append(_text(lang, "samples", names=", ".join(templates(lang))))
    lines.append(_text(lang, "search"))
    lines.append(_text(lang, "export"))
    lines.append(_text(lang, "lang"))
    return "\n".join(lines) + "\n"


def _search_files(lang: str) -> list[tuple[str, str]]:
    """(имя для вывода, путь от root()) — дерево на языке с фолбэком + AGENTS.md + README.md."""
    names = {rel: t.name for t in TOPICS if (rel := _tree_rel(t.path)) is not None}
    out = []
    for rel, have in tree(lang).items():
        path = f"docs/{have}/{rel}"
        out.append((names.get(rel, path), path))
    for name in ("agents", "readme"):
        item = topic(name)
        assert item is not None
        if (root() / item.path).is_file():
            out.append((name, item.path))
    return out


def search(text: str, lang: str | None = None, context: int = 1) -> list[str]:
    """Строки документации с `text` (без учёта регистра) и соседние строки."""
    lang = _lang(lang)
    pattern = re.compile(re.escape(text), re.IGNORECASE)
    out: list[str] = []
    for name, rel in _search_files(lang):
        lines = (root() / rel).read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            out.append(f"{name} · {rel}:{index + 1}")
            start, stop = max(0, index - context), min(len(lines), index + context + 1)
            for near in range(start, stop):
                mark = ">" if near == index else " "
                out.append(f"  {mark} {lines[near]}")
            out.append("")
    return out


# --- выгрузка папкой -----------------------------------------------------------


def _pointers(lang: str) -> dict[str, str]:
    """AGENTS.md, CLAUDE.md, GEMINI.md выгрузки — те же, что у сайта (scaffold.agents).

    Полей сайта у выгрузки нет: на их месте заглушки `<name>`; комплект лежит
    в корне папки, а не в agents/, — ссылки без префикса.
    """
    import heron
    from heron.scaffold import agents as kit

    fields = {
        "notes": lang,
        "version": heron.__version__,
        "channel": kit.channel(),
        "docs_url": kit.docs_url(lang),
    }
    files = kit.root_files(lang, fields)
    files["AGENTS.md"] = re.sub(r"\]\(agents/", "](", files["AGENTS.md"])
    return files


def _tree_items(lang: str, prefix: str = "") -> list[tuple[str, bytes]]:
    """Дерево docs/<lang>/ так, как его получает сайт в agents/ (ветка и образ канала)."""
    from heron.scaffold.agents import deliver

    return [
        (f"{prefix}{rel}", deliver(rel, (root() / "docs" / have / rel).read_bytes(), lang))
        for rel, have in tree(lang).items()
    ]


def export(target: Path, lang: str | None = None, all_langs: bool = False) -> list[str]:
    """Выложить документацию папкой — ровно то, что новый сайт получает в agents/.

    `docs/<lang>/**` → `target/**` (байт в байт, с фолбэком по файлу; в канале
    не prod — ссылки на ветку и образ канала, как в комплекте сайта), корневые
    указатели AGENTS.md, CLAUDE.md, GEMINI.md → `target/`, схемы → `target/schemas/`.
    `all_langs` — для сайта движка: `target/ru/**` и `target/en/**`, без указателей и схем.
    Запись — общим безопасным писателем: все цели проверяются до первой записи,
    ссылка или папка на месте файла и ссылка наружу — E024 (21 §4).
    Возвращает записанные пути относительно `target`.
    """
    from heron.scaffold.agents import write_files

    lang = _lang(lang)
    target = Path(target)
    if all_langs:
        items: list[tuple[str, bytes]] = []
        for each in LANGS:
            items += _tree_items(each, f"{each}/")
        return write_files(target, items)
    items = _tree_items(lang)
    items += [(name, text.encode("utf-8")) for name, text in _pointers(lang).items()]

    from heron.contracts.schemas import all_schemas

    items += [(f"schemas/{name}", text.encode("utf-8")) for name, text in all_schemas().items()]
    return write_files(target, items)


def start_hint(target: Path, lang: str | None = None) -> str:
    """Подсказка после выгрузки: «Начать с <target>/README.md»."""
    return _text(_lang(lang), "docs_start_with", path=Path(target) / "README.md")


def recipe_text() -> str:
    """Рецепт образа nginx для собранного сайта: из пакета или из клона."""
    packed = Path(__file__).parent / "_recipe" / "Dockerfile.site"
    source = Path(__file__).resolve().parent.parent / "Dockerfile.site"
    return (packed if packed.is_file() else source).read_text(encoding="utf-8")
