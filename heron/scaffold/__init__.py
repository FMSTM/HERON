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
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from heron.scaffold.agents import KitPlan

from heron import __version__
from heron.core import paths
from heron.core.errors import HeronError
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
        "consent_title: Згода на аналітику\n"
        "consent_text: Сайт використовує лічильники відвідуваності. "
        "Вони вмикаються лише з вашої згоди.\n"
        "consent_accept: Прийняти\nconsent_decline: Відмовитися\n"
        "consent_settings: Налаштування лічильників\n"
    ),
    "ru": (
        "powered_by: Работает на\nread_more: Читать дальше\nskip: К содержимому\n"
        "menu: Меню\nbreadcrumbs: Вы здесь\ntheme_toggle: Светлая или тёмная тема\n"
        "contact_main: Основной\ncontact_sales: Продажи\n"
        "contact_marketing: Маркетинг\ncontact_support: Поддержка\n"
        "contact_booking: Запись\ncontact_press: Пресса\n"
        "consent_title: Согласие на аналитику\n"
        "consent_text: Сайт использует счётчики посещаемости. "
        "Они включаются только с вашего согласия.\n"
        "consent_accept: Принять\nconsent_decline: Отказаться\n"
        "consent_settings: Настройки счётчиков\n"
    ),
    "en": (
        "powered_by: Powered by\nread_more: Read more\nskip: Skip to content\n"
        "menu: Menu\nbreadcrumbs: You are here\ntheme_toggle: Light or dark theme\n"
        "contact_main: Main\ncontact_sales: Sales\n"
        "contact_marketing: Marketing\ncontact_support: Support\n"
        "contact_booking: Booking\ncontact_press: Press\n"
        "consent_title: Analytics consent\n"
        "consent_text: This site uses visitor counters. "
        "They are switched on only with your consent.\n"
        "consent_accept: Accept\nconsent_decline: Decline\n"
        "consent_settings: Counter settings\n"
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
    # комплект для агентов (20 §1): его кладут new и init, а репозиторий сайта
    # нередко заводят с ним раньше сайта — `new .` такой папке не отказывает
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "agents",
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
        # Конфиг не разобрался — а ошибку о нём человек должен прочесть на своём
        # языке целиком, рамку и подробность (F05): тогда язык ищется простой
        # строкой `notes: ru|en` в тексте файла.
        declared = _declared(site_yaml)
        value = declared.get("notes") if declared is not None else notes_in_text(site_yaml)
    value = (value or "en").lower()
    if value not in NOTE_LANGS:
        raise ValueError(message("en", "bad_notes", value=value))
    return value


def ctx_notes() -> str | None:
    """`--notes` текущей команды click или объемлющей группы (`heron --notes ru build`).

    Единственное место, где язык запуска ищется в контексте click: им пользуются
    CLI, анкета (`setup.reasons.run_lang`) и установка темы. Вне команды click
    или без флага - None.
    """
    import click

    ctx = click.get_current_context(silent=True)
    while ctx is not None:
        value = (ctx.params or {}).get("notes")
        if value:
            return str(value)
        ctx = ctx.parent
    return None


def notes_error(flag: str | None, site_yaml: Path, error: ValueError) -> HeronError:
    """E011 вместо рамки «engine bug»: язык пояснений задан неверно (ru и en)."""
    import os

    if flag:
        where, key = "--notes", "bad_notes_flag_hint"
    elif os.environ.get(ENV_NOTES, "").strip():
        where, key = ENV_NOTES, "bad_notes_env_hint"
    else:
        where, key = str(site_yaml), "bad_notes_site_hint"
    return HeronError(code="E011", message=str(error), path=where, hint=message("en", key))


def site_yaml_problem(site_yaml: Path, lang: str) -> HeronError | None:
    """Что в site.yaml не даёт `init` и `theme get` честно работать: E011 или None.

    Не UTF-8, корень не блок ключей, `site.languages` не список - то, на чём
    команды раньше падали рамкой «engine bug» или молча делали вид, что всё
    в порядке. Сырой, но читаемый конфиг (опечатки, пустой файл, битый YAML)
    не проблема: `init` зовут именно чтобы его достроить.
    """
    if not site_yaml.is_file():
        return None
    try:
        text = site_yaml.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return HeronError(
            code="E011",
            message=message(lang, "site_not_utf8"),
            path=str(site_yaml),
            hint=message(lang, "site_not_utf8_hint"),
        )
    except OSError:
        return None
    import yaml

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if data is not None and not isinstance(data, dict):
        return HeronError(
            code="E011",
            message=message(lang, "site_not_block", value=_short(data)),
            path=str(site_yaml),
            hint=message(lang, "site_not_block_hint"),
        )
    block = data.get("site") if isinstance(data, dict) else None
    if isinstance(block, dict) and "languages" in block:
        raw = block["languages"]
        if raw is not None and not isinstance(raw, list):
            return HeronError(
                code="E011",
                message=message(lang, "site_languages_not_list", value=_short(raw)),
                path=str(site_yaml),
                hint=message(lang, "site_languages_not_list_hint"),
            )
    return None


# `notes: ru` в начале строки (с отступом, в кавычках или без, с комментарием
# после); закомментированная строка `# notes: ru` не считается.
NOTES_LINE = re.compile(r"""^[ \t]*notes:[ \t]*["']?(ru|en)["']?[ \t]*(?:#.*)?$""", re.M | re.I)


def notes_in_text(site_yaml: Path) -> str | None:
    """Язык пояснений из сырого текста site.yaml, который не разбирается как YAML.

    Читается только обычный файл: из FIFO или устройства под именем site.yaml
    чтение зависло бы или не кончилось.
    """
    try:
        if not site_yaml.is_file():
            return None
        text = site_yaml.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    found = NOTES_LINE.search(text)
    return found.group(1).lower() if found else None


def _text(lang: str, name: str) -> str:
    return (TEXT / lang / name).read_text(encoding="utf-8")


# Комментарии стартовой темы — на языке пояснений, как theme.yaml и записки.
# В шаблонах на их месте метка, текст — в text/<язык>/theme-notes.yaml.
# Ключа нет в таблице — KeyError: тема с меткой вместо комментария уехать
# в сайт не должна, и тест ловит это раньше.
NOTE_MARK = re.compile(r"\{# heron:note ([a-z0-9.-]+) #\}|/\* heron:note ([a-z0-9.-]+) \*/")


def theme_notes(lang: str) -> dict[str, str]:
    import yaml

    return yaml.safe_load(_text(lang, "theme-notes.yaml"))


def with_notes(text: str, lang: str) -> str:
    """Шаблон темы с комментариями на языке `lang` вместо меток."""
    table = theme_notes(lang)
    return NOTE_MARK.sub(lambda m: table[m.group(1) or m.group(2)], text)


def _theme_file(root: Path, source: Path, plan: Plan, force: bool, notes: str) -> None:
    rel = f"theme/{source.relative_to(TEMPLATES).as_posix()}"
    _put(root, rel, with_notes(source.read_text(encoding="utf-8"), notes), plan, force)


@dataclass(slots=True)
class Plan:
    """Что команда собирается создать."""

    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    found: list[str] = field(default_factory=list)
    notes: str = "en"
    # что сделано с комплектом для агентов; None — не трогали
    kit: KitPlan | None = None


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


def _demo_links(text: str) -> str:
    """Ветка и образ prod демо-страницы — на канал образа (`HERON_CHANNEL`, вне образа prod).

    Та же подстановка, что у комплекта (`scaffold.agents.channel_links`, 23 §12):
    сайт из beta-образа ведёт на ветку beta и в готовой команде — на образ beta.
    В prod текст байт в байт как исходник.
    """
    from heron.scaffold.agents import channel_links

    return channel_links(text)


def _demo(root: Path, lang: str, name: str, plan: Plan, force: bool, notes: str) -> None:
    """Демонстрационные страницы белой темы в язык `lang` и картинки к ним.

    Ссылки на репозиторий движка и образ в команде — на канал образа (`_demo_links`).
    """
    source = lang if lang in DEMO_LANGS else "en"
    for page, order in zip(DEMO_PAGES, (0, 10, 20, 30), strict=True):
        title, h1, description, nav = (part.format(name=name) for part in DEMO_TITLES[source][page])
        head = seo_block(title, h1, description, order=order, notes=notes, nav_title=nav)
        body = _demo_links((DEMO / source / f"{page}.md").read_text(encoding="utf-8"))
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
            _theme_file(stage, source, plan, True, notes)
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
    agents: str | bool = "true",
    *,
    place_kit: bool = True,
) -> Plan:
    """Разложить скелет сайта в папку.

    `notes` — язык комментариев и пояснений во всех файлах скелета:
    `ru` или `en`. Языки самого сайта — отдельно, в `languages`.
    `default_lang` — основной язык; не задан — первый из `languages`.
    `domain` не задан — заглушка `<имя>.example`.
    `demo` — демонстрационные страницы белой темы в каждом языке (главная, «Блоки»,
    «Темы», «Документация») и меню к нему. `init` его не кладёт: там у сайта
    свой контент.
    `agents` — комплект для агентов (20 §1): `true` — полный, `kit` — без гайдов
    и спецификаций, `false` — не класть; значение ложится в `build.agents`.
    `place_kit=False` — только записать значение, комплект кладёт вызывающий
    (`adopt` с `init --agents` обновляет его по манифесту).
    """
    if notes not in NOTE_LANGS:
        raise ValueError(message("en", "bad_notes", value=notes))
    agents = agents_level(agents)
    if agents != "false" and place_kit:
        # ссылка наружу на месте agents/ или указателя — E024 до первой записи скелета
        from heron.scaffold import agents as kit

        kit.check_targets(root, agents, notes)
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
        "agents": agents,
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
            _theme_file(root, source, plan, force, notes)
    for lang in languages:
        _put(root, f"theme/i18n/{lang}.yaml", STRINGS.get(lang, STRINGS["en"]), plan, force)

    if agents != "false" and place_kit:
        declared = {
            "name": name,
            "domain": domain,
            "languages": languages,
            "default_lang": default_lang,
        }
        _merge_kit(plan, _place_kit(root, notes, declared, "create", force, agents))

    return plan


AGENTS_LEVELS = ("true", "kit", "false")


def agents_level(value: object) -> str:
    """Значение `build.agents` строкой: true, kit или false (20 §5)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    if text not in AGENTS_LEVELS:
        raise ValueError(f"build.agents {value!r}: expected true, kit or false")
    return text


def _place_kit(
    root: Path,
    notes: str,
    declared: dict[str, object] | None,
    mode: Literal["create", "update"],
    force: bool,
    level: str,
    pointers: Literal["create", "update"] | None = None,
) -> KitPlan:
    from heron.scaffold import agents as kit

    fields = kit.fields(root, declared, notes)
    return kit.place(root, notes, fields, mode=mode, force=force, level=level, pointers=pointers)


def _merge_kit(plan: Plan, made: KitPlan) -> None:
    """Комплект — в общую сводку: положенное и заменённое — в created."""
    plan.created.extend(made.created)
    plan.created.extend(made.updated)
    plan.skipped.extend(made.skipped)
    plan.found.extend(made.found)
    plan.kit = made


def set_build_agents(root: Path, value: str, notes: str = "en") -> bool:
    """Записать `build.agents: <value>` в site.yaml точечно, не переформатируя файл.

    Строка `agents:` в блоке `build` есть — заменяется значение (комментарий
    в конце строки остаётся); нет — строка добавляется после `notes` (и его
    комментария), иначе сразу после `build:`; нет блока — он дописывается
    в конец. Нет site.yaml — ничего не пишется (False). Сообщение об ошибке - на
    языке `notes`.
    """
    import yaml

    value = agents_level(value)
    path = paths.in_site(root, "site.yaml")
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    head = next((i for i, line in enumerate(lines) if re.match(r"build:\s*(#.*)?$", line)), None)
    if head is None:
        flow = next((i for i, line in enumerate(lines) if re.match(r"build:\s*\{", line)), None)
        if flow is not None:
            lines[flow] = re.sub(r"\{\s*", f"{{agents: {value}, ", lines[flow], count=1)
        else:
            tail = "" if text.endswith("\n") or not text else "\n"
            lines = (text + tail + f"\nbuild:\n  agents: {value}\n").split("\n")
    else:
        end = head + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t")):
            end += 1
        block = range(head + 1, end)
        found = next((i for i in block if re.match(r"\s+agents:", lines[i])), None)
        if found is not None:
            lines[found] = re.sub(
                r"^(\s+agents:)\s*([^#\s][^#]*?)?(\s*#.*)?$",
                lambda m: f"{m.group(1)} {value}{m.group(3) or ''}",
                lines[found],
            )
        else:
            notes_at = next((i for i in block if re.match(r"\s+notes:", lines[i])), None)
            indent = "  "
            at = head + 1
            if notes_at is not None:
                indent = lines[notes_at][: len(lines[notes_at]) - len(lines[notes_at].lstrip())]
                at = notes_at + 1
                while at < end and lines[at].strip().startswith("#"):
                    at += 1
            lines.insert(at, f"{indent}agents: {value}")
    updated = "\n".join(lines)
    try:
        data = yaml.safe_load(updated) or {}
        written: str | None = agents_level((data.get("build") or {}).get("agents"))
    except Exception:  # noqa: BLE001 — правка не удалась: файл не трогаем
        written = None
    if written != value:
        raise HeronError(
            code="E011",
            message=message(notes, "build_agents_write_failed", value=value),
            path=str(path),
            hint=message(notes, "build_agents_write_failed_hint", value=value),
        )
    if updated != text:
        paths.in_site(root, "site.yaml").write_text(updated, encoding="utf-8")
    return True


def adopt(
    root: Path,
    force: bool = False,
    notes: str | None = None,
    agents_only: bool = False,
    agents_flag: str | None = None,
) -> Plan:
    """Дополнить папку тем, чего в ней нет, по написанному в `site.yaml`.

    Языки и тему берём из конфига, а не из того, какие папки уже лежат:
    иначе источников правды два, и рано или поздно они разойдутся. Дописал
    язык в `site.yaml`, выполнил `init` — папка под него появилась.

    Ничего не перезаписывает без `--force`: чужой файл важнее нашего образца.

    Комплект для агентов (20 §1): без флагов кладётся только недостающее, если
    `build.agents` не `false`, а корневые указатели (AGENTS.md: имя, языки,
    домен, о проекте) обновляются по манифесту — правленый человеком не
    трогается; `force` на комплект без флага не действует (21 §10). Язык
    комплекта без флага — язык манифеста (`agents.kept_lang`): недостающее и
    указатели кладутся на нём, а не на `build.notes`, и шапка манифеста с ними
    согласована; смену языка делает `init --agents` и называет её (`lang_from`).
    `agents_flag="false"` (`init --no-agents`) записывает `build.agents: false`
    и комплект не трогает; `"true"`/`"kit"` (`init --agents`) обновляет
    комплект по манифесту (с `force` — и правленые). `"true"` на сайте с
    `build.agents: kit` оставляет сокращённый комплект: спецификация включает
    «обратно в true» только выключенный сайт (20 §1, 21 §10). Значение пишется,
    только если оно меняется. Непонятное `build.agents` без флага — E011, как
    у check: комплект не трогается и ничего не пишется.
    `agents_only` — только комплект, остальной скелет не трогается.
    """
    plan = Plan()
    try:
        resolved = resolve_notes(notes, root / "site.yaml")
    except ValueError as error:
        raise notes_error(notes, root / "site.yaml", error) from error
    problem = site_yaml_problem(root / "site.yaml", resolved)
    if problem is not None:
        raise problem
    notes = resolved
    declared = _declared(root / "site.yaml")
    current = (declared or {}).get("agents")
    flag = agents_level(agents_flag) if agents_flag is not None else None
    if declared and declared.get("build_error") is not None:
        # с любым флагом: set_build_agents дописал бы второй блок build
        raise HeronError(
            code="E011",
            message=message(notes, "build_not_block", value=declared["build_error"]),
            path=str(root / "site.yaml"),
            hint=message(notes, "build_not_block_hint"),
        )
    if flag is None and declared and declared.get("agents_error") is not None:
        raise HeronError(
            code="E011",
            message=message(notes, "kit_bad_value", value=declared["agents_error"]),
            path=str(root / "site.yaml"),
            hint=message(notes, "kit_bad_value_hint"),
        )
    if flag == "true" and current == "kit":
        flag = "kit"
    level = flag or current or "true"
    kit_lang = notes
    if level != "false":
        # все цели комплекта — до первой записи, в том числе до правки build.agents
        from heron.scaffold import agents as kit

        previous = kit.read_manifest(root)
        if flag is None:
            # без флага язык комплекта — язык снимка по манифесту (20 §1, 21 §10)
            kit_lang = kit.kept_lang(previous, notes)
        kit.check_targets(root, level, kit_lang)
    if flag is not None and (flag != current or declared is None):
        set_build_agents(root, flag, notes)
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

    if not agents_only:
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
            agents=level,
            place_kit=False,
        )
        plan.created = made.created
        plan.skipped = made.skipped
    if level != "false":
        if flag is not None:
            # init --agents — по манифесту, на языке build.notes (смена — lang_from)
            mode: Literal["create", "update"] = "update" if previous.present else "create"
            made = _place_kit(root, notes, None, mode, force, level)
        else:
            # без флага — только недостающее, указатели — по манифесту (20 §1),
            # всё — на языке снимка; build.notes другой — сводка называет это
            pointers: Literal["update"] | None = "update" if previous.present else None
            made = _place_kit(root, kit_lang, None, "create", False, level, pointers)
            if kit_lang != notes:
                made.notes_lang = notes
        _merge_kit(plan, made)
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
    # build не блок ключей (`build: x`, `build: [1]`) — ответа о notes и agents
    # нет, а непонятое значение — текстом: init отвечает E011, как check, и не
    # дописывает второй build; справка и --version работают как обычно
    build_block = data.get("build")
    build_error = None
    if not isinstance(build_block, dict):
        if build_block is not None:
            build_error = _short(build_block)
        build_block = {}
    notes = str(build_block.get("notes") or "") or None
    agents, error = _declared_agents(build_block)
    return {
        "languages": languages,
        "theme": block.get("theme"),
        "notes": notes,
        "agents": agents,
        "agents_error": error,
        "build_error": build_error,
    }


def _short(value: object) -> str:
    """Значение из site.yaml для сообщения: коротко, даже если оно огромное."""
    import reprlib

    shown = reprlib.Repr(maxlevel=2, maxlist=4, maxdict=4, maxstring=40, maxother=40)
    return shown.repr(value)


def _declared_agents(build_block: object) -> tuple[str | None, str | None]:
    """`build.agents` мягко: (значение, непонятое значение текстом).

    Нет ключа — (None, None): по умолчанию комплект кладётся. Пустое `agents:`,
    «yes» строкой, число — как у валидатора BuildBlock: значение не понято
    (None, его текст), комплект не трогается, init и check отвечают E011.
    """
    if not isinstance(build_block, dict) or "agents" not in build_block:
        return None, None
    raw = build_block["agents"]
    if raw is not None:
        try:
            return agents_level(raw), None
        except ValueError:
            pass
    import json

    return None, json.dumps(raw, ensure_ascii=False)
