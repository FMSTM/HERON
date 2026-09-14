"""Сборка учебного сайта в tmp_path для тестов обхода и связей."""

from __future__ import annotations

from pathlib import Path

import yaml

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig


def page(title: str = "Заголовок", **fields) -> str:
    """Markdown-файл с фронтматтером и парой секций."""
    meta = {"title": title, "h1": title, "description": "Описание", **fields}
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{head}\n---\n\nВступление.\n\n## Что это {{#what}}\n\nТекст.\n"


def build(root: Path, files: dict[str, str]) -> Path:
    """Разложить файлы по путям относительно content/."""
    content = root / "content"
    for rel, text in files.items():
        path = content / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return content


def config(**over) -> SiteConfig:
    data = {
        "heron": ">=0.1,<0.2",
        "site": {
            "domain": "example.com",
            "theme": "demo",
            "default_lang": "uk",
            "languages": ["uk", "ru"],
        },
    }
    data.update(over)
    return SiteConfig.model_validate(data)


def theme(**over) -> ThemeConfig:
    return ThemeConfig.model_validate({"name": "demo", **over})


BASE = """<!doctype html>
<html lang="{{ lang }}">
<head><title>{{ page.title }}</title><link rel="canonical" href="{{ absolute(page.url) }}"></head>
<body>{% block content %}{% endblock %}</body>
</html>
"""

PAGE_TEMPLATE = """{% extends "base.html" %}
{% block content %}
<h1>{{ page.h1 }}</h1>
{{ mod.prose('what') }}
{{ mod.facts('quick-facts') }}
{{ mod.call() }}
{% endblock %}
"""

MODULES = {
    "prose.html": '<section class="prose">{{ html }}</section>\n',
    "facts.html": (
        "<dl>{% for row in items %}<dt>{{ row.key }}</dt><dd>{{ row.value }}</dd>"
        "{% endfor %}</dl>\n"
    ),
    "call.html": '<a href="#">{{ t.book_now }}</a>\n',
}


def theme_dir(root: Path, templates: dict[str, str] | None = None, strings: dict | None = None):
    """Разложить минимальную рабочую тему."""
    path = root / "theme"
    (path / "templates").mkdir(parents=True, exist_ok=True)
    (path / "modules").mkdir(parents=True, exist_ok=True)
    (path / "i18n").mkdir(parents=True, exist_ok=True)

    (path / "base.html").write_text(BASE, encoding="utf-8")
    for name, text in (
        templates or {"page.html": PAGE_TEMPLATE, "home.html": PAGE_TEMPLATE}
    ).items():
        (path / "templates" / name).write_text(text, encoding="utf-8")
    for name, text in MODULES.items():
        (path / "modules" / name).write_text(text, encoding="utf-8")
    (path / "i18n" / "uk.yaml").write_text(
        yaml.safe_dump(
            strings if strings is not None else {"book_now": "Записатися"}, allow_unicode=True
        ),
        encoding="utf-8",
    )
    return path
