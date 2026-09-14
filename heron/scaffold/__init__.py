"""Скелет сайта: что кладут `heron new` и `heron init`.

Команда неинтерактивна и детерминирована: одинаковый вызов даёт одинаковую
папку. Вопросов о способе размещения не задаёт — кладёт и папочный путь,
и докерный, всегда. Решение «папка или образ» принимается позже, флагом
сборки, а не в момент, когда о сайте ещё ничего не известно.

Спецификация: docs/spec/23-distribution.md, раздел 4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from heron import __version__

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
DOCKER = HERE / "docker"
SITE = HERE / "site"

GITIGNORE = """dist/
.heron-cache/
.env
.DS_Store
__pycache__/
"""

ENV_EXAMPLE = """# Секреты сервисов. Сборке они не нужны: она идёт без сети.
# Файл монтируется только в heron-relay, если на сайте есть формы.
SMTP_URL=
CRM_SECRET=
TG_CHAT=
"""

SITE_YAML = """# Версия движка, на которой собирается сайт. Обязательна.
heron: "{spec}"

site:
  domain: {domain}
  name: {name}
  theme: {theme}
  default_lang: {default_lang}
  languages: [{languages}]

seo:
  title_suffix: ""
  llms_txt: true
  robots_extra: []

nav:
  main: []

build:
  fail_on_warning: false
  allow_raw_html: false

plugins: []
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

INDEX_MD = """---
title: {name} — коротко о сайте
h1: {name}
description: Короткое описание сайта — оно попадёт в выдачу
---

Вводный абзац. Всё, что написано до первого заголовка с якорем, тема получает
как `intro`.

## О чём этот сайт {{#about}}

Заголовок с якорем начинает секцию. Якорь — адрес для темы, его не правят.
Сам заголовок — контент, его правят свободно.
"""

NOT_FOUND_MD = """---
title: Страница не найдена
h1: Такой страницы нет
description: Страница не найдена
type: "404"
noindex: true
---

Возможно, адрес устарел. Вернитесь на главную или воспользуйтесь меню.
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
    docker: bool = True,
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
    _put(root, ".env.example", ENV_EXAMPLE, plan, force)
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
        _put(root, f"content/{lang}/index.md", INDEX_MD.format(name=name), plan, force)
        _put(root, f"content/{lang}/404.md", NOT_FOUND_MD, plan, force)

    for folder in ("data", "img", "static", "plugins"):
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

    if docker:
        for source in sorted(DOCKER.iterdir()):
            _copy(root, source, source.name, plan, force, version=__version__)
        script = root / "build.sh"
        if script.is_file():
            script.chmod(0o755)

    return plan


def adopt(root: Path, force: bool = False) -> Plan:
    """Дополнить существующую папку тем, чего в ней нет.

    Ничего не перезаписывает без `--force`: чужой файл важнее нашего образца.
    """
    plan = Plan()
    content = root / "content"
    langs: list[str] = []
    if content.is_dir():
        langs = sorted(p.name for p in content.iterdir() if p.is_dir())
        pages = len(list(content.rglob("*.md")))
        plan.found.append(f"content/: {pages} страниц, языки: {', '.join(langs) or 'нет'}")
    for folder in ("data", "img", "static", "theme"):
        if (root / folder).is_dir():
            plan.found.append(f"{folder}/ на месте")

    name = root.resolve().name
    made = create(root, name=name, languages=langs or None, force=force)
    plan.created = made.created
    plan.skipped = made.skipped
    return plan
