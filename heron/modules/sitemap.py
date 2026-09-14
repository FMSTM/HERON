"""Карта сайта и языковые соответствия.

Мусор вида `cpt_layouts` в индексе старого сайта появился потому, что sitemap
генерировал сторонний плагин со своим представлением о том, что такое страница.
Здесь карта строится из того же дерева, что и сам сайт: служебных сущностей
без URL в системе нет, поэтому попасть в неё нечему.

`hreflang` симметричен по построению: связи берутся из одного дерева переводов,
а не проставляются руками на каждой странице.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from heron.contracts.site import SiteConfig
from heron.core.models import Page, Site
from heron.core.urls import absolute

XMLNS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML = "http://www.w3.org/1999/xhtml"


def indexable(page: Page) -> bool:
    return page.meta.published and not page.meta.noindex


def alternates(page: Page, config: SiteConfig) -> list[tuple[str, str]]:
    """Языковые версии страницы, включая её саму и x-default."""
    versions = {page.lang: page, **page.translations}
    out = [
        (lang, absolute(config, other.url))
        for lang, other in sorted(versions.items())
        if indexable(other)
    ]
    default = versions.get(config.site.default_lang)
    if default is not None and indexable(default):
        out.append(("x-default", absolute(config, default.url)))
    return out


def _entry(page: Page, config: SiteConfig) -> str:
    lines = ["  <url>", f"    <loc>{escape(absolute(config, page.url))}</loc>"]
    if page.meta.updated:
        lines.append(f"    <lastmod>{page.meta.updated.isoformat()}</lastmod>")
    links = alternates(page, config)
    if len(links) > 2:  # сама страница и x-default смысла не добавляют
        for lang, href in links:
            lines.append(
                f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{escape(href)}"/>'
            )
    lines.append("  </url>")
    return "\n".join(lines)


def generate(site: Site, config: SiteConfig) -> dict[str, str]:
    """`sitemap.xml` плюс по файлу на язык."""
    files: dict[str, str] = {}
    names: list[str] = []

    for lang in config.site.languages:
        pages = [p for p in site.of_lang(lang) if indexable(p)]
        if not pages:
            continue
        body = "\n".join(_entry(p, config) for p in sorted(pages, key=lambda p: p.url))
        name = f"sitemap-{lang}.xml"
        files[name] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="{XMLNS}" xmlns:xhtml="{XHTML}">\n{body}\n</urlset>\n'
        )
        names.append(name)

    index = "\n".join(
        f"  <sitemap><loc>{escape(absolute(config, '/' + name))}</loc></sitemap>" for name in names
    )
    files["sitemap.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<sitemapindex xmlns="{XMLNS}">\n{index}\n</sitemapindex>\n'
    )
    return files
