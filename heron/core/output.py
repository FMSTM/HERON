"""Результат сборки: кто чем владеет и как он попадает в папку сборки.

Раньше каждый этап писал в `dist/` сам: страницы, карты, статика поверх
них, нарезки, конфиг. Отсюда три беды:

- `static/robots.txt` молча заменял сгенерированный — кто записал
  последним, тот и прав;
- удалённая или снятая с публикации страница оставалась в `dist/` навсегда:
  никто не помнил, что её туда писали;
- строгая сборка падала на предупреждении уже после записи, и прошлая
  удачная версия оказывалась наполовину перезаписана.

Теперь этапы только заявляют файлы (`Outputs.add`), а пишет один
`commit`, и только после того, как сборка признана удачной. У каждого
выходного пути один владелец; спор двух владельцев — `E026`, кроме явно
разрешённых в `build.overrides` подмен генерированного файла статикой.

Применение — в два шага: сначала всё новое готовится во временной папке
внутри `dist/` (та же файловая система), затем переименованиями ставится
на место и удаляется устаревшее — только то, что числится в манифесте
прошлой сборки (`.heron-manifest.json`). Чужие файлы в `dist/` не
трогаются. Неизменившийся файл не переписывается: у него остаются время и
ETag, а у кэша — его жёсткая ссылка.

Файл из кэша ставится жёсткой ссылкой, но общий с кэшем inode никогда не
правится на месте: заменяется запись каталога (`os.replace`), не данные.

Спецификация: docs/spec/21-engine.md, раздел 4, «Запись результата».
"""

from __future__ import annotations

import fcntl
import filecmp
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from heron.core import paths
from heron.core.errors import Collector, HeronError
from heron.messages import Msg

MANIFEST = ".heron-manifest.json"
STAGING = ".heron-staging"
CONFLICT = "E026"
RESERVED = {MANIFEST}
FORMAT = 1


@dataclass(slots=True)
class Entry:
    """Один выходной файл: кто его заявил и откуда взять содержимое."""

    owner: str  # человеку: «страница en/a.md», «static/robots.txt»
    kind: str  # page, generator, static, asset, media, plugin
    text: str | None = None
    source: Path | None = None
    link: bool = False  # можно ставить жёсткой ссылкой (файл кэша)


# Кто может подменить чужой файл по `build.overrides`: только статика и
# только генерированный файл. Страницу или нарезку статика не подменяет.
OVERRIDABLE = {"generator"}


@dataclass(slots=True)
class Outputs:
    """Все файлы будущей сборки — до того, как хоть один записан."""

    entries: dict[str, Entry] = field(default_factory=dict)
    overrides: set[str] = field(default_factory=set)
    used_overrides: set[str] = field(default_factory=set)

    def add(self, rel: str, entry: Entry, collector: Collector) -> None:
        """Заявить файл. Спор владельцев — E026 с обоими именами."""
        clean = paths.normalize(rel)
        if clean in RESERVED or clean.split("/", 1)[0] == STAGING:
            collector.error(
                CONFLICT,
                Msg("output_reserved_name", owner=entry.owner, clean=clean),
                path=entry.owner,
                hint=Msg("output_rename_file"),
            )
            return
        if not clean or clean == "." or paths.escapes(clean):
            collector.error(
                paths.CODE,
                Msg("output_path_outside", owner=entry.owner, rel=repr(rel)),
                path=entry.owner,
            )
            return
        held = self.entries.get(clean)
        if held is None:
            self.entries[clean] = entry
            return
        if entry.kind == "static" and held.kind in OVERRIDABLE and clean in self.overrides:
            self.used_overrides.add(clean)
            self.entries[clean] = entry
            return
        collector.error(
            CONFLICT,
            Msg("output_conflict", clean=clean, held=held.owner, owner=entry.owner),
            path=entry.owner,
            hint=(
                Msg("output_conflict_override_hint", owner=entry.owner, clean=clean)
                if entry.kind == "static" and held.kind in OVERRIDABLE
                else Msg("output_conflict_hint")
            ),
        )

    def check_tree(self, collector: Collector) -> None:
        """Файл и папка с одним именем: `a` и `a/index.html` не уживутся."""
        names = set(self.entries)
        for rel in sorted(names):
            parts = rel.split("/")
            for depth in range(1, len(parts)):
                folder = "/".join(parts[:depth])
                if folder in names:
                    collector.error(
                        CONFLICT,
                        Msg(
                            "output_file_and_folder",
                            folder=folder,
                            file_owner=self.entries[folder].owner,
                            rel=rel,
                            owner=self.entries[rel].owner,
                        ),
                        path=self.entries[rel].owner,
                        hint=Msg("output_rename_either"),
                    )

    def check_overrides(self, collector: Collector) -> None:
        """Подмена, которая ничего не подменила, — опечатка в site.yaml."""
        for rel in sorted(self.overrides - self.used_overrides):
            collector.warn(
                Msg("output_override_unused", rel=rel),
                path="site.yaml",
                kind="прочее",
            )

    def text_of(self, rel: str) -> str | None:
        """Итоговое содержимое файла сборки текстом — кто бы его ни заявил.

        Файла в сборке нет — None. Файл есть, но не читается или не UTF-8 —
        E034: иначе проверка, которой нужен текст (nginx -t), молча
        пропускалась бы, а сам файл уезжал в сборку.
        """
        entry = self.entries.get(rel)
        if entry is None:
            return None
        if entry.text is not None:
            return entry.text
        if entry.source is None:
            return None
        try:
            return entry.source.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            reason = Msg("output_not_utf8", byte=error.start)
        except OSError as error:
            reason = Msg("output_unreadable", reason=error.strerror or type(error).__name__)
        raise HeronError(
            code="E034",
            message=Msg("output_file_unreadable", rel=rel, owner=entry.owner, reason=reason),
            path=str(entry.source),
            hint=Msg("output_utf8_hint"),
        )

    def texts(self) -> list[str]:
        return [e.text for e in self.entries.values() if e.text is not None]


@dataclass(slots=True)
class Applied:
    """Что сделал `commit`: для отчёта и для тестов."""

    written: list[str] = field(default_factory=list)  # новые или изменённые
    kept: list[str] = field(default_factory=list)  # те же байты, не тронуты
    removed: list[str] = field(default_factory=list)  # свои устаревшие


def previous(dist: Path) -> set[str]:
    """Файлы, которыми владела прошлая сборка в этой папке."""
    try:
        data = json.loads((dist / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return set()
    return {
        rel
        for rel in data.get("files", [])
        if isinstance(rel, str) and not paths.escapes(paths.normalize(rel))
    }


def _same(out: Path, entry: Entry) -> bool:
    """Лежит ли там уже ровно это — тогда не трогать."""
    if not out.is_file() or out.is_symlink():
        return False
    try:
        if entry.text is not None:
            data = entry.text.encode("utf-8")
            return out.stat().st_size == len(data) and out.read_bytes() == data
        assert entry.source is not None
        if entry.link and os.path.samefile(out, entry.source):
            return True
        return filecmp.cmp(out, entry.source, shallow=False)
    except OSError:
        return False


def _prepare(staging: Path, entry: Entry) -> Path:
    """Готовый файл во временной папке. Общий с кэшем inode не трогается."""
    temp = staging / uuid.uuid4().hex
    if entry.text is not None:
        temp.write_text(entry.text, encoding="utf-8")
        temp.chmod(0o644)
        return temp
    assert entry.source is not None
    if entry.link and entry.source.is_symlink():
        # Связываются только готовые нарезки кэша, и media.finish уже
        # проверил, что это обычные файлы. Ссылка здесь — подмена между
        # проверкой и записью: её цель в dist не попадает.
        raise HeronError(
            code=paths.CODE,
            message=Msg("output_cache_link", source=entry.source),
            path=str(entry.source),
            hint=Msg("output_cache_link_hint"),
        )
    if entry.link:
        try:
            os.link(entry.source, temp)
            return temp
        except OSError:
            pass  # другой том, FAT — копируем
    shutil.copyfile(entry.source, temp)
    temp.chmod(0o644)
    return temp


def _blocker(dist: Path, rel: str, stale: set[str]) -> str | None:
    """Чужой файл на месте нужной папки или чужая папка на месте файла."""
    parts = rel.split("/")
    for depth in range(1, len(parts)):
        folder = "/".join(parts[:depth])
        spot = dist / folder
        if (spot.is_file() or spot.is_symlink()) and folder not in stale:
            return folder
    out = dist / rel
    if out.is_dir() and not out.is_symlink():
        foreign = [
            p for p in out.rglob("*") if p.is_file() and p.relative_to(dist).as_posix() not in stale
        ]
        if foreign:
            return rel
    return None


def unwritable(path: Path, error: OSError) -> HeronError:
    """Нельзя создать папку или файл рядом со сборкой — E035 вместо общего «denied»."""
    return HeronError(
        code="E035",
        message=Msg("output_cannot_create", path=path, reason=error.strerror or error),
        path=str(path),
        hint=Msg("output_cannot_create_hint"),
    )


def make_dir(folder: Path) -> None:
    """Создать папку (с родителями), а отказ системы показать как E035."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise unwritable(folder, error) from error


def commit(dist: Path, outputs: Outputs) -> Applied:
    """Поставить новую сборку на место старой.

    Вызывается только после того, как сборка признана удачной: ошибок нет,
    а при строгом режиме нет и предупреждений. Всё, что может не получиться
    по вине содержимого, проверено до первого переименования.
    """
    make_dir(dist)
    # Две сборки в одну папку одновременно (CI, наблюдатель и ручная) не
    # должны применяться вперемешку: применение — под блокировкой. Файл
    # блокировки лежит рядом с папкой сборки, а не в ней: внутри он уехал бы
    # в сеть.
    lock_path = dist.parent / f".{dist.name}.heron-lock"
    try:
        lock = lock_path.open("a")
    except OSError as error:
        raise unwritable(lock_path, error) from error
    with lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _commit(dist, outputs)


def _write_manifest(dist: Path, staging: Path, files: set[str] | list[str]) -> None:
    """Список своих файлов — атомарно: временный файл и `os.replace`."""
    listing = json.dumps({"format": FORMAT, "files": sorted(files)}, ensure_ascii=False, indent=0)
    current = dist / MANIFEST
    if current.is_file() and current.read_text(encoding="utf-8") == listing:
        return
    manifest = staging / f"{MANIFEST}.{uuid.uuid4().hex}"
    manifest.write_text(listing, encoding="utf-8")
    manifest.chmod(0o644)
    os.replace(manifest, current)


def _legacy(dist: Path) -> bool:
    """Папка собрана движком до манифеста: в ней лежит его конфиг nginx.

    Тогда файлы на нужных путях — прошлая сборка, а не чужие: их можно
    заменить. Без этого признака и без манифеста файл на нужном месте
    положил не движок.
    """
    return not (dist / MANIFEST).exists() and (dist / ".heron-nginx.conf").is_file()


def _commit(dist: Path, outputs: Outputs) -> Applied:
    old = previous(dist)
    wanted = outputs.entries
    stale = old - set(wanted)
    applied = Applied()
    adopt = _legacy(dist)

    for rel in sorted(wanted):
        paths.target(dist, rel)  # E024, если путь уводит наружу через ссылку
        out = dist / rel
        # Чужой обычный файл на нужном месте: его положил не движок (нет в
        # манифесте) — молча затирать нельзя. Те же байты — не спор.
        if (
            out.is_file()
            and not out.is_symlink()
            and rel not in old
            and not adopt
            and not _same(out, wanted[rel])
        ):
            raise HeronError(
                code=CONFLICT,
                message=Msg("output_foreign_file", rel=rel),
                path=str(out),
                hint=Msg("output_foreign_hint"),
            )
        blocker = _blocker(dist, rel, stale)
        if blocker is not None:
            raise HeronError(
                code=CONFLICT,
                message=Msg("output_foreign_blocker", rel=rel, blocker=blocker),
                path=str(dist / blocker),
                hint=Msg("output_foreign_hint"),
            )

    staging = dist / STAGING
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        ready: list[tuple[str, Path]] = []
        for rel in sorted(wanted):
            entry = wanted[rel]
            if _same(dist / rel, entry):
                applied.kept.append(rel)
                continue
            ready.append((rel, _prepare(staging, entry)))

        # Журнал до первой правки: манифест заранее перечисляет всё, что
        # может оказаться в dist после этого применения, — старое и новое.
        # Оборвётся посреди переименований — следующая сборка знает, что
        # новые файлы её, и уберёт лишние, не трогая чужого.
        _write_manifest(dist, staging, old | set(wanted))

        # Сначала убрать своё устаревшее: на его месте может встать папка.
        # Только внутри dist по настоящему пути: папка, подменённая ссылкой
        # наружу, не даёт удалить чужой файл по старому имени.
        for rel in sorted(stale, key=lambda r: r.count("/"), reverse=True):
            spot = dist / rel
            if not paths.inside(dist, spot.parent):
                continue
            if spot.is_symlink() or spot.is_file():
                spot.unlink()
                applied.removed.append(rel)
                _prune(dist, spot.parent)

        for rel, temp in ready:
            out = dist / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.is_dir() and not out.is_symlink():
                shutil.rmtree(out)  # только своё: чужое отсёк _blocker
            os.replace(temp, out)
            applied.written.append(rel)

        _write_manifest(dist, staging, set(wanted))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    # Папки, в которые сборка что-то положила, должны открываться серверу.
    # Только свои и только внутри dist: чужие папки и цели ссылок не трогаем.
    folders = {dist}
    for rel in applied.written:
        parent = (dist / rel).parent
        while parent != dist and parent.is_relative_to(dist):
            folders.add(parent)
            parent = parent.parent
    for folder in sorted(folders):
        if folder.is_symlink() or not paths.inside(dist, folder):
            continue
        try:
            folder.chmod(folder.stat().st_mode | 0o755)
        except OSError:
            continue
    return applied


def _prune(dist: Path, folder: Path) -> None:
    """Убрать опустевшие папки вверх до корня сборки."""
    while folder != dist and folder.is_relative_to(dist):
        if folder.is_symlink() or not paths.inside(dist, folder):
            return
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent
