"""Обход `content/` и построение URL.

Путь файла определяет адрес — никаких отдельных карт маршрутов. Добавление
страницы это создание одного файла: она сама появится в меню, в каталоге своей
папки, в sitemap, в hreflang и в `llms.txt`. Удаление файла убирает её отовсюду.

Спецификация: docs/spec/20-data-contract.md, разделы 2 и 3.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt

from heron.contracts.site import SiteConfig
from heron.core import notes, paths
from heron.core.errors import Collector, HeronError
from heron.core.models import Page, Site
from heron.core.parser import blocks, frontmatter, markdown, sections
from heron.messages import Msg

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\Z")
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


def _read_index(path: Path) -> dict | None:
    """Фронтматтер `_index.md` или None, если файл негоден.

    Ничего не пишет в collector: об ошибке скажет основной обход `scan`,
    который читает каждый `_index.md` через `frontmatter.read` (E001/E030)
    с относительным путём. Так негодный файл даёт ровно одну ошибку.
    """
    try:
        data, _, _ = frontmatter.split(path.read_text(encoding="utf-8"), str(path))
    except (HeronError, UnicodeDecodeError, OSError):
        return None
    return data


def _folder_slugs(root: Path) -> dict[str, str]:
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
        if not paths.inside(root, path):
            continue  # об этом скажет основной обход
        rel = path.parent.relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        data = _read_index(path)
        if data is None:
            continue  # об ошибке скажет основной обход scan
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


HTML_HREF = re.compile(r'href="(/[^"]+)"')


def _links(md, body: str, offset: int) -> list[tuple[int, str]]:
    """Внутренние ссылки тела страницы с номером строки, как их написал автор.

    Номер строки нужен именно здесь: после разбора markdown остаётся HTML,
    в котором строк исходника уже нет, а человеку править файл. Тем более
    теперь, когда адрес раздела задаётся слагом: переименовали раздел —
    и руками написанные ссылки на него ведут в никуда, молча.

    Ссылки берутся из токенов того же разборщика, что рендерит страницу, а
    не регуляркой по строкам: так видны ссылки через определения
    (`[текст][метка]` и `[метка]: /адрес/`), а «ссылка» в блоке кода
    ссылкой не считается.
    """
    lines = markdown.split_lines(body)

    def line_of(href: str, start: int, end: int) -> int:
        for index in range(start, min(end, len(lines))):
            if href in lines[index]:
                return offset + index
        for index, text in enumerate(lines):  # ссылка через определение
            if "]:" in text and href in text:
                return offset + index
        return offset + start

    out: list[tuple[int, str]] = []
    for token in md.parse(body, {}):
        start, end = token.map or (0, 0)
        if token.type == "html_block":
            for match in HTML_HREF.finditer(token.content):
                out.append((line_of(match.group(1), start, end), match.group(1)))
            continue
        if token.type != "inline":
            continue
        for child in token.children or []:
            if child.type == "link_open":
                href = unquote(str(child.attrGet("href") or ""))
                if href.startswith("/") and not href.startswith("//"):
                    out.append((line_of(href, start, end), href))
            elif child.type == "html_inline":
                for match in HTML_HREF.finditer(child.content):
                    out.append((line_of(match.group(1), start, end), match.group(1)))
    return out


def _folder_types(root: Path) -> dict[str, tuple[str | None, str | None]]:
    """Для каждой папки: её собственный тип и тип её детей, из `_index.md`."""
    out: dict[str, tuple[str | None, str | None]] = {}
    for path in root.rglob(INDEX):
        if not paths.inside(root, path):
            continue  # об этом скажет основной обход
        rel = path.parent.relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        data = _read_index(path)
        if data is None:
            continue  # об ошибке скажет основной обход scan
        out[rel] = (data.get("type"), data.get("children_type"))
    return out


def _hold_inside(site: Site, lang: str) -> None:
    """Категория не переведена - не публикуются и страницы внутри неё (20 §4.2).

    Иначе боевая сборка выпустила бы переведённую страницу по адресу раздела,
    которого на этом языке нет: хлебные крошки и меню вели бы в 404.
    """
    folders = sorted(
        page.key
        for page in site.held
        if page.lang == lang and page.source.endswith("/" + INDEX) and page.key
    )
    if not folders:
        return
    for page in list(site.pages):
        if page.lang != lang:
            continue
        owner = next((f for f in folders if page.key.startswith(f + "/")), None)
        if owner is None:
            continue
        site.pages.remove(page)
        site.by_url.pop(page.url, None)
        site.by_key.pop((lang, page.key), None)
        page.held_by = owner
        site.held.append(page)


def scan(
    content_root: Path,
    config: SiteConfig,
    md: MarkdownIt | None = None,
    collector: Collector | None = None,
    drafts: bool = False,
    custom: dict | None = None,
    hold_pending: bool = False,
) -> tuple[Site, Collector]:
    """Прочитать все языковые деревья и собрать страницы.

    `hold_pending` - боевая сборка: страница с `translation: pending` не
    публикуется на своём языке и уходит в `site.held` (20 §4.2).
    """
    collector = collector or Collector()
    md = md or markdown.make(allow_raw_html=config.build.allow_raw_html)
    site = Site()

    for lang in config.site.languages:
        lang_root = content_root / lang
        if not lang_root.is_dir():
            collector.warn(
                Msg("tree_no_lang_tree", lang=lang),
                path=f"content/{lang}",
                kind="языки",
            )
            continue

        folder_types = _folder_types(lang_root)
        folder_slugs = _folder_slugs(lang_root)

        for path in sorted(lang_root.rglob("*.md")):
            rel = path.relative_to(content_root).as_posix()
            # Файл-ссылка на чужой диск читается как обычный — и его текст
            # уезжает в публичную сборку. Контент берётся только изнутри.
            if not paths.inside(content_root, path):
                collector.error(
                    paths.CODE,
                    Msg("tree_symlink_escape"),
                    path=rel,
                    hint=Msg("tree_symlink_escape_hint"),
                )
                continue
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
                    Msg("tree_bad_file_name", name=name),
                    path=rel,
                    hint=Msg("tree_bad_file_name_hint"),
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
                # offset - число строк файла до тела: формулы считают +1 сами.
                clean = markdown.strip_comments(body)
                markdown.guard_raw_html(
                    clean, rel, config.build.allow_raw_html, offset=body_line - 1
                )
                markdown.forbidden_attrs(md, clean, rel, offset=body_line - 1)
                intro, found = sections.split(md, clean, rel, offset=body_line - 1)
            except HeronError as exc:
                collector.errors.append(exc)
                continue
            # Определения ссылок берутся из всего тела: секция в одиночку
            # `[текст][метка]` не разберёт, если определение в другом месте.
            body_env: dict = {}
            md.parse(clean, body_env)
            references = body_env.get("references") or None
            collector.warnings.extend(blocks.apply(md, found, custom, references=references))
            if intro is not None:
                intro.kind, intro.data = "prose", intro.html
                for warning in blocks.intro_parts(md, intro, references=references):
                    warning.path = rel
                    collector.warnings.append(warning)

            # Сегмент адреса из имени папки проверяется так же, как имя файла:
            # `$` в адресе nginx прочёл бы как переменную, пробел и точка в
            # начале дают адрес, который сервер не отдаст.
            bad = [part for part in url_parts if not SLUG.match(part)]
            if bad:
                collector.error(
                    "E005",
                    Msg("tree_bad_url_segment", segment=bad[0]),
                    path=rel,
                    hint=Msg("tree_bad_url_segment_hint"),
                )
                continue

            page = Page(
                lang=lang,
                source=rel,
                key=key,
                meta=meta,
                sections=found,
                intro=intro,
                url=url_for(lang, config.site.default_lang, url_parts),
                type=page_type,
                links=_links(md, clean, body_line),
            )

            if not meta.published and not drafts:
                continue
            if hold_pending and meta.pending:
                site.held.append(page)
                continue

            clash = site.by_url.get(page.url)
            if clash is not None:
                collector.error(
                    "E004",
                    Msg("tree_url_taken", url=page.url, source=clash.source),
                    path=rel,
                    hint=Msg("tree_url_taken_hint"),
                )
                continue
            twin = site.by_key.get((lang, key))
            if twin is not None:
                # Ключ связывает переводы и ссылки. Два файла с одним ключом
                # (`a.md` со своим slug и раздел `a/_index.md`) молча
                # затирали друг друга: ссылки и переводы вели не туда.
                collector.error(
                    "E029",
                    Msg("tree_key_taken", page_key=key, lang=lang, source=twin.source),
                    path=rel,
                    hint=Msg("tree_key_taken_hint"),
                )
                continue

            site.pages.append(page)
            site.by_url[page.url] = page
            site.by_key[(lang, key)] = page
            if key == "home":
                collector.warn(
                    Msg("tree_home_key"),
                    path=rel,
                    kind="прочее",
                )

        if hold_pending:
            _hold_inside(site, lang)

        # Папка языка есть, страниц в ней нет. На деве это нормальная стадия:
        # второй язык часто пишут раньше основного. Но молчать нельзя — иначе
        # пустой язык обнаруживается по 404 на его главной.
        if not any(p.lang == lang for p in site.pages):
            collector.warn(
                Msg("tree_empty_lang", lang=lang),
                path=f"content/{lang}",
                kind="языки",
            )

    return site, collector
