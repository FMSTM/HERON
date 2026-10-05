"""Скелет сайта: что кладут `heron new` и `heron init`.

Команда неинтерактивна и детерминирована: одинаковый вызов даёт одинаковую
папку. Кладёт только контент: markdown, картинки, тему, site.yaml. Ни
Dockerfile, ни compose, ни скриптов сборки, ни .env здесь нет и быть не
может — сборка, окружения и упаковка живут в HERON, а папка сайта остаётся
папкой сайта. Решение «папка или образ» принимается при сборке.

Спецификация: docs/spec/23-distribution.md, раздел 4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from heron import __version__
from heron.core.notes import NOTE

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
NOTES = HERE / "notes"

# Папки, которым полагается пояснительная записка. Человек открывает свежий
# сайт и видит семь каталогов без единого слова о том, что куда класть, —
# а решение «куда положить» принимается через месяц и в другом окне, а не
# в момент чтения спецификации.
NOTED = ("content", "media", "theme", "data", "static", "plugins")

GITIGNORE = """dist/
.heron-cache/
.DS_Store
__pycache__/
"""

# Строки интерфейса темы на языке сайта. Нет языка — английские.
STRINGS = {
    "uk": "powered_by: Працює на\nread_more: Читати далі\n",
    "ru": "powered_by: Работает на\nread_more: Читать дальше\n",
    "en": "powered_by: Powered by\nread_more: Read more\n",
}

# Язык комментариев и пояснений, которые кладёт скелет: site.yaml,
# theme.yaml, SEO-блок страниц, записки heron-readme.md.
NOTE_LANGS = ("ru", "en")
TEXT = HERE / "text"


ENV_NOTES = "HERON_NOTES"

# Сообщения команд new и init — на языке пояснений.
MESSAGES = {
    "ru": {
        "found_site": "site.yaml: языки {languages}, тема {theme}",
        "found_content": "content/: {pages} страниц, языки: {langs}",
        "found_folder": "{folder}/ на месте",
        "none": "нет",
        "found": "нашёл",
        "created": "создал",
        "skipped": "оставил как есть: {count} файлов",
        "not_empty": "папка {name} не пуста — используйте `heron init` внутри неё",
        "site_created": "сайт {name} создан",
        "next": (
            "\nдальше:\n"
            "  1. заполните {name}/site.yaml — домен, название, языки, меню\n"
            "  2. heron init {name} — папки и стартовые страницы догонят конфиг\n"
            "  3. пишите страницы: копия index.md или heron page, затем heron build {name}"
        ),
        "folder_done": "папка {path} дополнена",
        "bad_notes": "язык пояснений {value!r}: есть ru и en",
    },
    "en": {
        "found_site": "site.yaml: languages {languages}, theme {theme}",
        "found_content": "content/: {pages} pages, languages: {langs}",
        "found_folder": "{folder}/ is in place",
        "none": "none",
        "found": "found",
        "created": "created",
        "skipped": "left as is: {count} files",
        "not_empty": "folder {name} is not empty — run `heron init` inside it",
        "site_created": "site {name} created",
        "next": (
            "\nnext:\n"
            "  1. fill in {name}/site.yaml — domain, name, languages, menu\n"
            "  2. heron init {name} — folders and starter pages follow the config\n"
            "  3. write pages: copy index.md or run heron page, then heron build {name}"
        ),
        "folder_done": "folder {path} completed",
        "bad_notes": "notes language {value!r}: ru and en are available",
    },
}


def message(notes: str, key: str, **fields: object) -> str:
    return MESSAGES.get(notes, MESSAGES["en"])[key].format(**fields)


def resolve_notes(flag: str | None = None, site_yaml: Path | None = None) -> str:
    """Язык пояснений: флаг --notes, затем HERON_NOTES, затем build.notes, затем en.

    Флаг и переменная — переключатель на один запуск. `site.yaml` — память
    сайта: `new` записывает туда выбор, и `init` с `page` без флага держат
    язык, на котором сайт заведён.
    """
    import os

    value = flag or os.environ.get(ENV_NOTES, "").strip() or None
    if value is None and site_yaml is not None:
        declared = _declared(site_yaml)
        value = (declared or {}).get("notes")
    value = (value or "en").lower()
    if value not in NOTE_LANGS:
        raise ValueError(message("en", "bad_notes", value=value))
    return value


def _text(lang: str, name: str) -> str:
    return (TEXT / lang / name).read_text(encoding="utf-8")


@dataclass(slots=True)
class Plan:
    """Что команда собирается создать."""

    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    found: list[str] = field(default_factory=list)
    notes: str = "en"


def slugify(name: str) -> str:
    """Имя папки в безопасный слаг. Нелатинское имя слага не даёт — и не надо."""
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


# Тексты стартовых страниц. Нет языка — английский: страница на чужом
# языке полезнее её отсутствия, и сайт собирается сразу.
STARTER = {
    "uk": {
        "home": (
            "{name} — головна",
            "{name}",
            "Головна сторінка сайту {name}",
            "Перший абзац: хто ви і чим корисні.\n\nДругий абзац: що людина отримає.",
        ),
        "404": (
            "Сторінку не знайдено",
            "Такої сторінки немає",
            "Сторінку не знайдено",
            "Можливо, адресу змінено. Почніть з [головної](/).",
        ),
    },
    "ru": {
        "home": (
            "{name} — главная",
            "{name}",
            "Главная страница сайта {name}",
            "Первый абзац: кто вы и чем полезны.\n\nВторой абзац: что человек получит.",
        ),
        "404": (
            "Страница не найдена",
            "Такой страницы нет",
            "Страница не найдена",
            "Возможно, адрес изменился. Начните с [главной](/).",
        ),
    },
    "en": {
        "home": (
            "{name} — home",
            "{name}",
            "Home page of {name}",
            "First paragraph: who you are and how you help.\n\n"
            "Second paragraph: what the visitor gets.",
        ),
        "404": (
            "Page not found",
            "There is no such page",
            "Page not found",
            "The address may have changed. Start from the [home page](/).",
        ),
    },
}


def seo_block(
    title: str,
    h1: str,
    description: str,
    order: int = 999,
    page_type: str | None = None,
    notes: str = "en",
) -> str:
    """Фронтматтер страницы: восемь групп SEO-блока с комментариями.

    Один образец на всё: его кладут `new` и `init` в стартовые страницы и
    `heron page` в новую. Новая страница — это копия файла с правкой
    значений, комментарии остаются.
    """
    import json

    hint = {
        "ru": ("тип страницы: какой шаблон темы её рисует", "тип, если не задан папкой"),
        "en": ("page type: which theme template renders it", "type, if not set by the folder"),
    }[notes]
    type_line = (
        f"type: {json.dumps(page_type, ensure_ascii=False)}\n# ↑ {hint[0]}\n"
        if page_type
        else f"# type:                      # {hint[1]} (children_type)\n"
    )
    return _text(notes, "seo-block.md").format(
        title=json.dumps(title, ensure_ascii=False),
        h1=json.dumps(h1, ensure_ascii=False),
        description=json.dumps(description, ensure_ascii=False),
        order=order,
        type_line=type_line,
    )


def _starter(root: Path, lang: str, name: str, plan: Plan, force: bool, notes: str) -> None:
    """Главная и страница 404 языка: сайт собирается сразу после создания."""
    texts = STARTER.get(lang, STARTER["en"])
    for page, rel in (("home", "index.md"), ("404", "404.md")):
        title, h1, description, body = (part.format(name=name) for part in texts[page])
        order = 0 if page == "home" else 999
        text = seo_block(title, h1, description, order=order, notes=notes)
        _put(root, f"content/{lang}/{rel}", text + "\n" + body + "\n", plan, force)


def _version_spec() -> str:
    major, minor, *_ = __version__.split(".")
    return f">={major}.{minor},<{major}.{int(minor) + 1}"


def _keep(root: Path, rel: str, plan: Plan) -> None:
    """Пустая папка, которую переживёт git."""
    path = root / rel
    if path.is_dir() and any(path.iterdir()):
        return
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".gitkeep"
    if not marker.exists():
        marker.write_text("", encoding="utf-8")
        plan.created.append(f"{rel}/")


def _put(root: Path, rel: str, text: str, plan: Plan, force: bool) -> None:
    path = root / rel
    if path.exists() and not force:
        plan.skipped.append(rel)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    plan.created.append(rel)


def _copy(root: Path, source: Path, rel: str, plan: Plan, force: bool, **fields: str) -> None:
    text = source.read_text(encoding="utf-8")
    if fields:
        text = text.format(**fields)
    _put(root, rel, text, plan, force)


def _note(
    root: Path,
    note: str,
    folder: str,
    lang: str,
    plan: Plan,
    force: bool,
    **fields: str,
) -> None:
    """Положить пояснительную записку в папку.

    Язык — тот, что выбрали при создании сайта. Нет перевода — кладём
    английский: записка на чужом языке полезнее её отсутствия, а ронять
    создание сайта из-за ненаписанного перевода незачем.
    """
    source = NOTES / lang / f"{note}.md"
    if not source.is_file():
        source = NOTES / "en" / f"{note}.md"
    if not source.is_file():
        return
    rel = f"{folder}/{NOTE}" if folder else NOTE
    _copy(root, source, rel, plan, force, **fields)


def create(
    root: Path,
    name: str,
    languages: list[str] | None = None,
    theme: str | None = None,
    force: bool = False,
    notes: str = "en",
) -> Plan:
    """Разложить скелет сайта в папку.

    `notes` — язык комментариев и пояснений во всех файлах скелета:
    `ru` или `en`. Языки самого сайта — отдельно, в `languages`.
    """
    if notes not in NOTE_LANGS:
        raise ValueError(message("en", "bad_notes", value=notes))
    plan = Plan(notes=notes)
    languages = languages or ["en"]
    theme_name = theme or "main"
    default_lang = languages[0]
    slug = slugify(name)
    # домен-заглушка: под нелатинским именем папки его не собрать,
    # и выдумывать транслит за человека не надо — он всё равно впишет свой
    domain = f"{slug}.example" if slug else "example.com"

    fields = {
        "name": name,
        "theme": theme_name,
        "domain": domain,
        "default_lang": default_lang,
        "languages": ", ".join(languages),
        "spec": _version_spec(),
    }

    _put(root, "site.yaml", _text(notes, "site.yaml").format(**fields), plan, force)
    _put(root, ".gitignore", GITIGNORE, plan, force)
    _note(root, "root", "", notes, plan, force, name=name, slug=slugify(name) or name)

    for lang in languages:
        _starter(root, lang, name, plan, force, notes)

    for folder in ("data", "media", "static", "plugins"):
        path = root / folder
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            (path / ".gitkeep").write_text("", encoding="utf-8")
            plan.created.append(f"{folder}/")

    for folder in NOTED:
        _note(root, folder, folder, notes, plan, force)

    _put(root, "theme/theme.yaml", _text(notes, "theme.yaml").format(**fields), plan, force)
    for source in sorted(TEMPLATES.rglob("*")):
        if source.is_file():
            _copy(root, source, f"theme/{source.relative_to(TEMPLATES).as_posix()}", plan, force)
    for lang in languages:
        _put(root, f"theme/i18n/{lang}.yaml", STRINGS.get(lang, STRINGS["en"]), plan, force)

    return plan


def adopt(root: Path, force: bool = False, notes: str | None = None) -> Plan:
    """Дополнить папку тем, чего в ней нет, по написанному в `site.yaml`.

    Языки и тему берём из конфига, а не из того, какие папки уже лежат:
    иначе источников правды два, и рано или поздно они разойдутся. Дописал
    язык в `site.yaml`, выполнил `init` — папка под него появилась.

    Ничего не перезаписывает без `--force`: чужой файл важнее нашего образца.
    """
    plan = Plan()
    notes = resolve_notes(notes, root / "site.yaml")
    declared = _declared(root / "site.yaml")
    if declared:
        plan.found.append(
            message(
                notes,
                "found_site",
                languages=", ".join(declared["languages"]),
                theme=declared["theme"],
            )
        )

    content = root / "content"
    present: list[str] = []
    if content.is_dir():
        present = sorted(p.name for p in content.iterdir() if p.is_dir())
        pages = len([p for p in content.rglob("*.md") if p.name != NOTE])
        langs = ", ".join(present) or message(notes, "none")
        plan.found.append(message(notes, "found_content", pages=pages, langs=langs))
    for folder in ("data", "media", "static", "theme"):
        if (root / folder).is_dir():
            plan.found.append(message(notes, "found_folder", folder=folder))

    languages = declared["languages"] if declared else present
    theme = declared["theme"] if declared else None

    made = create(
        root,
        name=root.resolve().name,
        languages=languages or None,
        theme=theme,
        force=force,
        notes=notes,
    )
    plan.created = made.created
    plan.skipped = made.skipped
    plan.notes = notes
    return plan


def _declared(site_yaml: Path) -> dict | None:
    """Языки и тема так, как их объявил сам сайт. Нет конфига — нет ответа.

    Читаем мягко: `init` часто зовут именно потому, что конфиг ещё сырой,
    и падать на нём в момент, когда человек просит помочь его достроить,
    было бы издевательством. Полноценную проверку сделает сборка.
    """
    if not site_yaml.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(site_yaml.read_text(encoding="utf-8")) or {}
        block = data.get("site") or {}
        languages = [str(x) for x in (block.get("languages") or []) if x]
        default = block.get("default_lang")
        if default and default not in languages:
            languages.insert(0, str(default))
    except Exception:
        return None
    if not languages:
        return None
    notes = str((data.get("build") or {}).get("notes") or "") or None
    return {"languages": languages, "theme": block.get("theme"), "notes": notes}
