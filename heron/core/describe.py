"""`heron describe`: контракт темы и служебные поля сайта одним объектом.

Тот же объект читают человек (текстом), агент (`--json`), опросник и студия:
типы страниц и их секции по порядку, поля каждого блока с местом в markdown,
виды категорий, подсказки на выбранном языке и значения по умолчанию из
`site.yaml`. Отдельного «API для редактора» нет - есть это описание.

Форма JSON - `describe.schema.json` (`heron schema --describe`).
Спецификация: docs/ru/spec/21-engine.md, «Контракт темы» и §10 «heron describe».
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import heron
from heron.contracts import fields as service
from heron.contracts.site import SiteConfig, load_site
from heron.contracts.theme import (
    ANY,
    MD_PLACES,
    USES_RE,
    FieldSpec,
    Hinted,
    ThemeConfig,
    kinds_of,
    load_theme,
)
from heron.core import resolver
from heron.core.errors import HeronError
from heron.core.parser.blocks import AUTO_ORDER, BY_CLASS
from heron.core.tree import DEFAULT_TYPE
from heron.messages import Msg, say

SCHEMA_URL = "describe.schema.json"

# Класс в якоре, которым форма задаётся явно: {#warning .alert}.
CLASS_OF = {kind: cls for cls, kind in BY_CLASS.items()}
# Формы, которые движок узнаёт по содержимому, без класса.
AUTO = frozenset(
    {kind for kind in AUTO_ORDER if kind != "groups"} | {"checklist", "two-lists", "prose"}
)


def _text(item: Hinted | None, key: str, lang: str) -> str | None:
    """Текст на языке `lang`; нет - без суффикса, затем en, затем любой."""
    if item is None:
        return None
    found = item.text(key, lang) or item.text(key, "en")
    if found:
        return found
    by_lang = item.i18n.get(key, {})
    return next((by_lang[code] for code in sorted(by_lang) if by_lang[code]), None)


def _hints(item: Hinted | None, lang: str, example: bool = False) -> dict[str, Any]:
    out = {"hint": _text(item, "hint", lang), "help": _text(item, "help", lang)}
    if example:
        out["example"] = _text(item, "example", lang)
    return out


def field(spec: FieldSpec, lang: str) -> dict[str, Any]:
    """Поле блока: все ключи есть всегда, отсутствующее - null или пустой список."""
    return {
        "name": spec.name,
        "type": spec.type,
        "required": spec.required,
        "md": spec.md,
        "min_length": spec.min_length,
        "max_length": spec.max_length,
        "min_items": spec.min_items,
        "max_items": spec.max_items,
        "ratio": spec.ratio,
        "min_width": spec.min_width,
        "values": list(spec.values),
        "ref": spec.ref,
        "schemaorg": spec.schemaorg,
        "item": spec.item,
        "fields": None if spec.fields is None else [field(f, lang) for f in spec.fields],
        **_hints(spec, lang, example=True),
    }


def _fields(specs: list[FieldSpec] | None, lang: str) -> list[dict[str, Any]] | None:
    return None if specs is None else [field(spec, lang) for spec in specs]


def _site(config: SiteConfig | None, lang: str) -> dict[str, Any] | None:
    if config is None:
        return None
    languages = list(config.site.languages)
    view = config.for_lang(lang if lang in languages else config.site.default_lang)
    return {
        "name": view.site.name,
        "languages": languages,
        "default_lang": config.site.default_lang,
        "title_suffix": view.seo.title_suffix,
        "og_default_image": view.seo.og_default_image,
        "menu": list(config.nav.main),
        "updated_from": config.build.updated_from,
    }


def _service(theme: ThemeConfig, config: SiteConfig | None, lang: str, scope: str) -> list:
    types = list(theme.types)
    site = _site(config, lang) or {}
    out = []
    for spec in service.of_scope(scope):
        default = spec.default
        if spec.name == "og_image":
            default = site.get("og_default_image")
        elif spec.name == "type":
            default = DEFAULT_TYPE if DEFAULT_TYPE in theme.types else None
        min_width = theme.images.cover_width if spec.type == "image" else None
        out.append(
            {
                "name": spec.name,
                "type": spec.type,
                "group": spec.group,
                "scope": spec.scope,
                "where": spec.where,
                "key": spec.key,
                "required": spec.required,
                "max_length": spec.max_length,
                "min_width": min_width,
                "item": spec.item,
                "values": types if spec.name in ("type", "children_type") else [],
                "only": spec.only,
                "default": default,
                "default_from": spec.default_from,
                "hint": spec.hint(lang),
                "help": spec.help(lang),
            }
        )
    return out


def _views(theme: ThemeConfig, name: str, lang: str) -> dict[str, Any] | None:
    views = theme.types[name].views
    if views is None:
        return None
    return {
        "key": views.key,
        "default": views.default,
        **_hints(views, lang),
        "options": [
            {"name": view, **_hints(option, lang)} for view, option in views.options.items()
        ],
    }


def _type(theme: ThemeConfig, name: str, lang: str) -> dict[str, Any]:
    spec = theme.types[name]
    sections = []
    for entry in spec.uses:
        if entry == ANY:
            section_id, kind = ANY, None
        else:
            match = USES_RE.match(entry)
            section_id, kind = match.group("id"), match.group("kind")  # type: ignore[union-attr]
        info = spec.sections.get(section_id)
        sections.append(
            {
                "id": section_id,
                "any": section_id == ANY,
                "kind": kind,
                "module": theme.module_for(kind) if kind else None,
                "required": bool(info and info.required),
                **_hints(info, lang),
                "fields": _fields(info.fields if info else None, lang),
            }
        )
    return {
        "name": name,
        **_hints(spec, lang),
        "template": spec.template or f"templates/{name}.html",
        "jsonld": list(spec.jsonld),
        "children_type": spec.children_type,
        "views": _views(theme, name, lang),
        "sections": sections,
    }


def _module(name: str, theme: ThemeConfig, lang: str) -> dict[str, Any]:
    spec = theme.module_specs[name]
    return {
        "name": name,
        "scope": spec.scope,
        "kinds": [
            {"kind": kind, "class": CLASS_OF.get(kind), "auto": kind in AUTO}
            for kind in kinds_of(name, spec)
        ],
        "schemaorg": spec.schemaorg,
        **_hints(spec, lang, example=True),
        "fields": _fields(spec.fields, lang),
    }


def _modules_for(theme: ThemeConfig, type_name: str) -> list[str]:
    """Модули, нужные странице типа: формы её секций и модули страницы.

    Тип с «любыми секциями» (`*`) может получить блок любой формы - тогда все.
    """
    specs = theme.module_specs
    if theme.any_sections(type_name):
        return list(specs)
    kinds = set(theme.formats_of(type_name).values())
    return [
        name
        for name, spec in specs.items()
        if spec.scope == "page" or kinds & set(kinds_of(name, spec))
    ]


def contract(
    theme: ThemeConfig,
    config: SiteConfig | None = None,
    lang: str = "en",
    name: str | None = None,
) -> dict[str, Any]:
    """Описание темы и служебных полей - объект `describe --json`.

    `name` - тип страницы или модуль: в описании остаются только он (и модули,
    которые нужны странице этого типа). Неизвестное имя - `HeronError` E008.
    """
    types = list(theme.types)
    modules = list(theme.module_specs)
    selected = None
    if name is not None:
        if name in theme.types:
            selected = {"kind": "type", "name": name}
            types, modules = [name], _modules_for(theme, name)
        elif name in theme.module_specs:
            selected = {"kind": "module", "name": name}
            types, modules = [], [name]
        else:
            raise HeronError(
                code="E008",
                message=Msg(
                    "describe_unknown",
                    name=name,
                    types=", ".join(theme.types) or "-",
                    modules=", ".join(theme.module_specs) or "-",
                ),
                hint=Msg("describe_unknown_hint"),
            )
    major, minor, *_ = heron.__version__.split(".")
    return {
        "$schema": f"https://sitebuilder.heron.software/schema/{major}.{minor}/{SCHEMA_URL}",
        "heron": heron.__version__,
        "lang": lang,
        "selected": selected,
        "site": _site(config, lang),
        "theme": {
            "name": theme.name,
            "title": theme.title,
            "version": theme.version,
            "heron": theme.heron,
            "languages": theme.hint_langs(),
            "described": theme.described,
        },
        "groups": [
            {"name": group, "title": service.group_title(lang, group)} for group in service.GROUPS
        ],
        "service": {
            "page": _service(theme, config, lang, "page"),
            "section": _service(theme, config, lang, "section"),
        },
        "md_places": [
            {"name": place, "hint": say(lang, "describe_md_" + place.replace("-", "_"))}
            for place in MD_PLACES
        ],
        "types": [_type(theme, type_name, lang) for type_name in types],
        "modules": [_module(module, theme, lang) for module in modules],
    }


def load(site_root: Path) -> tuple[ThemeConfig, SiteConfig]:
    """Тема и конфиг сайта - так же, как их находит сборка."""
    config = load_site(site_root / "site.yaml")
    found = resolver.theme(site_root, config.site.theme)
    return load_theme(found.path / "theme.yaml"), config


# --- текст для человека ----------------------------------------------------------


def _limits(item: dict[str, Any], lang: str) -> str:
    parts: list[str] = [say(lang, f"describe_type_{item['type']}")]
    if item.get("item"):
        parts.append(say(lang, "describe_of", item=say(lang, f"describe_type_{item['item']}")))
    if item.get("max_length"):
        parts.append(say(lang, "describe_max_length", n=item["max_length"]))
    if item.get("min_items"):
        parts.append(say(lang, "describe_min_items", n=item["min_items"]))
    if item.get("min_width"):
        parts.append(say(lang, "describe_min_width", n=item["min_width"]))
    if item.get("ratio"):
        parts.append(item["ratio"])
    if item.get("values"):
        parts.append(" | ".join(item["values"]))
    if item.get("schemaorg"):
        parts.append(f"schema.org {item['schemaorg']}")
    return ", ".join(parts)


def _hint_lines(item: dict[str, Any], indent: str, full: bool) -> list[str]:
    lines = []
    if full and item.get("help"):
        lines.extend(f"{indent}{line}".rstrip() for line in item["help"].splitlines())
    return lines


def _field_lines(
    items: list[dict[str, Any]], lang: str, indent: str, full: bool, places: dict[str, str]
) -> list[str]:
    lines: list[str] = []
    for item in items:
        mark = "*" if item["required"] else ""
        hint = f" - {item['hint']}" if item.get("hint") else ""
        lines.append(f"{indent}{item['name']}{mark} ({_limits(item, lang)}){hint}")
        if item.get("md"):
            lines.append(f"{indent}  {say(lang, 'describe_md', place=places[item['md']])}")
        lines.extend(_hint_lines(item, indent + "  ", full))
        if item.get("fields"):
            lines.extend(_field_lines(item["fields"], lang, indent + "  ", full, places))
    return lines


def _default(item: dict[str, Any], lang: str) -> str | None:
    """Что придёт, если поле не заполнить: значение или откуда оно берётся."""
    value = item["default"]
    if value not in (None, [], ""):
        shown = ("true" if value else "false") if isinstance(value, bool) else str(value)
        return say(lang, "describe_default", value=shown)
    source = item["default_from"]
    if not source:
        return None
    if source.startswith("site.yaml:"):
        origin = say(lang, "describe_from_site", path=source.split(":", 1)[1])
    else:
        origin = say(lang, "describe_from_" + source.replace("-", "_").replace(".", "_"))
    return say(lang, "describe_default", value=origin)


def text(data: dict[str, Any], lang: str) -> str:
    """Описание для человека. С выбранным типом или модулем - вместе с подробной справкой."""
    full = data["selected"] is not None
    places = {item["name"]: item["hint"] for item in data["md_places"]}
    theme = data["theme"]
    lines = [
        say(
            lang,
            "describe_head",
            theme=theme["name"],
            title=theme["title"] or theme["name"],
            version=theme["version"],
            langs=", ".join(theme["languages"]) or "-",
        )
    ]
    if data["site"]:
        site = data["site"]
        lines.append(
            say(
                lang,
                "describe_site",
                langs=", ".join(site["languages"]),
                default=site["default_lang"],
                lang=data["lang"],
            )
        )
    if not theme["described"]:
        lines += ["", say(lang, "describe_not_described")]

    if not full:
        titles = {group["name"]: group["title"] for group in data["groups"]}
        lines += ["", say(lang, "describe_service_head")]
        for scope in ("page", "section"):
            group = None
            for item in data["service"][scope]:
                if item["group"] != group:
                    group = item["group"]
                    lines.append(f"  {titles[group]}")
                mark = "*" if item["required"] else ""
                lines.append(f"    {item['name']}{mark} ({_limits(item, lang)}) - {item['hint']}")
                default = _default(item, lang)
                if default:
                    lines.append(f"      {default}")

    if data["types"]:
        lines += ["", say(lang, "describe_types_head")]
    for item in data["types"]:
        hint = f" - {item['hint']}" if item["hint"] else ""
        lines.append(f"  {item['name']}{hint}")
        lines.extend(_hint_lines(item, "    ", full))
        for section in item["sections"]:
            name = say(lang, "describe_any") if section["any"] else section["id"]
            mark = "*" if section["required"] else ""
            form = f" ({section['kind']})" if section["kind"] else ""
            hint = f" - {section['hint']}" if section["hint"] else ""
            lines.append(f"    {name}{mark}{form}{hint}")
            lines.extend(_hint_lines(section, "      ", full))
            if section["fields"]:
                lines.extend(_field_lines(section["fields"], lang, "      ", full, places))
        if item["children_type"]:
            lines.append("    " + say(lang, "describe_children", type=item["children_type"]))
        views = item["views"]
        if views:
            names = ", ".join(
                f"{view['name']}"
                + (say(lang, "describe_by_default") if view["name"] == views["default"] else "")
                for view in views["options"]
            )
            lines.append("    " + say(lang, "describe_views", key=views["key"], views=names))
            if full:
                for view in views["options"]:
                    lines.append(f"      {view['name']} - {view['hint'] or ''}".rstrip(" -"))
                    lines.extend(_hint_lines(view, "        ", full))

    if data["modules"]:
        lines += ["", say(lang, "describe_modules_head")]
    for item in data["modules"]:
        kinds = ", ".join(
            kind["kind"] + ("" if kind["auto"] else f" .{kind['class']}") for kind in item["kinds"]
        )
        where = say(lang, "describe_page_module") if item["scope"] == "page" else kinds
        hint = f" - {item['hint']}" if item["hint"] else ""
        lines.append(f"  {item['name']} ({where}){hint}")
        lines.extend(_hint_lines(item, "    ", full))
        if full and item.get("example"):
            lines.append("    " + say(lang, "describe_example"))
            lines.extend(f"      {line}".rstrip() for line in item["example"].splitlines())
        if item["fields"]:
            lines.extend(_field_lines(item["fields"], lang, "    ", full, places))
    if not full:
        lines += ["", say(lang, "describe_more")]
    return "\n".join(lines) + "\n"
