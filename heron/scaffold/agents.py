"""Комплект для агентов в папке сайта: `agents/`, манифест, корневые указатели.

Агенту дают ссылку на репозиторий сайта — и инструкции должны лежать там же,
на языке сайта, той версии движка, что сайт создала. Комплект — копия
`docs/<язык>/` движка (байт в байт, с фолбэком по файлу), схемы контрактов
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

# Ссылка README, которую в AGENTS.md надо направить внутрь agents/:
# не внешняя, не якорь, не от корня и не уже в agents/.
_LINK = re.compile(r"\]\((?!https?://|mailto:|#|/|agents/)")

# Строки, которых ещё может не быть в messages.py: шов S2.T6 кладёт их туда,
# а модуль работает и без него.
_TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "kit_about_placeholder": "<о проекте: заполняет архитектор>",
        "kit_skipped_edited": "правлен вами, не тронут: {files}",
        "kit_orphan": "нет в новом комплекте, оставлен: {files}",
        "kit_manifest_head": "# Манифест комплекта для агентов. Пишет движок, руками не правят.",
    },
    "en": {
        "kit_about_placeholder": "<about the project: the architect fills this in>",
        "kit_skipped_edited": "edited by you, left as is: {files}",
        "kit_orphan": "not in the new kit, left in place: {files}",
        "kit_manifest_head": "# Agent kit manifest. Written by the engine, not edited by hand.",
    },
}


def _say(lang: str, key: str, **values: object) -> str:
    try:
        from heron.messages import say

        return say(lang, key, **values)
    except (KeyError, IndexError, ValueError, ImportError):
        table = _TEXT.get(lang, _TEXT["en"])
        return table.get(key, _TEXT["en"][key]).format(**values)


class _Blank(dict):
    """Подстановки шаблона: неизвестное поле — заглушка `<поле>`."""

    def __missing__(self, key: str) -> str:
        return f"<{key}>"


@dataclass(slots=True)
class KitPlan(Plan):
    """Что сделано с комплектом: пути от корня сайта.

    `created` — положенные впервые, `updated` — заменённые новой версией,
    `edited` — правленные человеком и потому не тронутые, `orphans` — файлы
    прежнего комплекта, которых нет в новом (не удаляются), `fallback` — файлы
    комплекта, взятые с другого языка.
    """

    mode: str = "create"
    lang: str = "en"
    level: str = "true"
    updated: list[str] = field(default_factory=list)
    edited: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)
    files: int = 0


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


def kit_files(lang: str, level: str = "true") -> list[tuple[str, bytes]]:
    """Файлы `agents/` на языке `lang`: путь внутри agents/ → байты, по алфавиту.

    `docs/<lang>/**` (нет файла на языке — тот же файл другого языка),
    `schemas/` той же версии движка, `work/.gitkeep` и записка `work/`.
    `level == "kit"` — без `guide/` и `spec/`.
    """
    from heron import docs
    from heron.contracts.schemas import all_schemas

    level = _level(level)
    out: list[tuple[str, bytes]] = []
    for rel, have in docs.tree(lang).items():
        if level == "kit" and rel.startswith(SHORT):
            continue
        out.append((rel, (docs.root() / "docs" / have / rel).read_bytes()))
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


def root_files(lang: str, fields: dict[str, Any]) -> dict[str, str]:
    """Корневые указатели: AGENTS.md (шапка + текст agents/README.md), CLAUDE.md, GEMINI.md."""
    from heron import docs

    head = _template(lang, "AGENTS.md").format_map(_Blank(fields))
    found = docs.localize("README.md", lang)
    body = (docs.root() / found.path).read_text(encoding="utf-8") if found else ""
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
    return f"https://github.com/FMSTM/HERON/blob/{channel()}/docs/{lang}/"


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


def manifest(
    files: list[tuple[str, bytes]],
    lang: str,
    created: str | None = None,
    fallback: list[str] | tuple[str, ...] = (),
) -> str:
    """Текст `agents/heron-kit.yaml` (20 §1): блочный YAML, LF, файлы по алфавиту.

    `files` — пути, как их хранит манифест: внутри agents/ или `root/<имя>`;
    `work/` в манифест не входит. Файл с другого языка помечен `lang`.
    """
    import heron

    major, minor, *_ = heron.__version__.split(".")
    q = json.dumps
    lines = [
        _say(lang, "kit_manifest_head"),
        f"heron_kit: {MANIFEST_FORMAT}",
        f"engine: {q(heron.__version__)}",
        f"channel: {q(channel())}",
        f"contract: {q(f'{major}.{minor}')}",
        f"lang: {lang}",
        f"created: {q(created or created_at())}",
        f"docs_url: {q(docs_url(lang))}",
        "files:",
    ]
    marked = set(fallback)
    for rel, data in sorted(files):
        if rel.startswith(WORK):
            continue
        lines.append(f"  - path: {q(rel, ensure_ascii=False)}")
        lines.append(f"    sha256: {q(sha256(data))}")
        if rel in marked:
            other = "en" if lang == "ru" else "ru"
            lines.append(f"    lang: {other}")
    return "\n".join(lines) + "\n"


def read_manifest(root: Path) -> dict[str, str]:
    """Прежний манифест: путь → sha256. Нет, битый, чужой — пусто, без ошибки."""
    path = Path(root) / KIT / MANIFEST
    try:
        if not path.is_file() or path.stat().st_size > MANIFEST_LIMIT:
            return {}
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — битый манифест: все файлы считаются правлеными
        return {}
    entries = data.get("files") if isinstance(data, dict) else None
    out: dict[str, str] = {}
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            rel, digest = entry.get("path"), entry.get("sha256")
            if isinstance(rel, str) and isinstance(digest, str):
                out[rel] = digest
    return out


# --- запись --------------------------------------------------------------------


def _site_rel(rel: str) -> str:
    """Путь манифеста → путь от корня сайта."""
    return rel.removeprefix(ROOT_PREFIX) if rel.startswith(ROOT_PREFIX) else f"{KIT}/{rel}"


def _write(root: Path, rel: str, data: bytes) -> None:
    """Запись внутрь папки сайта: ссылка наружу — E024 до записи (21 §4)."""
    path = paths.in_site(root, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = paths.in_site(root, rel)  # папки созданы — проверить ещё раз
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise HeronError(
            code=paths.CODE,
            message=f"{rel}: на месте файла комплекта не обычный файл",
            path=str(path),
            hint="уберите или переименуйте его и повторите heron init --agents",
        )
    path.write_bytes(data)


def _on_disk(root: Path, rel: str) -> bytes | None:
    path = paths.in_site(root, rel)
    if not (path.exists() or path.is_symlink()):
        return None
    if not path.is_file():
        return b"\0not-a-file"
    return path.read_bytes()


def place(
    root: Path,
    lang: str,
    fields: dict[str, Any],
    mode: Literal["create", "update"] = "create",
    force: bool = False,
    level: str = "true",
) -> KitPlan:
    """Положить или обновить комплект в папке сайта `root`.

    `create` — как остальной скелет: недостающее кладётся, существующее
    остаётся (с `force` — перезаписывается). `update` — по манифесту:
    нетронутый файл заменяется, правленый остаётся и попадает в `edited`
    (с `force` — заменяется), лишний остаётся и попадает в `orphans`.
    `work/` кладётся, только если его нет, и не перезаписывается никогда.
    Манифест пишется последним.
    """
    if mode not in ("create", "update"):
        raise ValueError(f"mode {mode!r}: expected create or update")
    level = _level(level)
    root = Path(root)
    plan = KitPlan(notes=lang, mode=mode, lang=lang, level=level)

    inner = kit_files(lang, level)
    pointers = root_files(lang, fields)
    tracked = [(rel, data) for rel, data in inner if not rel.startswith(WORK)]
    tracked += [(f"{ROOT_PREFIX}{name}", pointers[name].encode("utf-8")) for name in ROOT_FILES]
    plan.files = len(inner) + len(ROOT_FILES) + 1
    plan.fallback = [f"{KIT}/{rel}" for rel in fallback_files(lang, level)]
    old = read_manifest(root) if mode == "update" else {}

    for rel, data in inner:
        site_rel = f"{KIT}/{rel}"
        if rel.startswith(WORK) and _on_disk(root, site_rel) is None:
            _write(root, site_rel, data)
            plan.created.append(site_rel)

    for rel, data in tracked:
        site_rel = _site_rel(rel)
        current = _on_disk(root, site_rel)
        if current is None:
            _write(root, site_rel, data)
            plan.created.append(site_rel)
            continue
        if current == data:
            continue
        if mode == "create":
            if force:
                _write(root, site_rel, data)
                plan.updated.append(site_rel)
            else:
                plan.skipped.append(site_rel)
            continue
        if force or (rel in old and sha256(current) == old[rel]):
            _write(root, site_rel, data)
            plan.updated.append(site_rel)
        else:
            plan.skipped.append(site_rel)
            plan.edited.append(site_rel)

    known = {rel for rel, _ in tracked}
    for rel in sorted(old):
        if rel in known or rel.startswith(WORK):
            continue
        site_rel = _site_rel(rel)
        if _on_disk(root, site_rel) is not None:
            plan.orphans.append(site_rel)

    if plan.edited:
        plan.found.append(_say(lang, "kit_skipped_edited", files=", ".join(plan.edited)))
    if plan.orphans:
        plan.found.append(_say(lang, "kit_orphan", files=", ".join(plan.orphans)))

    manifest_rel = f"{KIT}/{MANIFEST}"
    text = manifest(tracked, lang, fallback=fallback_files(lang, level)).encode("utf-8")
    current = _on_disk(root, manifest_rel)
    if current is None:
        _write(root, manifest_rel, text)
        plan.created.append(manifest_rel)
    elif mode == "update" or force:
        if current != text:
            _write(root, manifest_rel, text)
            plan.updated.append(manifest_rel)
    elif current != text:
        plan.skipped.append(manifest_rel)
    return plan
