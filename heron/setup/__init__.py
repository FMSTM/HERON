"""Конфигуратор `heron setup`: анкета вместо ручного `site.yaml`.

Один источник правды и для формы в браузере, и для агента:

- `answers` — модель ответов и их место в `site.yaml`;
- `vocab.yaml` — справочник типов schema.org и полей анкеты;
- `files` — что ещё ложится рядом с `site.yaml` по способу публикации;
- `server` — локальная страница анкеты.

`apply` делает всё целиком и одинаково при любом входе: проверяет ответы,
переписывает управляемые ключи `site.yaml` (прочее не трогает), подгоняет
папки под языки (`heron init`), ставит тему, если её выбрали, и пишет файлы
публикации. Повторный запуск читает тот же `site.yaml` и показывает ответы.

Спецификация: docs/spec/21-engine.md, раздел «heron setup».
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from heron.core import paths
from heron.setup import files as files_module
from heron.setup.answers import (
    CONTACT_TYPES,
    DAYS,
    PURPOSES,
    Answers,
    SchemaFindings,
    classifier,
    drop,
    field_for,
    fields_of,
    findings_payload,
    merge,
    ordered,
    read,
    vocab,
)
from heron.setup.reasons import Reason

__all__ = ["Answers", "SchemaFindings", "apply", "current_answers", "load_answers", "page", "state"]

SITE_YAML = "site.yaml"
PAGE = Path(__file__).parent / "page.html"
BACKUPS = ".heron-cache/setup"

HEADER = {
    "ru": (
        "# Все настройки сайта в одном файле. Записал heron setup: перезапуск\n"
        "# конфигуратора покажет эти ответы и перепишет только свои ключи —\n"
        "# остальное (gone, forms, свои блоки) останется как есть. Править руками\n"
        "# тоже можно: все ключи — heron docs contract, раздел 5.\n"
        "# Паролей и токенов здесь нет и быть не должно: они вне папки сайта.\n\n"
    ),
    "en": (
        "# All settings of the site in one file. Written by heron setup: running the\n"
        "# configurator again shows these answers and rewrites only its own keys;\n"
        "# the rest (gone, forms, your own blocks) stays as it is. Editing by hand\n"
        "# is fine too: every key is in heron docs contract, section 5.\n"
        "# No passwords or tokens here: they live outside the site folder.\n\n"
    ),
}


class _Dumper(yaml.SafeDumper):
    """YAML, который приятно читать: пустое без null, отступы списков."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


_Dumper.add_representer(
    type(None), lambda dumper, _value: dumper.represent_scalar("tag:yaml.org,2002:null", "")
)


def dump(data: dict[str, Any]) -> str:
    blocks = []
    for key, value in data.items():
        blocks.append(
            yaml.dump(
                {key: value},
                Dumper=_Dumper,
                sort_keys=False,
                allow_unicode=True,
                width=100,
                default_flow_style=False,
            )
        )
    return "\n".join(blocks)


@dataclass(slots=True)
class Result:
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    theme: str = ""
    backup: str = ""
    warnings: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    excepted: list[str] = field(default_factory=list)


def raw_config(root: Path) -> dict[str, Any]:
    path = root / SITE_YAML
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def notes_lang(data: dict[str, Any], flag: str | None = None) -> str:
    """Язык пояснений по флагу или build.notes разобранного конфига, иначе en."""
    block = data.get("build")
    notes = block.get("notes") if isinstance(block, dict) else None
    value = flag or str(notes or "en")
    return value if value in ("ru", "en") else "en"


def state(root: Path) -> dict[str, Any]:
    """Всё, что нужно странице анкеты: ответы, справочник, темы, репозиторий."""
    from heron import __version__, build_info

    data = raw_config(root)
    site = data.get("site")
    try:
        answers = read(data)
    except (AttributeError, TypeError, ValueError):  # site.yaml не по контракту — анкета с нуля
        answers = read({})
    themes = []
    try:
        from heron.themes import catalog

        themes = catalog()
    except Exception:  # каталог тем — подсказка, а не условие анкеты
        themes = []
    return {
        "answers": json.loads(answers.model_dump_json()),
        "vocab": vocab(),
        "fields_by_type": {kind: fields_of(kind) for kind in vocab()["types"]},
        "contact_types": list(CONTACT_TYPES),
        "purposes": list(PURPOSES),
        "git_remote": git_remote(root),
        "countries": countries(),
        "classifier": classifier(),
        "themes": themes,
        "site_theme": str((site.get("theme") if isinstance(site, dict) else "") or ""),
        "notes": notes_lang(data),
        "schema": {**schema_state(notes_lang(data)), "findings": _state_findings(data, answers)},
        "engine": build_info.label(),
        "version": __version__,
        "exists": bool(data),
    }


def _state_findings(data: dict[str, Any], answers: Answers) -> dict[str, list[dict[str, Any]]]:
    """Находки разметки в текущем site.yaml: действующие, исключённые, просроченные исключения."""
    from heron.contracts.site import SiteConfig
    from heron.core.errors import HeronError
    from heron.schemaorg.policy import site_findings

    out: dict[str, list[dict[str, Any]]] = {"active": [], "excepted": [], "expired": []}
    if not data:
        return out
    try:
        found = site_findings(SiteConfig(**data))
    except (ValueError, TypeError, HeronError):  # ошибку конфига страница показывает сама
        return out
    lang = notes_lang(data)

    def brief(entry: Any) -> dict[str, Any]:
        return {
            "key": entry.key,
            "code": entry.code,
            "path": entry.path,
            "field": field_for(entry.path),
            "reason": entry.reason,
            "until": entry.until.isoformat() if entry.until else None,
        }

    out["active"] = findings_payload(found.active, answers, lang)
    out["excepted"] = [brief(e) for e in found.excepted]
    out["expired"] = [brief(e) for e in found.expired]
    return out


DAY_LABELS = {
    "ru": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}


def schema_state(lang: str) -> dict[str, Any]:
    """Списки для полей анкеты: версия schema.org, значения перечислений, дни недели."""
    from heron.schemaorg import RELEASE
    from heron.schemaorg import vocab as schema_vocab

    labels = vocab().get("labels") or {}

    def label(enum: str, value: str) -> str:
        item = (labels.get(enum) or {}).get(value) or {}
        return str(item.get(lang) or value)

    lists: dict[str, list[dict[str, str]]] = {}
    for name, spec in vocab()["fields"].items():
        if spec.get("kind") == "enum":
            enum = spec["enum"]
            values = schema_vocab().members(enum)
            values.sort(key=lambda v: label(enum, v).casefold())
            lists[name] = [{"value": v, "label": label(enum, v)} for v in values]
        elif spec.get("kind") == "subtype":
            lists[name] = [
                {"value": v, "label": label(spec["of"], v)} for v in spec.get("options", [])
            ]
    names = DAY_LABELS.get(lang) or DAY_LABELS["en"]
    days = [{"value": d, "label": n} for d, n in zip(DAYS, names, strict=True)]
    return {"release": RELEASE, "lists": lists, "days": days}


def countries() -> list[list[str]]:
    """Справочник стран: код ISO, название по-русски и по-английски, телефонный код."""
    data = json.loads((Path(__file__).parent / "countries.json").read_text(encoding="utf-8"))
    return data["countries"]


def git_remote(root: Path) -> str:
    """`владелец/репозиторий` из origin в .git/config — подсказка для адреса образа."""
    import re

    config = Path(root) / ".git" / "config"
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    found = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', text, re.S)
    if not found:
        return ""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", found.group(1))
    return f"{match.group(1)}/{match.group(2)}" if match else ""


def _version_spec() -> str:
    from heron.scaffold import _version_spec as spec

    return spec()


def _check(data: dict[str, Any], path: Path) -> None:
    """Проверить итог той же схемой, что и сборка: анкета не пишет то, на чём сборка упадёт."""
    from heron.contracts.loader import build
    from heron.contracts.site import SiteConfig

    build(SiteConfig, data, path)


def _decide(
    root: Path,
    old: dict[str, Any],
    new: dict[str, Any],
    answers: Answers,
    schema: dict[str, Any] | None,
    lang: str,
    result: Result,
) -> dict[str, Any]:
    """Находки разметки в будущем site.yaml: check - отказ, drop - убрать, except - исключить."""
    from heron.contracts.site import SiteConfig
    from heron.schemaorg.policy import site_findings
    from heron.setup.answers import _drop

    schema = schema or {}
    mode = str(schema.get("mode") or "check")
    if mode not in ("check", "drop", "except"):
        raise Reason("schema_mode_bad", value=repr(mode))
    reason = str(schema.get("reason") or "").strip()
    if mode == "except" and not reason:
        raise Reason("reason_required")
    path = root / SITE_YAML

    def active(data: dict[str, Any]) -> list[Any]:
        return site_findings(SiteConfig(**data)).active

    entries = active(new)
    if not entries:
        return new
    payload = findings_payload(entries, answers, lang)
    if mode == "check":
        raise SchemaFindings(payload)
    if mode == "drop":
        chosen = schema.get("drop")
        if chosen is not None:
            chosen = {str(key) for key in chosen}
            payload = [f for f in payload if f["key"] in chosen]
        kept, new, labels = drop(answers, new, payload)
        rebuilt = ordered(merge(old, kept, _version_spec()))
        for item in payload:
            _drop(rebuilt, item["path"])
        _check(rebuilt, path)
        left = active(rebuilt)
        if left:
            raise SchemaFindings(findings_payload(left, kept, lang))
        result.dropped = labels
        return rebuilt
    exceptions = [dict(x) for x in (new.get("schema_exceptions") or []) if isinstance(x, dict)]
    for entry in entries:
        found = next((x for x in exceptions if x.get("key") == entry.key), None)
        if found is not None:
            found["reason"] = reason
            found.pop("until", None)
        else:
            exceptions.append({"key": entry.key, "reason": reason})
        result.excepted.append(entry.key)
    new["schema_exceptions"] = exceptions
    _check(new, path)
    return new


def backup(root: Path, name: str, data: bytes) -> Path:
    """Резервная копия в `.heron-cache/setup/<name>.<время>` — всегда новым файлом.

    Имя по секундам совпадает у двух сохранений в одну секунду. Файл
    создаётся исключительно (O_EXCL): занято — берётся следующий номер,
    существующая копия не перезаписывается никогда.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = paths.in_site(root, BACKUPS)
    for number in range(1, 1000):
        rel = f"{BACKUPS}/{name}.{stamp}" + (f"-{number}" if number > 1 else "")
        path = paths.in_site(root, rel)
        folder.mkdir(parents=True, exist_ok=True)
        paths.in_site(root, rel)  # папки созданы — проверить ещё раз
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        return path
    raise OSError(f"too many backups of {name} in one second")


def apply(
    root: Path,
    answers: Answers,
    lang: str | None = None,
    upload: Path | None = None,
    schema: dict[str, Any] | None = None,
) -> Result:
    """Записать ответы: site.yaml, папки языков, тему, файлы публикации, ключи.

    `schema` - решение по находкам проверки разметки: `mode` check (по
    умолчанию), drop или except, `drop` - ключи находок, `reason` - причина
    исключения. Нет аргумента - берётся ключ `schema` из файла ответов.
    """
    root = Path(root)
    if not (root / SITE_YAML).is_file():
        raise Reason("no_site", name=SITE_YAML, root=root)
    result = Result()
    old = raw_config(root)
    # язык пояснений — как у командной строки: --notes, HERON_NOTES, build.notes,
    # иначе en; на нём шапка site.yaml, стартовая тема и новые страницы
    from heron.setup.reasons import run_lang

    lang = run_lang(root, lang)
    new = ordered(merge(old, answers, _version_spec()))
    if answers.theme.source in ("starter", "name", "url", "file", "later") and not old:
        new["site"]["theme"] = new["site"].get("theme") or "main"
    _check(new, root / SITE_YAML)
    if schema is None:
        schema = answers._schema
    new = _decide(root, old, new, answers, schema, lang, result)

    # Всё, что анкета запишет, зарезервирует или удалит, — внутри папки сайта.
    # Проверяется до первой записи: ссылка наружу (site.yaml, content/,
    # .heron/, .heron-cache/, тема, .gitignore) — E024, и не меняется ничего.
    generated = files_module.plan(answers, lang)
    wanted = {item.rel for item in generated}
    ignore = None
    if answers.publish.helpers.get("gitignore", True) and (
        answers.publish.way != "none" or (root / ".git").exists()
    ):
        ignore = root / ".gitignore"
    checked = [SITE_YAML, BACKUPS, "content", "theme", *wanted, *files_module.OWNED]
    if ignore is not None:
        checked.append(".gitignore")
    for lang_name in new["site"]["languages"]:
        checked.append(f"content/{lang_name}")
    # комплект для агентов кладёт adopt ниже — его цели тоже до первой записи (21 §4)
    from heron.scaffold import agents as kit
    from heron.scaffold import agents_level

    level = agents_level((new.get("build") or {}).get("agents", True))
    if level != "false":
        checked += kit.targets(level, lang)
    for rel in checked:
        paths.in_site(root, rel)

    # тема — до записи site.yaml: не скачалась или не прошла проверку —
    # конфиг остаётся прежним, а не ссылается на тему, которой нет
    if answers.theme.source not in ("keep",):
        from heron import themes

        installed = themes.install(
            root,
            answers.theme.source,
            answers.theme.value,
            languages=new["site"]["languages"],
            upload=upload,
            notes=lang,
        )
        new["site"]["theme"] = installed.name
        result.theme = installed.name
        result.created.extend(installed.created)
        result.warnings.extend(installed.warnings)

    path = root / SITE_YAML
    text = HEADER[lang] + dump(new)
    if path.is_file():
        current = path.read_text(encoding="utf-8")
        if current != text:
            saved = backup(root, SITE_YAML, current.encode("utf-8"))
            result.backup = saved.relative_to(root).as_posix()
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
        result.written.append(SITE_YAML)

    # структура следует за конфигом: новый язык — папка, главная и 404
    from heron.scaffold import adopt

    made = adopt(root, notes=lang)
    result.created.extend(made.created)

    # файлы публикации
    for item in generated:
        target = root / item.rel
        if target.is_file():
            current = target.read_text(encoding="utf-8", errors="replace")
            if files_module.MARK not in current:
                result.kept.append(item.rel)
                continue
            if current == item.text:
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.text, encoding="utf-8")
        if item.executable:
            target.chmod(0o755)
        result.written.append(item.rel)
    for rel in files_module.OWNED:
        target = root / rel
        if rel in wanted or not target.is_file():
            continue
        if files_module.MARK in target.read_text(encoding="utf-8", errors="replace"):
            target.unlink()
            result.removed.append(rel)
            parent = target.parent
            while parent != root and parent.is_dir() and not any(parent.iterdir()):
                paths.in_site(root, parent)
                parent.rmdir()
                parent = parent.parent

    if ignore is not None:
        current = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
        updated = files_module.gitignore(current)
        if updated is not None:
            ignore.write_text(updated, encoding="utf-8")
            result.written.append(".gitignore")
    return result


def load_answers(text: str) -> Answers:
    """Ответы из YAML или JSON (`heron setup --answers файл`).

    Ключ `schema` (mode, drop, reason) - решение по находкам разметки, не ответ.
    """
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise Reason("answers_mapping")
    data = dict(data)
    decision = data.pop("schema", None)
    answers = Answers.model_validate(data)
    if isinstance(decision, dict):
        answers._schema = decision
    return answers


def current_answers(root: Path) -> str:
    """Записанные ответы в YAML — чтобы поправить и подать обратно."""
    answers = read(raw_config(root))
    data = json.loads(answers.model_dump_json())
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def page() -> bytes:
    """Страница анкеты так, как её отдаёт сервер: ссылки на документацию - на ветку канала образа.

    В исходнике страницы адрес ведёт на ветку prod; в образе канала beta
    (`HERON_CHANNEL`) его заменяет та же подстановка, что у комплекта и демо
    (`scaffold.agents.channel_links`, 23 §12). В prod текст байт в байт как исходник.
    """
    from heron.scaffold.agents import channel_links

    return channel_links(PAGE.read_bytes().decode("utf-8")).encode("utf-8")
