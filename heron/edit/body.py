"""Тело страницы: секции по якорям и поля блоков по словарю мест `MD_PLACES`.

Секции режутся тем же правилом, что у сборки (`core/parser/sections.py`), а
форма каждой секции определяется тем же разбором (`core/parser/blocks.py`):
редактор видит страницу так же, как её видит тема. Поля блока берутся из
контракта темы (`heron describe`), и каждое находит своё значение по `md` -
месту в markdown. Место, которого нет в словаре, или форма, которую не
записать без потерь, - поле только для чтения с причиной.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from heron.core.errors import HeronError
from heron.core.parser import blocks, markdown, sections
from heron.edit.slots import Entry, Seq, Slot
from heron.edit.text import Line, blank, lines_of, mask, plain

LEAD_END = blocks.LEAD_END
BOLD = re.compile(r"\*\*(?P<lead>.+?)\*\*", re.S)
TAG = re.compile(r"\[(?P<tag>[^\[\]]+)\][ \t]*")
IMAGE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]*)(?:[ \t]+\"[^\"]*\")?\)")
MARKER = re.compile(
    r"^(?P<pad> {0,3})(?P<mark>[-*+]|(?P<num>\d{1,9})(?P<delim>[.)]))(?P<gap> {1,4}|$)"
)
HEADING = re.compile(
    r"^(?P<pre> {0,3}(?P<hashes>#{1,6})[ \t]+|(?P<bare> {0,3}#{1,6})(?=[ \t]*$))"
    r"(?P<text>.*?)(?P<attrs>[ \t]*\{[^{}]*\})?(?P<close>[ \t]+#+)?[ \t]*$"
)
ANCHOR = re.compile(r"#(?P<id>[^\s{}#.]+)")

SECTION_PLACES = {
    "body",
    "first-paragraph",
    "second-paragraph",
    "lead",
    "quote",
    "items",
    "numbered",
    "groups",
    "pairs",
    "table-head",
    "table-rows",
}
GROUP_PLACES = {"heading", "heading-id", "content", "items", "numbered", "lead"}
ITEM_PLACES = {"bold", "tag", "text", "more", "image", "alt"}
PAIR_PLACES = {"key", "value"}
ROW_PLACES = {"cells"}


# --- область текста ---------------------------------------------------------------


class Region:
    """Подряд идущие строки исходника и их маска для разбора."""

    def __init__(self, text: str, lines: list[Line], rows: list[str], md: MarkdownIt) -> None:
        self.text, self.lines, self.rows, self.md = text, lines, rows, md
        self._tokens: list[Token] | None = None

    @property
    def tokens(self) -> list[Token]:
        if self._tokens is None:
            self._tokens = self.md.parse("\n".join(self.rows))
        return self._tokens

    def sub(self, a: int, b: int) -> Region:
        return Region(self.text, self.lines[a:b], self.rows[a:b], self.md)

    def trim(self, a: int = 0, b: int | None = None) -> tuple[int, int]:
        b = len(self.rows) if b is None else b
        while a < b and blank(self.rows[a]):
            a += 1
        while b > a and blank(self.rows[b - 1]):
            b -= 1
        return a, b

    def span(self, a: int, b: int) -> tuple[int, int]:
        return self.lines[a].start, self.lines[b - 1].end

    def chunks(self) -> list[tuple[int, int]]:
        """Абзацы-куски: подряд идущие непустые строки."""
        out: list[tuple[int, int]] = []
        start = None
        for index, row in enumerate(self.rows):
            if blank(row):
                if start is not None:
                    out.append((start, index))
                    start = None
            elif start is None:
                start = index
        if start is not None:
            out.append((start, len(self.rows)))
        return out

    def top(self, *types: str) -> list[Token]:
        return [t for t in self.tokens if t.level == 0 and t.type in types and t.map]

    def code_rows(self) -> set[int]:
        rows: set[int] = set()
        for token in self.tokens:
            if token.type in ("fence", "code_block") and token.map:
                rows.update(range(*token.map))
        return rows

    def main(self) -> int | None:
        """Строка основного узла: список, таблица, группа ### или строка «ключ | значение»."""
        for token in self.top(
            "bullet_list_open", "ordered_list_open", "table_open", "heading_open"
        ):
            if token.type != "heading_open" or token.tag == "h3":
                return token.map[0]  # type: ignore[index]
        return self.pairs_start()

    def pairs_start(self) -> int | None:
        code = self.code_rows() | self.quoted()
        for index, row in enumerate(self.rows):
            if index in code:
                continue
            if "|" in row and blocks.PAIR.match(row) and not set(row.strip()) <= set("|-: "):
                return index
        return None

    def quoted(self) -> set[int]:
        rows: set[int] = set()
        for token in self.top("blockquote_open"):
            rows.update(range(*token.map))  # type: ignore[misc]
        return rows

    def empty_insert(self, anchor_end: int) -> tuple[int, str, str]:
        """Куда и как вписать значение в пустую область после строки `anchor_end`.

        `anchor_end` - конец строки заголовка; отрицательный - начало тела без
        заголовка (вводный блок): `-1 - позиция`.
        """
        if self.rows:
            return self.lines[0].end, "\n", "\n"
        if anchor_end < 0:
            return -1 - anchor_end, "", "\n\n"
        return anchor_end, "\n\n", "\n"

    def after(self, row: int) -> tuple[int, str, str]:
        """Вставка новым абзацем после строки `row` (индекс в области)."""
        return self.lines[row].end, "\n\n", ""


# --- секции ------------------------------------------------------------------------


@dataclass(slots=True)
class Section:
    id: str
    kind: str | None
    classes: list[str]
    start: int
    end: int
    head: int | None  # строка заголовка: начало
    heading: Slot | None
    anchor: Slot | None
    region: Region
    anchor_end: int = 0
    present: bool = True
    module: str | None = None
    specs: list[dict[str, Any]] | None = None
    fields: dict[str, Slot | Seq] = field(default_factory=dict)
    readonly: str | None = None


@dataclass(slots=True)
class Body:
    start: int
    sections: list[Section]
    error: Any = None

    def get(self, anchor: str) -> Section | None:
        return next((s for s in self.sections if s.id == anchor), None)


SpecsFor = Callable[[str, str | None], tuple[str | None, list[dict[str, Any]] | None]]


def parse(text: str, start: int, md: MarkdownIt, specs_for: SpecsFor) -> Body:
    """Разобрать тело `text[start:]`: секции, их форма и поля по контракту."""
    lines = lines_of(text, start)
    rows = mask(text, lines)
    try:
        kinds = _kinds(md, "\n".join(plain(text[line.start : line.end]) for line in lines))
    except HeronError as exc:
        return Body(start, [], error=exc.message)
    whole = Region(text, lines, rows, _structure(md))
    marks: list[tuple[int, int, Token]] = []  # строка, конец заголовка (строка), токен
    base = None
    for token in whole.tokens:
        if token.type != "heading_open" or not token.attrGet("id") or not token.map:
            continue
        level = int(token.tag[1:])
        if base is None:
            base = level
        elif level > base:
            continue
        marks.append((token.map[0], token.map[1], token))

    out: list[Section] = []
    first = marks[0][0] if marks else len(rows)
    a, b = whole.trim(0, first)
    out.append(
        Section(
            "intro",
            "prose",
            [],
            lines[0].start,
            lines[first - 1].end if first else lines[0].start,
            None,
            None,
            None,
            whole.sub(0, first),
            anchor_end=-1 - lines[0].start,
            present=b > a,
        )
    )
    for position, (row, head_end, token) in enumerate(marks):
        stop = marks[position + 1][0] if position + 1 < len(marks) else len(rows)
        anchor = str(token.attrGet("id"))
        kind, classes = kinds.get(anchor, (None, []))
        heading, anchor_slot = _heading(text, lines[row], rows[row], head_end - row)
        region = whole.sub(head_end, stop)
        if not any(not blank(r) for r in region.rows):
            # пустая секция: форму по содержимому не узнать - по классу якоря или по теме
            declared = [blocks.BY_CLASS[c] for c in classes if c in blocks.BY_CLASS]
            kind = declared[0] if declared else None
        out.append(
            Section(
                anchor,
                kind,
                classes,
                lines[row].start,
                lines[stop - 1].end,
                lines[row].start,
                heading,
                anchor_slot,
                region,
                anchor_end=lines[head_end - 1].end,
            )
        )
    for section in out:
        module, specs = specs_for(section.id, section.kind)
        section.module, section.specs = module, specs
        if specs:
            section.fields = _fields(section, specs)
    return Body(start, out)


_STRUCTURE: dict[int, MarkdownIt] = {}


def _structure(md: MarkdownIt) -> MarkdownIt:
    """Разборщик только блоков: местам значений нужны карты строк, а не html и инлайн."""
    key = id(md)
    if key not in _STRUCTURE:
        quick = markdown.make(allow_raw_html=bool(md.options.get("html")))
        quick.disable(["inline", "heron_media_paths"], ignoreInvalid=True)
        _STRUCTURE[key] = quick
    return _STRUCTURE[key]


@functools.lru_cache(maxsize=512)
def _kinds_cached(html: bool, body: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    md = markdown.make(allow_raw_html=html)
    clean = markdown.strip_comments(body)
    _intro, found = sections.split(md, clean, "")
    env: dict = {}
    md.parse(clean, env)
    blocks.apply(md, found, None, references=env.get("references") or None)
    return tuple(
        (anchor, section.kind or "prose", tuple(section.classes))
        for anchor, section in found.items()
    )


def _kinds(md: MarkdownIt, body: str) -> dict[str, tuple[str, list[str]]]:
    """Форма каждой секции - тем же разбором, что у сборки. Один текст - один разбор."""
    found = _kinds_cached(bool(md.options.get("html")), body)
    return {anchor: (kind, list(classes)) for anchor, kind, classes in found}


def _heading(text: str, line: Line, row: str, height: int) -> tuple[Slot, Slot]:
    match = HEADING.match(row)
    if height != 1 or not match:
        reason = "edit_ro_setext"
        return (
            Slot(line.start, line.start, readonly=reason),
            Slot(line.start, line.start, readonly=reason),
        )
    s, e = match.span("text")
    heading = Slot(line.start + s, line.start + e, mode="line")
    attrs = match.group("attrs") or ""
    found = ANCHOR.search(attrs)
    if not found:  # pragma: no cover - секцию начинает только заголовок с якорем
        return heading, Slot(line.start, line.start, readonly="edit_ro_anchor")
    offset = line.start + match.start("attrs") + found.start("id")
    return heading, Slot(offset, offset + len(found.group("id")), mode="line")


# --- поля секции -------------------------------------------------------------------


def _fields(section: Section, specs: list[dict[str, Any]]) -> dict[str, Slot | Seq]:
    out: dict[str, Slot | Seq] = {}
    for spec in specs:
        out[spec["name"]] = _place(section.region, spec, section.anchor_end, "section")
    return out


def _readonly(reason: str) -> Slot:
    return Slot(0, 0, present=False, readonly=reason)


def _place(region: Region, spec: dict[str, Any], anchor_end: int, context: str) -> Slot | Seq:
    place = spec.get("md")
    allowed = SECTION_PLACES if context == "section" else GROUP_PLACES
    if place not in allowed:
        return _readonly("edit_ro_place")
    if place == "body":
        return _body(region, anchor_end)
    if place in ("first-paragraph", "second-paragraph"):
        return _paragraph(region, anchor_end, 0 if place == "first-paragraph" else 1)
    if place == "lead":
        return _lead(region, anchor_end)
    if place == "quote":
        return _quote(region, anchor_end)
    if place in ("items", "numbered"):
        return _list(region, spec, anchor_end, numbered=place == "numbered")
    if place == "groups":
        return _groups(region, spec, anchor_end)
    if place == "pairs":
        return _pairs(region, spec, anchor_end)
    if place == "table-head":
        return _table_head(region, anchor_end)
    if place == "table-rows":
        return _table_rows(region, spec, anchor_end)
    if place == "heading":  # pragma: no cover - заголовок группы разбирает _groups
        return _readonly("edit_ro_place")
    return _readonly("edit_ro_place")


def _body(region: Region, anchor_end: int) -> Slot:
    a, b = region.trim()
    if b > a:
        start, end = region.span(a, b)
        return Slot(start, end, mode="raw")
    pos, prefix, suffix = region.empty_insert(anchor_end)
    return Slot(pos, pos, mode="raw", present=False, prefix=prefix, suffix=suffix)


def _paragraph(region: Region, anchor_end: int, number: int) -> Slot:
    chunks = region.chunks()
    if number < len(chunks):
        a, b = chunks[number]
        start, end = region.span(a, b)
        if number:
            outer = (region.lines[chunks[number - 1][1] - 1].end, end)
        elif len(chunks) > 1:
            outer = (start, region.lines[chunks[1][0]].start)
        else:
            outer = None
        return Slot(start, end, mode="para", outer=outer)
    if number and chunks:
        if number > len(chunks):
            return _readonly("edit_ro_place")
        pos, prefix, suffix = region.after(chunks[-1][1] - 1)
        return Slot(pos, pos, mode="para", present=False, prefix=prefix, suffix=suffix)
    if number:
        return _readonly("edit_ro_first_paragraph")
    pos, prefix, suffix = region.empty_insert(anchor_end)
    return Slot(pos, pos, mode="para", present=False, prefix=prefix, suffix=suffix)


def _lead(region: Region, anchor_end: int) -> Slot:
    main = region.main()
    quotes = [t.map[0] for t in region.top("blockquote_open")]  # type: ignore[index]
    stop = main if main is not None else len(region.rows)
    before_quote = min([q for q in quotes if q < stop], default=stop)
    a, b = region.trim(0, before_quote)
    if before_quote < stop:
        quote_end = max(t.map[1] for t in region.top("blockquote_open") if t.map[0] < stop)  # type: ignore[index]
        x, y = region.trim(quote_end, stop)
        if y > x:
            return _readonly("edit_ro_lead_split")
    if b > a:
        start, end = region.span(a, b)
        outer = (start, region.lines[main].start) if main is not None else None
        return Slot(start, end, mode="raw", outer=outer)
    if main is not None:
        pos = region.lines[min(before_quote, main)].start
        return Slot(pos, pos, mode="raw", present=False, suffix="\n\n")
    pos, prefix, suffix = region.empty_insert(anchor_end)
    return Slot(pos, pos, mode="raw", present=False, prefix=prefix, suffix=suffix)


def _quote(region: Region, anchor_end: int) -> Slot:
    quotes = region.top("blockquote_open")
    if quotes:
        a, b = region.trim(*quotes[0].map)  # type: ignore[misc]
        start, end = region.span(a, b)
        previous = region.trim(0, a)
        outer = (region.lines[previous[1] - 1].end, end) if previous[1] > previous[0] else None
        return Slot(start, end, mode="quote", outer=outer)
    a, b = region.trim()
    if b > a:
        pos, prefix, suffix = region.after(b - 1)
        return Slot(pos, pos, mode="quote", present=False, prefix=prefix, suffix=suffix)
    pos, prefix, suffix = region.empty_insert(anchor_end)
    return Slot(pos, pos, mode="quote", present=False, prefix=prefix, suffix=suffix)


# --- списки ------------------------------------------------------------------------


def _seps(region: Region, spans: list[tuple[int, int]]) -> list[str]:
    return [region.text[spans[i][1] : spans[i + 1][0]] for i in range(len(spans) - 1)]


def _absent_seq(region: Region, anchor_end: int, render, sep, names, kind: str) -> Seq:
    """Список, которого в секции нет: вставка после подводки или в пустую секцию."""
    main = region.main()
    a, b = region.trim()
    if main is not None:
        return Seq([], 0, 0, [], sep, render, names, readonly="edit_ro_form")
    if b > a:
        pos, prefix, suffix = region.after(b - 1)
    else:
        pos, prefix, suffix = region.empty_insert(anchor_end)
    return Seq([], pos, pos, [], sep, render, names, prefix=prefix, suffix=suffix)


def _list(region: Region, spec: dict[str, Any], anchor_end: int, numbered: bool) -> Seq:
    opener = "ordered_list_open" if numbered else "bullet_list_open"
    closer = opener.replace("_open", "_close")
    tokens = region.tokens
    found = [i for i, t in enumerate(tokens) if t.type == opener and t.level == 0 and t.map]
    names = [f["name"] for f in spec.get("fields") or []] if spec.get("fields") else None
    subs = spec.get("fields") or []
    if not found:
        render = _item_renderer(subs, None, numbered, 1, ".")
        return _absent_seq(region, anchor_end, render, "\n", names, opener)
    index = found[0]
    entries: list[Entry] = []
    spans: list[tuple[int, int]] = []
    first_marker: re.Match[str] | None = None
    numbers: list[int] = []
    readonly = None
    depth = 0
    for token in tokens[index:]:
        if token.type == opener and token.level == 0:
            depth += 1
        if token.type == closer and token.level == 0:
            break
        if token.type != "list_item_open" or token.level != 1 or not token.map:
            continue
        a, b = region.trim(*token.map)
        marker = MARKER.match(region.rows[a])
        if marker is None:
            readonly = "edit_ro_marker"
            continue
        first_marker = first_marker or marker
        if marker.group("num"):
            numbers.append(int(marker.group("num")))
        start, end = region.span(a, b)
        spans.append((start, end))
        col = marker.end()
        entries.append(_item(region, a, b, col, spec, subs))
    seps = _seps(region, spans)
    start = spans[0][0] if spans else region.lines[0].start
    end = spans[-1][1] if spans else start
    numbered_from = numbers[0] if numbers else 1
    constant = len(numbers) > 1 and len(set(numbers)) == 1
    delim = first_marker.group("delim") if first_marker and first_marker.group("delim") else "."
    bullet = first_marker.group("mark") if first_marker and not numbered else "-"
    render = _item_renderer(subs, bullet, numbered, numbered_from, delim, constant)
    sep = seps[-1] if seps else "\n"
    return Seq(entries, start, end, seps, sep, render, names, readonly=readonly)


class _Flat:
    """Строки пункта без отступа маркера, с переходом позиции в смещение исходника."""

    def __init__(self, region: Region, a: int, b: int, col: int) -> None:
        self.starts: list[int] = []
        self.rows: list[str] = []
        self.ends: list[int] = []
        for k in range(a, b):
            row = region.rows[k]
            cut = col if k == a else min(col, len(row) - len(row.lstrip(" ")))
            self.starts.append(region.lines[k].start + cut)
            self.ends.append(region.lines[k].end)
            self.rows.append(row[cut:])

    def pos(self, row: int, col: int) -> int:
        return self.starts[row] + col

    def flat_pos(self, index: int, rows: int) -> int:
        """Позиция в склейке первых `rows` строк через \\n - в смещение исходника."""
        for k in range(rows):
            if index <= len(self.rows[k]):
                return self.starts[k] + index
            index -= len(self.rows[k]) + 1
        return self.ends[rows - 1]


def _item(
    region: Region, a: int, b: int, col: int, spec: dict[str, Any], subs: list[dict[str, Any]]
) -> Entry:
    flat = _Flat(region, a, b, col)
    start, end = flat.starts[0], flat.ends[-1]
    if not subs:
        return Entry(region.lines[a].start, end, slot=Slot(start, end, mode="indent", indent=col))
    places = {sub["md"] for sub in subs}
    para = next((k for k, row in enumerate(flat.rows) if blank(row)), len(flat.rows))
    joined = "\n".join(flat.rows[:para])
    p_end = flat.ends[para - 1]
    slots: dict[str, Slot] = {}

    # жирный зачин и метка
    lead_match = BOLD.match(joined) if joined.startswith("**") else None
    bold_slot: Slot | None = None
    tag_slot: Slot | None = None
    text_from = 0
    if lead_match:
        lead = lead_match.group("lead")
        rest = joined[lead_match.end() :]
        lead_s, lead_e = lead_match.span("lead")
        stripped = lead.rstrip()
        if stripped.endswith(tuple(LEAD_END)):
            value_e = lead_s + len(stripped.rstrip(LEAD_END).rstrip())
            text_from = lead_match.end() + (len(rest) - len(rest.lstrip()))
        elif rest.lstrip(" ").startswith(tuple(LEAD_END)):
            value_e = lead_s + len(stripped)
            gap = len(rest) - len(rest.lstrip(" "))
            after_mark = rest[gap:].lstrip(LEAD_END)
            text_from = lead_match.end() + gap + (len(rest) - gap - len(after_mark))
            text_from += len(after_mark) - len(after_mark.lstrip())
        else:
            lead_match = None
        if lead_match is not None:
            value_s = lead_s + (len(lead) - len(lead.lstrip()))
            if "\n" in joined[: lead_match.end()]:
                bold_slot = Slot(0, 0, readonly="edit_ro_bold_lines")
            else:
                outer = (flat.flat_pos(0, para), flat.flat_pos(text_from, para))
                if "tag" in places:
                    tag = TAG.match(joined, value_s)
                    tag_ok = tag and tag.group("tag").strip() == tag.group("tag").strip().upper()
                    if tag_ok:
                        tag_slot = Slot(
                            flat.flat_pos(tag.start("tag"), para),
                            flat.flat_pos(tag.end("tag"), para),
                            mode="line",
                            outer=(
                                flat.flat_pos(tag.start(), para),
                                flat.flat_pos(tag.end(), para),
                            ),
                        )
                        value_s = tag.end()
                    else:
                        pos = flat.flat_pos(value_s, para)
                        tag_slot = Slot(
                            pos, pos, mode="line", present=False, prefix="[", suffix="] "
                        )
                bold_slot = Slot(
                    flat.flat_pos(value_s, para),
                    flat.flat_pos(value_e, para),
                    mode="line",
                    outer=outer,
                )
    if bold_slot is None:
        head = flat.starts[0]
        bold_slot = Slot(head, head, mode="line", present=False, prefix="**", suffix=".** ")
        if "tag" in places:
            tag_slot = Slot(head, head, mode="line", present=False, prefix="**[", suffix="].** ")
    if "bold" in places:
        slots["bold"] = bold_slot
    if "tag" in places and tag_slot is not None:
        slots["tag"] = tag_slot

    # текст после зачина
    text_s = flat.flat_pos(text_from, para) if lead_match else flat.starts[0]
    if text_s >= p_end and lead_match:
        slots["text"] = Slot(p_end, p_end, mode="para", present=False, prefix=" ", indent=col)
    else:
        slots["text"] = Slot(text_s, p_end, mode="para", indent=col)
    # продолжение пункта после первого абзаца
    more_rows = [k for k in range(para, len(flat.rows)) if not blank(flat.rows[k])]
    if more_rows:
        m_s = flat.starts[more_rows[0]]
        slots["more"] = Slot(m_s, end, mode="indent", indent=col, outer=(p_end, end))
    else:
        pad = " " * col
        slots["more"] = Slot(
            p_end, p_end, mode="indent", indent=col, present=False, prefix="\n\n" + pad
        )
    # картинка
    image = IMAGE.search(joined)
    if image:
        slots["image"] = Slot(
            flat.flat_pos(image.start("src"), para),
            flat.flat_pos(image.end("src"), para),
            mode="url",
        )
        slots["alt"] = Slot(
            flat.flat_pos(image.start("alt"), para),
            flat.flat_pos(image.end("alt"), para),
            mode="line",
        )
    else:
        slots["image"] = _readonly("edit_ro_no_image")
        slots["alt"] = _readonly("edit_ro_no_image")

    fields: dict[str, Slot | Seq] = {}
    for sub in subs:
        place = sub.get("md")
        if place not in ITEM_PLACES or place not in slots:
            fields[sub["name"]] = _readonly("edit_ro_place")
            continue
        slot = slots[place]
        if place == "text" and "bold" not in places and lead_match:
            # без поля зачина текст - весь абзац, как у сборки без пар
            slot = Slot(flat.starts[0], p_end, mode="para", indent=col)
        if place in ("text", "more") and slot.mode in ("para", "indent"):
            slot.indent = col
        fields[sub["name"]] = slot
    return Entry(region.lines[a].start, end, fields=fields)


def _item_renderer(
    subs: list[dict[str, Any]],
    bullet: str | None,
    numbered: bool,
    first: int,
    delim: str,
    constant: bool = False,
) -> Callable[[Any, int], str]:
    by_place = {sub["md"]: sub["name"] for sub in subs}

    def render(value: Any, index: int) -> str:
        marker = (
            f"{first if constant else first + index}{delim} " if numbered else f"{bullet or '-'} "
        )
        content = _item_text(value, by_place)
        pad = " " * len(marker)
        rows = content.split("\n")
        return marker + "\n".join([rows[0], *((pad + r) if r.strip() else "" for r in rows[1:])])

    return render


def _item_text(value: Any, by_place: dict[str, str]) -> str:
    if not isinstance(value, dict):
        return plain(str(value or "")).strip("\n")

    def get(place: str) -> str:
        name = by_place.get(place)
        return plain(str(value.get(name) or "")).strip() if name else ""

    if "image" in by_place:
        return f"![{get('alt')}]({get('image')})"
    tag, bold, text, more = get("tag"), get("bold"), get("text"), get("more")
    lead = f"[{tag}] {bold}".strip() if tag else bold
    if lead:
        mark = "" if lead.endswith(tuple(LEAD_END)) else "."
        head = f"**{lead}{mark}**" + (f" {text}" if text else "")
    else:
        head = text
    return head + (f"\n\n{more}" if more else "")


# --- группы ###, факты, таблицы ----------------------------------------------------


def _groups(region: Region, spec: dict[str, Any], anchor_end: int) -> Seq:
    subs = spec.get("fields") or []
    names = [f["name"] for f in subs] if subs else None
    starts = [t.map[0] for t in region.top("heading_open") if t.tag == "h3"]  # type: ignore[index]
    render = _group_renderer(subs)
    if not starts:
        return _absent_seq(region, anchor_end, render, "\n\n", names, "groups")
    entries: list[Entry] = []
    spans: list[tuple[int, int]] = []
    for position, row in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(region.rows)
        a, b = region.trim(row, stop)
        start, end = region.span(a, b)
        spans.append((start, end))
        entries.append(_group(region, row, b, subs))
    seps = _seps(region, spans)
    return Seq(
        entries, spans[0][0], spans[-1][1], seps, seps[-1] if seps else "\n\n", render, names
    )


def _group(region: Region, row: int, stop: int, subs: list[dict[str, Any]]) -> Entry:
    line = region.lines[row]
    match = HEADING.match(region.rows[row])
    inner = region.sub(row + 1, stop)
    fields: dict[str, Slot | Seq] = {}
    head_slot: Slot
    id_slot: Slot
    if match and match.group("hashes") == "###":
        s, e = match.span("text")
        head_slot = Slot(line.start + s, line.start + e, mode="line")
        attrs = match.group("attrs") or ""
        found = ANCHOR.search(attrs)
        if found:
            pos = line.start + match.start("attrs") + found.start("id")
            only = attrs.strip() == "{#" + found.group("id") + "}"
            outer = (
                (line.start + match.start("attrs"), line.start + match.end("attrs"))
                if only
                else None
            )
            id_slot = Slot(pos, pos + len(found.group("id")), mode="line", outer=outer)
        else:
            pos = line.start + e
            id_slot = Slot(pos, pos, mode="line", present=False, prefix=" {#", suffix="}")
    else:
        head_slot = Slot(0, 0, present=False, readonly="edit_ro_setext")
        id_slot = Slot(0, 0, present=False, readonly="edit_ro_setext")
    for sub in subs:
        place = sub.get("md")
        if place == "heading":
            fields[sub["name"]] = head_slot
        elif place == "heading-id":
            fields[sub["name"]] = id_slot
        elif place == "content":
            fields[sub["name"]] = _body(inner, line.end)
        elif place in GROUP_PLACES:
            fields[sub["name"]] = _place(inner, sub, line.end, "group")
        else:
            fields[sub["name"]] = _readonly("edit_ro_place")
    return Entry(line.start, region.lines[stop - 1].end, fields=fields)


def _group_renderer(subs: list[dict[str, Any]]) -> Callable[[Any, int], str]:
    by_place = {sub["md"]: sub for sub in subs}

    def render(value: Any, index: int) -> str:
        value = value if isinstance(value, dict) else {}

        def get(place: str) -> Any:
            sub = by_place.get(place)
            return value.get(sub["name"]) if sub else None

        head = f"### {plain(str(get('heading') or '')).strip()}"
        anchor = plain(str(get("heading-id") or "")).strip()
        if anchor:
            head += f" {{#{anchor}}}"
        parts = [head]
        content = get("content")
        if content:
            parts.append(plain(str(content)).strip("\n"))
        for place in ("items", "numbered"):
            sub = by_place.get(place)
            if sub and get(place):
                inner = sub.get("fields") or []
                render_item = _item_renderer(inner, "-", place == "numbered", 1, ".")
                parts.append("\n".join(render_item(item, i) for i, item in enumerate(get(place))))
        return "\n\n".join(parts)

    return render


def _pairs(region: Region, spec: dict[str, Any], anchor_end: int) -> Seq:
    subs = spec.get("fields") or []
    names = [f["name"] for f in subs] if subs else None
    by_place = {sub["md"]: sub["name"] for sub in subs}

    def render(value: Any, index: int) -> str:
        value = value if isinstance(value, dict) else {}
        key = plain(str(value.get(by_place.get("key", ""), "") or "")).strip()
        val = plain(str(value.get(by_place.get("value", ""), "") or "")).strip()
        return f"{key} | {val}"

    first = region.pairs_start()
    if first is None or region.top("bullet_list_open", "ordered_list_open", "table_open"):
        if first is None:
            return _absent_seq(region, anchor_end, render, "\n", names, "pairs")
        return Seq([], 0, 0, [], "\n", render, names, readonly="edit_ro_form")
    skip = region.code_rows() | region.quoted()
    entries: list[Entry] = []
    spans: list[tuple[int, int]] = []
    for index in range(first, len(region.rows)):
        row = region.rows[index]
        match = blocks.PAIR.match(row)
        if index in skip or not match or "|" not in row:
            continue
        line = region.lines[index]
        key = Slot(line.start + match.start("key"), line.start + match.end("key"), mode="line")
        val = Slot(line.start + match.start("value"), line.start + match.end("value"), mode="line")
        fields: dict[str, Slot | Seq] = {}
        for sub in subs:
            place = sub.get("md")
            fields[sub["name"]] = (
                key if place == "key" else val if place == "value" else _readonly("edit_ro_place")
            )
        start = line.start + (len(row) - len(row.lstrip()))
        end = line.start + len(row.rstrip())
        spans.append((start, end))
        entries.append(Entry(start, end, fields=fields))
    seps = _seps(region, spans)
    return Seq(entries, spans[0][0], spans[-1][1], seps, "\n", render, names)


def _cells(region: Region, index: int) -> list[tuple[int, int]]:
    """Ячейки строки таблицы: (начало, конец) в исходнике, без пробелов по краям."""
    row = region.rows[index]
    line = region.lines[index]
    cuts: list[int] = []
    tick = False
    escaped = False
    for pos, ch in enumerate(row):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == "`":
            tick = not tick
        elif ch == "|" and not tick:
            cuts.append(pos)
    stripped_s = len(row) - len(row.lstrip())
    stripped_e = len(row.rstrip())
    bounds = [stripped_s - 1 if not (cuts and cuts[0] == stripped_s) else stripped_s, *cuts]
    if not (cuts and cuts[-1] == stripped_e - 1):
        bounds.append(stripped_e)
    edges = sorted(set(bounds))
    out: list[tuple[int, int]] = []
    for left, right in zip(edges, edges[1:], strict=False):
        cell = row[left + 1 : right]
        lead = len(cell) - len(cell.lstrip())
        s = left + 1 + lead
        e = left + 1 + len(cell.rstrip())
        out.append((line.start + s, line.start + max(s, e)))
    return out


def _cell_seq(region: Region, index: int) -> Seq:
    cells = _cells(region, index)
    entries = [Entry(s, e, slot=Slot(s, e, mode="line")) for s, e in cells]
    seps = _seps(region, cells)

    def render(value: Any, _index: int) -> str:
        cell = plain(str(value or "")).strip()
        if "\n" in cell:
            from heron.edit.slots import EditError

            raise EditError("edit_single_line")
        return cell.replace("|", "\\|")

    start = cells[0][0] if cells else region.lines[index].start
    end = cells[-1][1] if cells else start
    return Seq(entries, start, end, seps, " | ", render)


def _table(region: Region) -> tuple[int, int] | None:
    tables = region.top("table_open")
    if not tables:
        return None
    a, b = region.trim(*tables[0].map)  # type: ignore[misc]
    return a, b


def _table_head(region: Region, anchor_end: int) -> Seq:
    found = _table(region)

    def render(value: Any, _index: int) -> str:
        return plain(str(value or "")).strip()

    if found is None:
        return Seq([], 0, 0, [], " | ", render, readonly="edit_ro_table_new")
    a, _b = found
    seq = _cell_seq(region, a)
    separator = region.lines[a + 1]
    old = len(seq.entries)

    def after(count: int) -> tuple[int, int, str] | None:
        if count == old:
            return None
        row = "|" + "|".join("---" for _ in range(count)) + "|"
        return separator.start, separator.end, row

    seq.after = after
    return seq


def _table_rows(region: Region, spec: dict[str, Any], anchor_end: int) -> Seq:
    subs = spec.get("fields") or []
    names = [f["name"] for f in subs] if subs else None
    cell_name = next((s["name"] for s in subs if s.get("md") == "cells"), None)

    def render(value: Any, _index: int) -> str:
        cells = value.get(cell_name, []) if isinstance(value, dict) and cell_name else value
        cells = [plain(str(c or "")).strip().replace("|", "\\|") for c in cells or []]
        return "| " + " | ".join(cells) + " |"

    found = _table(region)
    if found is None:
        return Seq([], 0, 0, [], "\n", render, names, readonly="edit_ro_table_new")
    a, b = found
    entries: list[Entry] = []
    spans: list[tuple[int, int]] = []
    for index in range(a + 2, b):
        line = region.lines[index]
        row = region.rows[index]
        start = line.start + (len(row) - len(row.lstrip()))
        end = line.start + len(row.rstrip())
        spans.append((start, end))
        fields: dict[str, Slot | Seq] = {}
        for sub in subs:
            fields[sub["name"]] = (
                _cell_seq(region, index) if sub.get("md") == "cells" else _readonly("edit_ro_place")
            )
        entries.append(Entry(start, end, fields=fields))
    if not entries:
        pos = region.lines[a + 1].end
        return Seq([], pos, pos, [], "\n", render, names, prefix="\n")
    seps = _seps(region, spans)
    return Seq(entries, spans[0][0], spans[-1][1], seps, "\n", render, names)


def place(section: Section, spec: dict[str, Any]) -> Slot | Seq:
    """Место поля `spec` в секции - для поля формы, которой у секции ещё нет."""
    return _place(section.region, spec, section.anchor_end, "section")
