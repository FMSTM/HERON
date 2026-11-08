"""Страница и категория на всех языках сайта: найти, создать, править, перенести.

Одно ядро для `heron page add`, `heron category add`, консольного опросника,
ответов агента (`--answers`) и студии в браузере. Правило одной команды: есть -
открыть на правку, нет - создать. Создание идёт сразу на всех языках `site.yaml`:
основной язык заполняется целиком, остальные получают копию его текста и
переводы тех полей, которые перевели; пропущенный перевод - пометка
`translation: pending` в SEO-блоке файла языка (20 §4.2).

Перенос и переименование (другая категория, другой ключ) двигают файлы на всех
языках и ставят 301 со старых адресов (`redirect_from`) у самой страницы и у
всех страниц внутри перенесённой категории; ключи меню в `site.yaml` следуют за
ключом. `site.yaml` пишется с сохранением комментариев, как у `heron setup`.

Спецификация: docs/ru/spec/21-engine.md, «Страницы и категории: page add, category add».
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from heron.contracts.fields import PER_LANGUAGE, TRANSLATABLE
from heron.contracts.frontmatter import PENDING
from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core import paths
from heron.core.errors import Collector, HeronError
from heron.core.parser.frontmatter import FRONTMATTER
from heron.edit.langs import folder_type, key_of, rel_for
from heron.edit.model import (
    INDEX,
    TEXT_TYPES,
    THEME_GROUP,
    Field,
    Page,
    fields,
    load,
    set_field,
)
from heron.edit.slots import EditError
from heron.edit.validate import Issue, validate
from heron.messages import Msg

# Поля с текстом на каждом языке, свои поля языка и общие - один список на движок
# (`heron.contracts.fields`): тот же у `heron check` (`shared_mismatch`).
CATEGORY = "category"
TRANSLATION = "translation"
MENU = "menu"
HOME_KEYS = ("", "/")
KINDS = {False: "page", True: "category"}


def translatable(item: Field) -> bool:
    """Поле со своим текстом на каждом языке: его спрашивают при переводе."""
    if not item.editable:
        return False
    if item.group == THEME_GROUP:
        return item.type in TEXT_TYPES
    if item.where == "frontmatter":
        return item.name in TRANSLATABLE
    if item.where == "heading":
        return item.name == "heading"
    if item.where == "body":
        return item.type in ("text", "markdown", "list")
    return False


def own_value(item: Field) -> bool:
    """Поле, которое язык может иметь своим: перевод, свои адреса и пометки, разметка.

    Остальное (тип, порядок, обложка, флаги, даты, свои поля темы без текста,
    меню, категория, якорь секции) - одно на все языки и правится на основном.
    """
    if translatable(item):
        return True
    if item.where == "frontmatter":
        return item.name in PER_LANGUAGE or item.type == "schema"
    return False


def shared(item: Field) -> bool:
    """Поле SEO-блока, одно на все языки: правка на основном языке пишет его во все файлы.

    Служебные из них - ровно `SHARED` (тот же список сверяет `heron check`), а ещё
    свои поля темы без текста и вид раздела (ключ `views` типа).
    """
    return item.where == "frontmatter" and item.editable and not own_value(item)


def _filled(value: Any) -> bool:
    return value not in (None, "", [], {})


# --- сайт: тема, конфиг, контракт ---------------------------------------------------


@dataclass(slots=True)
class Ctx:
    """Папка сайта, его конфиг, тема и контракт на языке пояснений."""

    root: Path
    config: SiteConfig
    theme: ThemeConfig
    contract: dict[str, Any]
    notes: str

    @property
    def langs(self) -> list[str]:
        """Языки сайта, основной первым."""
        default = self.config.site.default_lang
        return [default] + [lang for lang in self.config.site.languages if lang != default]

    @property
    def default(self) -> str:
        return self.config.site.default_lang


def context(root: Path, notes: str = "en") -> Ctx:
    """Тема и конфиг - так же, как их находит сборка; контракт - как у `heron describe`."""
    from heron.core import describe

    theme, config = describe.load(root)
    contract = describe.contract(theme, config, notes)
    return Ctx(Path(root), config, theme, contract, notes)


def norm_key(key: str) -> str:
    """Ключ страницы без слешей по краям; каждая часть - слаг, иначе E005."""
    from heron.scaffold.page import SLUG

    clean = key.strip().strip("/")
    for part in clean.split("/") if clean else []:
        if not SLUG.match(part):
            raise HeronError(
                code="E005",
                message=Msg("edit_bad_key", key=key),
                hint=Msg("edit_bad_key_hint"),
            )
    return clean


def join(category: str | None, name: str) -> str:
    """Ключ страницы `name` в категории `category` (пусто - корень)."""
    category = (category or "").strip("/")
    return f"{category}/{name}" if category else name


def parent_of(key: str) -> str:
    return key.rsplit("/", 1)[0] if "/" in key else ""


def name_of(key: str) -> str:
    return key.rsplit("/", 1)[-1]


# --- что есть на диске --------------------------------------------------------------


def where(ctx: Ctx, key: str) -> bool | None:
    """Что лежит под ключом хоть на одном языке: категория (True), страница (False), ничего."""
    if key == "":
        return False
    for lang in ctx.langs:
        if (ctx.root / rel_for(lang, key, True)).is_file():
            return True
    for lang in ctx.langs:
        if (ctx.root / rel_for(lang, key, False)).is_file():
            return False
    return None


@dataclass(slots=True)
class Node:
    """Строка дерева `heron page list`: ключ, категория ли, состояние на каждом языке."""

    key: str
    category: bool
    langs: dict[str, str]  # язык → ok | pending | missing
    title: str = ""
    type: str | None = None
    # папка со страницами, но без `_index.md` ни на одном языке (так было в 0.2):
    # сборка считает её разделом, `heron category add <ключ>` заводит её явно
    implicit: bool = False

    @property
    def depth(self) -> int:
        return self.key.count("/") + (1 if self.key else 0)


def _head(path: Path) -> dict[str, Any]:
    try:
        match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
        data = yaml.safe_load(match.group("body")) if match else None
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def tree(ctx: Ctx) -> list[Node]:
    """Категории и страницы всех языков по порядку ключей, с пометками переводов."""
    from heron.core import notes
    from heron.core.tree import IGNORED

    found: dict[tuple[str, bool], dict[str, str]] = {}
    for lang in ctx.langs:
        lang_root = ctx.root / "content" / lang
        if not lang_root.is_dir():
            continue
        for path in sorted(lang_root.rglob("*.md")):
            if not paths.inside(lang_root, path):
                continue
            name = path.name
            if name.lower() in IGNORED or name.startswith(".") or notes.skip(name):
                continue
            if name.startswith("_") and name != INDEX:
                continue
            rel = path.relative_to(ctx.root).as_posix()
            parsed = key_of(rel)
            if parsed is None:
                continue
            _, key, category = parsed
            state = "pending" if _head(path).get(TRANSLATION) == PENDING else "ok"
            found.setdefault((key, category), {})[lang] = state
    out: list[Node] = []
    for (key, category), states in found.items():
        langs = {lang: states.get(lang, "missing") for lang in ctx.langs}
        first = next(lang for lang in ctx.langs if lang in states)
        head = _head(ctx.root / rel_for(first, key, category))
        title = str(head.get("nav_title") or head.get("h1") or head.get("title") or "")
        out.append(Node(key, category, langs, title, head.get("type")))
    folders = {key for key, category in found if category}
    for key, _category in list(found):
        parts = key.split("/")[:-1] if key else []
        for depth in range(1, len(parts) + 1):
            folder = "/".join(parts[:depth])
            if folder not in folders:
                folders.add(folder)
                missing = {lang: "missing" for lang in ctx.langs}
                out.append(Node(folder, True, missing, implicit=True))
    out.sort(key=lambda node: (node.key.split("/") if node.key else [], not node.category))
    return out


def categories(ctx: Ctx) -> list[Node]:
    return [node for node in tree(ctx) if node.category]


# --- страница или категория на всех языках ------------------------------------------


@dataclass(slots=True)
class Entity:
    """Страница или категория на всех языках: страницы модели правки и что с ними будет.

    `pages` - языки, у которых файл есть или уже заведён в памяти; `disk` - текст
    файла на диске (None - файла нет, он будет создан). `target` - ключ после
    переноса, `site` - правки site.yaml (меню).
    """

    ctx: Ctx
    key: str
    category: bool
    pages: dict[str, Page]
    disk: dict[str, str | None]
    new: bool
    target: str
    site: dict[str, Any] = field(default_factory=dict)
    made: list[str] = field(default_factory=list)  # категории, созданные попутно
    # языки без файла, которые правили явно: только они получат файл при правке
    touched: set[str] = field(default_factory=set)

    @property
    def main(self) -> Page:
        return self.pages[self.ctx.default]

    @property
    def moved(self) -> bool:
        return not self.new and self.target != self.key

    def created(self, lang: str) -> bool:
        return self.disk.get(lang) is None

    def missing(self) -> list[str]:
        """Языки без файла: у новой страницы получат копию основного языка и пометку."""
        return [lang for lang in self.ctx.langs if self.disk.get(lang) is None]

    def planned(self) -> list[str]:
        """Языки, чьи файлы запись пишет.

        Новая страница - все языки сайта. Правка существующей - файлы, которые
        есть, и языки без файла, которые правили явно (поле, `pending`); остальных
        языков запись не создаёт, как и недостающих категорий (это делают
        создание и перенос).
        """
        if self.new:
            return list(self.ctx.langs)
        return [
            lang
            for lang in self.ctx.langs
            if self.disk.get(lang) is not None or lang in self.touched
        ]

    def changed(self) -> bool:
        """Запись что-нибудь поменяет: файлы языков, перенос, site.yaml."""
        if self.new or self.moved or self.site:
            return True
        return any(
            lang in self.pages and self.pages[lang].text != self.disk.get(lang)
            for lang in self.planned()
        )

    def rel(self, lang: str, key: str | None = None) -> str:
        return rel_for(lang, self.target if key is None else key, self.category)


def _types(ctx: Ctx) -> list[str]:
    return list(ctx.theme.types)


def _check_type(ctx: Ctx, name: str) -> str:
    if name not in ctx.theme.types:
        known = ", ".join(ctx.theme.types)
        raise HeronError(
            code="E041",
            message=(
                Msg("scaffold_unknown_type", page_type=name, known=known)
                if known
                else Msg("scaffold_unknown_type_none", page_type=name)
            ),
            hint=Msg("edit_type_hint"),
        )
    return name


def default_type(ctx: Ctx, key: str, category: bool) -> str:
    """Тип новой страницы по правилу сборки: тип страниц папки, иначе основной тип темы."""
    rel = rel_for(ctx.default, key, category)
    kind = folder_type(ctx.root, rel)
    if kind in ctx.theme.types:
        return kind
    if "page" in ctx.theme.types:
        return "page"
    return next(iter(ctx.theme.types), "page")


def _load(ctx: Ctx, text: str, rel: str) -> Page:
    return load(
        text,
        ctx.contract,
        rel=rel,
        page_type=folder_type(ctx.root, rel),
        allow_raw_html=ctx.config.build.allow_raw_html,
    )


def open_entity(
    ctx: Ctx,
    key: str,
    category: bool = False,
    *,
    page_type: str | None = None,
    children_type: str | None = None,
    view: str | None = None,
    title: str | None = None,
) -> Entity:
    """Страница (или категория) `key`: есть хоть на одном языке - на правку, нет - заготовка.

    Под ключом лежит другое (страница вместо категории и наоборот) - E004:
    у страницы и категории с одним ключом был бы один адрес (E029 сборки).
    """
    from heron.scaffold.page import stub, title_of

    key = norm_key(key)
    if category and key == "":
        # корень сайта - не категория: это главная, у неё свой файл index.md
        raise HeronError(
            code="E005",
            message=Msg("edit_category_root"),
            hint=Msg("edit_category_root_hint"),
        )
    have = where(ctx, key)
    if have is not None and have != category:
        raise HeronError(
            code="E004",
            message=Msg("edit_key_is_category" if have else "edit_key_is_page", key=key or "/"),
            hint=Msg("edit_key_kind_hint", key=key or "/"),
        )
    disk: dict[str, str | None] = {}
    pages: dict[str, Page] = {}
    for lang in ctx.langs:
        rel = rel_for(lang, key, category)
        path = ctx.root / rel
        if path.is_file():
            paths.in_site(ctx.root, rel)
            text = path.read_bytes().decode("utf-8", errors="strict")
            disk[lang] = text
            pages[lang] = _load(ctx, text, rel)
        else:
            disk[lang] = None
    if have is not None:
        entity = Entity(ctx, key, category, pages, disk, False, key)
        if ctx.default not in pages:
            # основного языка нет, а другой есть: основа - первый найденный
            source = next(pages[lang] for lang in ctx.langs if lang in pages)
            pages[ctx.default] = _load(ctx, source.text, rel_for(ctx.default, key, category))
        return entity
    if key == "":
        raise HeronError(code="E005", message=Msg("edit_bad_key", key="/"))
    kind = _check_type(ctx, page_type or default_type(ctx, key, category))
    if children_type is not None:
        _check_type(ctx, children_type)
    elif category:
        spec = ctx.theme.types[kind]
        children_type = spec.children_type if spec.children_type in ctx.theme.types else None
    if view is not None:
        _check_view(ctx, kind, view)
    text = stub(
        ctx.theme,
        kind,
        title or title_of(key),
        ctx.notes,
        category=category,
        children_type=children_type,
        view=view,
    )
    rel = rel_for(ctx.default, key, category)
    pages[ctx.default] = _load(ctx, text, rel)
    return Entity(ctx, key, category, pages, disk, True, key)


def _check_view(ctx: Ctx, kind: str, view: str) -> None:
    spec = ctx.theme.types[kind].views
    options = list(spec.options) if spec is not None else []
    if view not in options:
        raise HeronError(
            code="E041",
            message=Msg("edit_unknown_view", view=view, type=kind, views=", ".join(options) or "-"),
        )


def retype(entity: Entity, page_type: str) -> Entity:
    """Новая страница другого типа: заготовка с секциями этого типа (до первой правки)."""
    if not entity.new:
        return entity
    from heron.scaffold.page import title_of

    title = str(entity.main.front.data.get("title") or title_of(entity.key))
    return open_entity(entity.ctx, entity.key, entity.category, page_type=page_type, title=title)


# --- правка --------------------------------------------------------------------------


def page_of(entity: Entity, lang: str) -> Page:
    """Страница языка: файл, или копия основного языка для языка без файла."""
    if lang not in entity.pages:
        entity.pages[lang] = translation_of(entity, lang)
    return entity.pages[lang]


def translation_of(entity: Entity, lang: str) -> Page:
    """Копия основного языка для нового файла языка `lang`, с пометкой «перевод не готов».

    Поля со своим значением у каждого языка (`PER_LANGUAGE`: прежние адреса, дата
    правки) не копируются: `redirect_from` основного языка на копии - те же старые
    адреса у двух страниц (E009), `updated` - дата чужой правки.
    """
    page = _load(entity.ctx, entity.main.text, rel_for(lang, entity.key, entity.category))
    for name in sorted(PER_LANGUAGE - {TRANSLATION}):
        if name in page.front.data:
            page = set_field(page, name, None)
    return set_field(page, TRANSLATION, PENDING)


def fields_of(entity: Entity, lang: str, only_translatable: bool = False) -> list[Field]:
    """Поля страницы языка по порядку показа; категорию можно менять (перенос)."""
    out = []
    for item in fields(page_of(entity, lang)):
        if item.name == CATEGORY and item.where == "path":
            item.editable = lang == entity.ctx.default and entity.key != ""
            item.readonly = None if item.editable else item.readonly
            item.value = parent_of(entity.target) or None
        if only_translatable and not translatable(item):
            continue
        out.append(item)
    return out


def set_value(entity: Entity, lang: str, path: str, value: Any) -> None:
    """Записать поле языка; `category` - перенос, `menu` - правка site.yaml (общая).

    Проверки до записи (`E039`): поле должно быть у страницы; неосновной язык
    правит только поля со своим значением (`own_value`), остальное общее и
    правится на основном; в однострочном поле нет перевода строки; значение
    поля секции не начинает новую секцию (заголовок с якорем `{#…}`).

    Якорь секции - структура страницы: он меняется сразу на всех языках, где
    секция есть. Поле секции, которой на основном языке ещё нет, добавляет её
    на всех языках с файлом (`add_section`): переведённые языки получают пометку.
    Общее поле (`shared`) на основном языке пишется во все файлы страницы.
    """
    main = lang == entity.ctx.default
    parts = path.split(".")
    item = _known(entity, lang, path)
    if not main and (path in (CATEGORY, MENU) or (item is not None and not own_value(item))):
        raise _failed(path, lang, Msg("edit_field_shared", main=entity.ctx.default))
    if path == CATEGORY:
        move(entity, join(_category_value(value), name_of(entity.target)))
        return
    if len(parts) == 3 and parts[0] == "sections" and parts[2] == "anchor":
        _set_anchor(entity, parts[1], value)
        return
    if item is None and parts[0] != "sections":
        raise _failed(path, lang, Msg("edit_unknown_field", path=path))
    if item is not None and _breaks(item, value):
        raise _failed(path, lang, Msg("edit_single_line"))
    section = parts[1] if len(parts) >= 3 and parts[0] == "sections" else None
    if section is not None and section != "intro" and main_lacks(entity, section):
        if not main:
            raise _failed(
                path, lang, Msg("edit_section_main", section=section, main=entity.ctx.default)
            )
        if entity.main.body.error is None:
            heading = value if parts[2] == "heading" else None
            add_section(entity, section, heading=heading)
            entity.touched.add(lang)
            if parts[2] == "heading":
                return
    page = page_of(entity, lang)
    before = page.text
    ids = _section_ids(page)
    try:
        page = set_field(page, path, value)
    except EditError as error:
        raise _failed(path, lang, error.args[0]) from error
    if section is not None:
        _keep_sections(path, lang, section, ids, _section_ids(page))
    if path == MENU:
        entity.site.update(page.site)
    entity.pages[lang] = page
    if page.text != before:
        entity.touched.add(lang)
    if main and item is not None and shared(item):
        # общее поле (тип, порядок, обложка, флаги, свои поля темы без текста) - одно на
        # все языки: то же значение у всех файлов страницы, без пометки перевода
        for code in entity.ctx.langs[1:]:
            if code in entity.pages:
                try:
                    entity.pages[code] = set_field(entity.pages[code], path, value)
                except EditError as error:
                    raise _failed(path, code, error.args[0]) from error


def _failed(path: str, lang: str, reason: Any) -> HeronError:
    return HeronError(
        code="E039", message=Msg("edit_field_failed", path=path, lang=lang, reason=reason)
    )


def _known(entity: Entity, lang: str, path: str) -> Field | None:
    """Поле страницы по пути; пункт списка (`….items.0.q`) - поле всего списка."""
    known = {item.path: item for item in fields_of(entity, lang)}
    if path in known:
        return known[path]
    parts = path.split(".")
    for depth in range(len(parts) - 1, 0, -1):
        if parts[depth].isdigit():
            return known.get(".".join(parts[:depth]))
    return None


def main_lacks(entity: Entity, section: str) -> bool:
    """Секции нет на основном языке (новый блок добавляют только там)."""
    page = page_of(entity, entity.ctx.default)
    return page.body.get(section) is None


SINGLE_LINE = ("markdown", "schema")  # типы, которым перевод строки можно


def _breaks(item: Field, value: Any) -> bool:
    """Перевод строки в однострочном поле (заголовок, title, пункт-строка списка)."""
    if item.type == "list":
        if not isinstance(value, list):
            return False
        subs = {sub["name"]: sub for sub in item.fields or []}
        inner = item.limits.get("item") or ("text" if item.where == "frontmatter" else "markdown")
        for entry in value:
            if isinstance(entry, dict):
                for name, sub in entry.items():
                    spec = subs.get(str(name)) or {}
                    if spec.get("type", "text") not in SINGLE_LINE and _newline(sub):
                        return True
            elif inner not in SINGLE_LINE and _newline(entry):
                return True
        return False
    return item.type not in SINGLE_LINE and _newline(value)


def _newline(value: Any) -> bool:
    return isinstance(value, str) and ("\n" in value or "\r" in value)


def _section_ids(page: Page) -> list[str]:
    return [section.id for section in page.body.sections]


def _keep_sections(path: str, lang: str, section: str, before: list[str], after: list[str]) -> None:
    """Значение поля не меняет набор секций: заголовок с якорем в тексте - E039.

    Секцию добавляет только её собственное поле (секции не было - появилась она);
    любая другая новая или пропавшая секция - заголовок `## … {#…}` в значении.
    """
    added = set(after) - set(before) - {section}
    removed = set(before) - set(after)
    if added or removed:
        raise _failed(path, lang, Msg("edit_heading_in_value"))


def _set_anchor(entity: Entity, old: str, value: Any) -> None:
    """Новый якорь секции `old` на всех языках, где она есть; на основном её нет - ошибка."""
    for lang in _with_pages(entity):
        page = entity.pages[lang]
        if lang != entity.ctx.default and page.body.get(old) is None:
            continue
        try:
            entity.pages[lang] = set_field(page, f"sections.{old}.anchor", value)
        except EditError as error:
            raise HeronError(
                code="E039",
                message=Msg(
                    "edit_field_failed",
                    path=f"sections.{old}.anchor",
                    lang=lang,
                    reason=error.args[0],
                ),
            ) from error


def unpublishes(entity: Entity, path: str, lang: str | None = None) -> list[str]:
    """Языки, которые правка `path` снимет с публикации: секции на основном языке ещё нет.

    Новую секцию получат все языки с файлом, и переведённые из них - пометку
    «перевод не готов»: опросник и студия спрашивают подтверждение заранее.
    """
    parts = path.split(".")
    lang = lang or entity.ctx.default
    if len(parts) < 3 or parts[0] != "sections" or parts[1] == "intro":
        return []
    if lang != entity.ctx.default or page_of(entity, lang).body.get(parts[1]) is not None:
        return []
    return [
        code
        for code in entity.ctx.langs[1:]
        if code in entity.pages and not entity.created(code) and not is_pending(entity, code)
    ]


def _category_value(value: Any) -> str:
    text = "" if value in (None, "/") else str(value)
    return norm_key(text)


def mark(entity: Entity, lang: str, pending: bool) -> None:
    """Поставить или снять пометку «перевод не готов» у языка."""
    page = page_of(entity, lang)
    entity.pages[lang] = set_field(page, TRANSLATION, PENDING if pending else None)


def is_pending(entity: Entity, lang: str) -> bool:
    return page_of(entity, lang).front.data.get(TRANSLATION) == PENDING


def move(entity: Entity, target: str) -> None:
    """Перенести (переименовать): новый ключ; для новой - просто другое место.

    Проверки до записи: ключ годен, место свободно на всех языках, категория
    не уезжает внутрь самой себя.
    """
    target = norm_key(target)
    if target == entity.target:
        return
    if entity.key == "" or target == "":
        raise HeronError(code="E005", message=Msg("edit_move_home"))
    if entity.category and (target + "/").startswith(entity.key + "/"):
        raise HeronError(
            code="E005", message=Msg("edit_move_inside", key=entity.key, target=target)
        )
    taken = where(entity.ctx, target)
    if taken is not None:
        raise HeronError(
            code="E004",
            message=Msg("edit_move_taken", key=entity.key or "/", target=target),
            hint=Msg("edit_move_taken_hint"),
        )
    entity.target = target
    if entity.new:
        entity.key = target
        for lang in list(entity.pages):
            page = entity.pages[lang]
            entity.pages[lang] = replace(page, rel=rel_for(lang, target, entity.category))


def untranslated(entity: Entity, lang: str, given: set[str]) -> list[str]:
    """Поля основного языка с текстом, которые для `lang` не перевели."""
    out = []
    for item in fields_of(entity, entity.ctx.default, only_translatable=True):
        if _filled(item.value) and item.path not in given:
            out.append(item.path)
    return out


def issues(entity: Entity, lang: str) -> list[Issue]:
    return validate(page_of(entity, lang), entity.ctx.root)


def problems(entity: Entity, lang: str, with_issues: bool = False) -> Any:
    """Ошибки и предупреждения всех языков строками `язык: поле - текст` (на языке `lang`).

    Ошибки держат запись; предупреждения - нет. У непереведённой копии те же
    замечания, что у основного языка: её предупреждения не повторяются.
    `with_issues` - третьим ещё сами замечания по языкам (студия показывает их у полей).
    """
    errors: list[str] = []
    warnings: list[str] = []
    found: dict[str, list[Issue]] = {}
    for code in entity.ctx.langs:
        found[code] = issues(entity, code)
        for issue in found[code]:
            line = f"{code}: {issue.path} - {issue.message.text(lang)}"
            if issue.level == "error":
                errors.append(line)
            elif code == entity.ctx.default or not is_pending(entity, code):
                warnings.append(line)
    return (errors, warnings, found) if with_issues else (errors, warnings)


# --- секции на всех языках -------------------------------------------------------------


def _section_failed(error: EditError, anchor: str, lang: str) -> HeronError:
    return HeronError(
        code="E039",
        message=Msg(
            "edit_field_failed", path=f"sections.{anchor}", lang=lang, reason=error.args[0]
        ),
    )


def _with_pages(entity: Entity) -> list[str]:
    """Основной язык и языки, у которых страница уже есть (файл или копия в памяти)."""
    default = entity.ctx.default
    page_of(entity, default)
    return [default, *[code for code in entity.ctx.langs[1:] if code in entity.pages]]


def add_section(
    entity: Entity,
    anchor: str,
    heading: str | None = None,
    kind: str | None = None,
    values: dict[str, Any] | None = None,
) -> list[str]:
    """Добавить секцию на всех языках, где у страницы уже есть файл или копия.

    Основной язык получает секцию как есть. Остальные языки с файлом получают
    ту же секцию (заголовок и поля - текст основного языка) и пометку
    «перевод не готов»: новый блок на них ещё не переведён. Языки без файла
    скопируют основной язык при записи. Возвращает языки, получившие пометку.
    """
    from heron.edit import model

    marked: list[str] = []
    for lang in _with_pages(entity):
        try:
            entity.pages[lang] = model.add_section(
                entity.pages[lang], anchor, heading=heading, kind=kind, values=values
            )
        except EditError as error:
            raise _section_failed(error, anchor, lang) from error
        if lang != entity.ctx.default and not entity.created(lang):
            mark(entity, lang, True)
            marked.append(lang)
    return marked


def remove_section(entity: Entity, anchor: str) -> None:
    """Убрать секцию со всех языков, где она есть; на основном её отсутствие - ошибка."""
    from heron.edit import model

    for lang in _with_pages(entity):
        page = entity.pages[lang]
        if lang != entity.ctx.default and page.body.get(anchor) is None:
            continue
        try:
            entity.pages[lang] = model.remove_section(page, anchor)
        except EditError as error:
            raise _section_failed(error, anchor, lang) from error


# --- запись --------------------------------------------------------------------------


@dataclass(slots=True)
class Saved:
    """Что сделала запись: файлы, переносы, 301, site.yaml, попутные категории."""

    created: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    moved: list[tuple[str, str]] = field(default_factory=list)
    redirects: list[tuple[str, str]] = field(default_factory=list)
    site_yaml: bool = False
    categories: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    comments_lost: bool = False


def ensure_category(ctx: Ctx, key: str, saved: Saved) -> None:
    """Категория `key` и все над ней - на всех языках; нет - создаются с заготовкой.

    Заготовка на неосновных языках - с пометкой `translation: pending`. На месте папки
    0.2 со страницами это прячет переведённые страницы внутри: запись до этого
    спрашивает согласия (`drops`).
    """
    if key == "":
        return
    parts = key.split("/")
    for depth in range(1, len(parts) + 1):
        path = "/".join(parts[:depth])
        have = where(ctx, path)
        if have is True:
            continue
        if have is False:
            raise HeronError(
                code="E004",
                message=Msg("edit_key_is_page", key=path),
                hint=Msg("edit_key_kind_hint", key=path),
            )
        entity = open_entity(ctx, path, category=True)
        for lang in ctx.langs[1:]:
            page_of(entity, lang)
        _write_files(entity, saved)
        saved.categories.append(path)


def implicit(ctx: Ctx, folder: str) -> bool:
    """Папка со страницами хоть на одном языке, но без `_index.md` ни на одном (0.2)."""
    if folder == "" or where(ctx, folder) is not None:
        return False
    for lang in ctx.langs:
        base = ctx.root / "content" / lang / folder
        inside = base.is_dir() and paths.inside(ctx.root / "content" / lang, base)
        if inside and any(path.is_file() for path in base.rglob("*.md")):
            return True
    return False


def published_inside(
    ctx: Ctx, folder: str, lang: str, nodes: list[Node] | None = None
) -> list[str]:
    """Переведённые страницы языка внутри папки: файлы, которые прод сейчас публикует.

    Страница с пометкой `translation: pending` и страница внутри непереведённой
    категории (её `_index.md` на этом языке с пометкой) в прод и так не идут.
    """
    nodes = tree(ctx) if nodes is None else nodes
    held = {n.key for n in nodes if n.category and n.langs.get(lang) == "pending"}
    out = []
    for node in nodes:
        if node.implicit or not node.key.startswith(folder + "/"):
            continue
        if node.langs.get(lang) != "ok":
            continue
        parts = node.key.split("/")
        above = ["/".join(parts[:depth]) for depth in range(1, len(parts))]
        if any(key in held for key in above if len(key) > len(folder)):
            continue
        out.append(rel_for(lang, node.key, node.category))
    return out


def drops(entity: Entity) -> dict[str, dict[str, list[str]]]:
    """Переведённые страницы, которые эта запись уберёт из прод: раздел -> язык -> файлы.

    Новая категория на месте папки 0.2 (страницы в ней уже есть) - сама эта
    категория или та, что создаётся попутно над новой или перенесённой страницей:
    язык, на котором её `_index.md` останется с пометкой `translation: pending`, не
    публикует и всё, что внутри. Правило остаётся (непереведённый раздел держит
    свои страницы), поэтому опросник и студия спрашивают подтверждение, а без него
    (`-y`, `--answers` без ответа для языка) запись не идёт - `E039`.
    """
    ctx = entity.ctx
    if not (entity.new or entity.moved):
        return {}
    planned = entity.planned()
    nodes: list[Node] | None = None
    out: dict[str, dict[str, list[str]]] = {}
    folders: list[tuple[str, bool]] = []
    parent = parent_of(entity.target)
    parts = parent.split("/") if parent else []
    for depth in range(1, len(parts) + 1):
        folder = "/".join(parts[:depth])
        if where(ctx, folder) is None:
            folders.append((folder, False))
    if entity.new and entity.category:
        folders.append((entity.target, True))
    for folder, own in folders:
        if not implicit(ctx, folder):
            continue
        nodes = tree(ctx) if nodes is None else nodes
        for lang in ctx.langs[1:]:
            if own and (lang not in planned or not is_pending(entity, lang)):
                continue
            found = published_inside(ctx, folder, lang, nodes)
            if not own and lang in planned and not is_pending(entity, lang):
                found.append(entity.rel(lang))  # сама страница уедет внутрь и тоже пропадёт
            if found:
                out.setdefault(folder, {})[lang] = found
    return out


def consented(entity: Entity, data: Any) -> set[tuple[str, str]]:
    """Что ответы явно разрешили: `<язык>: pending` у категории - её раздел на этом языке."""
    if not isinstance(data, dict) or not entity.category:
        return set()
    out = set()
    for lang, given in data.items():
        if given == PENDING or (isinstance(given, dict) and given.get(TRANSLATION) == PENDING):
            out.add((entity.target, str(lang)))
    return out


def every(found: dict[str, dict[str, list[str]]]) -> set[tuple[str, str]]:
    """Все пары (раздел, язык) из `drops`: человек подтвердил всё, что ему показали."""
    return {(folder, lang) for folder, langs in found.items() for lang in langs}


def _drop_msgs(found: dict[str, dict[str, list[str]]]) -> list[Msg]:
    return [
        Msg("edit_drops", count=len(rels), lang=lang, folder=folder, pages=", ".join(rels))
        for folder, langs in found.items()
        for lang, rels in langs.items()
    ]


def drops_lines(found: dict[str, dict[str, list[str]]], lang: str) -> list[str]:
    """Предупреждения о страницах, которые уйдут из прод, - по строке на раздел и язык."""
    return [message.text(lang) for message in _drop_msgs(found)]


def refuse_drops(
    entity: Entity, found: dict[str, dict[str, list[str]]], allowed: set[tuple[str, str]]
) -> None:
    """Без согласия на пары (раздел, язык) из `found` - `E039` до записи, с тем, что делать."""
    left: dict[str, dict[str, list[str]]] = {}
    for folder, langs in found.items():
        for lang, rels in langs.items():
            if (folder, lang) not in allowed:
                left.setdefault(folder, {})[lang] = rels
    if not left:
        return
    folder = next(iter(left))
    langs = ", ".join(left[folder])
    own = entity.category and entity.new and folder == entity.target
    raise HeronError(
        code="E039",
        message=Msg("edit_drops_refused", key=folder, lines=_drop_msgs(left)),
        hint=Msg("edit_drops_hint" if own else "edit_drops_parent_hint", key=folder, langs=langs),
    )


def save(entity: Entity) -> Saved:
    """Записать всё: попутные категории, перенос с 301, файлы языков, site.yaml.

    Пишутся только языки `entity.planned()` и только файлы, текст которых
    изменился. Недостающие категории на пути создаются при создании и переносе;
    правка страницы в папке без `_index.md` (папка 0.2) категорию не заводит.
    Всё, что пишется, проверяется на выход из папки сайта до первой записи (E024).
    """
    ctx = entity.ctx
    saved = Saved()
    langs = entity.planned()
    for lang in ctx.langs:
        paths.in_site(ctx.root, entity.rel(lang))
        if entity.moved:
            paths.in_site(ctx.root, rel_for(lang, entity.key, entity.category))
    for lang in langs:
        page_of(entity, lang)
    if entity.new or entity.moved:
        ensure_category(ctx, parent_of(entity.target), saved)
    # адреса до записи: перенос и правка slug (страницы или категории) меняют адреса
    before = urls(ctx) if not entity.new else {}
    if entity.moved:
        _move_files(entity, saved)
    _write_files(entity, saved, langs)
    if before:
        _redirects(entity, before, saved)
    changes = dict(entity.site)
    renames = (entity.key, entity.target) if entity.moved else None
    if changes or renames:
        saved.site_yaml, saved.comments_lost = write_site(ctx, changes, renames)
    return saved


def _write_files(entity: Entity, saved: Saved, langs: list[str] | None = None) -> None:
    ctx = entity.ctx
    for lang in ctx.langs if langs is None else langs:
        page = page_of(entity, lang)
        rel = entity.rel(lang)
        target = paths.in_site(ctx.root, rel)
        text = page.text
        if target.is_file() and target.read_bytes() == text.encode("utf-8"):
            continue
        fresh = not target.is_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        (saved.created if fresh else saved.written).append(rel)
        if page.front.data.get(TRANSLATION) == PENDING and lang != ctx.default:
            saved.pending.append(rel)


def _move_files(entity: Entity, saved: Saved) -> None:
    """Файл страницы или папка категории - на новое место на каждом языке."""
    ctx = entity.ctx
    for lang in ctx.langs:
        if entity.disk.get(lang) is None:
            continue
        if entity.category:
            old = ctx.root / "content" / lang / entity.key
            new = ctx.root / "content" / lang / entity.target
            shown = (f"content/{lang}/{entity.key}/", f"content/{lang}/{entity.target}/")
        else:
            old = ctx.root / rel_for(lang, entity.key)
            new = ctx.root / rel_for(lang, entity.target)
            shown = (rel_for(lang, entity.key), rel_for(lang, entity.target))
        paths.in_site(ctx.root, new.relative_to(ctx.root).as_posix())
        new.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old, new)
        saved.moved.append(shown)
    for lang in ctx.langs:
        if lang in entity.pages:
            entity.pages[lang] = replace(entity.pages[lang], rel=entity.rel(lang))


def urls(ctx: Ctx) -> dict[tuple[str, str], str]:
    """Адрес каждой страницы сайта по (язык, ключ) - так же, как его строит сборка."""
    from heron.core import tree

    site, _ = tree.scan(ctx.root / "content", ctx.config, collector=Collector(), drafts=True)
    return {(page.lang, page.key): page.url for page in site.pages}


def _redirects(entity: Entity, before: dict[tuple[str, str], str], saved: Saved) -> None:
    """301 со старых адресов у каждой страницы, чей адрес эта запись поменяла.

    Перенос и переименование (вместе со всем, что было в категории) и правка
    `slug` страницы или категории на любом языке. Новый адрес страницы из её
    `redirect_from` уходит: страница вернулась туда, где уже была (иначе E009).
    """
    ctx = entity.ctx
    after = urls(ctx)
    taken = set(after.values())
    old, new = entity.key, entity.target
    for (lang, key), url in sorted(before.items()):
        moved_key = key
        if entity.moved and (key == old or (entity.category and key.startswith(old + "/"))):
            moved_key = new + key[len(old) :]
        now = after.get((lang, moved_key))
        if now is None or now == url:
            continue
        category = (ctx.root / rel_for(lang, moved_key, True)).is_file()
        rel = rel_for(lang, moved_key, category)
        path = paths.in_site(ctx.root, rel)
        page = _load(ctx, path.read_text(encoding="utf-8"), rel)
        current = page.front.data.get("redirect_from")
        listed = list(current) if isinstance(current, list) else []
        kept = [item for item in listed if _stem(str(item)) != _stem(now)]
        add = url not in taken and _stem(url) not in {_stem(str(item)) for item in kept}
        wanted = [*kept, url] if add else kept
        if wanted == listed:
            continue
        page = set_field(page, "redirect_from", wanted or None)
        path.write_bytes(page.text.encode("utf-8"))
        if add:
            saved.redirects.append((url, now))
        if rel not in saved.written and rel not in saved.created:
            saved.written.append(rel)


def _stem(url: str) -> str:
    """Адрес без завершающего слеша: так сверяет адреса проверка 301 (E009)."""
    return url.strip().rstrip("/") or "/"


def _rename(items: list[Any], old: str, new: str) -> list[Any]:
    out = []
    for item in items:
        text = str(item).strip()
        bare = text.strip("/")
        if bare == old or bare.startswith(old + "/"):
            out.append(new + bare[len(old) :])
        else:
            out.append(item)
    return out


def write_site(
    ctx: Ctx, changes: dict[str, Any], renames: tuple[str, str] | None = None
) -> tuple[bool, bool]:
    """Правки site.yaml (меню, ключи после переноса) с комментариями автора.

    Возвращает (записан ли файл, потерялись ли комментарии). Способ - тот же,
    что у конфигуратора (`heron.setup.comments.carry`).
    """
    from heron.setup import dump
    from heron.setup.comments import carry

    path = paths.in_site(ctx.root, "site.yaml")
    current = path.read_text(encoding="utf-8")
    data = yaml.safe_load(current) or {}
    for dotted, value in changes.items():
        node = data
        parts = dotted.split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
    if renames is not None:
        nav = data.get("nav")
        if isinstance(nav, dict):
            for group, items in list(nav.items()):
                if isinstance(items, list):
                    nav[group] = _rename(items, *renames)
    if data == (yaml.safe_load(current) or {}):
        return False, False
    text = _in_place(current, yaml.safe_load(current) or {}, data)
    if text is not None:
        path.write_text(text, encoding="utf-8")
        return True, False
    text, lost = carry(current, dump(data), "", data)
    path.write_text(text, encoding="utf-8")
    return True, lost


def _in_place(text: str, old: dict[str, Any], new: dict[str, Any]) -> str | None:
    """Правка site.yaml на месте, как SEO-блока: меняются только значения изменённых ключей.

    Список меню в скобках (`main: [/, docs]`) остаётся в скобках, блочный - блочным,
    комментарии и порядок ключей - как были. Не вышло (новая ветка, необычный
    YAML) - None: тогда запись способом конфигуратора.
    """
    from heron.edit import front as fronts
    from heron.edit.text import newline_of

    changed: list[tuple[list[str], Any]] = []

    def walk(a: Any, b: Any, path: list[str]) -> bool:
        if isinstance(a, dict) and isinstance(b, dict):
            for key in set(a) | set(b):
                if key not in a or key not in b:
                    return False
                if a[key] != b[key] and not walk(a[key], b[key], [*path, str(key)]):
                    return False
            return True
        changed.append((path, b))
        return True

    if not walk(old, new, []) or not changed:
        return None
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return None
    nl = newline_of(text)
    for path, value in changed:
        front = fronts.Front(True, 0, len(text), len(text), yaml.safe_load(text), root, raw=text)
        try:
            start, end, piece = fronts.set_value(text, front, path, value, nl)
        except fronts.FrontError:
            return None
        text = text[:start] + piece + text[end:]
        root = yaml.compose(text)
    return text if yaml.safe_load(text) == new else None


# --- ответы для агента: --answers и --dump --------------------------------------------


def dump_answers(entity: Entity) -> dict[str, Any]:
    """Текущие значения полей по языкам - тот же вид, что принимает `apply_answers`.

    Основной язык - все поля, которые можно записать; остальные - поля перевода,
    свои `redirect_from` и `updated` и пометка `translation`. Значения с диска; у новой
    страницы - заготовка.
    """
    ctx = entity.ctx
    out: dict[str, Any] = {"key": entity.target, "kind": KINDS[entity.category]}
    for lang in ctx.langs:
        main = lang == ctx.default
        values: dict[str, Any] = {}
        for item in fields_of(entity, lang):
            if not item.editable:
                continue
            # неосновной язык: перевод и свои адреса и дата (`redirect_from`, `updated`)
            if not main and not translatable(item) and item.path not in PER_LANGUAGE:
                continue
            if not main and item.path == TRANSLATION:
                continue
            values[item.path] = _plain(item.value)
        if not main:
            values[TRANSLATION] = PENDING if is_pending(entity, lang) else None
        out[lang] = values
    return out


def _plain(value: Any) -> Any:
    import datetime as dt

    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _same(item: Field, value: Any) -> bool:
    current = _plain(item.value)
    if not _filled(current) and not _filled(value):
        return True
    return current == value or (isinstance(value, str) and str(current) == value)


def apply_answers(entity: Entity, data: dict[str, Any]) -> list[str]:
    """Записать ответы в страницу (в памяти). Возвращает языки, оставшиеся с пометкой.

    Вид: `key` - новый ключ (перенос), `type` - тип новой страницы, `<язык>:` -
    поля по путям `heron describe` / `--dump` (`title`, `sections.faq.items`);
    у неосновного языка вместо полей можно `pending`. Новая страница: язык без
    перевода всех полей с текстом получает `translation: pending`.
    """
    ctx = entity.ctx
    if not isinstance(data, dict):
        raise HeronError(code="E039", message=Msg("edit_answers_shape"))
    unknown = [name for name in data if name not in ("key", "kind", "type", *ctx.langs)]
    if unknown:
        raise HeronError(
            code="E039",
            message=Msg(
                "edit_answers_unknown",
                names=", ".join(map(str, unknown)),
                langs=", ".join(ctx.langs),
            ),
        )
    if entity.new and data.get("type") not in (None, "", entity.main.type):
        replaced = retype(entity, str(data["type"]))
        entity.pages, entity.key, entity.target = replaced.pages, replaced.key, replaced.target
    target = data.get("key")
    keyed = target not in (None, "") and norm_key(str(target)) != entity.target
    if keyed:
        move(entity, str(target))
    main = data.get(ctx.default) or {}
    if keyed and isinstance(main, dict) and CATEGORY in main:
        # `key` главнее: категория из выгрузки (`--dump`) - старое место, её не применять
        main = {k: v for k, v in main.items() if k != CATEGORY}
    _apply_lang(entity, ctx.default, main)
    pending: list[str] = []
    for lang in ctx.langs[1:]:
        given = data.get(lang)
        created = entity.created(lang)
        if given == PENDING or (given in (None, {}) and created):
            if created:
                if given == PENDING:
                    # `pending` языку без файла - просьба завести копию с пометкой
                    entity.touched.add(lang)
                mark(entity, lang, True)
                if lang in entity.planned():
                    pending.append(lang)
            continue
        if given is None:
            continue
        if not isinstance(given, dict):
            raise HeronError(code="E039", message=Msg("edit_answers_lang", lang=lang))
        _apply_lang(entity, lang, given)
        if created and TRANSLATION not in given:
            left = untranslated(entity, lang, {str(k) for k in given})
            mark(entity, lang, bool(left))
        if is_pending(entity, lang) and lang in entity.planned():
            pending.append(lang)
    return pending


def _apply_lang(entity: Entity, lang: str, values: Any) -> None:
    if not isinstance(values, dict):
        raise HeronError(code="E039", message=Msg("edit_answers_lang", lang=lang))
    known = {item.path: item for item in fields_of(entity, lang, only_translatable=False)}
    # неизвестное поле - E039 до записи, даже если остальные ответы годны
    for path in map(str, values):
        if path not in known and _known(entity, lang, path) is None and not _section_path(path):
            raise _failed(path, lang, Msg("edit_unknown_field", path=path))
    for path, value in values.items():
        path = str(path)
        item = known.get(path)
        if item is not None and _same(item, value):
            continue
        if item is not None and not item.editable:
            raise _failed(path, lang, item.readonly or "-")
        set_value(entity, lang, path, value)
        if path == CATEGORY:
            known = {i.path: i for i in fields_of(entity, lang)}


def _section_path(path: str) -> bool:
    """`sections.<якорь>.<поле>` - поле секции (новой секции в списке полей ещё нет)."""
    parts = path.split(".")
    return len(parts) >= 3 and parts[0] == "sections"
