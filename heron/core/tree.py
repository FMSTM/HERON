"""Обход `content/` и построение URL.

Путь файла определяет адрес — никаких отдельных карт маршрутов. Добавление
страницы это создание одного файла: она сама появится в меню, в каталоге своей
папки, в sitemap, в hreflang и в `llms.txt`. Удаление файла убирает её отовсюду.

Спецификация: docs/spec/20-data-contract.md, разделы 2 и 3.
"""

from __future__ import annotations

import re
from pathlib import Path

from markdown_it import MarkdownIt

from heron.contracts.site import SiteConfig
from heron.core.errors import Collector, HeronError
from heron.core.models import Page, Site
from heron.core.parser import blocks, frontmatter, markdown, sections

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
INDEX = "_index.md"
HOME = "index.md"
DEFAULT_TYPE = "page"
HOME_TYPE = "home"


def _slug_of(name: str) -> str:
    return name[: -len(".md")] if name.endswith(".md") else name


def url_for(lang: str, default_lang: str, parts: list[str]) -> str:
    """Собрать канонический адрес: всегда со слешем на конце."""
    prefix = [] if lang == default_lang else [lang]
    path = "/".join([*prefix, *parts])
    return f"/{path}/" if path else "/"


def _folder_types(root: Path, collector: Collector) -> dict[str, tuple[str | None, str | None]]:
    """Для каждой папки: её собственный тип и тип её детей, из `_index.md`."""
    out: dict[str, tuple[str | None, str | None]] = {}
    for path in root.rglob(INDEX):
        rel = path.parent.relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        try:
            data, _, _ = frontmatter.split(path.read_text(encoding="utf-8"), str(path))
        except HeronError as exc:
            collector.errors.append(exc)
            continue
        out[rel] = (data.get("type"), data.get("children_type"))
    return out


def scan(
    content_root: Path,
    config: SiteConfig,
    md: MarkdownIt | None = None,
    collector: Collector | None = None,
    drafts: bool = False,
) -> tuple[Site, Collector]:
    """Прочитать все языковые деревья и собрать страницы."""
    collector = collector or Collector()
    md = md or markdown.make(allow_raw_html=config.build.allow_raw_html)
    site = Site()

    for lang in config.site.languages:
        lang_root = content_root / lang
        if not lang_root.is_dir():
            collector.warn(f"нет дерева контента для языка {lang!r}", path=f"content/{lang}")
            continue

        folder_types = _folder_types(lang_root, collector)

        for path in sorted(lang_root.rglob("*.md")):
            rel = path.relative_to(content_root).as_posix()
            parts = list(path.relative_to(lang_root).parts)
            name = parts.pop()

            if name != INDEX and not SLUG.match(_slug_of(name)):
                collector.error(
                    "E005",
                    f"недопустимое имя файла {name!r}",
                    path=rel,
                    hint="слаг — латиница, цифры и дефис: getting-started.md",
                )
                continue

            try:
                meta, body, body_line, lint = frontmatter.read(path, rel=rel)
            except HeronError as exc:
                collector.errors.append(exc)
                continue
            collector.warnings.extend(lint)

            folder = "/".join(parts)
            own_type, children_type = folder_types.get(folder, (None, None))
            parent_folder = "/".join(parts[:-1]) if parts else ""
            _, inherited = folder_types.get(parent_folder, (None, None))

            if name == INDEX:
                url_parts = parts
                key = folder
                page_type = meta.type or own_type or (inherited or DEFAULT_TYPE)
            elif name == HOME and not parts:
                url_parts = []
                key = ""
                page_type = meta.type or HOME_TYPE
            else:
                slug = meta.slug or _slug_of(name)
                url_parts = [*parts, slug]
                key = "/".join([*parts, _slug_of(name)])
                page_type = meta.type or children_type or DEFAULT_TYPE

            try:
                markdown.guard_raw_html(body, rel, config.build.allow_raw_html, offset=body_line)
                intro, found = sections.split(md, body, rel, offset=body_line)
            except HeronError as exc:
                collector.errors.append(exc)
                continue
            collector.warnings.extend(blocks.apply(md, found))
            if intro is not None:
                intro.kind, intro.data = "prose", intro.html

            page = Page(
                lang=lang,
                source=rel,
                key=key,
                meta=meta,
                sections=found,
                intro=intro,
                url=url_for(lang, config.site.default_lang, url_parts),
                type=page_type,
            )

            if not meta.published and not drafts:
                continue

            clash = site.by_url.get(page.url)
            if clash is not None:
                collector.error(
                    "E004",
                    f"адрес {page.url} уже занят файлом {clash.source}",
                    path=rel,
                    hint="переименуйте файл или задайте другой slug во фронтматтере",
                )
                continue

            site.pages.append(page)
            site.by_url[page.url] = page
            site.by_key[(lang, key)] = page

    return site, collector
