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
from heron.core import notes
from heron.core.errors import Collector, HeronError
from heron.core.models import Page, Site
from heron.core.parser import blocks, frontmatter, markdown, sections

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
INDEX = "_index.md"
HOME = "index.md"
NOT_FOUND = "404.md"
IGNORED = {"readme.md", "changelog.md", "license.md", "contributing.md"}
DEFAULT_TYPE = "page"
HOME_TYPE = "home"


def _slug_of(name: str) -> str:
    return name[: -len(".md")] if name.endswith(".md") else name


def url_for(lang: str, default_lang: str, parts: list[str]) -> str:
    """Собрать канонический адрес: всегда со слешем на конце."""
    prefix = [] if lang == default_lang else [lang]
    path = "/".join([*prefix, *parts])
    return f"/{path}/" if path else "/"


def _folder_slugs(root: Path, collector: Collector) -> dict[str, str]:
    """Сегмент адреса каждой папки: её `slug`, если раздел его объявил.

    Собирается заранее, отдельным проходом: дочернюю страницу движок
    встречает раньше, чем `_index.md` её раздела, а адрес ребёнка зависит
    от того, как назвал себя родитель.

    Негодный слаг здесь молча пропускается — не потому, что он допустим,
    а потому, что об этом скажет чтение самого `_index.md`: там он
    проходит через контракт фронтматтера и даёт E002 с номером строки.
    Ругаться дважды об одном значит удвоить список ошибок на ровном месте.
    """
    out: dict[str, str] = {}
    for path in root.rglob(INDEX):
        rel = path.parent.relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        try:
            data, _, _ = frontmatter.split(path.read_text(encoding="utf-8"), str(path))
        except HeronError:
            continue  # об этой ошибке уже сказал _folder_types
        slug = data.get("slug")
        if isinstance(slug, str) and SLUG.match(slug.strip()):
            out[rel] = slug.strip()
    return out


def folder_url(parts: list[str], folder_slugs: dict[str, str]) -> list[str]:
    """Путь папок, где каждый сегмент заменён слагом своего раздела.

    Адрес собирается из цепочки сегментов, а не из строки пути, поэтому
    раздел, переименовавший себя, уводит за собой и всех детей.
    """
    return [
        folder_slugs.get("/".join(parts[:depth]), part) for depth, part in enumerate(parts, start=1)
    ]


LINK_IN_TEXT = re.compile(r"\]\(\s*(/[^)\s]+)|href=\"(/[^\"]+)\"")


def _links(body: str, offset: int) -> list[tuple[int, str]]:
    """Внутренние ссылки тела страницы с номером строки, как их написал автор.

    Номер строки нужен именно здесь: после разбора markdown остаётся HTML,
    в котором строк исходника уже нет, а человеку править файл. Тем более
    теперь, когда адрес раздела задаётся слагом: переименовали раздел —
    и руками написанные ссылки на него ведут в никуда, молча.
    """
    out: list[tuple[int, str]] = []
    for number, line in enumerate(body.splitlines(), start=offset):
        for match in LINK_IN_TEXT.finditer(line):
            out.append((number, match.group(1) or match.group(2)))
    return out


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
            collector.warn(
                f"нет дерева контента для языка {lang!r}",
                path=f"content/{lang}",
                kind="языки",
            )
            continue

        folder_types = _folder_types(lang_root, collector)
        folder_slugs = _folder_slugs(lang_root, collector)

        for path in sorted(lang_root.rglob("*.md")):
            rel = path.relative_to(content_root).as_posix()
            parts = list(path.relative_to(lang_root).parts)
            name = parts.pop()

            # Служебные файлы репозитория и черновики страницами не считаются.
            # README рядом с контентом — обычное дело, и объяснять человеку,
            # что у него «недопустимый слаг», значит спорить с ним о том,
            # чего он не просил.
            if name.lower() in IGNORED or name.startswith(".") or notes.skip(name):
                continue
            if name.startswith("_") and name != INDEX:
                continue

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

            # Ключ строится из пути файла и никогда не смотрит на слаг:
            # это идентификатор страницы, по нему движок находит её
            # языковые версии. Склеить его с адресом — значит запретить
            # языкам иметь разные адреса, а переименование адреса сделать
            # разрывом связи между переводами.
            if name == INDEX:
                url_parts = folder_url(parts, folder_slugs)
                key = folder
                page_type = meta.type or own_type or (inherited or DEFAULT_TYPE)
            elif name == HOME and not parts:
                url_parts = []
                key = ""
                page_type = meta.type or HOME_TYPE
            elif name == NOT_FOUND and not parts:
                # 404.md в корне языка — страница «не найдено» без объявления
                # типа: шаблон 404.html и исключение из карты сайта ей
                # положены по имени файла, как главной — по index.md.
                url_parts = ["404"]
                key = "404"
                page_type = meta.type or "404"
            else:
                own_slug = meta.slug or _slug_of(name)
                url_parts = [*folder_url(parts, folder_slugs), own_slug]
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
                for warning in blocks.intro_parts(md, intro):
                    warning.path = rel
                    collector.warnings.append(warning)

            page = Page(
                lang=lang,
                source=rel,
                key=key,
                meta=meta,
                sections=found,
                intro=intro,
                url=url_for(lang, config.site.default_lang, url_parts),
                type=page_type,
                links=_links(body, body_line),
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
            if key == "home":
                collector.warn(
                    "ключ home в подстановках schema означает главную: "
                    "эта страница через pages.home недоступна — переименуйте файл",
                    path=rel,
                    kind="прочее",
                )

        # Папка языка есть, страниц в ней нет. На деве это нормальная стадия:
        # второй язык часто пишут раньше основного. Но молчать нельзя — иначе
        # пустой язык обнаруживается по 404 на его главной.
        if not any(p.lang == lang for p in site.pages):
            collector.warn(
                f"в языке {lang!r} нет ни одной страницы",
                path=f"content/{lang}",
                kind="языки",
            )

    return site, collector
