"""Структурированные секции: что за модуль и какие в нём данные.

Никакого своего синтаксиса. Всё, что ниже, — валидный markdown, читаемый
глазами и в любом редакторе; модуль определяется по форме содержимого,
а при неоднозначности — явным классом в якоре.

Правило важнее удобства: шесть статей различаются только набором модулей
внутри секций. Если зашивать это в шаблон, каждая новая статья потребует
правки темы. При этом правиле седьмая статья — один markdown-файл
и ноль строк кода.

Разбор ошибается мягко: не распознал формат — отдал прозой и записал
предупреждение. Валить сборку из-за пропущенной палочки в таблице нельзя.

Спецификация: docs/spec/20-data-contract.md, раздел 6.1.
"""

from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from heron.core.errors import Warning_
from heron.core.models import Pair, Section

BY_CLASS = {
    "alert": "alert-list",
    "callout": "callout",
    "checklist": "checklist",
    "facts": "facts",
    "faq": "faq",
    "gallery": "gallery",
    "list": "list",
    "prose": "prose",
    "steps": "steps",
    "table": "table",
    "timeline": "timeline",
    "two-lists": "two-lists",
}

PAIR = re.compile(r"^\s*(?P<key>[^|]+?)\s*\|\s*(?P<value>.+?)\s*$")

# Жирный зачин: **Текст.** или **Текст:** в самом начале абзаца или пункта.
# Знак в конце — точка, двоеточие или тире: по ним человек и отделяет
# термин от пояснения, когда пишет.
BOLD_LEAD = re.compile(r"^\s*\*\*(?P<lead>.+?)\*\*\s*(?P<rest>.*)$", re.S)
LEAD_END = ".:—–-"

# Метка шага: [ЧАЩЕ ВСЕГО] в самом начале, целиком в верхнем регистре.
STEP_TAG = re.compile(r"^\s*\[(?P<tag>[^\[\]]+)\]\s*(?P<rest>.*)$", re.S)

LINK = re.compile(r'<a\s[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
TAGS = re.compile(r"<[^>]+>")


def links_of(html: str) -> list[dict[str, str]]:
    """Ссылки куска разметки списком: тема вправе показать их отдельно."""
    return [
        {"title": TAGS.sub("", match.group("title")).strip(), "href": match.group("href")}
        for match in LINK.finditer(html or "")
    ]


def split_bold_lead(text: str) -> tuple[str, str]:
    """Отделить жирный зачин от остатка. Нет зачина — пустой заголовок."""
    match = BOLD_LEAD.match(text or "")
    if not match:
        return "", (text or "").strip()
    lead = match.group("lead").strip()
    rest = match.group("rest").strip()
    if lead.endswith(tuple(LEAD_END)):
        lead = lead.rstrip("".join(LEAD_END)).strip()
    elif rest.startswith(tuple(LEAD_END)):
        rest = rest.lstrip("".join(LEAD_END)).strip()
    else:
        # жирный фрагмент без знака в конце — это выделение, а не зачин
        return "", (text or "").strip()
    return lead, rest


def _render(md: MarkdownIt, tokens: list[Token], env: dict) -> str:
    return md.renderer.render(tokens, md.options, env).strip()


def _blocks(tokens: list[Token], open_type: str, close_type: str) -> list[tuple[int, int]]:
    """Пары индексов открывающего и закрывающего токена верхнего уровня."""
    out: list[tuple[int, int]] = []
    depth = 0
    start = 0
    for index, token in enumerate(tokens):
        if token.type == open_type:
            if depth == 0:
                start = index
            depth += 1
        elif token.type == close_type and depth:
            depth -= 1
            if depth == 0:
                out.append((start, index))
    return out


def _items(md: MarkdownIt, tokens: list[Token], env: dict) -> list[str]:
    """Пункты списка.

    Пункт вида `**Термин.** Пояснение` разбирается в пару. Если зачин есть
    хотя бы у одного пункта, парами отдаётся весь список: половина строк,
    половина пар — это забота темы, которой у неё быть не должно. Список
    без зачинов остаётся списком строк, как раньше.
    """
    raw: list[tuple[str, str]] = []
    for start, end in _blocks(tokens, "list_item_open", "list_item_close"):
        inner = tokens[start + 1 : end]
        source = next((t.content for t in inner if t.type == "inline"), "")
        raw.append((source, _render(md, inner, env)))

    parsed = [split_bold_lead(source) for source, _ in raw]
    if not any(term for term, _ in parsed):
        return [html for _, html in raw]

    items: list[str] = []
    for (term, rest), (_source, html) in zip(parsed, raw, strict=True):
        text = md.renderInline(rest, {}) if rest else ""
        items.append(Pair(html, term=term, text=text, links=links_of(html)))
    return items


def _headed_groups(md: MarkdownIt, tokens: list[Token], env: dict) -> list[dict[str, Any]]:
    """Группы `### Заголовок` с содержимым до следующего такого же."""
    starts = [i for i, t in enumerate(tokens) if t.type == "heading_open" and t.tag == "h3"]
    groups: list[dict[str, Any]] = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(tokens)
        title = tokens[index + 1].content.strip() if index + 1 < len(tokens) else ""
        content = tokens[index + 3 : end]
        groups.append(
            {
                "title": title,
                "html": _render(md, content, env),
                "items": _items(md, content, env),
                "has_list": any(t.type == "bullet_list_open" for t in content),
            }
        )
    return groups


def _facts(raw: str) -> list[dict[str, str]] | None:
    """Строки вида `Ключ | Значение`. Таблица без шапки, а не markdown-таблица."""
    rows: list[dict[str, str]] = []
    bad = 0
    for line in (line for line in raw.splitlines() if line.strip()):
        if set(line.strip()) <= set("|-: "):
            return None  # это markdown-таблица, у неё есть строка-разделитель
        match = PAIR.match(line)
        if match and "|" in line:
            rows.append({"key": match.group("key"), "value": match.group("value")})
        else:
            bad += 1
    if not rows or bad > len(rows):
        return None
    return rows


def _table(md: MarkdownIt, tokens: list[Token], env: dict) -> dict[str, Any] | None:
    """Обычная markdown-таблица: первая строка — шапка."""
    if not any(t.type == "table_open" for t in tokens):
        return None

    head: list[str] = []
    rows: list[list[str]] = []
    current: list[str] | None = None
    in_head = False

    for index, token in enumerate(tokens):
        if token.type == "thead_open":
            in_head = True
        elif token.type == "thead_close":
            in_head = False
        elif token.type == "tr_open":
            current = []
        elif token.type == "tr_close":
            if current is not None:
                if in_head:
                    head = current
                else:
                    rows.append(current)
            current = None
        elif token.type in ("th_open", "td_open") and current is not None:
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            current.append(following.content.strip() if following else "")

    return {"head": head, "rows": rows}


def _steps(md: MarkdownIt, tokens: list[Token], env: dict) -> list[dict[str, Any]] | None:
    """Нумерованный список в шаги.

    Пункт `1. **[ЧАЩЕ ВСЕГО] Без операции.** Текст` разбирается на метку,
    заголовок и текст. Метка — скобки в самом начале, целиком в верхнем
    регистре; всё, что в скобках вперемешку с нижним регистром, — обычный
    текст, а не метка.
    """
    if not any(t.type == "ordered_list_open" for t in tokens):
        return None

    steps: list[dict[str, Any]] = []
    for number, (start, end) in enumerate(_blocks(tokens, "list_item_open", "list_item_close"), 1):
        inner = tokens[start + 1 : end]
        source = next((t.content for t in inner if t.type == "inline"), "")
        classes = _classes_of(tokens[start])

        title, rest = split_bold_lead(source)
        tag = ""
        if title:
            match = STEP_TAG.match(title)
            if match and match.group("tag").strip() == match.group("tag").strip().upper():
                tag = match.group("tag").strip()
                title = match.group("rest").strip()
        else:
            rest_html = _render(md, inner, env)
            steps.append(
                {
                    "n": number,
                    "tag": "",
                    "title": "",
                    "text": rest_html,
                    "html": rest_html,
                    "links": links_of(rest_html),
                    "top": "top" in classes,
                }
            )
            continue

        # Остаток — markdown, а поле называется html: ссылки и выделения
        # внутри шага должны быть разметкой, а не текстом
        text = md.renderInline(rest, {}) if rest else ""
        steps.append(
            {
                "n": number,
                "tag": tag,
                "title": title,
                "text": text,
                "html": text,
                "links": links_of(text),
                "top": "top" in classes,
            }
        )

    if steps and not any(step["top"] for step in steps):
        steps[0]["top"] = True
    return steps or None


def _classes_of(token: Token) -> list[str]:
    raw = token.attrGet("class") or ""
    return [name for name in raw.split() if name]


def detect(md: MarkdownIt, section: Section) -> tuple[str, Any, list[Warning_]]:
    """Определить модуль секции и разобрать её данные."""
    warnings: list[Warning_] = []
    env: dict = {}
    tokens = md.parse(section.raw, env)

    explicit: str | None = None
    for name in section.classes:
        if name in BY_CLASS:
            explicit = BY_CLASS[name]
            break
        warnings.append(
            Warning_(f"секция {section.id!r}: неизвестный класс {name!r}, определяю по содержимому")
        )

    groups = _headed_groups(md, tokens, env)
    with_lists = [g for g in groups if g["has_list"]]

    def parse(kind: str) -> tuple[str, Any] | None:
        if kind == "facts":
            rows = _facts(section.raw)
            return ("facts", rows) if rows is not None else None
        if kind == "timeline":
            # шкала бывает и парами «период | событие», и нумерованными шагами
            rows = _facts(section.raw)
            if rows is not None:
                return "timeline", rows
            steps = _steps(md, tokens, env)
            return ("timeline", steps) if steps else None
        if kind == "table":
            table = _table(md, tokens, env)
            return ("table", table) if table else None
        if kind == "steps":
            steps = _steps(md, tokens, env)
            return ("steps", steps) if steps else None
        if kind == "faq":
            return ("faq", [{"q": g["title"], "a": g["html"]} for g in groups]) if groups else None
        if kind in ("two-lists", "checklist"):
            return (kind, with_lists) if with_lists else None
        if kind in ("list", "alert-list", "gallery"):
            items = _items(md, tokens, env)
            return (kind, items) if items else None
        if kind == "callout":
            quotes = _blocks(tokens, "blockquote_open", "blockquote_close")
            if quotes:
                start, end = quotes[0]
                return "callout", _render(md, tokens[start + 1 : end], env)
            return None
        if kind == "prose":
            return "prose", section.html
        return None

    if explicit:
        parsed = parse(explicit)
        if parsed:
            return parsed[0], parsed[1], warnings
        warnings.append(
            Warning_(
                f"секция {section.id!r}: класс {explicit!r} не подходит к содержимому, "
                "вывожу прозой"
            )
        )
        return "prose", section.html, warnings

    # автоопределение по форме содержимого
    order = ["table", "facts", "steps"]
    if len(with_lists) >= 3:
        order.append("checklist")
    elif len(with_lists) == 2:
        order.append("two-lists")
    if groups and not with_lists:
        order.append("faq")
    order += ["callout", "list"]

    for kind in order:
        parsed = parse(kind)
        if parsed:
            return parsed[0], parsed[1], warnings

    return "prose", section.html, warnings


MAIN_NODE = ("bullet_list_open", "ordered_list_open", "table_open")
CLOSE_OF = {
    "bullet_list_open": "bullet_list_close",
    "ordered_list_open": "ordered_list_close",
    "table_open": "table_close",
}


def _lines_between(lines: list[str], start: int, end: int, skip: set[int]) -> str:
    chunk = [
        line for number, line in enumerate(lines) if start <= number < end and number not in skip
    ]
    return "\n".join(chunk).strip()


def structure(md: MarkdownIt, section: Section) -> None:
    """Разложить секцию на подводку, основной узел, примечание и врезку.

    Макет рисует их по-разному: подводка крупнее, примечание мельче,
    цитата — врезкой в рамке. Склеенный html тему устроить не может.
    """
    env: dict = {}
    tokens = md.parse(section.raw, env)
    lines = section.raw.splitlines()
    if not lines:
        return

    # цитата — врезка, где бы она ни стояла; из подводки и примечания уходит
    quoted: set[int] = set()
    for start, end in _blocks(tokens, "blockquote_open", "blockquote_close"):
        if not section.callout:
            section.callout = _render(md, tokens[start + 1 : end], env)
        span = tokens[start].map
        tail = tokens[end].map
        if span:
            stop = tail[1] if tail else span[1]
            quoted.update(range(span[0], stop))

    # основной узел: первый список, таблица или группа `###`
    main_start = main_end = None
    depth = 0
    for index, token in enumerate(tokens):
        if token.type in MAIN_NODE and depth == 0 and token.map:
            if token.map[0] in quoted:
                continue
            main_start, main_end = token.map
            close = CLOSE_OF[token.type]
            level = 0
            for follow in tokens[index:]:
                if follow.type == token.type:
                    level += 1
                elif follow.type == close:
                    level -= 1
                    if level == 0:
                        # у закрывающего токена карты строк нет, поэтому
                        # конец берём с открывающего: он знает весь блок
                        main_end = follow.map[1] if follow.map else main_end
                        break
            break
        if token.type == "heading_open" and token.tag == "h3" and token.map:
            main_start, main_end = token.map[0], len(lines)
            break

    if main_start is None:
        section.lead = ""
        section.note = ""
        section.links = links_of(section.html)
        return

    lead_md = _lines_between(lines, 0, main_start, quoted)
    note_md = _lines_between(lines, main_end or len(lines), len(lines), quoted)

    if note_md:
        head, *rest = re.split(r"\n\s*\n", note_md, maxsplit=1)
        term, tail = split_bold_lead(head)
        if term:
            section.note_title = term
            note_md = "\n\n".join([tail, *rest]).strip()

    section.lead = md.render(lead_md).strip() if lead_md else ""
    section.note = md.render(note_md).strip() if note_md else ""
    section.links = links_of(section.html)


def intro_parts(md: MarkdownIt, intro: Section) -> list[Warning_]:
    """Вводный блок: первый абзац — подводка, второй — обещание.

    Шаблон показывает ровно два: крупный первый абзац и один под ним.
    Третий и дальше в макете места не имеют, поэтому о них предупреждаем,
    а не выбрасываем молча.
    """
    chunks = [part.strip() for part in re.split(r"\n\s*\n", intro.raw) if part.strip()]
    if chunks:
        intro.lead = md.render(chunks[0]).strip()
    if len(chunks) > 1:
        intro.promise = md.render(chunks[1]).strip()
    intro.links = links_of(intro.html)
    if len(chunks) > 2:
        return [
            Warning_(
                f"вводный блок длиннее двух абзацев: третий и далее "
                f"({len(chunks) - 2}) не попадут в шаблон",
                kind="контент",
            )
        ]
    return []


def apply(md: MarkdownIt, sections: dict[str, Section]) -> list[Warning_]:
    """Проставить модуль, данные и части каждой секции."""
    warnings: list[Warning_] = []
    for section in sections.values():
        kind, data, found = detect(md, section)
        section.kind, section.data = kind, data
        structure(md, section)
        warnings.extend(found)
    return warnings
