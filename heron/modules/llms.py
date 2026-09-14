"""llms.txt и llms-full.txt по формату llmstxt.org.

Строится из того же дерева, что и меню: разделы — страницы-каталоги,
внутри — их дети с однострочным описанием.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

from heron.contracts.site import SiteConfig
from heron.core.models import Page, Site
from heron.core.urls import absolute, home_url


def _line(page: Page, config: SiteConfig) -> str:
    return f"- [{page.h1}]({absolute(config, page.url)}): {page.meta.description}"


def _body(page: Page) -> str:
    parts: list[str] = []
    if page.intro is not None and page.intro.raw:
        parts.append(page.intro.raw)
    for section in page.sections.values():
        title = f"## {section.title}" if section.title else ""
        parts.append("\n\n".join(x for x in (title, section.raw) if x))
    return "\n\n".join(parts)


def generate(site: Site, config: SiteConfig) -> dict[str, str]:
    files: dict[str, str] = {}
    lang = config.site.default_lang
    home = site.by_url.get(home_url(config, lang))
    pages = [p for p in site.of_lang(lang) if p.meta.published and not p.meta.noindex]

    title = home.h1 if home else (config.site.name or config.site.domain)
    head = [f"# {title}", ""]
    if home is not None:
        head += [f"> {home.meta.description}", ""]

    catalogs = [p for p in pages if p.children and p is not home]
    loose = [p for p in pages if not p.children and p.parent in (None, home) and p is not home]

    body: list[str] = []
    for catalog in sorted(catalogs, key=lambda p: (p.meta.order, p.url)):
        body.append(f"## {catalog.h1}")
        body.append("")
        body.extend(_line(child, config) for child in catalog.children)
        body.append("")
    if loose:
        body.append("## Сторінки" if lang == "uk" else "## Страницы")
        body.append("")
        body.extend(_line(page, config) for page in loose)
        body.append("")

    files["llms.txt"] = "\n".join(head + body).rstrip() + "\n"

    if config.seo.llms_txt:
        full = [f"# {title}", ""]
        for page in sorted(pages, key=lambda p: p.url):
            full += [f"# {page.h1}", "", f"URL: {absolute(config, page.url)}", "", _body(page), ""]
        files["llms-full.txt"] = "\n".join(full).rstrip() + "\n"

    return files
