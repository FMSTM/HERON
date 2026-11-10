"""Готовые `.gz` рядом с текстовыми файлами сборки (gzip_static у nginx).

nginx жмёт ответ на лету на каждый запрос; готовый файл `x.html.gz` рядом с
`x.html` он отдаёт без работы процессора (`gzip_static on`) - и сжатый
сильнее: на лету nginx жмёт уровнем 1, при сборке - уровнем 9.

Жмутся только текстовые форматы (страницы, стили, скрипты, карты, svg,
иконка, шрифты без собственного сжатия). woff/woff2, картинки, видео и pdf
уже сжаты. Файл меньше 1024 байт или файл, который не стал меньше, остаётся
без `.gz`: выигрыша нет, а лишний файл есть.

Сжатие детерминировано: уровень 9, время в заголовке 0, имени файла нет -
две сборки одних исходников дают одинаковые байты. Если в папке сборки уже
лежит свой `.gz` прошлой сборки и в нём ровно новые байты, он берётся как
есть: распаковать дешевле, чем сжать заново.

Спецификация: docs/spec/21-engine.md, раздел 4, «Запись результата»; 22 §5.
"""

from __future__ import annotations

import gzip
import os
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from heron.core import output

SUFFIX = ".gz"
EXTENSIONS = frozenset(
    {"html", "css", "js", "mjs", "json", "xml", "txt", "svg", "webmanifest", "ico", "ttf", "otf"}
)
MIN_SIZE = 1024
LEVEL = 9


def compressible(rel: str) -> bool:
    """Путь сборки, которому положен `.gz`: текстовый формат и не скрытый файл."""
    if any(part.startswith(".") for part in rel.split("/")):
        return False
    name = rel.rsplit("/", 1)[-1]
    return "." in name and name.rsplit(".", 1)[1].lower() in EXTENSIONS


def compress(data: bytes) -> bytes:
    """gzip уровня 9 без времени и имени файла: одинаковые байты на любой машине."""
    return gzip.compress(data, compresslevel=LEVEL, mtime=0)


def _content(entry: output.Entry) -> bytes | None:
    if entry.data is not None:
        return entry.data
    if entry.text is not None:
        return entry.text.encode("utf-8")
    if entry.source is None:
        return None
    try:
        return entry.source.read_bytes()
    except OSError:
        return None


def _reusable(packed: Path, data: bytes) -> bool:
    """В папке сборки уже лежит `.gz` ровно этих байт."""
    try:
        if packed.is_symlink() or not packed.is_file():
            return False
        unpack = zlib.decompressobj(wbits=31)
        got = unpack.decompress(packed.read_bytes(), len(data) + 1)
        return got == data and unpack.eof
    except (OSError, zlib.error):
        return False


def _one(rel: str, data: bytes, dist: Path | None, mine: bool) -> tuple[str, Path | bytes | None]:
    if dist is not None and mine and _reusable(dist / (rel + SUFFIX), data):
        return rel, dist / (rel + SUFFIX)
    packed = compress(data)
    return rel, packed if len(packed) < len(data) else None


def add(outputs: output.Outputs, dist: Path | None = None, workers: int | None = None) -> int:
    """Заявить `.gz` для всех подходящих файлов сборки. Возвращает их число.

    `.gz`, заявленный кем-то ещё (своим файлом статики), не перекрывается.
    `dist` - папка прошлой сборки: её `.gz` из манифеста берутся без сжатия.
    """
    previous = output.previous(dist) if dist is not None else set()
    jobs: list[tuple[str, bytes]] = []
    for rel in sorted(outputs.entries):
        if not compressible(rel) or rel + SUFFIX in outputs.entries:
            continue
        data = _content(outputs.entries[rel])
        if data is None or len(data) < MIN_SIZE:
            continue
        jobs.append((rel, data))
    count = workers or min(8, os.cpu_count() or 1)
    with ThreadPoolExecutor(max_workers=max(1, count)) as pool:
        done = list(
            pool.map(lambda job: _one(job[0], job[1], dist, job[0] + SUFFIX in previous), jobs)
        )
    added = 0
    for rel, result in done:
        if result is None:
            continue
        owner = outputs.entries[rel].owner
        if isinstance(result, Path):
            entry = output.Entry(owner=owner, kind="gzip", source=result)
        else:
            entry = output.Entry(owner=owner, kind="gzip", data=result)
        outputs.entries[rel + SUFFIX] = entry
        added += 1
    return added
