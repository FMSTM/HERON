"""Страница как набор полей: чтение, правка одного поля, запись без потерь.

`Page` держит исходный текст файла и знает, где в нём лежит каждое поле.
Правка поля заменяет только его символы и возвращает новую страницу; всё, чего
модель не понимает (комментарии, ручная разметка, порядок ключей и секций,
`\\r\\n`, BOM, отсутствие перевода строки в конце), остаётся на месте. Без
правок `dump(load(текст)) == текст` - байт в байт.

Список полей (`fields`) один для консоли, студии и агента: служебные поля
движка (`heron/contracts/fields.py`) по группам, затем разметка schema.org типа,
затем секции типа по порядку `uses` с полями их блоков из контракта темы.
Контракт - объект `heron describe` (`heron.core.describe.contract`).

Спецификация: docs/ru/spec/21-engine.md, «Модель правки страницы».
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any

from markdown_it import MarkdownIt

from heron.core.parser import markdown
from heron.edit import body as bodies
from heron.edit import front as fronts
from heron.edit.slots import EditError, Entry, Seq, Slot, entry_value, node_value
from heron.edit.text import lines_of, newline_of, plain
from heron.messages import Msg, say

DEFAULT_TYPE = "page"
HOME_TYPE = "home"
INDEX = "_index.md"
# Поле блока, когда тема полей не описала: секция - свободный markdown.
BODY_SPEC: dict[str, Any] = {
    "name": "text",
    "type": "markdown",
    "required": False,
    "md": "body",
    "fields": None,
    "item": None,
}
LIMITS = (
    "min_length",
    "max_length",
    "min_items",
    "max_items",
    "ratio",
    "min_width",
    "values",
    "ref",
    "schemaorg",
    "item",
)


@dataclass(frozen=True, slots=True)
class Page:
    """Файл страницы и его разбор. Меняется только через `set` - получается новая страница."""

    text: str
    contract: dict[str, Any]
    rel: str | None
    type: str
    front: fronts.Front
    body: bodies.Body
    nl: str
    default_type: str
    # правки за пределами файла страницы (меню - в site.yaml): путь → значение
    site: dict[str, Any] = field(default_factory=dict)
    allow_raw_html: bool = False

    @property
    def category(self) -> bool:
        """Страница категории: `_index.md` папки."""
        return bool(self.rel) and PurePosixPath(self.rel or "").name == INDEX

    @property
    def lang(self) -> str | None:
        parts = PurePosixPath(self.rel or "").parts
        return parts[1] if len(parts) > 2 and parts[0] == "content" else None

    @property
    def key(self) -> str | None:
        """Ключ страницы - путь от папки языка без `.md` (как у сборки)."""
        parts = list(PurePosixPath(self.rel or "").parts)
        if len(parts) < 3 or parts[0] != "content":
            return None
        inner = parts[2:]
        name = inner.pop()
        if name == INDEX:
            return "/".join(inner)
        if name == "index.md" and not inner:
            return ""
        return "/".join([*inner, name[: -len(".md")] if name.endswith(".md") else name])


@dataclass(slots=True)
class Field:
    """Поле страницы для опросника и студии: значение, умолчание, подсказки, ограничения.

    `path` - адрес поля для `get`/`set`: `title`, `schema.Service`,
    `sections.faq.heading`, `sections.faq.items`. Пункт списка - `….items.0.q`.
    `editable` ложно - значение показывается, но записать его без потерь
    нельзя (`readonly` - почему, текст на языке опросника).
    """

    path: str
    name: str
    type: str
    group: str
    value: Any
    default: Any = None
    default_from: str | None = None
    present: bool = True
    editable: bool = True
    readonly: str | None = None
    required: bool = False
    hint: str | None = None
    help: str | None = None
    example: str | None = None
    where: str = "frontmatter"
    md: str | None = None
    section: str | None = None
    kind: str | None = None
    module: str | None = None
    limits: dict[str, Any] = field(default_factory=dict)
    fields: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {name: getattr(self, name) for name in self.__slots__}  # type: ignore[attr-defined]
        out["value"] = _jsonable(self.value)
        out["default"] = _jsonable(self.default)
        return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


# --- чтение ------------------------------------------------------------------------


def load(
    source: str | bytes | Path,
    contract: dict[str, Any],
    *,
    rel: str | None = None,
    page_type: str | None = None,
    allow_raw_html: bool = False,
) -> Page:
    """Страница из текста, байтов или файла. `rel` - путь от корня сайта: `content/ru/about.md`.

    `page_type` - тип, который странице даёт папка (`children_type` категории);
    не задан - `type` из SEO-блока, иначе по имени файла (главная, 404), иначе `page`.
    """
    if isinstance(source, Path):
        source = source.read_bytes()
    if isinstance(source, bytes):
        try:
            source = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EditError("edit_not_utf8") from exc
    return _parse(source, contract, rel, page_type, {}, allow_raw_html)


def _parse(
    text: str,
    contract: dict[str, Any],
    rel: str | None,
    page_type: str | None,
    site: dict[str, Any],
    allow_raw_html: bool,
) -> Page:
    front = fronts.read(text)
    default = page_type or _type_by_name(rel)
    declared = front.data.get("type")
    kind = str(declared) if declared not in (None, "") else default
    md = _md(allow_raw_html)
    types = {item["name"]: item for item in contract.get("types", [])}
    body = bodies.parse(text, front.body, md, _specs_for(contract, types.get(kind)))
    return Page(
        text=text,
        contract=contract,
        rel=rel,
        type=kind,
        front=front,
        body=body,
        nl=newline_of(text),
        default_type=default,
        site=dict(site),
        allow_raw_html=allow_raw_html,
    )


_MD: dict[bool, MarkdownIt] = {}


def _md(allow_raw_html: bool) -> MarkdownIt:
    if allow_raw_html not in _MD:
        _MD[allow_raw_html] = markdown.make(allow_raw_html=allow_raw_html)
    return _MD[allow_raw_html]


def _type_by_name(rel: str | None) -> str:
    parts = PurePosixPath(rel or "").parts
    if len(parts) == 3 and parts[0] == "content":
        if parts[2] == "index.md":
            return HOME_TYPE
        if parts[2] == "404.md":
            return "404"
    return DEFAULT_TYPE


def _modules_by_kind(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for module in contract.get("modules", []):
        for kind in module.get("kinds", []):
            out.setdefault(kind["kind"], module)
    return out


def _specs_for(contract: dict[str, Any], type_info: dict[str, Any] | None):
    by_kind = _modules_by_kind(contract)
    sections = {s["id"]: s for s in (type_info or {}).get("sections", [])}

    def specs(section_id: str, kind: str | None) -> tuple[str | None, list[dict[str, Any]] | None]:
        own = sections.get(section_id)
        if own and own.get("fields") is not None:
            return own.get("module"), own["fields"]
        if kind is None and own:
            kind = own.get("kind")  # пустая секция: форма, которую ждёт тема (`how:steps`)
        module = by_kind.get(kind or "")
        if module is None:
            return None, [BODY_SPEC]
        if module.get("fields") is None:
            return module["name"], [BODY_SPEC]
        return module["name"], module["fields"]

    return specs


def reload(page: Page, text: str) -> Page:
    return _parse(text, page.contract, page.rel, page.default_type, page.site, page.allow_raw_html)


def dump(page: Page) -> str:
    """Текст страницы. Записывать - в UTF-8 (`save`)."""
    return page.text


def save(page: Page, path: Path) -> None:
    path.write_bytes(page.text.encode("utf-8"))


# --- список полей ------------------------------------------------------------------


def _lang(page: Page, lang: str | None) -> str:
    return lang or page.contract.get("lang") or "en"


def fields(page: Page) -> list[Field]:
    """Все поля страницы по порядку показа: служебные, schema.org, секции и блоки."""
    out: list[Field] = []
    out.extend(_service_fields(page))
    out.extend(_schema_fields(page))
    for section_id, info, section in _section_order(page):
        out.extend(_section_fields(page, section_id, info, section))
    return out


def groups(page: Page) -> list[dict[str, str]]:
    """Группы полей по порядку показа с заголовками на языке контракта (и `schema`)."""
    lang = _lang(page, None)
    out = [dict(group) for group in page.contract.get("groups", [])]
    names = [group["name"] for group in out]
    at = names.index("section") if "section" in names else len(out)
    out.insert(at, {"name": "schema", "title": say(lang, "edit_group_schema")})
    return out


def _front_readonly(page: Page) -> str | None:
    return say(_lang(page, None), "edit_ro_front") if page.front.error else None


def _service_fields(page: Page) -> list[Field]:
    out: list[Field] = []
    lang = _lang(page, None)
    data = page.front.data
    for item in page.contract.get("service", {}).get("page", []):
        name = item["name"]
        if item.get("only") == "category" and not page.category:
            continue
        where = item.get("where", "frontmatter")
        present, value = (
            fronts.lookup(page.front, [item["key"]]) if where == "frontmatter" else (True, None)
        )
        readonly = _front_readonly(page, [item["key"]]) if where == "frontmatter" else None
        default = item.get("default")
        if where == "path":
            value = _category_of(page)
            readonly = say(lang, "edit_ro_path")
        elif where == "site.yaml":
            value = _in_menu(page)
            present = True
            if page.key is None:
                readonly = say(lang, "edit_no_key")
        default = _service_default(page, name, default, data)
        out.append(
            Field(
                path=name,
                name=name,
                type=item["type"],
                group=item["group"],
                value=value,
                default=default,
                default_from=item.get("default_from"),
                present=present,
                editable=readonly is None,
                readonly=readonly,
                required=bool(item.get("required")),
                hint=item.get("hint"),
                help=item.get("help"),
                where=where,
                limits={k: item.get(k) for k in LIMITS if item.get(k) not in (None, [])},
            )
        )
        if name == "children_type" or (name == "type" and not page.category):
            out.extend(_view_field(page, after=name))
    return out


def _view_field(page: Page, after: str) -> list[Field]:
    """Вид отображения категории - ключ из `views` типа (только категория и главная)."""
    if not (page.category or page.key == "") or after != (
        "children_type" if page.category else "type"
    ):
        return []
    info = _type_info(page)
    views = (info or {}).get("views")
    if not views:
        return []
    key = views["key"]
    present, value = fronts.lookup(page.front, [key])
    readonly = _front_readonly(page, [key])
    return [
        Field(
            path=key,
            name=key,
            type="enum",
            group="address",
            value=value,
            default=views.get("default"),
            present=present,
            editable=readonly is None,
            readonly=readonly,
            hint=views.get("hint"),
            help=views.get("help"),
            limits={"values": [option["name"] for option in views.get("options", [])]},
            fields=[
                {"name": o["name"], "hint": o.get("hint"), "help": o.get("help")}
                for o in views.get("options", [])
            ],
        )
    ]


def _type_info(page: Page) -> dict[str, Any] | None:
    return next((t for t in page.contract.get("types", []) if t["name"] == page.type), None)


def _service_default(page: Page, name: str, default: Any, data: dict[str, Any]) -> Any:
    """Что будет, если поле не заполнить: конкретное значение, где его можно знать."""
    stem = PurePosixPath(page.rel or "").name
    if name == "slug":
        if page.category:
            return PurePosixPath(page.rel or "").parent.name or None
        return None if stem in ("index.md", "") else stem[: -len(".md")]
    if name == "type":
        return page.default_type
    if name == "nav_title":
        return data.get("h1")
    if name == "og_title":
        return data.get("title")
    if name == "og_description":
        return data.get("description")
    if name == "og_image":
        return data.get("image") or default
    return default


def _category_of(page: Page) -> str | None:
    parts = list(PurePosixPath(page.rel or "").parts)
    if len(parts) < 3 or parts[0] != "content":
        return None
    inner = parts[2:-1]
    if page.category:
        inner = inner[:-1]
    return "/".join(inner) or None


def _in_menu(page: Page) -> bool:
    if "nav.main" in page.site:
        menu = page.site["nav.main"]
    else:
        menu = (page.contract.get("site") or {}).get("menu") or []
    return page.key is not None and _menu_item(page.key) in [_menu_norm(m) for m in menu]


def _menu_item(key: str) -> str:
    return "/" if key == "" else key


def _menu_norm(item: str) -> str:
    item = str(item).strip()
    return "/" if item.strip("/") == "" else item.strip("/")


def _schema_kinds(page: Page) -> list[str]:
    info = _type_info(page) or {}
    kinds = list(info.get("jsonld", []))
    own = page.front.data.get("schema")
    if isinstance(own, dict):
        kinds += [k for k in own if k not in kinds and k != "entity"]
    return kinds


def _schema_fields(page: Page) -> list[Field]:
    lang = _lang(page, None)
    own = page.front.data.get("schema")
    own = own if isinstance(own, dict) else {}
    readonly = _front_readonly(page)
    out = []
    for kind in _schema_kinds(page):
        value = own.get(kind)
        readonly = _front_readonly(page, ["schema", kind])
        out.append(
            Field(
                path=f"schema.{kind}",
                name=kind,
                type="schema",
                group="schema",
                value=value if isinstance(value, dict) else {},
                present=kind in own,
                editable=readonly is None,
                readonly=readonly,
                hint=say(lang, "edit_schema_hint", kind=kind),
                help=say(lang, "edit_schema_help", kind=kind),
                limits={"schemaorg": kind},
            )
        )
    return out


def _section_order(page: Page):
    """(id, описание секции в типе, секция в файле) в порядке показа."""
    info = _type_info(page)
    present = {s.id: s for s in page.body.sections if s.id != "intro" or s.present}
    listed = [s for s in (info or {}).get("sections", [])]
    known = {s["id"] for s in listed if not s.get("any")}
    order: list[tuple[str, dict[str, Any] | None, bodies.Section | None]] = []
    used: set[str] = set()
    star = next((s for s in listed if s.get("any")), None)
    for spec in listed:
        if spec.get("any"):
            for section in page.body.sections:
                if section.id not in known and section.id in present and section.id not in used:
                    order.append((section.id, star, section))
                    used.add(section.id)
            continue
        section = page.body.get(spec["id"])
        if spec["id"] == "intro" and section is not None:
            order.append(("intro", spec, section))
        else:
            order.append((spec["id"], spec, present.get(spec["id"])))
        used.add(spec["id"])
    for section in page.body.sections:
        if section.id not in used and section.id in present:
            order.append((section.id, None, section))
    return order


def _hints(item: dict[str, Any] | None) -> dict[str, Any]:
    item = item or {}
    return {"hint": item.get("hint"), "help": item.get("help"), "example": item.get("example")}


def _section_fields(
    page: Page, section_id: str, info: dict[str, Any] | None, section: bodies.Section | None
) -> list[Field]:
    lang = _lang(page, None)
    exists = section is not None and (section.id != "intro" or section.present)
    base = f"sections.{section_id}"
    kind = section.kind if section else (info or {}).get("kind")
    module = section.module if section else (info or {}).get("module")
    common = {"group": "section", "section": section_id, "kind": kind, "module": module}
    out: list[Field] = []
    body_error = page.body.error
    ro = say(lang, "edit_ro_body", reason=body_error) if body_error is not None else None
    if section_id != "intro":
        for item in page.contract.get("service", {}).get("section", []):
            slot = None
            if section is not None:
                slot = section.heading if item["name"] == "heading" else section.anchor
            value = slot.read(page.text) if slot is not None else ""
            reason = ro or (_reason(lang, slot.readonly) if slot and slot.readonly else None)
            if item["name"] == "anchor" and not exists:
                value = section_id
            out.append(
                Field(
                    path=f"{base}.{item['name']}",
                    name=item["name"],
                    type=item["type"],
                    value=value,
                    present=exists,
                    editable=reason is None,
                    readonly=reason,
                    required=bool(item.get("required")),
                    hint=item.get("hint"),
                    help=item.get("help"),
                    where="heading",
                    **common,
                )
            )
    if section is not None and section.specs is not None:
        specs = section.specs
    else:
        _module, specs = _specs_for(page.contract, _type_info(page))(section_id, kind)
        specs = specs or [BODY_SPEC]
    section_hints = _hints(info)
    for spec in specs:
        node = section.fields.get(spec["name"]) if section is not None else None
        value: Any = (
            node_value(page.text, node)
            if node is not None
            else ([] if spec["type"] == "list" else "")
        )
        reason = ro or (
            _reason(lang, node.readonly) if node is not None and node.readonly else None
        )
        hints = _hints(spec)
        if spec is BODY_SPEC:
            hints = section_hints
        out.append(
            Field(
                path=f"{base}.{spec['name']}",
                name=spec["name"],
                type=spec["type"],
                value=value,
                present=bool(node is not None and node.present),
                editable=reason is None,
                readonly=reason,
                # обязательность поля блока - когда сам блок на странице есть
                required=bool(spec.get("required"))
                if spec is not BODY_SPEC
                else bool(info and info.get("required")),
                where="body",
                md=spec.get("md"),
                limits={k: spec.get(k) for k in LIMITS if spec.get(k) not in (None, [])},
                fields=spec.get("fields"),
                **hints,
                **common,
            )
        )
    return out


def _reason(lang: str, key: str) -> str:
    return say(lang, key)


# --- чтение и запись по пути -------------------------------------------------------


def get(page: Page, path: str) -> Any:
    """Значение поля по пути, как его показывает `fields`."""
    for item in fields(page):
        if item.path == path:
            return item.value
    parts = path.split(".")
    if parts[0] == "sections" and len(parts) > 3:
        node, rest = _node(page, parts)
        return _value_at(page.text, node, rest)
    found, value = fronts.lookup(page.front, parts)
    return value if found else None


def span(page: Page, path: str) -> tuple[int, int] | None:
    """Где в тексте лежит значение поля: (начало, конец); пустое место - (вставка, вставка).

    Нужен, чтобы показать поле в исходнике (студия подсвечивает его рядом с формой).
    """
    parts = path.split(".")
    if parts[0] == "sections":
        try:
            node, rest = _node(page, parts)
            for part in rest:
                if isinstance(node, Seq):
                    node = node.entries[_index(part, len(node.entries) - 1)]
                elif isinstance(node, Entry):
                    node = node.fields[part]
        except (EditError, KeyError):
            return None
        if isinstance(node, Entry):
            return node.start, node.end
        if node.readonly:
            return None
        if not node.present:
            return node.start, node.start
        return node.start, node.end
    return fronts.span(page.front, parts)


def _value_at(text: str, node: Any, rest: list[str]) -> Any:
    for part in rest:
        if isinstance(node, Seq):
            node = node.entries[_index(part, len(node.entries) - 1)]
        elif isinstance(node, Entry):
            node = node.fields.get(part)
            if node is None:
                raise EditError("edit_unknown_field", path=part)
        else:
            raise EditError("edit_unknown_field", path=part)
    if isinstance(node, Entry):
        return entry_value(text, node)
    return node_value(text, node)


def _index(part: str, top: int) -> int:
    if not part.isdigit() or int(part) > top:
        raise EditError("edit_bad_index", index=part)
    return int(part)


def set_field(page: Page, path: str, value: Any) -> Page:
    """Записать значение поля. Пусто (`None`, `""`, `[]`) - поле убирается.

    Возвращает новую страницу; исходная не меняется. Значение, которое не
    записать на его место (перевод строки в заголовке, поле только для чтения),
    - `EditError`.
    """
    parts = path.split(".")
    if not parts or not all(parts):
        raise EditError("edit_unknown_field", path=path)
    if parts[0] == "sections":
        return _set_section(page, parts, value)
    if parts[0] == "menu" and len(parts) == 1:
        return _set_menu(page, bool(_flag(value)))
    if parts[0] == "category" and len(parts) == 1:
        raise EditError("edit_readonly", reason=Msg("edit_ro_path"))
    service = {item["name"]: item for item in page.contract.get("service", {}).get("page", [])}
    if parts[0] in service and len(parts) == 1:
        value = _coerce(service[parts[0]]["type"], value)
        parts = [service[parts[0]]["key"]]
    elif parts[0] in own and len(parts) == 1:
        value = _coerce(own[parts[0]]["type"], value)
    parts, value = _list_index(page, parts, value)
    found, current = fronts.lookup(page.front, parts)
    if found and _same_value(current, value):
        return page
    if _empty(value):
        try:
            edit = fronts.unset(page.text, page.front, parts, page.nl)
        except fronts.FrontError as exc:
            raise EditError(str(exc.args[0])) from exc
        return _apply(page, [edit] if edit else [])
    try:
        edit = fronts.set_value(page.text, page.front, parts, value, page.nl)
    except fronts.FrontError as exc:
        raise EditError(str(exc.args[0])) from exc
    return _apply(page, [edit])


def _list_index(page: Page, parts: list[str], value: Any) -> tuple[list[str], Any]:
    """`redirect_from.1` - пункт списка SEO-блока: записать список целиком с этим пунктом."""
    for depth, part in enumerate(parts):
        if not part.isdigit() or depth == 0:
            continue
        found, current = fronts.lookup(page.front, parts[:depth])
        if not found or not isinstance(current, list) or depth != len(parts) - 1:
            raise EditError("edit_unknown_field", path=".".join(parts))
        items = list(current)
        index = _index(part, len(items))
        if index == len(items):
            items.append(value)
        elif _empty(value):
            items.pop(index)
        else:
            items[index] = value
        return parts[:depth], items
    return parts, value


def _same_value(current: Any, value: Any) -> bool:
    if _empty(current) and _empty(value):
        return True
    if isinstance(current, bool) or isinstance(value, bool):
        return current is value
    if isinstance(current, dt.date) and isinstance(value, str):
        return current.isoformat() == value.strip()
    if isinstance(current, int | float) and isinstance(value, str):
        return str(current) == value.strip()
    return current == value


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "on")
    return bool(value)


def _coerce(kind: str, value: Any) -> Any:
    """Строка из консоли - в значение своего типа: `true`, `10`, `2026-03-14`."""
    if not isinstance(value, str) or value == "":
        return value
    if kind == "flag":
        return _flag(value)
    if kind == "number":
        try:
            return int(value)
        except ValueError:
            return value
    if kind == "date":
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return value
    if kind == "list":
        return [line.strip() for line in plain(value).split("\n") if line.strip()]
    return value


def _apply(page: Page, edits: list[tuple[int, int, str]]) -> Page:
    edits = [e for e in edits if e is not None]
    if not edits:
        return page
    text = page.text
    for start, end, new in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + new + text[end:]
    return reload(page, text)


def _set_menu(page: Page, on: bool) -> Page:
    if page.key is None:
        if not on:
            return page
        raise EditError("edit_no_key")
    menu = list(page.site.get("nav.main", (page.contract.get("site") or {}).get("menu") or []))
    item = _menu_item(page.key)
    has = item in [_menu_norm(m) for m in menu]
    if on and not has:
        menu.append(item)
    elif not on and has:
        menu = [m for m in menu if _menu_norm(m) != item]
    else:
        return page
    return replace(page, site={**page.site, "nav.main": menu})


def site_changes(page: Page) -> dict[str, Any]:
    """Правки site.yaml, которые накопила страница: путь в site.yaml → новое значение."""
    return dict(page.site)


def _node(page: Page, parts: list[str]) -> tuple[Any, list[str]]:
    if page.body.error is not None:
        raise EditError("edit_readonly", reason=Msg("edit_ro_body", reason=page.body.error))
    if len(parts) < 3:
        raise EditError("edit_unknown_field", path=".".join(parts))
    section = page.body.get(parts[1])
    if section is None:
        raise EditError("edit_no_section", section=parts[1])
    name = parts[2]
    if name in ("heading", "anchor") and parts[1] != "intro":
        node: Any = section.heading if name == "heading" else section.anchor
    elif name in section.fields:
        node = section.fields[name]
    else:
        raise EditError("edit_unknown_field", path=".".join(parts))
    return node, parts[3:]


def _set_section(page: Page, parts: list[str], value: Any) -> Page:
    if len(parts) < 3:
        raise EditError("edit_unknown_field", path=".".join(parts))
    if page.body.get(parts[1]) is None:
        if parts[2] == "anchor":
            raise EditError("edit_no_section", section=parts[1])
        page = add_section(page, parts[1], heading=value if parts[2] == "heading" else None)
        if parts[2] == "heading":
            return page
    node, rest = _node(page, parts)
    if parts[2] == "anchor" and not rest:
        value = str(value or "").strip()
        if not bodies.sections.SECTION_ID.match(value):
            raise EditError("edit_bad_anchor", anchor=value)
        if value != parts[1] and page.body.get(value) is not None:
            raise EditError("edit_section_exists", section=value)
    if parts[2] == "heading" and not rest and not str(value or "").strip():
        raise EditError("edit_heading_empty")
    # спуститься к пункту списка; путь кончается на пункте - заменить пункт целиком
    for index, part in enumerate(rest):
        if isinstance(node, Seq):
            top = len(node.entries) if index == len(rest) - 1 else len(node.entries) - 1
            position = _index(part, top)
            if index == len(rest) - 1:
                items = [entry_value(page.text, e) for e in node.entries]
                if position == len(items):
                    items.append(value)
                elif _empty(value):
                    items.pop(position)
                else:
                    items[position] = value
                return _write(page, node, items)
            node = node.entries[position]
        elif isinstance(node, Entry):
            if part not in node.fields:
                raise EditError("edit_unknown_field", path=part)
            node = node.fields[part]
        else:
            raise EditError("edit_unknown_field", path=part)
    if isinstance(node, Entry):  # pragma: no cover - путь на пункт обработан выше
        raise EditError("edit_unknown_field", path=".".join(parts))
    return _write(page, node, value)


def _write(page: Page, node: Slot | Seq, value: Any) -> Page:
    if isinstance(node, Seq):
        if isinstance(value, str):
            value = [line for line in plain(value).split("\n") if line.strip()]
        edit = node.write(page.text, value, page.nl)
        edits = [edit] if edit else []
        if edit and node.after is not None:
            extra = node.after(len(value or []))
            if extra:
                edits.append(extra)
        return _apply(page, edits)
    edit = node.write(page.text, value, page.nl)
    return _apply(page, [edit] if edit else [])


# --- секции целиком ----------------------------------------------------------------


def _class_for(page: Page, kind: str | None) -> str | None:
    """Класс якоря, без которого форма не узнаётся: `.tabs`, `.gallery`, `.timeline`."""
    for module in page.contract.get("modules", []):
        for item in module.get("kinds", []):
            if item["kind"] == kind and not item.get("auto"):
                return item.get("class")
    return None


def add_section(
    page: Page,
    anchor: str,
    heading: str | None = None,
    kind: str | None = None,
    after: str | None = None,
    values: dict[str, Any] | None = None,
) -> Page:
    """Добавить секцию `## Заголовок {#якорь}`: по порядку `uses` типа или после `after`.

    Форма из `uses` (`how:steps`) или `kind`; форма, которую движок узнаёт только
    по классу, получает класс в якоре. Вводный блок (`intro`) - не секция:
    он есть всегда, его поля пишутся напрямую.

    `values` - поля блока этой формы (`{"items": [...]}`): пустую секцию без
    класса по содержимому не узнать, поэтому её поля записываются сразу.
    """
    if anchor == "intro":
        return page
    if not bodies.sections.SECTION_ID.match(anchor):
        raise EditError("edit_bad_anchor", anchor=anchor)
    if page.body.error is not None:
        raise EditError("edit_readonly", reason=Msg("edit_ro_body", reason=page.body.error))
    if page.body.get(anchor) is not None:
        raise EditError("edit_section_exists", section=anchor)
    info = _type_info(page) or {}
    listed = {s["id"]: s for s in info.get("sections", [])}
    kind = kind or (listed.get(anchor) or {}).get("kind")
    title = plain(str(heading or "")).strip() or anchor.replace("-", " ").capitalize()
    if "\n" in title:
        raise EditError("edit_single_line")
    css = _class_for(page, kind)
    line = f"## {title} {{#{anchor}{' .' + css if css else ''}}}"
    page = _insert_section(page, anchor, line, info, after)
    if values:
        page = _fill(page, anchor, kind, values)
    return page


def _fill(page: Page, anchor: str, kind: str | None, values: dict[str, Any]) -> Page:
    """Записать поля новой секции формы `kind`: сначала основной узел, потом остальное."""
    module = _modules_by_kind(page.contract).get(kind or "")
    specs = (module or {}).get("fields") or [BODY_SPEC]
    first = sorted(specs, key=lambda spec: spec["type"] != "list")
    for spec in first:
        if spec["name"] not in values:
            continue
        section = page.body.get(anchor)
        assert section is not None
        node = section.fields.get(spec["name"])
        if node is None:
            node = bodies.place(section, spec)
        page = _write(page, node, values[spec["name"]])
    return page


def _insert_section(
    page: Page, anchor: str, line: str, info: dict[str, Any], after: str | None
) -> Page:
    nl = page.nl
    present = [s for s in page.body.sections if s.id != "intro" or s.present]
    target: bodies.Section | None = None
    if after is not None:
        target = page.body.get(after)
        if target is None:
            raise EditError("edit_no_section", section=after)
    else:
        order = [s["id"] for s in info.get("sections", []) if not s.get("any")]
        if anchor in order:
            later = order[order.index(anchor) + 1 :]
            following = next(
                (page.body.get(i) for i in later if page.body.get(i) and i != "intro"), None
            )
            if following is not None:
                pos = following.start
                return _apply(page, [(pos, pos, line + nl + nl)])
        target = present[-1] if present else None
    if target is None:
        return _append(page, line)
    pos = _content_end(page, target)
    return _apply(page, [(pos, pos, nl + nl + line)])


def _tail(text: str, nl: str, body: int) -> str:
    """Что дописать перед новой строкой в конце файла: перевод строки и пустую строку."""
    if len(text) == body:
        return "" if text.endswith(("\n", "\r")) or not text else nl
    stripped = text.rstrip("\r\n")
    ends = text[len(stripped) :]
    count = ends.count("\n") or ends.count("\r")
    return nl * max(0, 2 - count)


def _append(page: Page, line: str) -> Page:
    text = page.text
    closing = page.nl if text.endswith(("\n", "\r")) or len(text) == page.front.body else ""
    head = _tail(text, page.nl, page.front.body)
    return _apply(page, [(len(text), len(text), head + line + closing)])


def _content_end(page: Page, section: bodies.Section) -> int:
    a, b = section.region.trim()
    if b > a:
        return section.region.lines[b - 1].end
    if section.heading is not None and section.head is not None:
        end = page.text.find("\n", section.head)
        end = len(page.text) if end < 0 else end
        return end - 1 if end > 0 and page.text[end - 1] == "\r" else end
    return section.start


def remove_section(page: Page, anchor: str) -> Page:
    """Убрать секцию вместе с заголовком; соседние секции и их отступы не трогаются."""
    section = page.body.get(anchor)
    if section is None or anchor == "intro":
        raise EditError("edit_no_section", section=anchor)
    end = _content_end(page, section)
    before = [
        line
        for line in lines_of(page.text, page.front.body, section.start)
        if page.text[line.start : line.end].strip()
    ]
    start = before[-1].end if before else section.start
    if start == section.start:
        # секция первая в теле: убрать и пустые строки после неё
        rest = page.text[end:]
        end += len(rest) - len(rest.lstrip("\r\n"))
    return _apply(page, [(start, end, "")])
