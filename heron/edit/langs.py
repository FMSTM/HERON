"""Одна страница на всех языках сайта: какие файлы есть, каких нет, какой у неё тип.

Ключ страницы - путь от папки языка без `.md`, как у сборки (`core/tree.py`):
`""` - главная (`index.md`), `about` - `about.md`, `services/roofing` -
`services/roofing.md` или категория `services/roofing/_index.md`. Переводы
связаны ключом, а не адресом: у каждого языка свой `slug`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from heron.contracts.site import SiteConfig
from heron.core import yamlsafe
from heron.core.parser.frontmatter import FRONTMATTER
from heron.edit.model import DEFAULT_TYPE, HOME_TYPE, INDEX, Page, load


@dataclass(frozen=True, slots=True)
class LangFile:
    """Файл страницы на одном языке: путь от корня сайта и есть ли он на диске."""

    lang: str
    rel: str
    exists: bool
    default: bool = False


def rel_for(lang: str, key: str, category: bool = False) -> str:
    """Путь файла страницы `key` на языке `lang`."""
    key = key.strip("/")
    if key == "":
        return f"content/{lang}/index.md"
    if category:
        return f"content/{lang}/{key}/{INDEX}"
    return f"content/{lang}/{key}.md"


def key_of(rel: str) -> tuple[str, str, bool] | None:
    """(язык, ключ, категория ли) по пути `content/<язык>/…`; не страница - None."""
    parts = list(PurePosixPath(rel).parts)
    if len(parts) < 3 or parts[0] != "content" or not parts[-1].endswith(".md"):
        return None
    lang, inner = parts[1], parts[2:]
    name = inner.pop()
    if name == INDEX:
        return lang, "/".join(inner), True
    if name == "index.md" and not inner:
        return lang, "", False
    return lang, "/".join([*inner, name[: -len(".md")]]), False


def files(
    site_root: Path, config: SiteConfig, key: str, category: bool | None = None
) -> list[LangFile]:
    """Файлы страницы `key` на каждом языке `site.yaml`, основной язык первым.

    `category` не задан - форма та, что уже есть хоть на одном языке
    (категория `key/_index.md` или страница `key.md`); нигде нет - страница.
    """
    langs = list(config.site.languages)
    default = config.site.default_lang
    langs = [default] + [lang for lang in langs if lang != default]
    if category is None:
        category = any(
            (site_root / rel_for(lang, key, True)).is_file() for lang in langs
        ) and not any((site_root / rel_for(lang, key, False)).is_file() for lang in langs)
    out = []
    for lang in langs:
        rel = rel_for(lang, key, category)
        out.append(LangFile(lang, rel, (site_root / rel).is_file(), lang == default))
    return out


def missing(
    site_root: Path, config: SiteConfig, key: str, category: bool | None = None
) -> list[str]:
    """Языки, на которых страницы `key` ещё нет."""
    return [item.lang for item in files(site_root, config, key, category) if not item.exists]


def _index_data(path: Path) -> dict[str, Any]:
    try:
        match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
        data = yamlsafe.load(match.group("body")) if match else None
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def folder_type(site_root: Path, rel: str) -> str:
    """Тип, который файлу даёт его место, если в SEO-блоке нет `type` (правило сборки).

    Страница - `children_type` своей папки, иначе `page`; категория -
    `children_type` родительской папки, иначе `page`; главная - `home`,
    `404.md` в корне языка - `404`. `type` в самом файле важнее - его читает `load`.
    """
    found = key_of(rel)
    if found is None:
        return DEFAULT_TYPE
    lang, key, category = found
    lang_root = site_root / "content" / lang
    parts = key.split("/") if key else []
    if not category:
        if key == "":
            return HOME_TYPE
        if key == "404":
            return "404"
        folder = parts[:-1]
        own = _index_data(lang_root.joinpath(*folder, INDEX))
        return str(own.get("children_type") or DEFAULT_TYPE)
    parent = parts[:-1]
    inherited = _index_data(lang_root.joinpath(*parent, INDEX))
    return str(inherited.get("children_type") or DEFAULT_TYPE)


def open_page(
    site_root: Path, rel: str, contract: dict[str, Any], allow_raw_html: bool = False
) -> Page:
    """Страница сайта по пути от корня, с типом по правилу сборки."""
    return load(
        site_root / rel,
        contract,
        rel=rel,
        page_type=folder_type(site_root, rel),
        allow_raw_html=allow_raw_html,
    )
