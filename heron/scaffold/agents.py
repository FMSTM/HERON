"""Комплект для агентов в папке сайта: `agents/`, манифест, корневые указатели.

Агенту дают ссылку на репозиторий сайта — и инструкции должны лежать там же,
на языке сайта, той версии движка, что сайт создала. Комплект — копия
`docs/<язык>/` движка (байт в байт, с фолбэком по файлу; адреса ветки и
образа — по каналу, ссылки сокращённого комплекта на guide/ и spec/ —
абсолютные: `deliver`), схемы контрактов
`schemas/`, папка результатов `work/` и манифест `agents/heron-kit.yaml`
с sha256 каждого файла. Рядом в корне — `AGENTS.md` (шапка о сайте и текст
`agents/README.md`), `CLAUDE.md` и `GEMINI.md` из одной строки `@AGENTS.md`.

Обновление (`init --agents`) сверяет хеши с манифестом: нетронутый файл
заменяется, правленый остаётся и называется, лишний не удаляется, `work/`
не трогается никогда. Сборка комплект не читает; `check` читает только
манифест (`heron.core.report.kit_status`).

Спецификация: docs/ru/spec/20-data-contract.md, раздел 1, «Комплект для агентов»;
docs/ru/spec/21-engine.md, раздел 10.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from heron.core import paths
from heron.core.errors import HeronError
from heron.core.notes import NOTE
from heron.scaffold import NOTES, Plan

KIT = "agents"
MANIFEST = "heron-kit.yaml"
MANIFEST_FORMAT = 1
# Корневые указатели — в манифесте с префиксом root/, чтобы не спутать
# с файлами внутри agents/.
ROOT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
ROOT_PREFIX = "root/"
TEMPLATES = Path(__file__).parent / "agents-root"
WORK = "work/"
LEVELS = ("true", "kit")
# Сокращённый комплект (build.agents: kit) — без гайдов и спецификаций.
SHORT = ("guide/", "spec/")
# Манифест — несколько сотен строк; больше — не наш манифест.
MANIFEST_LIMIT = 256 * 1024
# Поля шапки манифеста, которые обновление «только недостающего» сохраняет.
HEADER_KEYS = ("engine", "channel", "contract", "lang", "created", "docs_url")
LANGS_OF_KIT = ("ru", "en")

# Ссылка README, которую в AGENTS.md надо направить внутрь agents/:
# не внешняя, не якорь, не от корня и не уже в agents/.
_LINK = re.compile(r"\]\((?!https?://|mailto:|#|/|agents/)")
# Цель ссылки markdown: `](цель)` или `](цель#якорь)`.
_TARGET = re.compile(r"\]\(([^)\s#]*)(#[^)\s]*)?\)")
REPO = "https://github.com/FMSTM/HERON"
GITHUB = f"{REPO}/blob"
IMAGE = "ghcr.io/fmstm/heron"
# Адреса канала в тексте docs/<язык>/ и демо-страниц: ссылка на ветку prod (файл
# blob/ или папка tree/) и образ prod в готовой команде (`H="docker run … heron:prod"`).
# Тег в таблице тегов (`heron:prod` в обратных кавычках) — описание каналов,
# а не адрес: он не меняется.
_PROD_BLOB = re.compile(re.escape(REPO) + r"/(blob|tree)/prod/")
_PROD_IMAGE = re.compile(re.escape(f"{IMAGE}:prod") + r"(?=[\"'\s])")


def _say(lang: str, key: str, **values: object) -> str:
    from heron.messages import say

    return say(lang, key, **values)


class _Blank(dict):
    """Подстановки шаблона: неизвестное поле — заглушка `<поле>`."""

    def __missing__(self, key: str) -> str:
        return f"<{key}>"


@dataclass(slots=True)
class KitPlan(Plan):
    """Что сделано с комплектом: пути от корня сайта.

    `created` — положенные впервые, `updated` — заменённые новой версией,
    `edited` — правленные человеком и потому не тронутые, `forced` — правленные,
    но перезаписанные по `force`, `orphans` — файлы прежнего комплекта, которых
    нет в новом (не удаляются), `fallback` — файлы комплекта, взятые с другого языка.
    `lang_from` — язык прежнего комплекта по манифесту (`lang`, 20 §1), если он
    другой: комплект переложен с `lang_from` на `lang` (пусто — язык тот же).
    `notes_lang` — язык пояснений (`build.notes`), если `init` без флагов оставил
    комплект на языке манифеста `lang` (`kept_lang`): сменить язык — `init --agents`.
    """

    mode: str = "create"
    lang: str = "en"
    level: str = "true"
    updated: list[str] = field(default_factory=list)
    edited: list[str] = field(default_factory=list)
    forced: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)
    files: int = 0
    # прежний манифест был, но не годился (битый, чужой, с путями наружу)
    damaged: bool = False
    lang_from: str = ""
    notes_lang: str = ""


def _level(level: str | bool) -> str:
    value = "true" if level is True else str(level).lower()
    if value not in LEVELS:
        raise ValueError(f"agent kit level {level!r}: expected true or kit")
    return value


# --- состав --------------------------------------------------------------------


def _work_note(lang: str) -> bytes:
    source = NOTES / lang / "work.md"
    if not source.is_file():
        source = NOTES / "en" / "work.md"
    return source.read_bytes()


def _short_links(rel: str, text: str, lang: str) -> str:
    """Сокращённый комплект: ссылки в guide/ и spec/ — абсолютные, на GitHub (23 §12).

    `rel` — путь файла внутри agents/; цель ссылки считается от его папки.
    Ссылка ведёт на ветку канала образа (`HERON_CHANNEL`, вне образа — prod)
    и на тот язык, чей файл лёг бы в полный комплект (фолбэк по файлу).
    Прочие ссылки не меняются: их файлы в сокращённом комплекте есть.
    """
    from heron import docs

    tree = docs.tree(lang)
    base = posixpath.dirname(rel)

    def swap(match: re.Match[str]) -> str:
        target, anchor = match.group(1), match.group(2) or ""
        if not target or re.match(r"[a-z]+:|/", target):
            return match.group(0)
        where = posixpath.normpath(posixpath.join(base, target))
        if not where.startswith(SHORT) or where not in tree:
            return match.group(0)
        return f"]({GITHUB}/{channel()}/docs/{tree[where]}/{where}{anchor})"

    return _TARGET.sub(swap, text)


def channel_links(text: str) -> str:
    """Ветка и образ prod в тексте — на канал сборки (`HERON_CHANNEL`, 23 §12).

    Одна подстановка на все точки вывода: комплект, `heron docs` (тема, образец,
    поиск, `--export`) и демо-страницы нового сайта. В prod — текст как есть.
    """
    name = channel()
    if name == "prod":
        return text
    text = _PROD_BLOB.sub(lambda m: f"{REPO}/{m[1]}/{name}/", text)
    return _PROD_IMAGE.sub(f"{IMAGE}:{name}", text)


def deliver(rel: str, data: bytes, lang: str, level: str = "true") -> bytes:
    """Файл `docs/<язык>/<rel>` так, как он ложится в комплект: байты для манифеста.

    Канал prod, полный комплект — байт в байт. Другой канал (beta) — ссылки на
    ветку prod и образ prod в готовых командах ведут на ветку и образ канала.
    Сокращённый комплект (`kit`) — ещё и абсолютные ссылки на отсутствующие в нём
    guide/ и spec/. Тот же текст выгружает `heron docs --export`. Манифест
    считается по этим байтам, поэтому обновление не принимает подстановку за
    правку человека.
    """
    level = _level(level)
    if not rel.endswith(".md"):
        return data
    text = data.decode("utf-8")
    changed = channel_links(text)
    if level == "kit":
        changed = _short_links(rel, changed, lang)
    return data if changed == text else changed.encode("utf-8")


def kit_files(lang: str, level: str = "true") -> list[tuple[str, bytes]]:
    """Файлы `agents/` на языке `lang`: путь внутри agents/ → байты, по алфавиту.

    `docs/<lang>/**` (нет файла на языке — тот же файл другого языка),
    `schemas/` той же версии движка, `work/.gitkeep` и записка `work/`.
    `level == "kit"` — без `guide/` и `spec/`, ссылки на них — абсолютные (`deliver`).
    """
    from heron import docs
    from heron.contracts.schemas import all_schemas

    level = _level(level)
    out: list[tuple[str, bytes]] = []
    for rel, have in docs.tree(lang).items():
        if level == "kit" and rel.startswith(SHORT):
            continue
        data = (docs.root() / "docs" / have / rel).read_bytes()
        out.append((rel, deliver(rel, data, lang, level)))
    for name, text in all_schemas().items():
        out.append((f"schemas/{name}", text.encode("utf-8")))
    out.append((f"{WORK}.gitkeep", b""))
    out.append((f"{WORK}{NOTE}", _work_note(lang)))
    return sorted(out)


def fallback_files(lang: str, level: str = "true") -> list[str]:
    """Пути внутри agents/, которые взяты с другого языка: перевода нет."""
    from heron import docs

    level = _level(level)
    return [
        rel
        for rel, have in docs.tree(lang).items()
        if have != lang and not (level == "kit" and rel.startswith(SHORT))
    ]


def _template(lang: str, name: str) -> str:
    for path in (TEMPLATES / lang / name, TEMPLATES / "en" / name, TEMPLATES / name):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(TEMPLATES / lang / name)


def root_files(lang: str, fields: dict[str, Any], level: str = "true") -> dict[str, str]:
    """Корневые указатели: AGENTS.md (шапка + текст agents/README.md), CLAUDE.md, GEMINI.md.

    Тело AGENTS.md — README комплекта в том виде, как он лёг в agents/ (`deliver`),
    со ссылками, направленными внутрь agents/.
    """
    from heron import docs

    head = _template(lang, "AGENTS.md").format_map(_Blank(fields))
    found = docs.localize("README.md", lang)
    raw = (docs.root() / found.path).read_bytes() if found else b""
    body = deliver("README.md", raw, lang, level).decode("utf-8")
    body = _LINK.sub("](agents/", body)
    if found is not None and found.lang_used != lang and found.note:
        body = f"{found.note}\n{body}"
    return {
        "AGENTS.md": head + "\n" + body,
        "CLAUDE.md": _template(lang, "CLAUDE.md"),
        "GEMINI.md": _template(lang, "GEMINI.md"),
    }


def _site_data(site_yaml: Path) -> dict[str, Any]:
    """site.yaml мягко: комплект кладут и в недостроенную папку."""
    try:
        import yaml

        if not site_yaml.is_file():
            return {}
        data = yaml.safe_load(site_yaml.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — сырой конфиг не повод оставить сайт без комплекта
        return {}
    return data if isinstance(data, dict) else {}


def _line(value: object) -> str:
    return " ".join(str(value).split())


def channel() -> str:
    return os.environ.get("HERON_CHANNEL", "").strip() or "prod"


def docs_url(lang: str) -> str:
    return f"{GITHUB}/{channel()}/docs/{lang}/"


def fields(root: Path, declared: dict[str, Any] | None, lang: str) -> dict[str, str]:
    """Подстановки шапки AGENTS.md: из параметров вызова, иначе из site.yaml сайта."""
    import heron

    declared = dict(declared or {})
    data = _site_data(Path(root) / "site.yaml")
    site = data.get("site") if isinstance(data.get("site"), dict) else {}
    org = data.get("organization") if isinstance(data.get("organization"), dict) else {}

    languages = declared.get("languages") or site.get("languages") or []
    if isinstance(languages, str):
        languages = [languages]
    languages = [str(x) for x in languages if x]
    default_lang = declared.get("default_lang") or site.get("default_lang") or ""
    default_lang = str(default_lang or (languages[0] if languages else ""))
    about = org.get(f"about_{lang}") or org.get("about")
    name = declared.get("name") or site.get(f"name_{default_lang}") or site.get("name")
    return {
        "name": _line(name or Path(root).resolve().name),
        "domain": _line(declared.get("domain") or site.get("domain") or "—"),
        "languages": ", ".join(languages) or "—",
        "default_lang": default_lang or "—",
        "notes": lang,
        "version": heron.__version__,
        "channel": channel(),
        "docs_url": docs_url(lang),
        "about": _line(about) if about else _say(lang, "kit_about_placeholder"),
    }


# --- манифест ------------------------------------------------------------------


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def created_at() -> str:
    """Момент записи, UTC: SOURCE_DATE_EPOCH, если задан, — для одинаковых байтов."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    try:
        moment = datetime.fromtimestamp(int(epoch), UTC) if epoch else datetime.now(UTC)
    except (ValueError, OverflowError, OSError):
        moment = datetime.now(UTC)
    return moment.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _manifest_text(
    records: dict[str, str],
    lang: str,
    header: dict[str, str] | None = None,
    fallback: list[str] | tuple[str, ...] = (),
) -> str:
    """Манифест по записям путь → sha256; `header` — сохранить поля прежней шапки."""
    import heron

    major, minor, *_ = heron.__version__.split(".")
    head = {
        "engine": heron.__version__,
        "channel": channel(),
        "contract": f"{major}.{minor}",
        "lang": lang,
        "created": created_at(),
        "docs_url": docs_url(lang),
        **{k: v for k, v in (header or {}).items() if k in HEADER_KEYS and v},
    }
    q = json.dumps
    kit_lang = head["lang"]
    lines = [
        _say(kit_lang if kit_lang in LANGS_OF_KIT else "en", "kit_manifest_head"),
        f"heron_kit: {MANIFEST_FORMAT}",
        f"engine: {q(head['engine'])}",
        f"channel: {q(head['channel'])}",
        f"contract: {q(head['contract'])}",
        f"lang: {kit_lang}",
        f"created: {q(head['created'])}",
        f"docs_url: {q(head['docs_url'])}",
        "files:",
    ]
    marked = set(fallback)
    other = "en" if kit_lang == "ru" else "ru"
    for rel in sorted(records):
        lines.append(f"  - path: {q(rel, ensure_ascii=False)}")
        lines.append(f"    sha256: {q(records[rel])}")
        if rel in marked:
            lines.append(f"    lang: {other}")
    return "\n".join(lines) + "\n"


@dataclass(slots=True)
class Manifest:
    """Прежний манифест: путь → sha256 и шапка. `damaged` — есть, но не годится."""

    files: dict[str, str] = field(default_factory=dict)
    header: dict[str, str] = field(default_factory=dict)
    present: bool = False
    damaged: bool = False


def _valid_entry(rel: object) -> bool:
    """Путь записи манифеста: внутри agents/ или один из корневых указателей.

    `..`, абсолютный путь, обратная косая — признак чужого или подменённого
    манифеста: такой не читается вовсе (иначе init --agents пошёл бы по нему).
    """
    if not isinstance(rel, str) or not rel or "\\" in rel or rel.startswith("/"):
        return False
    if rel.startswith(ROOT_PREFIX):
        return rel.removeprefix(ROOT_PREFIX) in ROOT_FILES
    clean = paths.normalize(rel)
    return clean == rel and not paths.escapes(clean) and ".." not in clean.split("/")


def read_manifest(root: Path) -> Manifest:
    """`agents/heron-kit.yaml` мягко: нет — пусто; битый, чужой, ссылка — `damaged`, без ошибки.

    Файл открывается через проверку пути: ссылку наружу движок не читает.
    """
    try:
        path = paths.in_site(Path(root), f"{KIT}/{MANIFEST}")
    except HeronError:
        return Manifest(present=True, damaged=True)
    if not (path.exists() or path.is_symlink()):
        return Manifest()
    broken = Manifest(present=True, damaged=True)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MANIFEST_LIMIT:
            return broken
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — битый манифест: все файлы считаются правлеными
        return broken
    entries = data.get("files") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return broken
    out: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not _valid_entry(entry.get("path")):
            return broken
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return broken
        out[entry["path"]] = digest
    header = {key: str(data[key]) for key in HEADER_KEYS if isinstance(data.get(key), str)}
    return Manifest(files=out, header=header, present=True)


def kept_lang(previous: Manifest, notes: str) -> str:
    """Язык комплекта для `init` без флагов: язык снимка по манифесту, иначе `notes`.

    Комплект — снимок на момент записи, `lang` манифеста — `build.notes` того
    момента (20 §1); `init` без флагов только дописывает недостающее (21 §10) и
    шапку манифеста сохраняет. Поэтому недостающие файлы и указатели он кладёт на
    языке снимка: комплект и `lang` не расходятся. Сменить язык комплекта —
    `init --agents`: обновление по манифесту на языке `build.notes` (`lang_from`).
    Нет манифеста, он битый или язык в нём не ru/en — `notes`.
    """
    was = previous.header.get("lang", "")
    if previous.present and not previous.damaged and was in LANGS_OF_KIT:
        return was
    return notes


# --- запись --------------------------------------------------------------------


def _site_rel(rel: str) -> str:
    """Путь манифеста → путь от корня сайта."""
    return rel.removeprefix(ROOT_PREFIX) if rel.startswith(ROOT_PREFIX) else f"{KIT}/{rel}"


def _not_a_file(rel: str, path: Path, lang: str) -> HeronError:
    """На месте файла ссылка или папка: текст целиком на языке вызывающего."""
    return HeronError(
        code=paths.CODE,
        message=f"{rel}: {_say(lang, 'write_not_file')}",
        path=str(path),
        hint=_say(lang, "write_not_file_hint"),
    )


def _not_a_folder(shown: str, path: Path, lang: str) -> HeronError:
    """На месте папки - висячая ссылка, файл или ссылка не на папку: mkdir упал бы."""
    key = "write_dangling" if path.is_symlink() and not path.exists() else "write_not_folder"
    return HeronError(
        code=paths.CODE,
        message=f"{shown}: {_say(lang, key)}",
        path=str(path),
        hint=_say(lang, "write_folder_hint"),
    )


def _blocked(path: Path) -> bool:
    """Путь занят не папкой: висячая ссылка, файл, ссылка на файл."""
    return (path.exists() or path.is_symlink()) and not path.is_dir()


def _check_folders(root: Path, items: list[tuple[str, bytes]], lang: str) -> None:
    """E024 до записи: папка, которую пришлось бы создать, занята не папкой.

    Сама `root` и папки над ней, которых ещё нет (их создаст mkdir), и папки
    по пути к каждому файлу внутри `root`. Ссылка на существующую папку —
    папка: так и задумано (21 §4).
    """
    for folder in (root, *root.parents):
        if _blocked(folder):
            shown = str(folder) if folder != root else root.name or str(root)
            raise _not_a_folder(shown, folder, lang)
        if folder.exists():
            break
    for rel, _ in items:
        parts = Path(rel).parts[:-1]
        for depth in range(1, len(parts) + 1):
            folder = root.joinpath(*parts[:depth])
            if _blocked(folder):
                raise _not_a_folder("/".join(parts[:depth]), folder, lang)


def write_files(root: Path, items: list[tuple[str, bytes]], lang: str = "en") -> list[str]:
    """Безопасная запись файлов в папку `root`: сначала проверка всех целей, потом запись.

    Цель, ведущая ссылкой за пределы `root` (сам файл или папка по пути к нему), —
    E024; ссылка или папка на месте файла — тоже E024, даже внутри: запись через
    неё изменила бы не тот файл. Висячая ссылка или файл на месте папки (сама
    `root` или папка по пути к файлу) — E024, а не падение mkdir. Всё проверяется
    до первой записи, сама запись — с O_NOFOLLOW (ссылка, подложенная после
    проверки, — ошибка, а не запись мимо). Сама `root` может быть ссылкой на
    папку: её назвал человек. Подробность E024 - на одном языке `lang` (язык
    пояснений вызывающего: `--notes`, `HERON_NOTES`, `build.notes`; без него - en).
    Возвращает записанные пути.
    """
    root = Path(root)
    for rel, _ in items:
        path = paths.in_site(root, rel)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise _not_a_file(rel, path, lang)
    _check_folders(root, items, lang)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    for rel, data in items:
        path = paths.in_site(root, rel)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, NotADirectoryError) as exc:  # подложили после проверки
            raise _not_a_folder(rel, path.parent, lang) from exc
        path = paths.in_site(root, rel)  # папки созданы — проверить ещё раз
        fd = os.open(path, flags, 0o644)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
    return [rel for rel, _ in items]


def _kit_names(lang: str, level: str) -> list[str]:
    """Пути внутри agents/ без чтения файлов: для проверки целей до записи."""
    from heron import docs
    from heron.contracts.schemas import FILES

    names = [rel for rel in docs.tree(lang) if not (level == "kit" and rel.startswith(SHORT))]
    names += [f"schemas/{name}" for name in FILES]
    names += [f"{WORK}.gitkeep", f"{WORK}{NOTE}", MANIFEST]
    return sorted(names)


def targets(level: str = "true", lang: str = "en") -> list[str]:
    """Все пути комплекта от корня сайта: agents/, agents/work/, файлы, манифест, указатели."""
    level = _level(level)
    return [KIT, f"{KIT}/work", *(f"{KIT}/{rel}" for rel in _kit_names(lang, level)), *ROOT_FILES]


def check_targets(root: Path, level: str = "true", lang: str = "en") -> None:
    """E024 до первой записи: путь комплекта ведёт ссылкой за пределы папки сайта (21 §4)."""
    for rel in targets(level, lang):
        paths.in_site(Path(root), rel)


# Ссылка (внутри сайта) или папка на месте файла комплекта: читать её и писать
# через неё не надо — это решение человека, оно считается правкой.
_ODD = b"\0not-a-regular-file"


def _on_disk(root: Path, rel: str) -> bytes | None:
    """Что лежит на месте файла комплекта: None — ничего; ссылка или папка — `_ODD`."""
    path = paths.in_site(root, rel)
    if not (path.exists() or path.is_symlink()):
        return None
    if path.is_symlink() or not path.is_file():
        return _ODD
    return path.read_bytes()


def _pointer_link(root: Path, name: str) -> bool:
    """CLAUDE.md или GEMINI.md — ссылка внутри сайта на AGENTS.md: указатель уже на месте."""
    path = root / name
    if name == "AGENTS.md" or not path.is_symlink():
        return False
    try:
        return path.resolve() == (root / "AGENTS.md").resolve()
    except OSError:
        return False


def place(
    root: Path,
    lang: str,
    fields: dict[str, Any],
    mode: Literal["create", "update"] = "create",
    force: bool = False,
    level: str = "true",
    pointers: Literal["create", "update"] | None = None,
) -> KitPlan:
    """Положить или обновить комплект в папке сайта `root`.

    `create` — как остальной скелет: недостающее кладётся, существующее
    остаётся (с `force` — перезаписывается и попадает в `forced`, если его
    правили). `update` — по манифесту: нетронутый файл заменяется, правленый
    остаётся и попадает в `edited` (с `force` — заменяется и попадает в
    `forced`), лишний остаётся и попадает в `orphans`. `pointers` — свой режим
    для корневых указателей: `init` без флагов и анкета обновляют AGENTS.md по
    манифесту (в нём имя, языки, домен, о проекте — 20 §1), остальной комплект
    только дописывают. `work/` кладётся, только если его нет, и не
    перезаписывается никогда. Ссылка или папка на месте файла не перезаписываются
    никогда — это правка. Сначала решается всё, потом проверяются все цели
    (E024), потом запись; манифест пишется последним.
    """
    if mode not in ("create", "update"):
        raise ValueError(f"mode {mode!r}: expected create or update")
    if pointers not in (None, "create", "update"):
        raise ValueError(f"pointers {pointers!r}: expected create or update")
    level = _level(level)
    root = Path(root)
    plan = KitPlan(notes=lang, mode=mode, lang=lang, level=level)
    check_targets(root, level, lang)

    inner = kit_files(lang, level)
    texts = root_files(lang, fields, level)
    tracked = [(rel, data) for rel, data in inner if not rel.startswith(WORK)]
    tracked += [(f"{ROOT_PREFIX}{name}", texts[name].encode("utf-8")) for name in ROOT_FILES]
    plan.files = len(inner) + len(ROOT_FILES) + 1
    plan.fallback = [f"{KIT}/{rel}" for rel in fallback_files(lang, level)]
    previous = read_manifest(root)
    old = previous.files
    was = previous.header.get("lang", "")
    if was in LANGS_OF_KIT and was != lang:
        plan.lang_from = was
    writes: list[tuple[str, bytes]] = []
    records: dict[str, str] = {}

    for rel, data in inner:
        site_rel = f"{KIT}/{rel}"
        if rel.startswith(WORK) and _on_disk(root, site_rel) is None:
            writes.append((site_rel, data))
            plan.created.append(site_rel)

    for rel, data in tracked:
        site_rel = _site_rel(rel)
        fresh = sha256(data)
        if rel.startswith(ROOT_PREFIX) and _pointer_link(root, site_rel):
            continue
        current = _on_disk(root, site_rel)
        if current is None:
            writes.append((site_rel, data))
            plan.created.append(site_rel)
            records[rel] = fresh
            continue
        if current == data:
            records[rel] = fresh
            continue
        if current is _ODD:
            plan.skipped.append(site_rel)
            plan.edited.append(site_rel)
            records[rel] = old.get(rel, fresh)
            continue
        untouched = rel in old and sha256(current) == old[rel]
        how = pointers if (pointers and rel.startswith(ROOT_PREFIX)) else mode
        if force or (how == "update" and untouched):
            writes.append((site_rel, data))
            plan.updated.append(site_rel)
            if not untouched:
                plan.forced.append(site_rel)
            records[rel] = fresh
            continue
        plan.skipped.append(site_rel)
        if how == "update":
            plan.edited.append(site_rel)
        records[rel] = old.get(rel, fresh)

    if mode == "update":
        known = {rel for rel, _ in tracked}
        for rel in sorted(old):
            if rel in known or rel.startswith(WORK):
                continue
            try:
                if _on_disk(root, _site_rel(rel)) is not None:
                    plan.orphans.append(_site_rel(rel))
            except HeronError:
                continue  # ссылка наружу на месте лишнего файла: его и так не трогаем

    if plan.edited:
        plan.found.append(_say(lang, "kit_skipped_edited", files=", ".join(plan.edited)))
    if plan.orphans:
        plan.found.append(_say(lang, "kit_orphan", files=", ".join(plan.orphans)))
    if mode == "update" and previous.damaged:
        plan.damaged = True
        plan.found.append(_say(lang, "kit_manifest_damaged"))

    manifest_rel = f"{KIT}/{MANIFEST}"
    fallback = fallback_files(lang, level)
    current = _on_disk(root, manifest_rel)
    if mode == "update" or force or not previous.present:
        text = _manifest_text(records, lang, fallback=fallback).encode("utf-8")
    elif not previous.damaged:
        # только недостающее: шапка (версия, язык, дата) прежняя, записи — прежние
        # и тех файлов, что положены или заменены сейчас
        merged = {**old, **records}
        text = _manifest_text(merged, lang, previous.header, fallback).encode("utf-8")
        if merged == old:
            text = current if current is not None else text
    else:
        text = current if current is not None else b""
    if current is None:
        writes.append((manifest_rel, text))
        plan.created.append(manifest_rel)
    elif current != text:
        writes.append((manifest_rel, text))
        plan.updated.append(manifest_rel)
    write_files(root, writes, lang)
    return plan
