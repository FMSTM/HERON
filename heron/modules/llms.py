"""llms.txt и llms-full.txt по формату llmstxt.org.

Строится из того же дерева, что и меню: разделы — страницы-каталоги,
внутри — их дети с однострочным описанием.

Спецификация: docs/spec/21-engine.md, раздел 9.
"""

from __future__ import annotations

from heron.contracts.site import SiteConfig
from heron.core.models import Page, Site
from heron.core.urls import absolute, home_url
from heron.modules.sitemap import indexable


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


# Как назвать язык в блоке «другие языки». Нейронке всё равно, человеку —
# нет, а файл читают оба.
NAMES = {
    "uk": "Українською",
    "ru": "На русском",
    "en": "In English",
    "de": "Auf Deutsch",
    "pl": "Po polsku",
}


def generate(site: Site, config: SiteConfig) -> dict[str, str]:
    """Корневой файл со списком языков плюс файл на каждый язык.

    Собирался только основной язык: остальных версий сайта для нейронок не
    существовало вовсе. На сайте, где основной язык ещё не написан, это
    означало четыре строки при трёх десятках готовых страниц на других.

    Языки не смешиваются в одном файле: модель отвечает на языке того
    текста, который прочла, а близкие языки — украинский с русским — она
    путает чаще всего. Раздельные файлы дают ей выбрать нужный,
    перекрёстные ссылки — найти остальные.

    Формат llmstxt.org языковых версий не описывает, поэтому конвенция
    своя: файл читает модель, ей достаточно внятной строки человеческим
    текстом, изобретать разметку незачем.
    """
    files: dict[str, str] = {}
    langs = [lang for lang in config.site.languages if _has_pages(site, lang)]
    for lang in langs:
        files.update(_for_lang(site, config, lang, langs))
    files["llms.txt"] = _index(site, config, langs)
    return files


def _has_pages(site: Site, lang: str) -> bool:
    """Есть ли у языка что показывать, кроме заглушки.

    Ссылка на пустой файл хуже её отсутствия: модель уходит по ней и
    возвращается ни с чем.
    """
    return len([p for p in site.of_lang(lang) if indexable(p)]) > 1


def _index(site: Site, config: SiteConfig, langs: list[str]) -> str:
    """Корневой файл: что это за сайт и где его языковые версии."""
    lang = config.site.default_lang
    home = site.by_url.get(home_url(config, lang))
    title = home.h1 if home else (config.site.name or config.site.domain)
    lines = [f"# {title}", ""]
    if home is not None:
        lines += [f"> {home.meta.description}", ""]
    if langs:
        lines += ["## Языковые версии", ""]
        lines += [f"- {NAMES.get(one, one)}: {absolute(config, _name(one))}" for one in langs]
    return "\n".join(lines).rstrip() + "\n"


def _name(lang: str, full: bool = False) -> str:
    """Имя файла языка: /llms-ru.txt, /llms-full-ru.txt."""
    return f"/llms-full-{lang}.txt" if full else f"/llms-{lang}.txt"


def _others(config: SiteConfig, lang: str, langs: list[str], full: bool = False) -> list[str]:
    """Шапка со ссылками на остальные версии и на корневой файл."""
    rest = [one for one in langs if one != lang]
    if not rest:
        return []
    lines = [f"Все языковые версии: {absolute(config, '/llms.txt')}"]
    lines += [f"{NAMES.get(one, one)}: {absolute(config, _name(one, full))}" for one in rest]
    lines.append("")
    return lines


def _for_lang(site: Site, config: SiteConfig, lang: str, langs: list[str]) -> dict[str, str]:
    files: dict[str, str] = {}
    home = site.by_url.get(home_url(config, lang))
    pages = [p for p in site.of_lang(lang) if indexable(p)]

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

    head = _others(config, lang, langs) + head
    files[_name(lang).lstrip("/")] = "\n".join(head + body).rstrip() + "\n"

    if config.seo.llms_txt:
        full = [f"# {title}", ""]
        for page in sorted(pages, key=lambda p: p.url):
            full += [f"# {page.h1}", "", f"URL: {absolute(config, page.url)}", "", _body(page), ""]
        full = _others(config, lang, langs, full=True) + full
        files[_name(lang, full=True).lstrip("/")] = "\n".join(full).rstrip() + "\n"

    return files
