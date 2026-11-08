"""Справочная страница темы: контракт и демо на одной странице.

Справку никто не пишет руками: она собирается из контракта темы (`theme.yaml`:
типы, секции, модули, поля, виды разделов, подсказки - тот же объект, что у
`heron describe`) и из демо (контент сайта). У каждого блока рядом стоят
**живой пример** - секция демо, нарисованная модулем темы, - и **её исходный
markdown**. Поменялся контракт или демо - поменялась справка.

Где её видно:

- `heron docs theme-ref [путь]` - текстом в терминале (`text`);
- служебная страница черновой сборки и `heron serve`: `/_heron/theme/` на
  языке по умолчанию, `/_heron/theme/<язык>/` на остальных (`pages`). В боевую
  сборку (`--env prod`), в карту сайта и в `llms.txt` она не попадает, у неё
  `noindex`. Её же встраивает студия.

Данные справки - `reference()`: обычный словарь, его читают и текст, и HTML.

Спецификация: docs/ru/spec/21-engine.md, «Справка темы».
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from markupsafe import Markup, escape

from heron.contracts.site import SiteConfig
from heron.contracts.theme import FieldSpec, ThemeConfig, kinds_of
from heron.core import describe
from heron.core.demo import Shown
from heron.core.environment import BuildEnv
from heron.core.errors import Collector, HeronError
from heron.core.media import Manifest
from heron.core.models import Page, Section, Site
from heron.core.render import env as envmod
from heron.core.render import signature
from heron.messages import say

FOLDER = "_heron/theme"
URL = f"/{FOLDER}/"
CSS_VAR = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;}{]+);")
ROOT_BLOCK = re.compile(r":root\s*\{([^}]*)\}")
COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\))$")


def url_for(config: SiteConfig, lang: str) -> str:
    """Адрес справки на языке: язык по умолчанию - `/_heron/theme/`."""
    return URL if lang == config.site.default_lang else f"{URL}{lang}/"


def file_for(config: SiteConfig, lang: str) -> str:
    return url_for(config, lang).strip("/") + "/index.html"


# --- данные справки ---------------------------------------------------------------


def _demo_lang(config: SiteConfig, lang: str) -> str:
    return lang if lang in config.site.languages else config.site.default_lang


def source_markdown(section: Section) -> str:
    """Markdown секции как в файле: заголовок с якорем и классами, затем содержимое."""
    attrs = "".join(f" .{cls}" for cls in section.classes)
    head = f"{'#' * max(section.level, 2)} {section.title} {{#{section.id}{attrs}}}"
    return f"{head}\n\n{section.raw}".rstrip() + "\n"


def _page_ref(page: Page) -> dict[str, Any]:
    return {"source": str(page.source), "url": page.url, "lang": page.lang, "h1": page.h1}


def _ordered(pages: list[Page], lang: str) -> list[Page]:
    """Сначала страницы языка справки, затем остальные - в порядке сайта."""
    return [p for p in pages if p.lang == lang] + [p for p in pages if p.lang != lang]


def _examples(
    name: str, theme: ThemeConfig, found: Shown, lang: str
) -> list[tuple[Page, str | None]]:
    """Примеры модуля из демо: по одному на каждую форму, которую он рисует.

    У модуля страницы (крошки, список детей) - одна страница, где он что-то нарисовал.
    """
    places = found.modules.get(name, [])
    first = {id(page): index for index, page in enumerate(_ordered([p for p, _ in places], lang))}
    places = sorted(places, key=lambda item: first[id(item[0])])
    kinds = kinds_of(name, theme.module_specs[name])
    if not kinds:
        return places[:1]
    out: list[tuple[Page, str | None]] = []
    for kind in kinds:
        for page, section_id in places:
            section = page.section(section_id) if section_id else None
            if section is not None and section.kind == kind:
                out.append((page, section_id))
                break
    return out or places[:1]


def _schema_fields(prefix: str, fields: list[FieldSpec] | None, out: list[dict[str, str]]) -> None:
    for spec in fields or []:
        if spec.schemaorg:
            out.append({"where": f"{prefix}.{spec.name}", "schemaorg": spec.schemaorg})
        _schema_fields(f"{prefix}.{spec.name}", spec.fields, out)


def _schema(theme: ThemeConfig) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name, spec in theme.types.items():
        for kind in spec.jsonld:
            out.append({"where": f"types.{name}", "schemaorg": kind})
    for name, spec in theme.module_specs.items():
        if spec.schemaorg:
            out.append({"where": f"modules.{name}", "schemaorg": spec.schemaorg})
        _schema_fields(f"modules.{name}", spec.fields, out)
    for name, spec in theme.types.items():
        _schema_fields(f"types.{name}", spec.fields, out)
        for section, info in spec.sections.items():
            _schema_fields(f"types.{name}.sections.{section}", info.fields, out)
    return out


def _styles(theme_dir: Path) -> dict[str, Any]:
    """Файлы стилей темы и переменные `:root` из них - то, что меняют первым."""
    assets = theme_dir / "assets"
    files: list[str] = []
    tokens: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in sorted(assets.rglob("*.css")) if assets.is_dir() else []:
        if not path.is_file():
            continue
        files.append(path.relative_to(theme_dir).as_posix())
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        block = ROOT_BLOCK.search(text)
        for name, value in CSS_VAR.findall(block.group(1) if block else ""):
            if name in seen:
                continue
            seen.add(name)
            value = " ".join(value.split())
            tokens.append({"name": f"--{name}", "value": value, "color": bool(COLOR.match(value))})
    return {"files": files, "tokens": tokens}


def _flat(values: dict[str, Any], prefix: str = "") -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, value in values.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.extend(_flat(value, f"{name}."))
        else:
            out.append({"key": name, "value": "" if value is None else str(value)})
    return out


def _strings(theme_dir: Path, lang: str) -> list[dict[str, str]]:
    try:
        return _flat(envmod.load_strings(theme_dir, lang, Collector()).as_dict())
    except HeronError:
        return []


def reference(
    theme: ThemeConfig,
    theme_dir: Path,
    site: Site,
    config: SiteConfig,
    found: Shown,
    lang: str,
) -> dict[str, Any]:
    """Всё, что показывает справка: контракт на языке `lang` и демо этого языка."""
    demo_lang = _demo_lang(config, lang)
    contract = describe.contract(theme, config, lang)
    by_type: dict[str, list[Page]] = {}
    for page in _ordered(found.pages, demo_lang):
        by_type.setdefault(page.type, []).append(page)
    for item in contract["types"]:
        item["demo"] = [_page_ref(page) for page in by_type.get(item["name"], [])]
        views = item["views"]
        if views:
            for option in views["options"]:
                pages = _ordered(found.views.get((views["key"], option["name"]), []), demo_lang)
                own = [page for page in pages if page.type == item["name"]]
                pages = own + [page for page in pages if page.type != item["name"]]
                option["demo"] = [_page_ref(page) for page in pages]
                option["default"] = option["name"] == views["default"]
    for item in contract["modules"]:
        examples = []
        for page, section_id in _examples(item["name"], theme, found, demo_lang):
            section = page.section(section_id) if section_id else None
            examples.append(
                {
                    **_page_ref(page),
                    "section": section_id,
                    "kind": section.kind if section is not None else None,
                    "markdown": source_markdown(section) if section is not None else None,
                }
            )
        item["demo"] = examples
    return {
        "lang": lang,
        "demo_lang": demo_lang,
        "contract": contract,
        "schema": _schema(theme),
        "styles": _styles(theme_dir),
        "strings": _strings(theme_dir, demo_lang),
        "languages": list(config.site.languages),
        "errors": [error.render(lang) for error in found.errors],
    }


def load(site_root: Path, lang: str, drafts: bool = True) -> dict[str, Any]:
    """Справка темы сайта для `heron docs theme-ref`: прочитать сайт, собрать демо."""
    from heron.core import build as pipeline
    from heron.core import demo

    collector = Collector()
    site_root = site_root.resolve()
    config, theme, theme_dir, hooks = pipeline.prepare(site_root, collector)
    site = pipeline.content(site_root, config, theme, theme_dir, hooks, collector, drafts)
    found = demo.render(theme_dir, site, config, theme, hooks)
    return reference(theme, theme_dir, site, config, found, lang)


# --- текст для терминала -----------------------------------------------------------


def _indent(text: str | None, pad: str) -> list[str]:
    return [f"{pad}{line}".rstrip() for line in (text or "").splitlines()]


def _where(ref: dict[str, Any]) -> str:
    return f"{ref['source']} ({ref['url']})"


def text(data: dict[str, Any], lang: str) -> str:
    """Справка темы для человека в терминале: контракт и примеры из демо."""
    contract = data["contract"]
    theme = contract["theme"]
    lines = [
        say(lang, "ref_title", theme=theme["title"] or theme["name"], name=theme["name"]),
        say(lang, "ref_text_lead", url=URL),
    ]
    if not theme["described"]:
        lines += ["", say(lang, "describe_not_described")]
    for error in data["errors"]:
        lines += ["", say(lang, "ref_render_failed", error=error)]

    lines += ["", say(lang, "ref_types")]
    for item in contract["types"]:
        hint = f" - {item['hint']}" if item["hint"] else ""
        lines.append(f"  {item['name']}{hint}")
        lines.extend(_indent(item["help"], "    "))
        lines.append("    " + say(lang, "ref_template", template=item["template"]))
        if item.get("fields"):
            lines.append("    " + say(lang, "describe_type_fields"))
            for spec in item["fields"]:
                mark = "*" if spec["required"] else ""
                tail = f" - {spec['hint']}" if spec.get("hint") else ""
                lines.append(f"      {spec['name']}{mark} ({spec['type']}){tail}")
        for section in item["sections"]:
            name = say(lang, "describe_any") if section["any"] else section["id"]
            mark = "*" if section["required"] else ""
            form = f" ({section['kind']})" if section["kind"] else ""
            shint = f" - {section['hint']}" if section["hint"] else ""
            lines.append(f"    {say(lang, 'ref_section')} {name}{mark}{form}{shint}")
        if item["children_type"]:
            lines.append("    " + say(lang, "describe_children", type=item["children_type"]))
        if item["jsonld"]:
            lines.append("    schema.org: " + ", ".join(item["jsonld"]))
        demo_pages = ", ".join(_where(ref) for ref in item["demo"][:3])
        lines.append(
            "    " + say(lang, "ref_demo_pages", pages=demo_pages or say(lang, "ref_none"))
        )

    lines += ["", say(lang, "ref_modules")]
    for item in contract["modules"]:
        kinds = ", ".join(
            kind["kind"] + ("" if kind["auto"] else f" .{kind['class']}") for kind in item["kinds"]
        )
        where = say(lang, "describe_page_module") if item["scope"] == "page" else kinds
        hint = f" - {item['hint']}" if item["hint"] else ""
        lines.append(f"  {item['name']} ({where}){hint}")
        lines.extend(_indent(item["help"], "    "))
        if not item["demo"]:
            lines.append("    " + say(lang, "ref_no_example"))
            if item.get("example"):
                lines.append("    " + say(lang, "ref_theme_example"))
                lines.extend(_indent(item["example"], "      "))
        for example in item["demo"]:
            lines.append("    " + say(lang, "ref_example_at", where=_where(example)))
            if example["markdown"]:
                lines.extend(_indent(example["markdown"], "      "))
            else:
                lines.append("      " + say(lang, "ref_page_module_text"))

    views = [item for item in contract["types"] if item["views"]]
    if views:
        lines += ["", say(lang, "ref_views")]
    for item in views:
        info = item["views"]
        lines.append("  " + say(lang, "ref_views_of", type=item["name"], key=info["key"]))
        for option in info["options"]:
            enable = say(
                lang,
                "ref_view_default" if option["default"] else "ref_view_key",
                key=info["key"],
                view=option["name"],
            )
            hint = f" - {option['hint']}" if option["hint"] else ""
            lines.append(f"    {option['name']}{hint}")
            lines.append(f"      {enable}")
            shown = ", ".join(_where(ref) for ref in option["demo"][:3])
            lines.append(
                "      " + say(lang, "ref_demo_pages", pages=shown or say(lang, "ref_none"))
            )

    lines += ["", say(lang, "ref_schema")]
    for item in data["schema"] or [{"where": say(lang, "ref_none"), "schemaorg": ""}]:
        lines.append(f"  {item['schemaorg']:<28} {item['where']}".rstrip())

    lines += ["", say(lang, "ref_styles")]
    for name in data["styles"]["files"]:
        lines.append(f"  {name}")
    for token in data["styles"]["tokens"]:
        lines.append(f"    {token['name']}: {token['value']}")

    lines += ["", say(lang, "ref_strings", lang=data["demo_lang"])]
    for item in data["strings"] or [{"key": say(lang, "ref_none"), "value": ""}]:
        lines.append(f"  {item['key']}: {item['value']}".rstrip(": "))
    return "\n".join(lines) + "\n"


# --- служебная страница сборки ------------------------------------------------------

STYLE = """
.heron-ref{--ref-line:var(--line,#e3e5ea);--ref-muted:var(--muted,#5f6270)}
.heron-ref .ref-note{color:var(--ref-muted);border-left:3px solid var(--ref-line);
padding-left:.8rem}
.heron-ref nav.ref-toc ul{display:flex;flex-wrap:wrap;gap:.4rem 1.2rem;list-style:none;padding:0}
.heron-ref .ref-item{border-top:1px solid var(--ref-line);padding-top:1.2rem;margin-top:1.6rem}
.heron-ref .ref-help{white-space:pre-line;color:var(--ref-muted)}
.heron-ref .ref-pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem;
margin:1rem 0}
@media (max-width:52rem){.heron-ref .ref-pair{grid-template-columns:minmax(0,1fr)}}
.heron-ref .ref-live{border:1px dashed var(--ref-line);border-radius:8px;padding:1rem;min-width:0}
.heron-ref .ref-src{margin:0;white-space:pre-wrap;word-break:break-word;font-size:.85rem}
.heron-ref .ref-label{font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;
color:var(--ref-muted);margin:0 0 .4rem}
.heron-ref table{border-collapse:collapse;width:100%;font-size:.9rem}
.heron-ref th,.heron-ref td{border-bottom:1px solid var(--ref-line);padding:.35rem .5rem;
text-align:left;vertical-align:top}
.heron-ref .ref-swatch{display:inline-block;width:1em;height:1em;border:1px solid var(--ref-line);
vertical-align:-.15em;margin-right:.4em}
.heron-ref .ref-error{color:var(--alert,#b42318)}
"""


def _esc(value: Any) -> str:
    return str(escape("" if value is None else value))


def _help(text: str | None) -> str:
    return f'<p class="ref-help">{_esc(text)}</p>' if text else ""


def _link(ref: dict[str, Any]) -> str:
    return f'<a href="{_esc(ref["url"])}">{_esc(ref["h1"])}</a> <code>{_esc(ref["source"])}</code>'


def _limits(item: dict[str, Any], lang: str) -> str:
    return describe._limits(item, lang)  # noqa: SLF001 - тот же текст, что у describe


def _fields_table(items: list[dict[str, Any]] | None, lang: str, places: dict[str, str]) -> str:
    if not items:
        return ""
    rows = []

    def walk(fields: list[dict[str, Any]], prefix: str) -> None:
        for item in fields:
            mark = "*" if item["required"] else ""
            place = places.get(item["md"] or "", "")
            rows.append(
                "<tr>"
                f"<td><code>{_esc(prefix + item['name'])}{mark}</code></td>"
                f"<td>{_esc(_limits(item, lang))}</td>"
                f"<td>{_esc(place)}</td>"
                f"<td>{_esc(item['hint'])}</td>"
                "</tr>"
            )
            if item.get("fields"):
                walk(item["fields"], f"{prefix}{item['name']}.")

    walk(items, "")
    head = "".join(
        f"<th>{_esc(say(lang, key))}</th>"
        for key in ("ref_col_field", "ref_col_type", "ref_col_place", "ref_col_hint")
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _pair(live: str, markdown: str | None, lang: str, caption: str) -> str:
    source = (
        f'<pre class="ref-src"><code>{_esc(markdown)}</code></pre>'
        if markdown
        else f'<p class="ref-help">{_esc(say(lang, "ref_page_module_text"))}</p>'
    )
    return (
        '<div class="ref-pair">'
        f'<div><p class="ref-label">{_esc(say(lang, "ref_live"))}</p>'
        f'<div class="ref-live">{live}</div></div>'
        f'<div><p class="ref-label">{_esc(say(lang, "ref_source"))}</p>{source}</div>'
        "</div>"
        f'<p class="ref-help">{caption}</p>'
    )


class Live:
    """Живые примеры: модуль темы рисует секцию демо в окружении её страницы."""

    def __init__(
        self,
        theme_dir: Path,
        site: Site,
        config: SiteConfig,
        theme: ThemeConfig,
        media: Manifest | None,
        build_env: BuildEnv | None,
        hooks=None,
    ) -> None:
        self.env = envmod.make(theme_dir, config, hooks)
        self.theme_dir = theme_dir
        self.site, self.config, self.theme = site, config, theme
        self.media, self.build_env = media, build_env
        self.by_source = {str(page.source): page for page in site.pages}
        self.strings: dict[str, envmod.Strings] = {}

    def render(self, source: str, module: str, section_id: str | None, lang: str) -> str:
        page = self.by_source.get(source)
        if page is None:
            return ""
        try:
            if page.lang not in self.strings:
                self.strings[page.lang] = envmod.load_strings(
                    self.theme_dir, page.lang, Collector()
                )
            scope = envmod.context(
                self.env,
                page,
                self.site,
                self.config,
                self.theme,
                self.strings[page.lang],
                Collector(),
                self.media,
                self.build_env,
            )
            call = getattr(scope["mod"], module.replace("-", "_"))
            return str(call(section_id) if section_id else call())
        except HeronError as error:
            return f'<p class="ref-error">{_esc(error.render(lang))}</p>'
        except Exception as error:  # noqa: BLE001 - чужой шаблон, справка не роняет сборку
            return f'<p class="ref-error">{_esc(type(error).__name__)}: {_esc(error)}</p>'


def _view_modules(found: Shown) -> dict[str, set[str]]:
    """Модули страницы, которые зависят от детей: на страницах без детей их нет.

    По ним справка показывает вид раздела живьём (у стартовой темы - список детей).
    """
    childless = {
        str(page.source)
        for page in found.pages
        if not [c for c in page.children if not c.generated]
    }
    common = {
        module
        for module, places in found.modules.items()
        if any(section is None and str(page.source) in childless for page, section in places)
    }
    out: dict[str, set[str]] = {}
    for module, places in found.modules.items():
        if module in common:
            continue
        for page, section in places:
            if section is None:
                out.setdefault(str(page.source), set()).add(module)
    return out


def html(data: dict[str, Any], live: Live, found: Shown, config: SiteConfig) -> str:
    """Служебная страница справки: та же справка, что текстом, с живыми примерами."""
    lang = data["lang"]
    contract = data["contract"]
    theme = contract["theme"]
    places = {item["name"]: item["hint"] for item in contract["md_places"]}
    title = say(lang, "ref_title", theme=theme["title"] or theme["name"], name=theme["name"])
    out: list[str] = []
    add = out.append
    add(f"<h1>{_esc(title)}</h1>")
    add(f'<p class="ref-note">{_esc(say(lang, "ref_page_lead"))}</p>')
    others = [code for code in data["languages"] if code != lang]
    if others:
        links = " · ".join(
            f'<a href="{_esc(url_for(config, code))}">{_esc(code)}</a>' for code in others
        )
        add(f"<p>{_esc(say(lang, 'ref_other_langs'))} {links}</p>")
    if not theme["described"]:
        add(f'<p class="ref-note">{_esc(say(lang, "describe_not_described"))}</p>')
    for error in data["errors"]:
        add(f'<p class="ref-error">{_esc(say(lang, "ref_render_failed", error=error))}</p>')
    toc = [
        ("ref-types", "ref_types"),
        ("ref-modules", "ref_modules"),
        ("ref-views", "ref_views"),
        ("ref-schema", "ref_schema"),
        ("ref-styles", "ref_styles"),
        ("ref-strings", "ref_strings"),
    ]
    items = "".join(
        f'<li><a href="#{anchor}">{_esc(say(lang, key, lang=data["demo_lang"]))}</a></li>'
        for anchor, key in toc
    )
    add(f'<nav class="ref-toc"><ul>{items}</ul></nav>')

    add(f'<section id="ref-types"><h2>{_esc(say(lang, "ref_types"))}</h2>')
    for item in contract["types"]:
        add(f'<div class="ref-item" id="type-{_esc(item["name"])}">')
        add(f"<h3><code>{_esc(item['name'])}</code> {_esc(item['hint'])}</h3>")
        add(_help(item["help"]))
        add(f"<p>{_esc(say(lang, 'ref_template', template=item['template']))}</p>")
        rows = []
        for section in item["sections"]:
            name = say(lang, "describe_any") if section["any"] else section["id"]
            mark = "*" if section["required"] else ""
            rows.append(
                f"<tr><td><code>{_esc(name)}{mark}</code></td><td>{_esc(section['kind'] or '')}"
                f"</td><td>{_esc(section['hint'])}</td></tr>"
            )
        if rows:
            head = "".join(
                f"<th>{_esc(say(lang, key))}</th>"
                for key in ("ref_col_section", "ref_col_kind", "ref_col_hint")
            )
            add(f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>")
        if item.get("fields"):
            add(f"<p>{_esc(say(lang, 'describe_type_fields'))}</p>")
            add(_fields_table(item["fields"], lang, places))
        for section in item["sections"]:
            if section["fields"]:
                add(f"<p><code>{_esc(section['id'])}</code></p>")
                add(_fields_table(section["fields"], lang, places))
        if item["children_type"]:
            add(f"<p>{_esc(say(lang, 'describe_children', type=item['children_type']))}</p>")
        if item["jsonld"]:
            add(f"<p>schema.org: <code>{_esc(', '.join(item['jsonld']))}</code></p>")
        pages = ", ".join(_link(ref) for ref in item["demo"][:5]) or _esc(say(lang, "ref_none"))
        add(f"<p>{_esc(say(lang, 'ref_demo_pages', pages=''))}{pages}</p>")
        add("</div>")
    add("</section>")

    add(f'<section id="ref-modules"><h2>{_esc(say(lang, "ref_modules"))}</h2>')
    for item in contract["modules"]:
        kinds = ", ".join(
            kind["kind"] + ("" if kind["auto"] else f" .{kind['class']}") for kind in item["kinds"]
        )
        where = say(lang, "describe_page_module") if item["scope"] == "page" else kinds
        add(f'<div class="ref-item" id="module-{_esc(item["name"])}">')
        add(f"<h3><code>{_esc(item['name'])}</code> <small>{_esc(where)}</small></h3>")
        if item["hint"]:
            add(f"<p><strong>{_esc(item['hint'])}</strong></p>")
        add(_help(item["help"]))
        if item["schemaorg"]:
            add(f"<p>schema.org: <code>{_esc(item['schemaorg'])}</code></p>")
        add(_fields_table(item["fields"], lang, places))
        for example in item["demo"]:
            rendered = live.render(example["source"], item["name"], example["section"], lang)
            caption = _esc(say(lang, "ref_example_at", where="")) + _link(example)
            add(_pair(rendered, example["markdown"], lang, caption))
        if not item["demo"]:
            add(f'<p class="ref-error">{_esc(say(lang, "ref_no_example"))}</p>')
            if item.get("example"):
                add(f'<p class="ref-label">{_esc(say(lang, "ref_theme_example"))}</p>')
                add(f'<pre class="ref-src"><code>{_esc(item["example"])}</code></pre>')
        add("</div>")
    add("</section>")

    by_page = _view_modules(found)
    add(f'<section id="ref-views"><h2>{_esc(say(lang, "ref_views"))}</h2>')
    for item in contract["types"]:
        info = item["views"]
        if not info:
            continue
        add('<div class="ref-item">')
        add(f"<h3>{_esc(say(lang, 'ref_views_of', type=item['name'], key=info['key']))}</h3>")
        add(_help(info["help"]))
        for option in info["options"]:
            enable = say(
                lang,
                "ref_view_default" if option["default"] else "ref_view_key",
                key=info["key"],
                view=option["name"],
            )
            add(f"<h4><code>{_esc(option['name'])}</code> {_esc(option['hint'])}</h4>")
            add(_help(option["help"]))
            add(f"<p>{_esc(enable)}</p>")
            if not option["demo"]:
                add(f'<p class="ref-error">{_esc(say(lang, "ref_no_view_example"))}</p>')
                continue
            ref = option["demo"][0]
            rendered = "".join(
                live.render(ref["source"], module, None, lang)
                for module in sorted(by_page.get(ref["source"], set()))
            )
            source = f"{info['key']}: {option['name']}"
            caption = _esc(say(lang, "ref_example_at", where="")) + _link(ref)
            add(_pair(rendered, source, lang, caption))
        add("</div>")
    add("</section>")

    add(f'<section id="ref-schema"><h2>{_esc(say(lang, "ref_schema"))}</h2>')
    if data["schema"]:
        rows = "".join(
            f"<tr><td><code>{_esc(row['schemaorg'])}</code></td><td><code>{_esc(row['where'])}"
            "</code></td></tr>"
            for row in data["schema"]
        )
        add(f"<table><tbody>{rows}</tbody></table>")
    else:
        add(f"<p>{_esc(say(lang, 'ref_none'))}</p>")
    add("</section>")

    add(f'<section id="ref-styles"><h2>{_esc(say(lang, "ref_styles"))}</h2>')
    add(
        "<p>" + ", ".join(f"<code>{_esc(name)}</code>" for name in data["styles"]["files"]) + "</p>"
    )
    if data["styles"]["tokens"]:
        rows = "".join(
            "<tr><td><code>{}</code></td><td>{}<code>{}</code></td></tr>".format(
                _esc(token["name"]),
                f'<span class="ref-swatch" style="background:{_esc(token["value"])}"></span>'
                if token["color"]
                else "",
                _esc(token["value"]),
            )
            for token in data["styles"]["tokens"]
        )
        add(f"<table><tbody>{rows}</tbody></table>")
    add("</section>")

    add(
        f'<section id="ref-strings"><h2>'
        f"{_esc(say(lang, 'ref_strings', lang=data['demo_lang']))}</h2>"
    )
    if data["strings"]:
        rows = "".join(
            f"<tr><td><code>{_esc(row['key'])}</code></td><td>{_esc(row['value'])}</td></tr>"
            for row in data["strings"]
        )
        add(f"<table><tbody>{rows}</tbody></table>")
    else:
        add(f"<p>{_esc(say(lang, 'ref_none'))}</p>")
    add("</section>")

    css = "".join(
        f'<link rel="stylesheet" href="/{_esc(name)}">' for name in data["styles"]["files"]
    )
    return (
        "<!doctype html>\n"
        f'<html lang="{_esc(data["demo_lang"])}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        '<meta name="robots" content="noindex, nofollow">\n'
        f"{css}\n<style>{STYLE}</style>\n</head>\n<body>\n"
        f'<main class="heron-ref">\n{Markup("".join(out))}\n</main>\n</body>\n</html>\n'
    )


def pages(
    theme_dir: Path,
    site: Site,
    config: SiteConfig,
    theme: ThemeConfig,
    found: Shown,
    media: Manifest | None = None,
    build_env: BuildEnv | None = None,
    hooks=None,
    notes_lang: str | None = None,
) -> dict[str, str]:
    """Файлы справки для черновой сборки: имя в сборке → HTML, по языку сайта.

    Подсказки - на языке страницы справки, рамка - на нём же, если движок его
    знает (ru, en), иначе на языке сообщений запуска.
    """
    live = Live(theme_dir, site, config, theme, media, build_env, hooks)
    out: dict[str, str] = {}
    for lang in config.site.languages:
        data = reference(theme, theme_dir, site, config, found, lang)
        if lang not in ("ru", "en") and notes_lang:
            data["lang"] = notes_lang
        page = html(data, live, found, config)
        out[file_for(config, lang)] = signature.sign(page) if config.build.generator else page
    return out
