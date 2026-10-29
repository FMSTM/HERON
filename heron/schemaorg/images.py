"""Картинки из разметки: какие адреса граф называет и где их искать.

Разметка ссылается на файл, которого нет в сборке, - и это видно только в
панели вебмастера. Здесь только разбор графа и адреса; политика находок
(ключи, исключения, строгость) - в heron.schemaorg.policy.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from heron.contracts.site import SiteConfig
from heron.core.media import FOLDERS
from heron.core.urls import absolute

IMAGE_PROPS = ("image", "logo", "photo", "thumbnailUrl", "contentUrl", "primaryImageOfPage")
_INNER = ("url", "contentUrl")
_KEEP = (".jpg", ".jpeg", ".png", ".webp")
_SLICE = re.compile(r"^(?P<stem>.+)-[^-/]+-\d+$")


def image_refs(node: Any, path: str = "") -> list[tuple[str, str]]:
    """Адреса картинок узла: (путь внутри узла, адрес)."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if key in IMAGE_PROPS:
                found.extend(_values(value, here))
            else:
                found.extend(image_refs(value, here))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(image_refs(item, f"{path}.{index}" if path else str(index)))
    return found


def _values(value: Any, path: str) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)] if value.strip() else []
    if isinstance(value, list):
        out: list[tuple[str, str]] = []
        for index, item in enumerate(value):
            out.extend(_values(item, f"{path}.{index}"))
        return out
    if isinstance(value, dict):
        out = []
        for inner in _INNER:
            if isinstance(value.get(inner), str) and value[inner].strip():
                out.append((f"{path}.{inner}", value[inner]))
        return out
    return []


def local_path(url: str, config: SiteConfig) -> str | None:
    """Путь своего файла от корня сборки (без начального слеша) или None для чужого адреса."""
    text = url.strip()
    if not text or text.startswith(("data:", "//")):
        return None
    base = absolute(config, "/")
    if text.startswith(base):
        text = "/" + text[len(base):]
    elif text.startswith(("http://", "https://")):
        return None
    if not text.startswith("/"):
        return None
    text = text.split("#", 1)[0].split("?", 1)[0]
    rel = text.lstrip("/")
    return rel or None


def source_exists(site_root: Path, rel: str, theme_dir: Path | None = None) -> bool:
    """check без сборки: файл по исходникам - так же, как его разложит build.

    media/ (и legacy img/) - мастер или нарезка существующего мастера;
    assets/ - static/assets/ или theme/assets/ (build кладёт оба в assets/);
    иначе static/<путь>.
    """
    head = rel.split("/", 1)[0]
    if head in FOLDERS:
        if (site_root / rel).is_file():
            return True
        match = _SLICE.match(Path(rel).stem)
        if match:
            parent = (site_root / rel).parent
            return any((parent / f"{match['stem']}{ext}").is_file() for ext in _KEEP)
        return False
    if (site_root / "static" / rel).is_file():
        return True
    return head == "assets" and theme_dir is not None and (theme_dir / rel).is_file()
