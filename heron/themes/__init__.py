"""Темы: встроенная стартовая, каталог HERON, ссылка или свой архив.

Тема с демо-контентом — это архив:

    heron-theme.yaml      имя, название, версия, совместимые версии HERON
    theme/                тема: theme.yaml, шаблоны, модули, стили
    demo/                 демонстрационные страницы темы: content/<язык>/, media/, data/

Откуда берётся:

- **starter** (и «выберу позже») — стартовая тема из самого движка, без сети;
- **по имени** — каталог HERON (`HERON_THEMES_URL`, по умолчанию
  `catalog.json` репозитория тем): имя → адрес архива и его sha256;
- **по ссылке** — архив по https; `#sha256=<хеш>` в конце сверяется;
- **своим архивом** — файл .zip или .tar.gz.

Архив чужой, поэтому распаковка недоверчивая: ни абсолютных путей, ни `..`,
ни ссылок и устройств, предел размера и числа файлов, никакого кода сборки
(`plugins/`, `.py`, `.sh`). После распаковки тема проверяется той же схемой,
что и при сборке, и только потом встаёт на место. Прежняя тема уезжает в
`.heron-cache/setup/`, а не стирается. Демо-контент кладётся только в пустые
места: существующая страница сайта не перезаписывается никогда.

Спецификация: docs/spec/21-engine.md, раздел «heron theme».
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from heron.core import paths
from heron.core.errors import HeronError

CATALOG_ENV = "HERON_THEMES_URL"
CATALOG_URL = "https://raw.githubusercontent.com/FMSTM/heron-themes/main/catalog.json"
STARTER = "starter"
MANIFEST = "heron-theme.yaml"

MAX_TOTAL = 200 * 1024 * 1024
MAX_FILE = 50 * 1024 * 1024
MAX_FILES = 5000
TIMEOUT = 20
FORBIDDEN_PARTS = {"plugins", ".git", "__pycache__"}
FORBIDDEN_SUFFIXES = {".py", ".pyc", ".sh", ".exe", ".bat", ".cmd", ".ps1", ".so", ".dll"}
DEMO_FOLDERS = ("content", "media", "data")
SHA_IN_URL = re.compile(r"#sha256=([0-9a-f]{64})$")
NAME_RE = paths.NAME_RE


@dataclass(slots=True)
class Installed:
    name: str
    created: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    backup: str = ""


def _fail(message: str, hint: str = "") -> HeronError:
    return HeronError(code="E032", message=message, hint=hint)


_CATALOG: dict[str, list[dict[str, Any]]] = {}


def catalog(timeout: float = 3.0) -> list[dict[str, Any]]:
    """Темы каталога: встроенная всегда, остальные — если каталог доступен.

    Ответ запоминается на время процесса: анкета спрашивает каталог при
    каждом сохранении, и без сети каждое сохранение ждало бы таймаута.
    """
    url = os.environ.get(CATALOG_ENV, CATALOG_URL)
    if url not in _CATALOG:
        _CATALOG[url] = _catalog(url, timeout)
    return list(_CATALOG[url])


def _catalog(url: str, timeout: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {
            "name": STARTER,
            "title": "Starter",
            "description": "White and plain: every section form HERON knows. Built in.",
            "builtin": True,
        }
    ]
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            data = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except Exception:
        return out
    for item in data.get("themes", []) if isinstance(data, dict) else []:
        name = str(item.get("name", "")) if isinstance(item, dict) else ""
        if NAME_RE.match(name) and name != STARTER:
            out.append({k: item.get(k) for k in ("name", "title", "description", "preview")})
    return out


def _entry(name: str) -> dict[str, Any]:
    url = os.environ.get(CATALOG_ENV, CATALOG_URL)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:  # noqa: S310
            data = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except Exception as error:
        raise _fail(
            f"theme catalog is not reachable: {error}",
            "check the network or take the theme by link or archive: heron theme get <url|file>",
        ) from error
    for item in data.get("themes", []) if isinstance(data, dict) else []:
        if isinstance(item, dict) and item.get("name") == name:
            if not str(item.get("url", "")).startswith("https://"):
                raise _fail(f"theme {name!r}: the catalog gives no https address")
            return item
    names = ", ".join(str(i.get("name")) for i in data.get("themes", []) if isinstance(i, dict))
    raise _fail(f"no theme {name!r} in the catalog", f"known: {STARTER}, {names}".rstrip(", "))


def _download(url: str) -> bytes:
    if not url.startswith("https://"):
        raise _fail(f"{url}: only https addresses", "a file on disk is taken as a path")
    request = urllib.request.Request(url, headers={"User-Agent": "heron-theme"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            body = response.read(MAX_TOTAL + 1)
    except Exception as error:
        raise _fail(f"cannot download {url}: {error}") from error
    if len(body) > MAX_TOTAL:
        raise _fail(f"{url}: the archive is larger than {MAX_TOTAL // (1024 * 1024)} MB")
    return body


def _members(blob: bytes) -> list[tuple[str, bytes]]:
    """Файлы архива (zip или tar.gz) с проверкой каждого пути."""
    files: list[tuple[str, bytes]] = []
    total = 0

    def take(name: str, size: int, read) -> None:
        nonlocal total
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise _fail(f"archive entry {name!r} leaves the archive folder")
        if any(part in FORBIDDEN_PARTS for part in path.parts):
            raise _fail(f"archive entry {name!r}: build code is not allowed in a theme")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise _fail(f"archive entry {name!r}: scripts are not allowed in a theme")
        if size > MAX_FILE:
            raise _fail(f"archive entry {name!r} is larger than {MAX_FILE // (1024 * 1024)} MB")
        total += size
        if total > MAX_TOTAL or len(files) >= MAX_FILES:
            raise _fail("the archive is too large or has too many files")
        files.append((path.as_posix(), read()))

    if blob[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode and mode != 0o100000:
                    raise _fail(f"archive entry {info.filename!r} is a link or a device")
                take(info.filename, info.file_size, lambda i=info: archive.read(i))
        return files
    try:
        archive = tarfile.open(fileobj=io.BytesIO(blob), mode="r:*")  # noqa: SIM115
    except tarfile.TarError as error:
        raise _fail("not a theme archive: zip or tar.gz expected") from error
    with archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise _fail(f"archive entry {member.name!r} is a link or a device")
            handle = archive.extractfile(member)
            take(member.name, member.size, lambda h=handle: h.read() if h else b"")
    return files


def _strip_root(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Архив, упакованный с общей папкой сверху (`my-theme/theme/...`), — без неё."""
    tops = {name.split("/", 1)[0] for name, _ in files}
    single = len(tops) == 1 and not any(name == MANIFEST for name, _ in files)
    if single and all("/" in name for name, _ in files):
        return [(name.split("/", 1)[1], data) for name, data in files]
    return files


def _unpack(blob: bytes, target: Path) -> dict[str, Any]:
    files = _strip_root(_members(blob))
    if not any(name.startswith("theme/") for name, _ in files):
        raise _fail("the archive has no theme/ folder", "a theme archive holds theme/ and demo/")
    for name, data in files:
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    manifest_path = target / MANIFEST
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        manifest = loaded if isinstance(loaded, dict) else {}
    return manifest


def _check_theme(theme_dir: Path, manifest: dict[str, Any]) -> str:
    """Проверить тему той же схемой, что сборка; вернуть её имя."""
    from heron import __version__
    from heron.contracts.loader import build, read_yaml
    from heron.contracts.theme import ThemeConfig
    from heron.contracts.version import satisfies

    theme_yaml = theme_dir / "theme.yaml"
    if not theme_yaml.is_file():
        raise _fail("theme/theme.yaml is missing in the archive")
    config = build(ThemeConfig, read_yaml(theme_yaml), theme_yaml)
    wanted = str(manifest.get("heron") or "")
    if wanted and not satisfies(__version__, wanted):
        raise _fail(
            f"the theme wants HERON {wanted}, this is {__version__}",
            "take a theme version made for this HERON",
        )
    return config.name


def _starter(stage: Path, languages: list[str]) -> None:
    """Стартовая тема и её демо из самого движка."""
    from heron.scaffold import starter_theme

    starter_theme(stage, languages)


def _backup_dir(root: Path) -> Path:
    """Свободное имя `.heron-cache/setup/theme.<время>[-N]` — занятое исключительно.

    Две установки в одну секунду иначе получили бы одно имя, и вторая
    копия легла бы поверх первой. Папка создаётся `mkdir` без exist_ok: кто
    создал, тот и владеет именем.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = paths.in_site(root, ".heron-cache/setup")
    folder.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000):
        rel = f".heron-cache/setup/theme.{stamp}" + (f"-{number}" if number > 1 else "")
        candidate = paths.in_site(root, rel)
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise _fail("too many theme backups in one second")


def _place(root: Path, stage: Path, result: Installed) -> None:
    # Куда тема и демо лягут — внутри папки сайта, до первой записи: ссылка
    # theme/, content/ или .heron-cache/ наружу — E024, ничего не меняется.
    theme = paths.in_site(root, "theme")
    paths.in_site(root, ".heron-cache/setup")
    source = stage / "demo"
    demo: list[tuple[Path, Path, str]] = []
    if source.is_dir():
        for folder in DEMO_FOLDERS:
            base = source / folder
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(source).as_posix()
                demo.append((path, paths.in_site(root, rel), rel))

    if theme.exists() or theme.is_symlink():
        backup = _backup_dir(root)
        if theme.is_symlink():
            backup.rmdir()  # ссылка уезжает сама, а не то, на что она ведёт
        try:
            os.rename(theme, backup)
        except OSError:  # другой том: переносом, имя уже занято нами
            backup.rmdir()
            shutil.move(str(theme), str(backup))
        result.backup = backup.relative_to(root).as_posix()
    shutil.copytree(stage / "theme", theme)
    result.created.append("theme/")
    for path, target, rel in demo:
        if target.exists() or target.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        paths.in_site(root, rel)  # папки созданы — проверить ещё раз
        shutil.copy2(path, target)
        result.created.append(rel)


def _demo_languages(stage: Path, languages: list[str]) -> None:
    """Демонстрационные страницы темы — в каждый язык сайта.

    Они стоят в меню темы, и язык без них давал бы меню в никуда. Нет
    страниц на языке сайта — берутся страницы основного языка, иначе первые.
    Языки демо, которых у сайта нет, не кладутся.
    """
    content = stage / "demo" / "content"
    if not content.is_dir():
        return
    present = sorted(p.name for p in content.iterdir() if p.is_dir())
    if not present:
        return
    base = languages[0] if languages[0] in present else present[0]
    for lang in languages:
        if lang not in present:
            shutil.copytree(content / base, content / lang)
    for lang in present:
        if lang not in languages:
            shutil.rmtree(content / lang)


def install(
    root: Path,
    source: str,
    value: str = "",
    languages: list[str] | None = None,
    upload: Path | None = None,
) -> Installed:
    """Поставить тему в `theme/` сайта; прежнюю — в резервную копию."""
    root = Path(root)
    languages = languages or ["en"]
    with tempfile.TemporaryDirectory(prefix="heron-theme-") as tmp:
        stage = Path(tmp)
        manifest: dict[str, Any] = {}
        if source in ("starter", "later") or (source == "name" and value in ("", STARTER)):
            _starter(stage, languages)
        else:
            if source == "name":
                if not NAME_RE.match(value):
                    raise _fail(f"theme name {value!r}: latin letters, digits, dash")
                entry = _entry(value)
                blob = _download(str(entry["url"]))
                expected = str(entry.get("sha256") or "")
            elif source == "url":
                match = SHA_IN_URL.search(value)
                expected = match.group(1) if match else ""
                blob = _download(SHA_IN_URL.sub("", value))
            elif source == "file":
                path = upload or (root / value if not Path(value).is_absolute() else Path(value))
                if not path.is_file():
                    raise _fail(f"no archive at {value}")
                if path.stat().st_size > MAX_TOTAL:
                    raise _fail("the archive is too large")
                blob = path.read_bytes()
                expected = ""
            else:
                raise _fail(f"unknown theme source {source!r}")
            if expected:
                actual = hashlib.sha256(blob).hexdigest()
                if actual != expected:
                    raise _fail(
                        "the archive checksum does not match: changed on the way or at the source",
                        f"expected {expected}, got {actual}",
                    )
            manifest = _unpack(blob, stage)
        _demo_languages(stage, languages)
        name = _check_theme(stage / "theme", manifest)
        result = Installed(name=name)
        _place(root, stage, result)
        return result


def pack(root: Path, out: Path) -> Path:
    """Упаковать тему сайта и его контент (демонстрационные страницы темы) в архив темы."""
    root = Path(root)
    theme = root / "theme"
    name = _check_theme(theme, {})
    from heron import __version__

    major, minor, *_ = __version__.split(".")
    manifest = {
        "name": name,
        "heron": f">={major}.{minor},<{major}.{int(minor) + 1}",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as archive:
        data = yaml.safe_dump(manifest, allow_unicode=True).encode("utf-8")
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
        for path in sorted(theme.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=f"theme/{path.relative_to(theme).as_posix()}")
        for folder in DEMO_FOLDERS:
            base = root / folder
            for path in sorted(base.rglob("*")) if base.is_dir() else []:
                if path.is_file() and path.name not in ("heron-readme.md", ".gitkeep"):
                    archive.add(path, arcname=f"demo/{path.relative_to(root).as_posix()}")
    return out
