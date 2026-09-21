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

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
SITE = HERE / "site"

GITIGNORE = """dist/
.heron-cache/
.DS_Store
__pycache__/
"""

SITE_YAML = """# Единственная точка правды о сайте. Всё, что здесь написано,
# определяет и сборку, и структуру папок: языки отсюда, тема отсюда.
# Заполните файл, затем выполните `heron init` — папки догонят конфиг.

# Версия движка, на которой собирается сайт. Обязательна.
heron: "{spec}"

site:
  domain: {domain}
  name: {name}
  theme: {theme}
  default_lang: uk
  languages: [uk]
  # ↑ добавьте языки сюда, потом `heron init` — появятся content/<язык>/
  #   и theme/i18n/<язык>.yaml. Первый язык должен быть в списке.

seo:
  title_suffix: ""
  llms_txt: true
  robots_extra: []

nav:
  main: []
  # ↑ слаги страниц верхнего меню, в нужном порядке

# Публичные идентификаторы счётчиков. Не секреты: видны в исходнике
# страницы. Вставляются только в прод-сборке.
analytics:
  metrika:
  gtm:
  ga4:

build:
  fail_on_warning: false
  allow_raw_html: false

plugins: []

# Пароли и токены сюда НЕ пишут. SMTP форм, ключи деплоя и прочее
# живут в окружении сборки, в HERON/env/.env.<сайт>.<окружение>:
# сборка статическая, и всё, что она видит, может оказаться в HTML.
"""

THEME_YAML = """name: {theme}
version: "0.1"
title: Тема сайта {name}

# Что тема ждёт от site.yaml. Движок проверит наличие
requires: []

modules: [prose, facts, list, steps, faq, cards, breadcrumbs]

types:
  home:
    uses: [intro, about]
  page:
    uses: [intro]
  "404":
    uses: [intro]

# Пропорции и ширины, которые движок нарежет из мастеров 1:1
images:
  widths: [400, 800, 1200, 1600]
  ratios: ["1:1", "16:9"]
  formats: [avif, webp]
"""


STRINGS = """powered_by: Работает на
read_more: Читать дальше
"""


@dataclass(slots=True)
class Plan:
    """Что команда собирается создать."""

    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    found: list[str] = field(default_factory=list)


def slugify(name: str) -> str:
    """Имя папки в безопасный слаг. Нелатинское имя слага не даёт — и не надо."""
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


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


def create(
    root: Path,
    name: str,
    languages: list[str] | None = None,
    theme: str | None = None,
    force: bool = False,
) -> Plan:
    """Разложить скелет сайта в папку."""
    plan = Plan()
    languages = languages or ["uk"]
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

    _put(root, "site.yaml", SITE_YAML.format(**fields), plan, force)
    _put(root, ".gitignore", GITIGNORE, plan, force)
    _copy(
        root,
        SITE / "README.md",
        "README.md",
        plan,
        force,
        name=name,
        slug=name.lower().replace("_", "-"),
    )

    for lang in languages:
        _keep(root, f"content/{lang}", plan)

    for folder in ("data", "media", "static", "plugins"):
        path = root / folder
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            (path / ".gitkeep").write_text("", encoding="utf-8")
            plan.created.append(f"{folder}/")

    _put(root, "theme/theme.yaml", THEME_YAML.format(**fields), plan, force)
    for source in sorted(TEMPLATES.rglob("*")):
        if source.is_file():
            _copy(root, source, f"theme/{source.relative_to(TEMPLATES).as_posix()}", plan, force)
    for lang in languages:
        _put(root, f"theme/i18n/{lang}.yaml", STRINGS, plan, force)

    return plan


def adopt(root: Path, force: bool = False) -> Plan:
    """Дополнить папку тем, чего в ней нет, по написанному в `site.yaml`.

    Языки и тему берём из конфига, а не из того, какие папки уже лежат:
    иначе источников правды два, и рано или поздно они разойдутся. Дописал
    язык в `site.yaml`, выполнил `init` — папка под него появилась.

    Ничего не перезаписывает без `--force`: чужой файл важнее нашего образца.
    """
    plan = Plan()
    declared = _declared(root / "site.yaml")
    if declared:
        plan.found.append(
            "site.yaml: языки " + ", ".join(declared["languages"]) + f", тема {declared['theme']}"
        )

    content = root / "content"
    present: list[str] = []
    if content.is_dir():
        present = sorted(p.name for p in content.iterdir() if p.is_dir())
        pages = len(list(content.rglob("*.md")))
        plan.found.append(f"content/: {pages} страниц, языки: {', '.join(present) or 'нет'}")
    for folder in ("data", "media", "static", "theme"):
        if (root / folder).is_dir():
            plan.found.append(f"{folder}/ на месте")

    languages = declared["languages"] if declared else present
    theme = declared["theme"] if declared else None

    made = create(
        root,
        name=root.resolve().name,
        languages=languages or None,
        theme=theme,
        force=force,
    )
    plan.created = made.created
    plan.skipped = made.skipped
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
    return {"languages": languages, "theme": block.get("theme")}
