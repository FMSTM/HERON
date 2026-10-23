"""Скелет сайта: что кладут `heron new` и `heron init`.

Сам скелет неинтерактивен и детерминирован: одинаковый вызов даёт одинаковую
папку. Опрос в терминале живёт в командной строке и лишь собирает аргументы
для этого вызова. Кладёт только контент: markdown, картинки, тему, site.yaml. Ни
Dockerfile, ни compose, ни скриптов сборки, ни .env здесь нет и быть не
может — сборка, окружения и упаковка живут в HERON, а папка сайта остаётся
папкой сайта. Скрипты публикации под выбранный способ кладёт только
конфигуратор (`heron setup`), и это короткие вызовы образа HERON.

Тема скелета — стартовая: белая, рисует все формы секций. Её же ставит
`heron theme get starter` (`starter_theme`).

Спецификация: docs/spec/23-distribution.md, раздел 4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from heron import __version__
from heron.core import paths
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
.heron-docs/
.*.heron-lock
.DS_Store
__pycache__/
"""

# Строки интерфейса темы на языке сайта. Нет языка — английские.
STRINGS = {
    "uk": (
        "powered_by: Працює на\nread_more: Читати далі\nskip: До змісту\n"
        "menu: Меню\nbreadcrumbs: Ви тут\ntheme_toggle: Світла або темна тема\n"
        "contact_main: Основний\ncontact_sales: Продажі\n"
        "contact_marketing: Маркетинг\ncontact_support: Підтримка\n"
        "contact_booking: Запис\ncontact_press: Преса\n"
    ),
    "ru": (
        "powered_by: Работает на\nread_more: Читать дальше\nskip: К содержимому\n"
        "menu: Меню\nbreadcrumbs: Вы здесь\ntheme_toggle: Светлая или тёмная тема\n"
        "contact_main: Основной\ncontact_sales: Продажи\n"
        "contact_marketing: Маркетинг\ncontact_support: Поддержка\n"
        "contact_booking: Запись\ncontact_press: Пресса\n"
    ),
    "en": (
        "powered_by: Powered by\nread_more: Read more\nskip: Skip to content\n"
        "menu: Menu\nbreadcrumbs: You are here\ntheme_toggle: Light or dark theme\n"
        "contact_main: Main\ncontact_sales: Sales\n"
        "contact_marketing: Marketing\ncontact_support: Support\n"
        "contact_booking: Booking\ncontact_press: Press\n"
    ),
}

# Демонстрационный сайт белой темы: тема без своих страниц — пустая витрина.
# Главная, «Блоки» (все виды блоков, которые рисует тема), «Темы»,
# «Документация» — в каждом языке сайта: страницы стоят в меню, и без них
# меню второго языка вело бы в никуда (строгая сборка падает). Тексты есть
# на русском и английском; остальные языки получают английские.
DEMO = HERE / "demo"
DEMO_MEDIA = DEMO / "media"
DEMO_LANGS = ("ru", "en")
DEMO_PAGES = ("index", "blocks", "themes", "docs")
DEMO_TITLES = {
    # страница → (title, h1, description, пункт меню), {name} — название сайта
    "ru": {
        "index": (
            "{name} — сайт на HERON",
            "{name}",
            "Демонстрационный сайт белой темы HERON: как устроены страницы и что править.",
            "Главная",
        ),
        "blocks": (
            "Блоки страницы — что умеет тема",
            "Блоки страницы",
            "Все виды блоков HERON на одной странице: список, шаги, таблица, факты, "
            "вопросы, вкладки и другие.",
            "Блоки",
        ),
        "themes": (
            "Темы — как сменить внешний вид",
            "Темы",
            "Как сменить тему сайта на HERON и что приезжает вместе с ней.",
            "Темы",
        ),
        "docs": (
            "Документация — главные команды HERON",
            "Документация",
            "Главные команды HERON: создать, настроить, посмотреть, проверить, собрать.",
            "Документация",
        ),
    },
    "en": {
        "index": (
            "{name} — a site on HERON",
            "{name}",
            "The demo site of the HERON white theme: how pages are made and what to edit.",
            "Home",
        ),
        "blocks": (
            "Page blocks — what the theme draws",
            "Page blocks",
            "Every kind of HERON block on one page: list, steps, table, facts, "
            "questions, tabs and more.",
            "Blocks",
        ),
        "themes": (
            "Themes — how to change the look",
            "Themes",
            "How to change the theme of a HERON site and what comes with it.",
            "Themes",
        ),
        "docs": (
            "Documentation — the main HERON commands",
            "Documentation",
            "The main HERON commands: create, set up, look, check, build.",
            "Documentation",
        ),
    },
}
DEMO_NAV = ["/", "blocks", "themes", "docs"]

# Язык комментариев и пояснений, которые кладёт скелет: site.yaml,
# theme.yaml, SEO-блок страниц, записки heron-readme.md.
NOTE_LANGS = ("ru", "en")
TEXT = HERE / "text"


ENV_NOTES = "HERON_NOTES"

# Сообщения команд — на языке пояснений, словарь общий для всего CLI.
from heron.messages import say as message  # noqa: E402

# Что лежит в папке под git ещё до сайта. Такая папка для `new` пустая:
# репозиторий заводят раньше сайта, и отказывать из-за .git бессмысленно.
SERVICE = (
    ".git",
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    ".github",
    ".gitlab",
    ".DS_Store",
    ".editorconfig",
    "README",
    "README.md",
    "LICENSE",
    "LICENSE.md",
)


def foreign_files(root: Path) -> list[str]:
    """Что в папке мешает создать сайт с нуля: всё, кроме служебного."""
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.name not in SERVICE)


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


def placeholder_domain(name: str) -> str:
    """Домен-заглушка: `.example` зарезервирован и никуда не ведёт."""
    slug = slugify(name)
    return f"{slug}.example" if slug else "example.com"


# Тексты стартовых страниц. Нет языка — английский: страница на чужом
# языке полезнее её отсутствия, и сайт собирается сразу — и без единого
# предупреждения: секция about есть, потому что её ждёт тип home стартовой
# темы, короткое имя есть, потому что главная стоит в меню.
NAV_HOME = {"uk": "Головна", "ru": "Главная", "en": "Home"}

STARTER = {
    "uk": {
        "home": (
            "{name} — головна",
            "{name}",
            "Головна сторінка сайту {name}",
            "Перший абзац: хто ви і чим корисні.\n\nДругий абзац: що людина отримає.\n\n"
            "## Про нас {{#about}}\n\n"
            "Кілька речень про вас: досвід, підхід, чому вам довіряють.",
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
            "Первый абзац: кто вы и чем полезны.\n\nВторой абзац: что человек получит.\n\n"
            "## О нас {{#about}}\n\n"
            "Несколько предложений о вас: опыт, подход, почему вам доверяют.",
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
            "Second paragraph: what the visitor gets.\n\n"
            "## About {{#about}}\n\n"
            "A few sentences about you: experience, approach, why people trust you.",
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
    nav_title: str | None = None,
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
    text = _text(notes, "seo-block.md")
    if nav_title:
        lines = text.split("\n")
        for index, line in enumerate(lines):
            if line.startswith("# nav_title:"):
                hint = line.split("#", 2)[-1].strip()
                lines[index] = (
                    "nav_title: {nav}\n# ↑ ".replace(
                        "{nav}", json.dumps(nav_title, ensure_ascii=False)
                    )
                    + hint
                )
                break
        text = "\n".join(lines)
    return text.format(
        title=json.dumps(title, ensure_ascii=False),
        h1=json.dumps(h1, ensure_ascii=False),
        description=json.dumps(description, ensure_ascii=False),
        order=order,
        type_line=type_line,
    )


def _demo(root: Path, lang: str, name: str, plan: Plan, force: bool, notes: str) -> None:
    """Демонстрационные страницы белой темы в язык `lang` и картинки к ним."""
    source = lang if lang in DEMO_LANGS else "en"
    for page, order in zip(DEMO_PAGES, (0, 10, 20, 30), strict=True):
        title, h1, description, nav = (part.format(name=name) for part in DEMO_TITLES[source][page])
        head = seo_block(title, h1, description, order=order, notes=notes, nav_title=nav)
        body = (DEMO / source / f"{page}.md").read_text(encoding="utf-8")
        _put(root, f"content/{lang}/{page}.md", head + "\n" + body, plan, force)
    for image in sorted(DEMO_MEDIA.glob("*")):
        rel = f"media/demo/{image.name}"
        if rel not in plan.created:
            _put(root, rel, image.read_text(encoding="utf-8"), plan, force)


def starter_theme(stage: Path, languages: list[str], notes: str = "en") -> None:
    """Белая тема в папку `stage`: theme/ и demo/ — как архив любой темы.

    Тот же источник, что у `heron new`: тема, которую получает новый сайт,
    и тема, которую ставит `heron theme get starter`, — одна и та же, вместе
    с демонстрационными страницами.
    """
    plan = Plan(notes=notes)
    fields = {"theme": "starter", "theme_title": '"HERON starter"'}
    _put(stage, "theme/theme.yaml", _text(notes, "theme.yaml").format(**fields), plan, True)
    for source in sorted(TEMPLATES.rglob("*")):
        if source.is_file():
            _copy(stage, source, f"theme/{source.relative_to(TEMPLATES).as_posix()}", plan, True)
    for lang in languages:
        _put(stage, f"theme/i18n/{lang}.yaml", STRINGS.get(lang, STRINGS["en"]), plan, True)
    for lang in languages:
        _demo(stage / "demo", lang, "HERON", plan, True, notes)


def _starter(
    root: Path,
    lang: str,
    name: str,
    plan: Plan,
    force: bool,
    notes: str,
    pages: tuple[str, ...] = ("home", "404"),
) -> None:
    """Главная и страница 404 языка: сайт собирается сразу после создания."""
    texts = STARTER.get(lang, STARTER["en"])
    for page, rel in (("home", "index.md"), ("404", "404.md")):
        if page not in pages:
            continue
        title, h1, description, body = (part.format(name=name) for part in texts[page])
        order = 0 if page == "home" else 999
        nav = NAV_HOME.get(lang, NAV_HOME["en"]) if page == "home" else None
        text = seo_block(title, h1, description, order=order, notes=notes, nav_title=nav)
        _put(root, f"content/{lang}/{rel}", text + "\n" + body + "\n", plan, force)


def _version_spec() -> str:
    major, minor, *_ = __version__.split(".")
    return f">={major}.{minor},<{major}.{int(minor) + 1}"


def _put(root: Path, rel: str, text: str, plan: Plan, force: bool) -> None:
    # Ссылка наружу на файле или на папке по пути к нему — E024 до записи:
    # init и setup дописывают чужие папки сайта, а не только новые.
    path = paths.in_site(root, rel)
    if path.exists() and not force:
        plan.skipped.append(rel)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    paths.in_site(root, rel)  # папки созданы — проверить ещё раз
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
    domain: str | None = None,
    default_lang: str | None = None,
    demo: bool = False,
) -> Plan:
    """Разложить скелет сайта в папку.

    `notes` — язык комментариев и пояснений во всех файлах скелета:
    `ru` или `en`. Языки самого сайта — отдельно, в `languages`.
    `default_lang` — основной язык; не задан — первый из `languages`.
    `domain` не задан — заглушка `<имя>.example`.
    `demo` — демонстрационные страницы белой темы в каждом языке (главная, «Блоки»,
    «Темы», «Документация») и меню к нему. `init` его не кладёт: там у сайта
    свой контент.
    """
    if notes not in NOTE_LANGS:
        raise ValueError(message("en", "bad_notes", value=notes))
    plan = Plan(notes=notes)
    languages = list(languages or ["en"])
    if default_lang:
        languages = [default_lang] + [x for x in languages if x != default_lang]
    theme_name = theme or "main"
    default_lang = languages[0]
    # домен-заглушка: под нелатинским именем папки его не собрать,
    # и выдумывать транслит за человека не надо — он всё равно впишет свой
    domain = domain or placeholder_domain(name)

    import json

    theme_title = {"ru": f"Тема сайта {name}", "en": f"Theme of {name}"}[notes]
    fields = {
        "name": name,
        # в YAML имя идёт строкой в кавычках: «Студия: Киев» без них не читается
        "name_yaml": json.dumps(name, ensure_ascii=False),
        "theme_title": json.dumps(theme_title, ensure_ascii=False),
        "theme": theme_name,
        "domain": domain,
        "default_lang": default_lang,
        "languages": ", ".join(languages),
        "spec": _version_spec(),
    }

    site_yaml = _text(notes, "site.yaml").format(**fields)
    if demo:
        menu = ", ".join(json.dumps(item) if item == "/" else item for item in DEMO_NAV)
        site_yaml = site_yaml.replace('  main: ["/"]', f"  main: [{menu}]", 1)
    _put(root, "site.yaml", site_yaml, plan, force)
    _put(root, ".gitignore", GITIGNORE, plan, force)
    _note(root, "root", "", notes, plan, force, name=name, slug=slugify(name) or name)

    for lang in languages:
        if demo:
            _demo(root, lang, name, plan, force, notes)
            _starter(root, lang, name, plan, force, notes, pages=("404",))
        else:
            _starter(root, lang, name, plan, force, notes)

    for folder in ("data", "media", "static", "plugins"):
        path = paths.in_site(root, folder)
        if not path.exists() and not path.is_symlink():
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

    # Демонстрационные страницы стоят в меню. Новый язык получает их, если они ещё
    # есть в основном языке, — иначе его меню вело бы в никуда. Сайт, где
    # их уже заменили своими страницами, ничего лишнего не получает.
    first = (languages or present or [None])[0]
    demo = bool(first) and (content / first / "blocks.md").is_file()
    made = create(
        root,
        name=root.resolve().name,
        languages=languages or None,
        theme=theme,
        force=force,
        notes=notes,
        demo=demo,
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
