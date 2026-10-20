"""Ключи доступа сайта — вне папки сайта.

Токен GitHub, токен Docker Hub, адрес и закрытый ключ модуля базы данных не
должны оказаться ни в `site.yaml`, ни в git: сборка статична, и всё, что она
видит, может уехать в HTML. Поэтому у ключей своё место — файл настроек HERON
на компьютере человека, по одному на сайт:

    ~/.config/heron/sites/<домен>.env      (права 600)

Папку можно переназначить переменной `HERON_CONFIG_DIR`. В образе HERON
домашней папки человека нет: ключи сохраняются, только если папка настроек
проброшена в контейнер (`-v ~/.config/heron:/config -e HERON_CONFIG_DIR=/config`).
Иначе конфигуратор ключей не принимает и показывает, как записать их на
компьютере: `scripts/keys.sh` спрашивает их без эха и кладёт в тот же файл.

Конфигуратор никогда не показывает значения обратно — только «задан / нет».
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ENV = "HERON_CONFIG_DIR"

NAMES = {
    "github_token": "HERON_GITHUB_TOKEN",
    "dockerhub_token": "HERON_DOCKERHUB_TOKEN",
    "db_url": "HERON_DB_URL",
    "db_key": "HERON_DB_KEY",
}
SAFE_ID = re.compile(r"[^a-z0-9.-]+")


def folder(in_container: bool) -> Path | None:
    """Папка настроек HERON или None, если её здесь нет."""
    explicit = os.environ.get(ENV, "").strip()
    if explicit:
        return Path(explicit)
    if in_container:
        return None
    return Path.home() / ".config" / "heron"


def site_id(domain: str, fallback: str) -> str:
    """Имя файла ключей: домен сайта, а без домена — имя папки."""
    value = SAFE_ID.sub("-", (domain or fallback or "site").lower()).strip("-.")
    return value or "site"


def path_for(base: Path, ident: str) -> Path:
    return base / "sites" / f"{ident}.env"


def read(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() in NAMES.values():
            out[name.strip()] = value.strip()
    return out


def status(path: Path | None) -> dict[str, bool]:
    """Какие ключи заданы. Самих значений наружу не отдаём."""
    found = read(path) if path is not None else {}
    return {key: bool(found.get(env)) for key, env in NAMES.items()}


def save(path: Path, given: dict[str, str], clear: set[str] | None = None) -> list[str]:
    """Записать ключи: пустое значение — «не менять», `clear` — удалить.

    Файл создаётся с правами 600 до записи: ключ не должен прожить ни
    мгновения в файле, который читают все.
    """
    clear = clear or set()
    current = read(path)
    changed: list[str] = []
    for key, env in NAMES.items():
        value = (given.get(key) or "").strip()
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key}: a key is one line")
        if key in clear and env in current:
            current.pop(env)
            changed.append(key)
        elif value and current.get(env) != value:
            current[env] = value
            changed.append(key)
    if not changed:
        return []
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = "".join(f"{env}={current[env]}\n" for env in NAMES.values() if env in current)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.chmod(path, 0o600)
    return changed
