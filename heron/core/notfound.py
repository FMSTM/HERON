"""Страница 404 на каждом языке.

Текст 404 — контент: `content/<lang>/404.md`, тип `404`, рисуется шаблоном
темы `templates/404.html`. Файла нет — страница всё равно нужна: без неё
nginx отдаёт свою встроенную заглушку, и нарисованную темой 404 не видит
никто. Тогда движок собирает её из шаблона темы без текста контента и
предупреждает: заголовок и пояснение тема берёт из своих строк (`t`).

Спецификация: docs/spec/20-data-contract.md, раздел 2, «Страница 404».
"""

from __future__ import annotations

from pathlib import Path

from heron.contracts.frontmatter import PageMeta
from heron.contracts.site import SiteConfig
from heron.core.errors import Collector
from heron.core.models import Page, Site
from heron.core.urls import home_url

TYPE = "404"
KEY = "404"


def url_of(config: SiteConfig, lang: str) -> str:
    return f"{home_url(config, lang)}404/"


def ensure(site: Site, config: SiteConfig, theme_dir: Path, collector: Collector) -> None:
    """Достроить 404 там, где у языка есть страницы, а файла 404.md нет."""
    template = theme_dir / "templates" / f"{TYPE}.html"
    for lang in config.site.languages:
        real = [p for p in site.of_lang(lang) if not p.generated]
        if not real or any(p.type == TYPE for p in real):
            continue
        if not template.is_file():
            collector.warn(
                f"нет content/{lang}/404.md и шаблона темы templates/404.html: "
                "на несуществующий адрес сервер отдаст свою заглушку",
                path=f"content/{lang}",
                kind="контент",
            )
            continue
        collector.warn(
            f"нет content/{lang}/404.md: страница 404 собрана из шаблона темы без текста",
            path=f"content/{lang}",
            kind="контент",
        )
        page = Page(
            lang=lang,
            source=f"content/{lang}/404.md (нет файла)",
            key=KEY,
            meta=PageMeta.model_validate(
                {"title": "404", "h1": "404", "description": "404", "noindex": True}
            ),
            url=url_of(config, lang),
            type=TYPE,
            generated=True,
        )
        site.pages.append(page)
        site.by_url[page.url] = page
        site.by_key[(lang, KEY)] = page
