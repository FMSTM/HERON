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
    PURPOSES,
    Answers,
    classifier,
    fields_of,
    merge,
    ordered,
    read,
    vocab,
)

__all__ = ["Answers", "apply", "current_answers", "load_answers", "state"]

SITE_YAML = "site.yaml"
BACKUPS = ".heron-cache/setup"

HEADER = {
    "ru": (
        "# Все настройки сайта в одном файле. Записал heron setup: перезапуск\n"
        "# конфигуратора покажет эти ответы и перепишет только свои ключи —\n"
        "# остальное (gone, forms, свои блоки) останется как есть. Править руками\n"
        "# тоже можно: все ключи — heron docs site-yaml.\n"
        "# Паролей и токенов здесь нет и быть не должно: они вне папки сайта.\n\n"
    ),
    "en": (
        "# All settings of the site in one file. Written by heron setup: running the\n"
        "# configurator again shows these answers and rewrites only its own keys;\n"
        "# the rest (gone, forms, your own blocks) stays as it is. Editing by hand\n"
        "# is fine too: every key is in heron docs site-yaml.\n"
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


def raw_config(root: Path) -> dict[str, Any]:
    path = root / SITE_YAML
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def notes_lang(data: dict[str, Any], flag: str | None = None) -> str:
    value = flag or str((data.get("build") or {}).get("notes") or "en")
    return value if value in ("ru", "en") else "en"


def state(root: Path) -> dict[str, Any]:
    """Всё, что нужно странице анкеты: ответы, справочник, темы, репозиторий."""
    from heron import __version__, build_info

    data = raw_config(root)
    answers = read(data)
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
        "site_theme": str((data.get("site") or {}).get("theme") or ""),
        "notes": notes_lang(data),
        "engine": build_info.label(),
        "version": __version__,
        "exists": bool(data),
    }


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
) -> Result:
    """Записать ответы: site.yaml, папки языков, тему, файлы публикации, ключи."""
    root = Path(root)
    if not (root / SITE_YAML).is_file():
        raise ValueError(f"no {SITE_YAML} in {root}: create the site first (heron new)")
    result = Result()
    old = raw_config(root)
    lang = notes_lang(old, lang)
    new = ordered(merge(old, answers, _version_spec()))
    if answers.theme.source in ("starter", "name", "url", "file", "later") and not old:
        new["site"]["theme"] = new["site"].get("theme") or "main"
    _check(new, root / SITE_YAML)

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
    """Ответы из YAML или JSON (`heron setup --answers файл`)."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("answers: a mapping is expected")
    return Answers.model_validate(data)


def current_answers(root: Path) -> str:
    """Записанные ответы в YAML — чтобы поправить и подать обратно."""
    answers = read(raw_config(root))
    data = json.loads(answers.model_dump_json())
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)
