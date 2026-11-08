"""Проверка страницы на лету: те же правила, что у `heron check`, и ограничения контракта.

SEO-блок проверяет та же модель, что у сборки (`PageMeta`): ошибки разбора и
мягкие замечания (`lint`: длина `title`/`description`, `title` = `h1`,
`image` без `image_alt`) - слово в слово. Сверх этого - то, что знает контракт
темы: обязательные поля и секции, длина, число пунктов, допустимые значения,
картинка (есть ли файл, ширина, пропорции) и разметка schema.org страницы
(тип есть в словаре, свойство есть у типа).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from heron.contracts.frontmatter import PageMeta
from heron.contracts.loader import describe
from heron.core.parser.frontmatter import REQUIRED
from heron.edit.model import Field, Page, fields
from heron.messages import Msg

# Ключ замечания lint → поле, к которому оно относится.
LINT_FIELD = {
    "loader_fm_title_long": "title",
    "loader_fm_description_long": "description",
    "loader_fm_image_alt": "image_alt",
    "loader_fm_title_h1_same": "h1",
}
RATIO_TOLERANCE = 0.02


@dataclass(frozen=True, slots=True)
class Issue:
    """Замечание к полю: `level` - `error` (не соберётся или поле обязательно) или `warning`."""

    path: str
    level: str
    message: Msg

    def to_dict(self, lang: str) -> dict[str, Any]:
        return {"path": self.path, "level": self.level, "message": self.message.text(lang)}


def validate(page: Page, site_root: Path | None = None) -> list[Issue]:
    """Все замечания к странице. `site_root` - проверять ещё и файлы картинок."""
    out: list[Issue] = []
    out.extend(_front(page))
    if page.body.error is not None:
        out.append(Issue("sections", "error", Msg("edit_ro_body", reason=page.body.error)))
    for item in fields(page):
        out.extend(_field(page, item, site_root))
    out.extend(_sections(page))
    return out


def _front(page: Page) -> list[Issue]:
    if page.front.error is not None:
        return [Issue("front", "error", Msg("edit_ro_front"))]
    data = page.front.data
    missing = [name for name in REQUIRED if not str(data.get(name, "") or "").strip()]
    out = [Issue(name, "error", Msg("edit_required", field=name)) for name in missing]
    if missing:
        return out
    try:
        meta = PageMeta.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors():
            where = str(error["loc"][0]) if error.get("loc") else "front"
            out.append(Issue(where, "error", describe(error)))
        return out
    for warning in meta.lint(page.rel or ""):
        message = warning.message
        key = getattr(message, "key", "")
        out.append(Issue(LINT_FIELD.get(key, "front"), "warning", message))  # type: ignore[arg-type]
    return out


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str | list | dict) and not value)


def _field(page: Page, item: Field, site_root: Path | None) -> list[Issue]:
    out: list[Issue] = []
    value = item.value
    limits = item.limits
    # обязательность SEO-блока проверяет _front, секции без файла - _sections
    seo = item.where == "frontmatter" and item.name in REQUIRED
    # вводный блок есть всегда, даже пустой: его обязательное поле пустым не бывает
    in_file = item.section in (None, "intro") or _section_present(page, item.section)
    if not seo and item.required and _empty(value) and in_file:
        out.append(Issue(item.path, "error", Msg("edit_required", field=item.path)))
    if item.type == "schema":
        return _schema(item)
    if item.type == "enum":
        values = limits.get("values") or []
        if not _empty(value) and values and str(value) not in values:
            out.append(
                Issue(
                    item.path,
                    "error"
                    if item.name in ("type", "children_type") or item.group == "theme"
                    else "warning",
                    Msg(
                        "edit_not_in_values",
                        field=item.path,
                        value=str(value),
                        values=", ".join(values),
                    ),
                )
            )
    out.extend(_text_limits(item.path, value, limits, skip=item.name in LINT_FIELD.values()))
    if item.type == "list" and isinstance(value, list):
        out.extend(_count(item.path, value, limits))
        out.extend(_entries(item, value, site_root))
    if item.type == "image" and isinstance(value, str) and value and site_root is not None:
        width = limits.get("min_width") or _cover_width(page, item)
        out.extend(_image(item.path, value, width, limits.get("ratio"), site_root))
    return out


def _section_present(page: Page, section: str) -> bool:
    found = page.body.get(section)
    return found is not None and (section != "intro" or found.present)


def _cover_width(page: Page, item: Field) -> int | None:
    if item.where != "frontmatter":
        return None
    service = page.contract.get("service", {}).get("page", [])
    spec = next((s for s in service if s["name"] == item.name), None)
    return spec.get("min_width") if spec else None


def _text_limits(path: str, value: Any, limits: dict[str, Any], skip: bool = False) -> list[Issue]:
    if not isinstance(value, str) or not value or skip:
        return []
    out = []
    length = len(value.strip())
    if limits.get("max_length") and length > limits["max_length"]:
        out.append(
            Issue(
                path,
                "warning",
                Msg("edit_too_long", field=path, length=length, max=limits["max_length"]),
            )
        )
    if limits.get("min_length") and length < limits["min_length"]:
        out.append(
            Issue(
                path,
                "warning",
                Msg("edit_too_short", field=path, length=length, min=limits["min_length"]),
            )
        )
    return out


def _count(path: str, value: list, limits: dict[str, Any]) -> list[Issue]:
    out = []
    if value and limits.get("min_items") and len(value) < limits["min_items"]:
        out.append(
            Issue(
                path,
                "warning",
                Msg("edit_few_items", field=path, count=len(value), min=limits["min_items"]),
            )
        )
    if limits.get("max_items") and len(value) > limits["max_items"]:
        out.append(
            Issue(
                path,
                "warning",
                Msg("edit_many_items", field=path, count=len(value), max=limits["max_items"]),
            )
        )
    return out


def _entries(item: Field, value: list, site_root: Path | None) -> list[Issue]:
    """Поля пунктов списка: обязательность, длина, картинки."""
    out: list[Issue] = []
    subs = item.fields or []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            out.extend(_text_limits(f"{item.path}.{index}", entry, item.limits))
            continue
        for sub in subs:
            path = f"{item.path}.{index}.{sub['name']}"
            got = entry.get(sub["name"])
            if sub.get("required") and _empty(got):
                out.append(Issue(path, "error", Msg("edit_required", field=path)))
            limits = {k: sub.get(k) for k in ("max_length", "min_length", "min_items", "max_items")}
            out.extend(_text_limits(path, got, limits))
            if sub.get("type") == "list" and isinstance(got, list):
                out.extend(_count(path, got, limits))
            if sub.get("type") == "image" and isinstance(got, str) and got and site_root:
                out.extend(_image(path, got, sub.get("min_width"), sub.get("ratio"), site_root))
    return out


def _image(
    path: str, src: str, min_width: int | None, ratio: str | None, site_root: Path
) -> list[Issue]:
    from heron.core import media, paths
    from heron.core.errors import HeronError

    if "://" in src:
        return []
    # те же правила, что у `heron check` (media.locate и media.verify): картинка - только
    # из media/ сайта (иначе E024), и файл есть на диске (иначе E007). Это ошибки: запись
    # не идёт, как не пройдёт и проверка
    rel = paths.normalize(src)
    head, _, rest = rel.partition("/")
    try:
        if head not in media.FOLDERS or not rest:
            raise HeronError(code=paths.CODE, message="")
        source = paths.source(site_root / head, rest)
    except HeronError:
        return [Issue(path, "error", Msg("edit_image_outside", field=path, src=src))]
    if not source.is_file():
        return [Issue(path, "error", Msg("edit_image_missing", field=path, src=src))]
    if source.suffix.lower() not in media.KEEP:
        return []
    try:
        shape = media.shape_of(source)
    except media.BAD_MASTER:
        return [Issue(path, "warning", Msg("edit_image_unreadable", field=path, src=src))]
    out = []
    if min_width and shape.width < min_width:
        out.append(
            Issue(
                path,
                "warning",
                Msg("edit_image_narrow", field=path, src=src, width=shape.width, min=min_width),
            )
        )
    if ratio and shape.height:
        a, b = (int(x) for x in ratio.split(":"))
        actual = shape.width / shape.height
        if abs(actual - a / b) > RATIO_TOLERANCE * (a / b):
            out.append(
                Issue(
                    path,
                    "warning",
                    Msg(
                        "edit_image_ratio",
                        field=path,
                        src=src,
                        actual=f"{shape.width}:{shape.height}",
                        ratio=ratio,
                    ),
                )
            )
    return out


def _schema(item: Field) -> list[Issue]:
    from heron.schemaorg import vocab

    words = vocab()
    kind = item.name
    if not words.is_type(kind):
        return [Issue(item.path, "warning", Msg("edit_schema_type", kind=kind))]
    out = []
    for prop in item.value or {}:
        if not words.allows(kind, str(prop)):
            out.append(
                Issue(
                    f"{item.path}.{prop}", "warning", Msg("edit_schema_prop", kind=kind, prop=prop)
                )
            )
    return out


def _sections(page: Page) -> list[Issue]:
    info = next((t for t in page.contract.get("types", []) if t["name"] == page.type), None)
    out = []
    for section in (info or {}).get("sections", []):
        needed = section.get("required") and not section.get("any")
        if needed and not _section_present(page, section["id"]):
            out.append(
                Issue(
                    f"sections.{section['id']}",
                    "warning",
                    Msg("edit_section_missing", section=section["id"]),
                )
            )
    return out
