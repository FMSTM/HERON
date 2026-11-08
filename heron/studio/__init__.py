"""Студия в браузере: вкладка «Страницы» поверх ядра правки страниц.

Студия не хранит своего и не проверяет по-своему. Каждый запрос открывает
страницу или категорию заново с диска (`heron.edit.entity.open_entity`),
применяет к ней действия человека (`ops`: секции) и ответы (`answers` - тот
же вид, что у `heron page add --answers`), а дальше - те же функции, что у
CLI: проверка (`problems`, `issues`), запись без потерь (`save`), дерево
(`tree`), сборка (`heron.core.build`). Нетронутые файлы остаются байт в байт.

Запрос страницы:

    {"target": {"kind": "page", "key": "about", "type": null},
     "ops": [{"op": "add_section", "anchor": "faq", "kind": "faq", "values": {...}}],
     "answers": {"key": "company/about", "ru": {"title": "..."}, "de": "pending"},
     "lang": "ru"}

Картинки ложатся только в `media/` сайта: имя - латиницей, тип - по
расширению и по содержимому, размер ограничен. Ширину и пропорции проверяет
та же проверка полей, что у опросника (`heron.edit.validate`).

Спецификация: docs/ru/spec/21-engine.md, «heron studio».
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from heron.core import paths
from heron.core.errors import HeronError
from heron.edit import entity as ops
from heron.edit.model import groups
from heron.messages import Msg, rendered, say

MAX_IMAGE = 25 * 1024 * 1024
RASTER = (".jpg", ".jpeg", ".png", ".webp", ".gif")
IMAGES = (*RASTER, ".svg")
MEDIA = "media"
KINDS = {"page": False, "category": True}
# SVG проверяет heron.core.svg (XML-парсер, а не поиск по тексту) - тот же, что у heron check.


HERE = Path(__file__).parent


def asset(name: str) -> bytes:
    """Файл страницы студии: `studio.js` и `studio.css` (отдаёт сервер конфигуратора)."""
    return (HERE / name).read_bytes()


# --- сайт и дерево -----------------------------------------------------------------------


def context(root: Path, lang: str) -> ops.Ctx:
    """Тема, конфиг и контракт на языке интерфейса студии (ru, en)."""
    return ops.context(Path(root), lang if lang in ("ru", "en") else "en")


def _types(ctx: ops.Ctx) -> list[dict[str, Any]]:
    out = []
    for item in ctx.contract.get("types", []):
        views = item.get("views") or None
        out.append(
            {
                "name": item["name"],
                "hint": item.get("hint"),
                "help": item.get("help"),
                "children_type": item.get("children_type"),
                "views": views,
            }
        )
    return out


def tree(root: Path, lang: str) -> dict[str, Any]:
    """Дерево категорий и страниц всех языков - как у `heron page list --json`."""
    ctx = context(root, lang)
    nodes = ops.tree(ctx)
    return {
        "languages": ctx.langs,
        "default_lang": ctx.default,
        "items": [
            {
                "key": node.key,
                "category": node.category,
                "type": node.type,
                "title": node.title,
                "langs": node.langs,
                "implicit": node.implicit,
            }
            for node in nodes
        ],
        "types": _types(ctx),
        "default_type": {
            "page": ops.default_type(ctx, "new", False),
            "category": ops.default_type(ctx, "new", True),
        },
    }


# --- страница или категория --------------------------------------------------------------


def _text(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise HeronError(code="E039", message=Msg("studio_bad_request", field=field))
    return value


def open_target(ctx: ops.Ctx, target: Any) -> ops.Entity:
    """Объект запроса: `{"kind": "page"|"category", "key": …, "type": …}`."""
    if not isinstance(target, dict) or target.get("kind") not in KINDS:
        raise HeronError(code="E039", message=Msg("studio_bad_request", field="target"))
    return ops.open_entity(
        ctx,
        str(target.get("key") or ""),
        KINDS[target["kind"]],
        page_type=_text(target.get("type"), "target.type"),
        children_type=_text(target.get("children_type"), "target.children_type"),
        view=_text(target.get("view"), "target.view"),
        title=_text(target.get("title"), "target.title"),
    )


def _auto_kinds(ctx: ops.Ctx) -> dict[str, dict[str, Any]]:
    """Формы, которые движок узнаёт по содержимому, кроме прозы: им нужен первый пункт."""
    out = {}
    for module in ctx.contract.get("modules", []):
        for item in module.get("kinds", []):
            if item.get("auto") and item["kind"] != "prose":
                out[item["kind"]] = module
    return out


def apply_ops(entity: ops.Entity, items: Any) -> list[str]:
    """Действия над секциями до ответов: добавить и убрать - на всех языках сразу."""
    if items in (None, []):
        return []
    if not isinstance(items, list):
        raise HeronError(code="E039", message=Msg("studio_bad_request", field="ops"))
    marked: list[str] = []
    auto = _auto_kinds(entity.ctx)
    for item in items:
        if not isinstance(item, dict):
            raise HeronError(code="E039", message=Msg("studio_bad_request", field="ops"))
        name = item.get("op")
        anchor = str(item.get("anchor") or "").strip()
        if name == "add_section":
            kind = _text(item.get("kind"), "ops.kind")
            values = item.get("values") or None
            if values is not None and not isinstance(values, dict):
                raise HeronError(code="E039", message=Msg("studio_bad_request", field="values"))
            if kind in auto and not values:
                raise HeronError(code="E039", message=Msg("studio_section_values", kind=kind))
            marked += ops.add_section(
                entity,
                anchor,
                heading=_text(item.get("heading"), "heading"),
                kind=kind,
                values=values,
            )
        elif name == "remove_section":
            ops.remove_section(entity, anchor)
        else:
            raise HeronError(code="E039", message=Msg("studio_bad_request", field="op"))
    return sorted(set(marked))


def prepare(root: Path, request: dict[str, Any], lang: str) -> ops.Entity:
    """Объект с диска, затем секции (`ops`), затем ответы - как `page add --answers`."""
    return _prepare(root, request, lang)[0]


def _prepare(root: Path, request: dict[str, Any], lang: str) -> tuple[ops.Entity, list[str]]:
    """Объект, и какие языки правка снимет с публикации (были переведены, станут pending)."""
    ctx = context(root, lang)
    entity = open_target(ctx, request.get("target"))
    was = {code: ops.is_pending(entity, code) for code in ctx.langs if code in entity.pages}
    apply_ops(entity, request.get("ops"))
    answers = request.get("answers") or {}
    if answers:
        ops.apply_answers(entity, answers)
    lost = [
        code
        for code in ctx.langs[1:]
        if code in was and not was[code] and ops.is_pending(entity, code)
    ]
    return entity, lost


def _sections(entity: ops.Entity) -> dict[str, Any]:
    """Что есть на странице и что можно добавить: секции типа и формы тем."""
    page = entity.main
    present = [
        {"id": s.id, "kind": s.kind, "module": s.module}
        for s in page.body.sections
        if s.id != "intro"
    ]
    have = {s["id"] for s in present}
    info = next((t for t in entity.ctx.contract.get("types", []) if t["name"] == page.type), {})
    suggested = [
        {"id": s["id"], "kind": s.get("kind"), "hint": s.get("hint"), "required": s["required"]}
        for s in info.get("sections", [])
        if not s.get("any") and s["id"] != "intro" and s["id"] not in have
    ]
    free = any(s.get("any") for s in info.get("sections", []))
    kinds = []
    for module in entity.ctx.contract.get("modules", []):
        if module.get("scope") == "page":
            continue
        for item in module.get("kinds", []):
            kinds.append(
                {
                    "kind": item["kind"],
                    "module": module["name"],
                    "class": None if item.get("auto") else item.get("class"),
                    "auto": bool(item.get("auto")),
                    "hint": module.get("hint"),
                    "help": module.get("help"),
                    "example": module.get("example"),
                    "fields": module.get("fields") or [],
                }
            )
    return {
        "present": present,
        "suggested": suggested,
        "free": free,
        "kinds": kinds,
        "readonly": say(entity.ctx.notes, "edit_ro_body", reason=page.body.error)
        if page.body.error is not None
        else None,
    }


def state(entity: ops.Entity, lang: str) -> dict[str, Any]:
    """Всё для формы: поля по языкам, группы, файлы, пометки, замечания, секции."""
    ctx = entity.ctx
    fields: dict[str, list[dict[str, Any]]] = {}
    issues: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, dict[str, Any]] = {}
    for code in ctx.langs:
        main = code == ctx.default
        fields[code] = [
            item.to_dict() for item in ops.fields_of(entity, code, only_translatable=not main)
        ]
        files[code] = {
            "rel": entity.rel(code),
            "exists": entity.disk.get(code) is not None,
            # запись создаст или поправит этот файл (у правки - только языки с файлом и тронутые)
            "planned": code in entity.planned(),
            "pending": ops.is_pending(entity, code),
        }
    errors, warnings, found = ops.problems(entity, lang, with_issues=True)
    for code in ctx.langs:
        issues[code] = [issue.to_dict(lang) for issue in found[code]]
    return {
        "target": {"kind": "category" if entity.category else "page", "key": entity.target},
        "key": entity.key,
        "new": entity.new,
        "moved": entity.moved,
        "type": entity.main.type,
        "languages": ctx.langs,
        "default_lang": ctx.default,
        "groups": groups(entity.main),
        "fields": fields,
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
        "files": files,
        "site": entity.site,
        "sections": _sections(entity),
    }


def check(root: Path, request: dict[str, Any], lang: str) -> dict[str, Any]:
    """Проверка на лету: что получится после правок, ничего не записывая."""
    return state(prepare(root, request, lang), lang)


def save(root: Path, request: dict[str, Any], lang: str) -> dict[str, Any]:
    """Записать правки теми же функциями, что `heron page add`: ошибки полей - E039.

    Новый блок снимает переведённые языки с публикации (пометка «перевод не
    готов»): без `confirm_pending` запись не идёт, ответ называет эти языки -
    страница спрашивает человека и повторяет запрос с подтверждением.
    """
    entity, lost = _prepare(root, request, lang)
    if lost and not request.get("confirm_pending"):
        return {
            "confirm": {
                "langs": lost,
                "message": say(lang, "studio_confirm_pending", langs=", ".join(lost)),
            }
        }
    errors, _warnings = ops.problems(entity, lang)
    if errors:
        raise HeronError(
            code="E039",
            message=Msg("edit_invalid", lines=errors),
            hint=Msg("studio_invalid_hint"),
        )
    saved = ops.save(entity) if entity.changed() else ops.Saved()
    target = {"kind": "category" if entity.category else "page", "key": entity.target}
    fresh = open_target(context(root, lang), target)
    return {
        "saved": {
            "created": saved.created,
            "written": saved.written,
            "moved": [list(pair) for pair in saved.moved],
            "redirects": [list(pair) for pair in saved.redirects],
            "site_yaml": saved.site_yaml,
            "categories": saved.categories,
            "pending": saved.pending,
            "comments_lost": saved.comments_lost,
        },
        "state": state(fresh, lang),
    }


# --- картинки ----------------------------------------------------------------------------


def media_name(name: str) -> str:
    """Имя файла в media/: латиница, цифры и дефисы, расширение картинки - или E039."""
    base = Path(str(name or "")).name
    stem, dot, ext = base.rpartition(".")
    ext = f".{ext.lower()}" if dot else ""
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in IMAGES:
        raise HeronError(
            code="E039",
            message=Msg("studio_upload_type", name=base or "-", kinds=", ".join(IMAGES)),
        )
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return f"{slug or 'image'}{ext}"


def _verify(data: bytes, ext: str, name: str) -> tuple[int | None, int | None]:
    """Содержимое - картинка своего типа: растр читается Pillow, SVG без скриптов."""
    if ext == ".svg":
        head = data[:2048].lstrip()
        if b"<svg" not in data[:4096] or not head.startswith((b"<", b"\xef\xbb\xbf<")):
            raise HeronError(code="E039", message=Msg("studio_upload_bad", name=name))
        if not svg_safe(data):
            raise HeronError(code="E039", message=Msg("studio_upload_svg", name=name))
        return None, None
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            kind = (image.format or "").lower()
            width, height = image.size
    except Exception as error:  # noqa: BLE001 - любой сбой разбора - не картинка
        raise HeronError(code="E039", message=Msg("studio_upload_bad", name=name)) from error
    want = {".jpg": "jpeg", ".png": "png", ".webp": "webp", ".gif": "gif"}[ext]
    if kind != want:
        raise HeronError(code="E039", message=Msg("studio_upload_bad", name=name))
    return width, height


def svg_safe(data: bytes) -> bool:
    """SVG без исполняемого и без внешних ссылок (`heron.core.svg`, как у `heron check`)."""
    from heron.core import svg

    return svg.safe(data)


def upload(root: Path, name: str, data: bytes) -> dict[str, Any]:
    """Положить картинку в media/ сайта. Такой же файл уже есть - он же; имя занято - `-2`."""
    if len(data) > MAX_IMAGE:
        raise HeronError(
            code="E039", message=Msg("studio_upload_large", mb=MAX_IMAGE // (1024 * 1024))
        )
    if not data:
        raise HeronError(code="E039", message=Msg("studio_upload_bad", name=name or "-"))
    clean = media_name(name)
    stem, ext = clean.rsplit(".", 1)
    width, height = _verify(data, f".{ext}", clean)
    folder = paths.in_site(root, MEDIA)
    folder.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000):
        rel = f"{MEDIA}/{stem}{'' if number == 1 else f'-{number}'}.{ext}"
        target = paths.in_site(root, rel)
        if target.is_file():
            if target.read_bytes() == data:
                return {"path": rel, "width": width, "height": height, "reused": True}
            continue
        _write_new(target, data)
        return {"path": rel, "width": width, "height": height, "reused": False}
    raise HeronError(code="E039", message=Msg("studio_upload_bad", name=clean))


def _write_new(target: Path, data: bytes) -> None:
    """Новый файл: создаётся исключительно (O_EXCL), чужой файл не перезаписывается."""
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb") as out:
        out.write(data)


def media_file(root: Path, rel: str) -> Path | None:
    """Картинка из media/ для превью в форме: только media/ и только картинки."""
    rel = rel.lstrip("/")
    if not rel.startswith(f"{MEDIA}/") or not rel.lower().endswith(IMAGES):
        return None
    try:
        path = paths.in_site(root, rel)
    except HeronError:
        return None
    return path if path.is_file() else None


# --- проверка и просмотр -----------------------------------------------------------------


def _error(item: HeronError, lang: str) -> dict[str, Any]:
    return {
        "code": item.code,
        "path": rendered(item.path, lang),
        "line": item.line,
        "message": rendered(item.message, lang),
        "hint": rendered(item.hint, lang),
    }


def site_check(root: Path, lang: str) -> dict[str, Any]:
    """Кнопка «Проверить»: тот же `heron check`, что в терминале (черновики включены)."""
    from heron.core import build

    try:
        result = build.check(Path(root), drafts=True, notes_lang=lang)
    except HeronError as error:
        return {"ok": False, "errors": [_error(error, lang)], "warnings": []}
    errors = [_error(item, lang) for item in result.collector.errors]
    warnings = [
        {
            "path": rendered(item.path, lang),
            "line": item.line,
            "message": rendered(item.message, lang),
        }
        for item in result.collector.warnings
    ]
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def preview_dist() -> tempfile.TemporaryDirectory:
    """Папка просмотра студии - вне папки сайта, как у `heron serve`."""
    return tempfile.TemporaryDirectory(prefix="heron-studio-")


def preview(root: Path, dist: Path, lang: str, target: Any = None) -> dict[str, Any]:
    """Кнопка «Посмотреть» и вкладка «Справка темы»: черновая сборка, как у `heron serve`.

    Возвращает адрес страницы `target` на каждом языке и адрес справки темы.
    """
    from heron.core import build
    from heron.core.render import themeref

    root = Path(root)
    try:
        result = build.run(root, dist=dist, drafts=True, notes_lang=lang)
    except HeronError as error:
        return {"ok": False, "errors": [_error(error, lang)]}
    errors = [_error(item, lang) for item in result.collector.errors]
    ctx = context(root, lang)
    urls: dict[str, str] = {}
    if isinstance(target, dict) and target.get("kind") in KINDS:
        key = ops.norm_key(str(target.get("key") or ""))
        for (code, page_key), url in ops.urls(ctx).items():
            if page_key == key:
                urls[code] = url
    return {
        "ok": not errors,
        "errors": errors,
        "urls": urls,
        "ref": themeref.url_for(ctx.config, ctx.default),
    }
