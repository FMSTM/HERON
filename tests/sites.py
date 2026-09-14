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
