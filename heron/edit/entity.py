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

from heron.contracts.frontmatter import PENDING
from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core import paths
from heron.core.errors import Collector, HeronError
from heron.core.parser.frontmatter import FRONTMATTER
from heron.edit.langs import folder_type, key_of, rel_for
from heron.edit.model import INDEX, Field, Page, fields, load, set_field
from heron.edit.slots import EditError
from heron.edit.validate import Issue, validate
from heron.messages import Msg

# Служебные поля, у которых на каждом языке свой текст; остальные (тип, порядок,
# обложка, флаги) общие и при создании копируются с основного языка.
TRANSLATABLE = frozenset(
    {"title", "h1", "description", "nav_title", "slug", "image_alt", "og_title", "og_description"}
)
CATEGORY = "category"
TRANSLATION = "translation"
MENU = "menu"
HOME_KEYS = ("", "/")
KINDS = {False: "page", True: "category"}


def translatable(item: Field) -> bool:
    """Поле со своим текстом на каждом языке: его спрашивают при переводе."""
    if not item.editable:
        return False
    if item.where == "frontmatter":
        return item.name in TRANSLATABLE
    if item.where == "heading":
        return item.name == "heading"
    if item.where == "body":
        return item.type in ("text", "markdown", "list")
    return False


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

    @property
    def main(self) -> Page:
        return self.pages[self.ctx.default]

    @property
    def moved(self) -> bool:
        return not self.new and self.target != self.key

    def created(self, lang: str) -> bool:
        return self.disk.get(lang) is None

    def missing(self) -> list[str]:
        """Языки без файла: при сохранении получат копию основного языка и пометку."""
        return [lang for lang in self.ctx.langs if self.disk.get(lang) is None]

    def rel(self, lang: str, key: str | None = None) -> str:
        return rel_for(lang, self.target if key is None else key, self.category)


def _types(ctx: Ctx) -> list[str]:
    return list(ctx.theme.types)


def _check_type(ctx: Ctx, name: str) -> str:
    if name not in ctx.theme.types:
        known = ", ".join(ctx.theme.types)
        raise HeronError(
            code="E008",
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
            code="E008",
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
    """Копия основного языка для нового файла языка `lang`, с пометкой «перевод не готов»."""
    page = _load(entity.ctx, entity.main.text, rel_for(lang, entity.key, entity.category))
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
    """Записать поле языка; `category` - перенос, `menu` - правка site.yaml (общая)."""
    if path == CATEGORY:
        move(entity, join(_category_value(value), name_of(entity.target)))
        return
    page = page_of(entity, lang)
    try:
        page = set_field(page, path, value)
    except EditError as error:
        raise HeronError(
            code="E039",
            message=Msg("edit_field_failed", path=path, lang=lang, reason=error.args[0]),
        ) from error
    if path == MENU:
        entity.site.update(page.site)
    entity.pages[lang] = page


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
    """Категория `key` и все над ней - на всех языках; нет - создаются с заготовкой."""
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


def save(entity: Entity) -> Saved:
    """Записать всё: попутные категории, перенос с 301, файлы языков, site.yaml.

    Всё, что пишется, проверяется на выход из папки сайта до первой записи (E024).
    """
    ctx = entity.ctx
    saved = Saved()
    for lang in ctx.langs:
        paths.in_site(ctx.root, entity.rel(lang))
        if entity.moved:
            paths.in_site(ctx.root, rel_for(lang, entity.key, entity.category))
    for lang in ctx.langs:
        page_of(entity, lang)
    ensure_category(ctx, parent_of(entity.target), saved)
    before = _urls(ctx) if entity.moved else {}
    if entity.moved:
        _move_files(entity, saved)
    _write_files(entity, saved)
    if entity.moved:
        _redirects(entity, before, saved)
    changes = dict(entity.site)
    renames = (entity.key, entity.target) if entity.moved else None
    if changes or renames:
        saved.site_yaml, saved.comments_lost = write_site(ctx, changes, renames)
    return saved


def _write_files(entity: Entity, saved: Saved) -> None:
    ctx = entity.ctx
    for lang in ctx.langs:
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
        entity.disk[lang] = entity.disk.get(lang)
        page = entity.pages[lang]
        entity.pages[lang] = replace(page, rel=entity.rel(lang))


def _urls(ctx: Ctx) -> dict[tuple[str, str], str]:
    """Адрес каждой страницы сайта по (язык, ключ) - так же, как его строит сборка."""
    from heron.core import tree

    site, _ = tree.scan(ctx.root / "content", ctx.config, collector=Collector(), drafts=True)
    return {(page.lang, page.key): page.url for page in site.pages}


def _redirects(entity: Entity, before: dict[tuple[str, str], str], saved: Saved) -> None:
    """301 со старых адресов: у перенесённой страницы и у всего, что было в категории."""
    ctx = entity.ctx
    after = _urls(ctx)
    taken = set(after.values())
    old, new = entity.key, entity.target
    for (lang, key), url in sorted(before.items()):
        if key != old and not (entity.category and key.startswith(old + "/")):
            continue
        moved_key = new + key[len(old) :]
        now = after.get((lang, moved_key))
        if now is None or now == url or url in taken:
            continue
        category = (ctx.root / rel_for(lang, moved_key, True)).is_file()
        rel = rel_for(lang, moved_key, category)
        path = paths.in_site(ctx.root, rel)
        page = _load(ctx, path.read_text(encoding="utf-8"), rel)
        current = page.front.data.get("redirect_from")
        listed = list(current) if isinstance(current, list) else []
        if url in listed:
            continue
        page = set_field(page, "redirect_from", [*listed, url])
        path.write_bytes(page.text.encode("utf-8"))
        saved.redirects.append((url, now))
        if rel not in saved.written and rel not in saved.created:
            saved.written.append(rel)


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
    text, lost = carry(current, dump(data), "", data)
    path.write_text(text, encoding="utf-8")
    return True, lost


# --- ответы для агента: --answers и --dump --------------------------------------------


def dump_answers(entity: Entity) -> dict[str, Any]:
    """Текущие значения полей по языкам - тот же вид, что принимает `apply_answers`.

    Основной язык - все поля, которые можно записать; остальные - поля перевода
    и пометка `translation`. Значения с диска; у новой страницы - заготовка.
    """
    ctx = entity.ctx
    out: dict[str, Any] = {"key": entity.target, "kind": KINDS[entity.category]}
    for lang in ctx.langs:
        main = lang == ctx.default
        values: dict[str, Any] = {}
        for item in fields_of(entity, lang, only_translatable=not main):
            if not item.editable:
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
    if target not in (None, "") and norm_key(str(target)) != entity.target:
        move(entity, str(target))
    _apply_lang(entity, ctx.default, data.get(ctx.default) or {})
    pending: list[str] = []
    for lang in ctx.langs[1:]:
        given = data.get(lang)
        created = entity.created(lang)
        if given == PENDING or (given in (None, {}) and created):
            if created:
                mark(entity, lang, True)
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
        if is_pending(entity, lang):
            pending.append(lang)
    return pending


def _apply_lang(entity: Entity, lang: str, values: Any) -> None:
    if not isinstance(values, dict):
        raise HeronError(code="E039", message=Msg("edit_answers_lang", lang=lang))
    known = {item.path: item for item in fields_of(entity, lang, only_translatable=False)}
    for path, value in values.items():
        path = str(path)
        item = known.get(path)
        if item is not None and _same(item, value):
            continue
        if item is not None and not item.editable:
            raise HeronError(
                code="E039",
                message=Msg("edit_field_failed", path=path, lang=lang, reason=item.readonly or "-"),
            )
        set_value(entity, lang, path, value)
        if path == CATEGORY:
            known = {i.path: i for i in fields_of(entity, lang)}
