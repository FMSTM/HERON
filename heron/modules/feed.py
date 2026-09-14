"""Лента публикаций.

Нужна не каждому сайту: у одного блог отложен, у другого лента с первого дня.
Поэтому тип страниц для ленты задаётся в `site.yaml` (`seo.feed`), а без него
файл просто не генерируется — это штатная ситуация, а не ошибка.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from heron.contracts.site import SiteConfig
from heron.core.models import Page, Site
from heron.core.urls import absolute, home_url

EPOCH = date(1970, 1, 1)


def _item(page: Page, config: SiteConfig) -> str:
    url = absolute(config, page.url)
    updated = (page.meta.updated or EPOCH).isoformat()
    return (
        "  <entry>\n"
        f"    <title>{escape(page.h1)}</title>\n"
        f'    <link href="{escape(url)}"/>\n'
        f"    <id>{escape(url)}</id>\n"
        f"    <updated>{updated}T00:00:00Z</updated>\n"
        f"    <summary>{escape(page.meta.description)}</summary>\n"
        "  </entry>"
    )


def generate(site: Site, config: SiteConfig) -> dict[str, str]:
    if not config.seo.feed:
        return {}

    lang = config.site.default_lang
    pages = [
        p for p in site.of_type(config.seo.feed, lang) if p.meta.published and not p.meta.noindex
    ]
    pages.sort(key=lambda p: (p.meta.updated or EPOCH, p.url), reverse=True)
    pages = pages[: config.seo.feed_limit]

    home = site.by_url.get(home_url(config, lang))
    title = home.h1 if home else (config.site.name or config.site.domain)
    updated = max((p.meta.updated or EPOCH for p in pages), default=EPOCH).isoformat()

    entries = "\n".join(_item(p, config) for p in pages)
    return {
        "feed.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            f"  <title>{escape(title)}</title>\n"
            f'  <link href="{escape(absolute(config, home_url(config, lang)))}"/>\n'
            f"  <id>{escape(absolute(config, home_url(config, lang)))}</id>\n"
            f"  <updated>{updated}T00:00:00Z</updated>\n"
            f"{entries}\n"
            "</feed>\n"
        )
    }
