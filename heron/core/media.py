"""Картинки: варианты под брейкпоинты и пропорции.

В репозитории лежит ровно один файл на сущность — мастер 1:1 с запасом
по краям. Все пропорции, которые нужны теме, режутся из него при сборке.
Второй комплект под другое соотношение руками не делается: так 27 файлов
превращаются в 54 и расходятся между собой на третьей неделе.

Пропорции просит тема, ядро режет. Оригиналы не трогаются никогда.

Спецификация: docs/spec/20-data-contract.md, раздел 9;
docs/spec/21-engine.md, раздел 8.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import notes, paths
from heron.core.errors import Collector, HeronError
from heron.core.models import EXTERNAL_URL, Site
from heron.core.parser import markdown

# Папка ресурсов сайта. Имя `img` обещало только изображения, и видео класть
# было некуда — оно оседало в `static/` и ехало в сборку без обработки.
MEDIA = "media"
LEGACY = "img"
FOLDERS = (MEDIA, LEGACY)

# Путь к файлу в произвольном поле фронтматтера: тема вправе объявить своё
# поле (вторая фотография, обложка, ролик, памятка), и такой файл тоже должен
# доехать до сборки. Старое имя папки принимается наравне с новым: сайт
# переезжает одним проходом, а собираться он должен и до него, и после.
#
# Расширение не перечисляем: в media/ лежит не только то, что движок умеет
# обрабатывать. Иначе каждый новый тип файла — видео, PDF, презентация —
# требовал бы правки ядра, а до неё оседал бы в static/ мимо всех проверок.
_IN = "|".join(FOLDERS)
MEDIA_FIELD = re.compile(rf"^\.?/?(?:{_IN})/[^\s]+\.[a-z0-9]+$", re.I)

# Что движок обрабатывает сам: режет под пропорции и конвертирует. Список
# остаётся явным — файл не из него не ошибка, он просто копируется как есть.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg"}

# Порог веса. Тяжёлый файл — не ошибка: бывает и ролик на двадцать минут.
# Но человек должен узнать об этом на сборке, а не от посетителя с мобильным
# интернетом.
HEAVY = 10 * 1024 * 1024

# Чужой адрес: схема или протокол-относительная ссылка. Проверяется отдельно
# от MEDIA_FIELD, а не «само не совпадёт»: поля со ссылкой на сторонний
# хостинг будут появляться, и молчаливое совпадение однажды перестанет быть
# молчаливым — движок пойдёт искать чужой файл у себя на диске.
EXTERNAL = EXTERNAL_URL

# Предел вложенности обхода. YAML-якоря дают общие объекты, и без предела
# один дурной файл данных уводит обход в бесконечность.
MAX_DEPTH = 8

# Путь в тексте страницы: `media/x.png`, `./media/x.png` и `/media/x.png` —
# один и тот же файл. Абсолютный от корня раньше не находился, и картинка
# из markdown молча не доезжала до сборки.
REFERENCE = re.compile(rf"""(?:\(|["'\s])((?:\./|/)?(?:{_IN})/[^)"'\s]+\.[a-zA-Z0-9]+)""")
KEEP = {".jpg", ".jpeg", ".png", ".webp"}

# Нарезки живут в кэше, а в сборку попадают жёсткой ссылкой. Кэш адресуется
# содержимым: папка записи — sha256 байтов мастера, имя файла — параметры
# преобразования (вписать или кропнуть, пропорция, ширина, формат). Поэтому
#
# - два сайта с одинаковым `media/photo.jpg` и разным содержимым не делят
#   записей, а с одинаковым — делят честно: байты те же;
# - изменённый мастер — другая папка, старая нарезка не подхватится;
# - наличие файла по выходному имени ничего не значит: имя в сборке берётся
#   от сайта, а содержимое — из записи по хешу.
#
# Записывается всё через временный файл и `os.replace`: две сборки, режущие
# одно и то же одновременно, пишут одинаковые байты и не видят полуфайлов.
SLICES = "renditions"
CACHE_VERSION = 4
# Прежние форматы: индекс по путям сайта и нарезки по именам сайта. Именно
# они смешивали сайты в общем .heron-cache — убираются при первой сборке.
LEGACY_CACHE = ("media.json", "media")
# Запись, которой не пользовалась ни одна сборка столько дней, удаляется.
# Уборка по «не нужно этой сборке» в общем кэше удаляла бы чужое.
KEEP_DAYS = 30
USED = ".used"
LOCK = ".lock"

# Скорость кодировщика avif. Замер на наборе из 95 мастеров, 800px, quality 82:
#
#   speed=0   5.3 с/вариант   43.0K
#   speed=4   0.7 с/вариант   44.4K
#   speed=6   0.1 с/вариант   45.6K   <- умолчание библиотеки
#   speed=10  0.02 с/вариант  57.1K
#
# Шестёрка и есть разумный размен: четвёрка стоит впятеро дороже по времени
# ради 2.6% размера, десятка экономит время ценой четверти веса. Значение
# выставлено явно, чтобы смена умолчания в библиотеке не сделала сборку
# впятеро медленнее без единой строчки в нашем коде.
AVIF_SPEED = 6


@dataclass(slots=True)
class Rendition:
    """Один вариант картинки: пропорция, размеры, файлы по форматам."""

    ratio: str
    width: int
    height: int
    sources: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    fallback: str = ""


@dataclass(slots=True)
class Manifest:
    """Что движок может нарезать: адрес исходника -> пропорция -> вариант.

    Это план, а не готовые файлы. Шаблоны берут из него имена нарезок и
    размеры, а кодируется после рендера только то, на что в собранном сайте
    есть ссылка (`finish`). Имена нарезок от этого не меняются.
    """

    items: dict[str, dict[str, Rendition]] = field(default_factory=dict)
    # нарезка → (мастер, пропорция, формат, ширина): что кодировать по имени
    planned: dict[str, tuple[str, str, str, int]] = field(default_factory=dict)
    # мастера, которые движок режет: их самих кладём, только если на них ссылаются
    masters: set[str] = field(default_factory=set)
    # нарезка → файл записи кэша, где лежат (или лягут) её байты
    cached: dict[str, Path] = field(default_factory=dict)
    # мастера, нужные целиком по объявлению: картинка из текста, og, постер
    raw: set[str] = field(default_factory=set)
    # файлы, которые движок не режет и кладёт как есть: видео, pdf, as_is
    copies: dict[str, Path] = field(default_factory=dict)

    def get(self, src: str, ratio: str) -> Rendition | None:
        return self.items.get(paths.normalize(src), {}).get(ratio)

    def add(self, src: str, renditions: dict[str, Rendition]) -> None:
        self.items[src] = renditions
        self.masters.add(src)
        for rendition in renditions.values():
            for fmt, variants in rendition.sources.items():
                for width, rel in variants:
                    self.planned[rel] = (src, rendition.ratio, fmt, width)


def _ratio_of(ratio: str) -> tuple[int, int]:
    left, right = ratio.split(":")
    return int(left), int(right)


def _label(ratio: str) -> str:
    return ratio.replace(":", "x")


def folder(site_root: Path, collector: Collector) -> str:
    """Какая папка ресурсов у сайта: новая, старая или беда.

    Переименование `img/` в `media/` — разовый проход по сайту, и пока он
    не сделан, сайт обязан собираться: ронять чужую работу ради своего
    переименования движок не вправе. Но две папки сразу — не переходное
    состояние, а развилка: в какой из них лежит правда, движок не знает,
    и гадать здесь дороже, чем остановиться.

    Статика копируется в корень как есть, поэтому `static/media` метит
    в те же адреса, что и `media/`. Совпадение имён там — тихая перезапись
    файла, которую замечают уже в сети.
    """
    new, old = site_root / MEDIA, site_root / LEGACY
    if new.is_dir() and old.is_dir():
        raise HeronError(
            code="E018",
            message=f"в сайте есть и {MEDIA}/, и {LEGACY}/ — движок не знает, какая настоящая",
            path=str(site_root),
            hint=f"перенесите файлы в {MEDIA}/ и удалите {LEGACY}/",
        )
    shadow = site_root / "static" / MEDIA
    if shadow.is_dir() and new.is_dir():
        # Обе папки метят в /media/. Само по себе это ещё не беда: пока
        # имена не совпадают, файлы просто ложатся рядом. Беда начинается
        # на совпадении — один файл молча затирает другой уже в сети.
        clash = sorted(
            {f.relative_to(shadow).as_posix() for f in shadow.rglob("*") if f.is_file()}
            & {f.relative_to(new).as_posix() for f in new.rglob("*") if f.is_file()}
        )
        if clash:
            raise HeronError(
                code="E018",
                message=f"static/{MEDIA} и {MEDIA}/ дают один адрес: {', '.join(clash[:3])}",
                path=str(site_root),
                hint=f"держите ресурсы в одном месте: {MEDIA}/",
            )
        collector.warn(
            f"в /{MEDIA}/ отдаются две папки сразу: {MEDIA}/ и static/{MEDIA} — "
            "перенесите содержимое второй в первую",
            path=str(shadow),
            kind="картинки",
        )
    if old.is_dir():
        collector.warn(
            f"папка ресурсов называется {LEGACY}/ — переименуйте в {MEDIA}/, туда же ложится видео",
            path=str(site_root / LEGACY),
            kind="картинки",
        )
        return LEGACY
    return MEDIA


def declared_by(site: Site, config=None) -> dict[str, list[str]]:
    """Кто ссылается на картинку: путь → страницы, где он объявлен.

    Нужно для внятного предупреждения: «нет на диске» без имени страницы
    заставляет искать объявление руками по всему контенту.
    """
    where: dict[str, list[str]] = {}
    for page in site.pages:
        for src in _page_images(page):
            where.setdefault(src, []).append(page.source)
    # Сквозные блоки живут в data/ — картинка оттуда такая же настоящая.
    # Владельцем называем файл справочника: искать объявление всё равно там.
    for name, node in (getattr(site, "data", None) or {}).items():
        found: set[str] = set()
        walk(node, found)
        for src in found:
            where.setdefault(src, []).append(f"data/{name}")
    # site.yaml тоже объявляет файлы — картинку по умолчанию для соцсетей,
    # например. Без этого она не доезжала до сборки: ни одна страница её
    # не называет, и движок про неё просто не знал.
    if config is not None:
        found = set()
        walk(config.model_dump(), found)
        for src in found:
            where.setdefault(src, []).append("site.yaml")
    return where


def walk(value, found: set[str], depth: int = 0) -> None:
    """Собрать пути к картинкам из любой структуры.

    Тема вправе объявить своё поле, и поле это бывает не строкой: карта
    с подписью, список карт, карта со списками внутри. Разбирать только
    две верхние формы значит молча терять картинку — ни ошибки, ни
    предупреждения, просто пустое место на странице.

    Файл узнаём по значению, а не по имени поля: имена движок не угадывает,
    а `MEDIA_FIELD` якорится на папку медиа и требует расширения, поэтому
    строка из прозы под него не попадает.
    """
    if depth > MAX_DEPTH:
        return
    if isinstance(value, str):
        if not EXTERNAL.match(value) and MEDIA_FIELD.match(value):
            found.add(paths.normalize(value))
    elif isinstance(value, dict):
        for item in value.values():
            walk(item, found, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            walk(item, found, depth + 1)


def _page_images(page) -> set[str]:
    """Картинки одной страницы: поля фронтматтера и пути из текста."""
    found: set[str] = set()
    known_fields = (page.meta.image, page.meta.og_image, page.meta.video, page.meta.video_poster)
    for value in known_fields:
        # Поле объявлено в контракте, но значением может быть и чужой адрес:
        # ролик на стороннем хостинге искать у себя на диске незачем.
        if value and not EXTERNAL.match(value):
            found.add(paths.normalize(value))
    walk(page.meta.model_extra or {}, found)
    chunks = [page.intro.raw if page.intro else "", *(s.raw for s in page.sections.values())]
    for chunk in chunks:
        found.update(
            paths.normalize(match.group(1))
            for match in REFERENCE.finditer(markdown.without_code(chunk))
        )
    return found


def raw_references(site: Site, config=None) -> set[str]:
    """Файлы, которые нужны целиком, а не нарезками: так их объявил сайт.

    Картинка из текста страницы, обложка для соцсетей, постер ролика —
    у них один адрес, и браузер или краулер просит именно его. Такие мастера
    едут в сборку всегда, даже если тема их пока не выводит.
    """
    found: set[str] = set()
    for page in site.pages:
        for value in (
            page.meta.og_image,
            page.meta.video_poster,
            page.meta.extra.get("twitter_image"),
        ):
            if isinstance(value, str) and value and not EXTERNAL.match(value):
                found.add(paths.normalize(value))
        chunks = [page.intro.raw if page.intro else "", *(s.raw for s in page.sections.values())]
        for chunk in chunks:
            found.update(
                paths.normalize(match.group(1))
                for match in REFERENCE.finditer(markdown.without_code(chunk))
            )
    if config is not None:
        seo = config.seo.model_dump()
        for value in [
            seo.get("og_default_image"),
            *seo.get("i18n", {}).get("og_default_image", {}).values(),
        ]:
            if isinstance(value, str) and value and not EXTERNAL.match(value):
                found.add(paths.normalize(value))
    return found


def references(site: Site, config=None) -> set[str]:
    """Все файлы, которые объявил сайт: страницы, data/ и site.yaml."""
    return set(declared_by(site, config))


def _owner(declared: dict[str, list[str]], src: str) -> str:
    """Где объявлена картинка: первая страница и сколько ещё."""
    pages = declared.get(src) or []
    if not pages:
        return src
    tail = f" и ещё {len(pages) - 1}" if len(pages) > 1 else ""
    return f"{pages[0]}{tail}"


def _fit(image: Image.Image, ratio: tuple[int, int]) -> Image.Image:
    """Вписать мастер в пропорцию, добив прозрачными полями.

    Иллюстрацию кропать нельзя: рисунок доходит до края кадра, и любой
    центральный кроп срезает его часть. Поля прозрачные, поэтому на любой
    подложке темы вписанная картинка выглядит как исходная.
    """
    want = ratio[0] / ratio[1]
    have = image.width / image.height
    if abs(want - have) < 0.001:
        return image
    if have > want:
        width, height = image.width, round(image.width / want)
    else:
        width, height = round(image.height * want), image.height
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return canvas


def _has_alpha(image: Image.Image) -> bool:
    """Есть ли в картинке настоящая прозрачность."""
    if image.mode not in ("RGBA", "LA"):
        return False
    alpha = image.getchannel("A")
    return alpha.getextrema()[0] < 255


def _crop(image: Image.Image, ratio: tuple[int, int]) -> Image.Image:
    """Центральный кроп под нужную пропорцию. Только для фотографий."""
    want = ratio[0] / ratio[1]
    have = image.width / image.height
    if abs(want - have) < 0.001:
        return image
    if have > want:
        new_width = round(image.height * want)
        left = (image.width - new_width) // 2
        return image.crop((left, 0, left + new_width, image.height))
    new_height = round(image.width / want)
    top = (image.height - new_height) // 2
    return image.crop((0, top, image.width, top + new_height))


def _opaque(image: Image.Image) -> Image.Image:
    """Убрать альфа-канал, если он ничего не скрывает.

    Картинка, конвертированная из webp или снятая со сканера, часто несёт
    полностью непрозрачную альфу. Пользы от неё никакой, а кодировщики из-за
    неё уходят на медленный путь: тот же webp кодируется в десятки раз дольше.
    Прозрачность, которая действительно используется, остаётся нетронутой.
    """
    if image.mode != "RGBA":
        return image
    alpha = image.getchannel("A")
    low, _ = alpha.getextrema()
    return image.convert("RGB") if low == 255 else image


def digest(path: Path) -> str:
    """sha256 содержимого мастера — адрес его записи в кэше."""
    found = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            found.update(chunk)
    return found.hexdigest()


def _encoder() -> str:
    """Отпечаток настроек кодировщика: смена качества — другие байты."""
    payload = json.dumps(
        {f: _options(f) for f in ("webp", "avif", "jpg", "png")}, sort_keys=True
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def _weigh(source: Path, src: str, declared: dict[str, list[str]], collector: Collector) -> None:
    """Предупредить о тяжёлом файле, назвав страницу, которая его объявила."""
    if source.stat().st_size > HEAVY:
        megabytes = source.stat().st_size / 1024 / 1024
        collector.warn(
            f"{src} весит {megabytes:.0f} МБ",
            path=_owner(declared, src),
            kind="картинки",
        )


def check_video(site: Site, collector: Collector) -> None:
    """Локальный ролик обязан нести постер.

    Без постера браузер тянет первый кадр — то есть грузит видео до того,
    как посетитель нажал «играть». На мобильном интернете это десятки
    мегабайт за просмотр страницы, которую листают дальше. У стороннего
    плеера свой постер, там требовать нечего.
    """
    for page in site.pages:
        video = page.video
        if video is None or video.external or video.poster:
            continue
        collector.error(
            "E019",
            "у видео нет постера",
            path=page.source,
            hint="добавьте video_poster: без него браузер грузит ролик ради первого кадра",
        )


def unused(site: Site, site_root: Path, config=None) -> list[str]:
    """Файлы в папке ресурсов, которых не ждёт ни одна страница.

    Не ошибка и не предупреждение сборки: мастер часто кладут раньше, чем
    пишут страницу. Но в отчёте это видеть надо — иначе папка за полгода
    зарастает старыми версиями, и никто не решается ничего удалить.
    """
    root = site_root / (LEGACY if (site_root / LEGACY).is_dir() else MEDIA)
    if not root.is_dir():
        return []
    known = set(declared_by(site, config))
    rest = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        # Заметки для человека — записка движка, README рядом с мастерами,
        # список того, что ещё предстоит нарисовать, — и мусор файлового
        # менеджера. Ни то ни другое не ресурс сайта.
        if path.suffix.lower() in (".md", ".txt") or notes.skip(path):
            continue
        rel = path.relative_to(site_root).as_posix()
        if rel not in known:
            rest.append(rel)
    return rest


def verify(site: Site, site_root: Path, collector: Collector, config=None) -> None:
    """Проверить, что каждая объявленная картинка лежит на диске.

    В сборке это предупреждение: страницу пишут раньше, чем рисуют
    иллюстрацию, и блокировать работу над текстом очередью художника
    незачем. В `heron check` — ошибка: команду зовут именно затем, чтобы
    узнать, что сайт не готов.
    """
    declared = declared_by(site, config)
    for src in sorted(declared):
        source = locate(site_root, src, declared, collector)
        if source is None:
            continue
        if not source.is_file():
            collector.error(
                "E007",
                f"нет файла {src}",
                path=_owner(declared, src),
                hint="поправьте путь во фронтматтере или положите картинку",
            )


def locate(
    site_root: Path, src: str, declared: dict[str, list[str]], collector: Collector
) -> Path | None:
    """Файл ресурса на диске — только внутри папки ресурсов сайта.

    Путь берётся из фронтматтера, данных и текста, то есть пишет его сайт.
    `media/../../x` раньше читался с диска и копировался в сборку как есть.
    Теперь путь нормализуется и разрешается со всеми ссылками; выход за
    `media/` (или старую `img/`) — E024 с именем страницы, где он объявлен.
    """
    head = src.split("/", 1)[0]
    try:
        if head not in FOLDERS:
            raise HeronError(code=paths.CODE, message="")
        return paths.source(site_root / head, src.split("/", 1)[1] if "/" in src else "")
    except HeronError:
        collector.error(
            paths.CODE,
            f"путь {src!r} выходит за пределы {MEDIA}/",
            path=_owner(declared, src),
            hint="ресурсы берутся только из папки media/; уберите `..` и "
            "символические ссылки наружу",
        )
        return None


def _options(fmt: str) -> dict[str, object]:
    """Настройки кодировщика под формат."""
    options: dict[str, object] = {}
    if fmt in ("webp", "avif", "jpg", "jpeg"):
        options["quality"] = 82
    if fmt == "webp":
        # method=6 — самый медленный режим кодировщика. На пробной сборке он давал
        # 7 секунд на вариант вместо 0.1 при выигрыше в размере около двух
        # процентов: сборка сайта на полсотни картинок уезжала в часы.
        # Четыре — умолчание кодировщика и разумный размен.
        options["method"] = 4
    if fmt == "avif":
        options["speed"] = AVIF_SPEED
    return options


def _geometry(width: int, height: int, ratio: str, fits: bool) -> tuple[int, int]:
    """Размер кадра в пропорции — без самой картинки.

    Вписывание добавляет поля, кроп отрезает края: обе операции зависят
    только от размеров мастера и пропорции. Поэтому шаблон получает ширину
    и высоту `<img>` до того, как что-то закодировано.
    """
    left, right = _ratio_of(ratio)
    want = left / right
    have = width / height
    if abs(want - have) < 0.001:
        return width, height
    if fits:
        return (width, round(width / want)) if have > want else (round(height * want), height)
    return (round(height * want), height) if have > want else (width, round(width / want))


@dataclass(frozen=True, slots=True)
class Shape:
    """Что о мастере нужно плану: размеры и есть ли настоящая прозрачность.

    Зависит только от содержимого, поэтому хранится в записи кэша рядом с
    нарезками: мастер, который уже видели, не декодируется ради плана.
    """

    width: int
    height: int
    alpha: bool


def _load(source: Path) -> Image.Image:
    with Image.open(source) as opened:
        return _opaque(opened.convert("RGBA" if opened.mode in ("RGBA", "LA", "P") else "RGB"))


def shape_of(source: Path) -> Shape:
    image = _load(source)
    return Shape(width=image.width, height=image.height, alpha=_has_alpha(image))


def _fits(src: str, shape: Shape, spec: ImagesSpec) -> bool:
    """Вписать (иллюстрация) или кропнуть (фотография)."""
    return shape.alpha and not any(src.startswith(rule) for rule in spec.crop)


def variant(fits: bool, ratio: str, width: int, ext: str) -> str:
    """Имя файла нарезки внутри записи кэша: только параметры преобразования."""
    return f"{'fit' if fits else 'crop'}-{_label(ratio)}-{width}.{ext}"


def plan_master(
    src: str, source: Path, spec: ImagesSpec, shape: Shape | None = None
) -> dict[str, Rendition]:
    """Имена и размеры всех нарезок мастера, ничего не кодируя."""
    shape = shape or shape_of(source)
    stem = Path(src)
    origin = stem.suffix.lstrip(".").lower()
    fits = _fits(src, shape, spec)

    def named(ratio: str, fmt: str, size: int) -> str:
        return f"{stem.parent.as_posix()}/{stem.stem}-{_label(ratio)}-{size}.{fmt}"

    out: dict[str, Rendition] = {}
    for ratio in spec.ratios:
        frame_w, frame_h = _geometry(shape.width, shape.height, ratio, fits)
        widths = [w for w in spec.widths if w <= frame_w] or [frame_w]
        rendition = Rendition(
            ratio=ratio,
            width=widths[-1],
            height=round(widths[-1] * frame_h / frame_w),
        )
        for fmt in spec.formats:
            rendition.sources[fmt] = [(w, named(ratio, fmt, w)) for w in widths]
        # Запасной файл в исходном формате: в `<img src>` идёт одна ширина,
        # не больше fallback_width. Остальные ширины доступны media_url по
        # запросу (og:image на 1200) — и режутся, только если их попросили.
        fallback = min(spec.fallback_width, frame_w)
        origin_widths = sorted({*widths, fallback})
        rendition.sources["origin"] = [(w, named(ratio, origin, w)) for w in origin_widths]
        rendition.fallback = named(ratio, origin, fallback)
        out[ratio] = rendition
    return out


def slice_master(
    src: str,
    source: Path,
    spec: ImagesSpec,
    wanted: list[tuple[str, str, int, Path]],
) -> None:
    """Закодировать нарезки одного мастера в их файлы кэша.

    `wanted` — (пропорция, формат, ширина, файл кэша). Работает целиком
    внутри себя, без общего состояния: эту функцию зовут в отдельных
    процессах. Задача — мастер, а не вариант: декодировать исходник на
    каждую нарезку значило бы делать это сотни раз вместо одного.
    """
    if not wanted:
        return
    origin = Path(src).suffix.lstrip(".").lower()
    image = _load(source)
    # Иллюстрацию вписываем, фотографию кропаем. Признак — прозрачность:
    # у фотографии её нет и поля взять неоткуда.
    fits = _fits(src, Shape(image.width, image.height, _has_alpha(image)), spec)
    frames: dict[str, Image.Image] = {}
    for ratio, fmt, width, kept in wanted:
        if ratio not in frames:
            frames[ratio] = (_fit if fits else _crop)(image, _ratio_of(ratio))
        frame = frames[ratio]
        height = round(width * frame.height / frame.width)
        resized = frame.resize((width, height), Image.LANCZOS)
        real = origin if fmt == "origin" else fmt
        if real in ("jpg", "jpeg") and resized.mode == "RGBA":
            resized = resized.convert("RGB")
        kept.parent.mkdir(parents=True, exist_ok=True)
        temp = kept.with_name(f".{kept.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        resized.save(temp, format=_FORMATS.get(real, real.upper()), **_options(real))
        temp.chmod(0o644)  # файл уйдёт в сборку жёсткой ссылкой — сразу читаемым
        os.replace(temp, kept)


_FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "avif": "AVIF"}


def _encode(
    jobs: list[tuple[str, Path, list[tuple[str, str, int, Path]]]],
    spec: ImagesSpec,
    workers: int,
    progress,
) -> None:
    """Закодировать нужные нарезки по мастерам. По возможности — по ядрам.

    Кодирование независимо и упирается в процессор, так что ядра дают почти
    линейный выигрыш на холодной сборке — а она и есть у прода и CI, где
    кэша нет по определению.

    Прогресс тикает в порядке исходного списка, а не готовности: иначе лог
    перестаёт читаться, а смотрят в него как раз тогда, когда сборка долгая.
    """
    if not jobs:
        return
    total = len(jobs)
    count = workers if workers > 0 else (os.cpu_count() or 1)
    if count == 1 or total == 1:
        for index, (src, source, wanted) in enumerate(jobs, 1):
            if progress is not None:
                progress.tick(index, total, src)
            slice_master(src, source, spec, wanted)
        return

    with ProcessPoolExecutor(max_workers=count) as pool:
        futures = [
            pool.submit(slice_master, src, source, spec, wanted) for src, source, wanted in jobs
        ]
        for index, ((src, _, _), future) in enumerate(zip(jobs, futures, strict=True), 1):
            future.result()
            if progress is not None:
                progress.tick(index, total, src)


def store(cache_dir: Path) -> Path:
    """Папка записей кэша нарезок: формат и настройки кодировщика в имени."""
    return cache_dir / SLICES / f"v{CACHE_VERSION}-{_encoder()}"


def guard(cache_dir: Path) -> None:
    """Корень кэша и `renditions/` — настоящие папки, а не ссылки, иначе E024.

    `contained` сравнивает пути с разрешённым корнем. Если сам корень —
    ссылка наружу, разрешённый корень и есть чужая папка, и всё в ней
    «внутри кэша»: уборка удалила бы её содержимое, запись — писала бы туда.
    Битая ссылка тоже отвергается: `mkdir` создал бы папку по ней. Ссылка
    выше корня (вся папка сайта — ссылкой) законна: кэш остаётся рядом со
    сборкой, где бы она ни лежала.
    """
    for folder in (cache_dir, cache_dir / SLICES):
        if folder.is_symlink():
            raise HeronError(
                code=paths.CODE,
                message=f"кэш — ссылка, а не папка: {folder}",
                path=str(folder),
                hint="удалите эту ссылку — папка кэша пересоздастся при сборке",
            )


def contained(cache_dir: Path, path: Path) -> bool:
    """Лежит ли путь кэша внутри кэша — после разрешения всех ссылок.

    Каталог версии или записи, подменённый ссылкой наружу, иначе превращал
    бы уборку кэша в удаление чужих файлов, а запись нарезок — в запись
    куда угодно.
    """
    guard(cache_dir)
    return paths.inside(cache_dir, path) and not path.is_symlink()


def _entry(cache_dir: Path, root: Path, key: str) -> Path:
    """Запись кэша по хешу — только внутри кэша, иначе E024."""
    entry = root / key
    for folder in (cache_dir / SLICES, root, entry):
        if folder.exists() and not contained(cache_dir, folder):
            raise HeronError(
                code=paths.CODE,
                message=f"кэш нарезок ведёт за свои пределы через ссылку: {folder}",
                path=str(folder),
                hint="удалите папку .heron-cache — она пересоздастся при сборке",
            )
    return entry


def _shape(entry: Path, source: Path) -> Shape:
    """Размеры мастера из записи кэша, а нет — из самой картинки."""
    record = entry / "shape.json"
    try:
        if record.is_symlink():
            raise ValueError("shape.json — ссылка")  # пересчитать и заменить
        data = json.loads(record.read_text(encoding="utf-8"))
        return Shape(int(data["width"]), int(data["height"]), bool(data["alpha"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    shape = shape_of(source)
    entry.mkdir(parents=True, exist_ok=True)
    temp = entry / f".shape.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    temp.write_text(
        json.dumps({"width": shape.width, "height": shape.height, "alpha": shape.alpha}),
        encoding="utf-8",
    )
    os.replace(temp, record)
    return shape


def _reusable(path: Path) -> bool:
    """Готовая нарезка в записи кэша — обычный файл, его можно брать.

    Тип смотрится по самому пути (`lstat`), без перехода по ссылкам: кэш
    могли подменить — восстановить из чужого архива, положить в репозиторий
    сайта, — и ссылка на внешний файл иначе приносила бы его содержимое в
    dist. Ссылка или другой не-файл на месте нарезки убирается (сама
    запись, не её цель) и нарезка кодируется заново. Каталог на этом месте
    молча не удаляется: E024.
    """
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISREG(info.st_mode):
        return True
    if stat.S_ISDIR(info.st_mode):
        raise HeronError(
            code=paths.CODE,
            message=f"на месте нарезки в кэше — папка: {path}",
            path=str(path),
            hint="удалите папку .heron-cache — она пересоздастся при сборке",
        )
    path.unlink()
    return False


def _touch(entry: Path) -> None:
    """Отметить, что запись нужна живой сборке. Не сам файл нарезки:
    его время — это время файла в сборке, а оно не должно меняться."""
    with contextlib.suppress(OSError):
        (entry / USED).touch()


def plan(
    site: Site,
    site_root: Path,
    spec: ImagesSpec,
    collector: Collector,
    cache_dir: Path | None = None,
    strict: bool = False,
    config=None,
) -> Manifest:
    """Первая половина: что можно нарезать. Ничего не кодирует.

    Отсутствующая картинка в проде дороже упавшей сборки — поэтому в
    `--strict`, которым собирают CI и прод, это ошибка. Но страницу пишут
    раньше, чем рисуют иллюстрацию, и блокировать работу над текстом
    очередью художника незачем: при обычной сборке это предупреждение.

    Мастер читается ради хеша; декодируется он, только если его ещё не
    видел ни один сайт с этим кэшем.
    """
    manifest = Manifest()
    manifest.raw = raw_references(site, config)
    cache = cache_dir or site_root / ".heron-cache"
    root = store(cache)
    _forget_legacy(cache)

    declared = declared_by(site, config)
    for src in sorted(declared):
        source = locate(site_root, src, declared, collector)
        if source is None:
            continue
        if not source.is_file():
            if strict:
                collector.error(
                    "E007",
                    f"картинки {src} нет на диске",
                    path=_owner(declared, src),
                    hint="битая картинка в проде дороже упавшей сборки",
                )
            else:
                collector.warn(f"нет файла {src}", path=_owner(declared, src), kind="картинки")
            continue

        _weigh(source, src, declared, collector)

        # Файл не из списка обрабатываемых — не ошибка. Движок его не трогает,
        # а просто кладёт в сборку: так в media/ живут видео, памятки и всё
        # прочее, а не оседают в static/ мимо всех проверок.
        #
        # Тем же путём идёт то, что тема попросила не трогать: скан документа
        # не иллюстрация, его открывают целиком и в одном виде.
        untouched = any(src.startswith(rule) for rule in spec.as_is)
        if untouched or source.suffix.lower() not in KEEP:
            manifest.copies[src] = source
            continue

        entry = _entry(cache, root, digest(source))
        shape = _shape(entry, source)
        _touch(entry)
        renditions = plan_master(src, source, spec, shape)
        fits = _fits(src, shape, spec)
        origin = Path(src).suffix.lstrip(".").lower()
        clash = [
            rel
            for r in renditions.values()
            for variants in r.sources.values()
            for _, rel in variants
            if rel in manifest.planned and manifest.planned[rel][0] != src
        ]
        if clash:
            other = manifest.planned[clash[0]][0]
            collector.error(
                "E027",
                f"{other} и {src} дают одинаковые имена нарезок: {clash[0]}",
                path=_owner(declared, src),
                hint="имена нарезок берутся от имени файла без расширения — "
                "переименуйте один из мастеров",
            )
            continue
        manifest.add(src, renditions)
        for r in renditions.values():
            for fmt, variants in r.sources.items():
                ext = origin if fmt == "origin" else fmt
                for width, rel in variants:
                    manifest.cached[rel] = entry / variant(fits, r.ratio, width, ext)
    return manifest


def _forget_legacy(cache_dir: Path) -> None:
    """Убрать кэш прежних форматов: он адресовался путями сайта."""
    guard(cache_dir)
    for name in LEGACY_CACHE:
        old = cache_dir / name
        if old.is_symlink() or old.is_file():
            old.unlink(missing_ok=True)  # ссылку — саму ссылку, не цель
        elif old.is_dir() and contained(cache_dir, old):
            shutil.rmtree(old, ignore_errors=True)


def sweep(cache_dir: Path, days: int = KEEP_DAYS, now: float | None = None) -> list[Path]:
    """Удалить записи, которыми давно не пользовалась ни одна сборка.

    Кэш общий для сайтов, собираемых в одну папку, поэтому «не нужно этой
    сборке» — не повод удалять. Уборка идёт под исключительной блокировкой,
    чтобы две сборки не убирали одно и то же; запись, отмеченная живой
    сборкой при планировании, моложе срока и не трогается. Нарезка, уже
    стоящая в сборке жёсткой ссылкой, удалением записи не задевается.
    """
    import fcntl
    import time

    guard(cache_dir)
    base = cache_dir / SLICES
    if not base.is_dir():
        return []
    now = now or time.time()
    removed: list[Path] = []
    with (base / LOCK).open("a") as lock:
        # Живые сборки держат разделяемую блокировку (`using`) от плана до
        # записи результата. Занято — уборка ждёт следующего раза, а не
        # сборку: удалить запись, которую соседняя сборка вот-вот возьмёт,
        # значит уронить её.
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return []
        for version in base.iterdir():
            # Каталог версии, ставший ссылкой наружу, не обходится вовсе:
            # иначе «записи» в нём — чужие папки, и rmtree удалил бы их.
            if not version.is_dir() or not contained(cache_dir, version):
                continue
            current = version.name.startswith(f"v{CACHE_VERSION}-")
            for entry in version.iterdir():
                if not entry.is_dir() or not contained(cache_dir, entry):
                    continue
                marker = entry / USED
                try:
                    age = now - marker.stat().st_mtime
                except OSError:
                    age = float("inf")
                if not current or age > days * 86400:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed.append(entry)
            if not current and not any(version.iterdir()):
                version.rmdir()
    return removed


# Путь к файлу ресурсов в собранном тексте: в атрибуте, в srcset, в url()
# стилей, в разметке, в абсолютном адресе. Совпадение сверяется с планом,
# поэтому лишнее (путь из чужой папки) просто не находит пары.
_USED = re.compile(rf"""(?<=[/"'\s(,=])((?:{_IN})/[^\s"'<>()\\,]+)""")


def used_in(texts) -> set[str]:
    """Пути к ресурсам, на которые ссылается собранный сайт."""
    found: set[str] = set()
    for text in texts:
        for match in _USED.finditer(text):
            path = match.group(1)
            found.add(path)
            found.add(path.rstrip(".;:!?"))
    return found


@dataclass(frozen=True, slots=True)
class Placed:
    """Файл ресурса для сборки: куда, откуда и можно ли жёсткой ссылкой."""

    rel: str
    source: Path
    link: bool
    owner: str = ""


def finish(
    manifest: Manifest,
    site_root: Path,
    spec: ImagesSpec,
    used: set[str] | None = None,
    workers: int = 0,
    progress=None,
) -> list[Placed]:
    """Вторая половина: закодировать то, что нужно, и сказать, что класть.

    `used` — пути, на которые ссылается собранный сайт. Кодируется только
    их пересечение с планом; мастер кладётся целиком, только если на него
    самого есть ссылка (og:image, ссылка из текста, разметка). `used=None` —
    всё, что есть в плане.

    Нарезка, байты которой уже лежат в записи кэша, не кодируется заново —
    ни этим сайтом, ни соседним с тем же мастером.
    """
    wanted = set(manifest.planned) if used is None else set(manifest.planned) & used
    masters = set(manifest.masters) if used is None else manifest.masters & (used | manifest.raw)

    jobs: dict[str, list[tuple[str, str, int, Path]]] = {}
    for rel in sorted(wanted):
        kept = manifest.cached[rel]
        if _reusable(kept):
            continue
        src, ratio, fmt, width = manifest.planned[rel]
        jobs.setdefault(src, []).append((ratio, fmt, width, kept))
    _encode(
        [(src, paths.source(site_root, src), items) for src, items in jobs.items()],
        spec,
        workers,
        progress,
    )

    placed = [
        Placed(rel, manifest.cached[rel], True, f"нарезка {manifest.planned[rel][0]}")
        for rel in sorted(wanted)
    ]
    # Мастер рядом с нарезками — только по ссылке: «открыть целиком»,
    # og:image, картинка из текста. Без ссылки это мегабайты в каждой сборке.
    placed += [
        Placed(src, paths.source(site_root, src), False, f"файл {src}") for src in sorted(masters)
    ]
    placed += [
        Placed(src, source, False, f"файл {src}") for src, source in sorted(manifest.copies.items())
    ]
    return placed


@contextlib.contextmanager
def using(cache_dir: Path):
    """Сборка пользуется кэшем: разделяемая блокировка от плана до записи.

    Под ней сборки идут параллельно сколько угодно; уборке (`sweep`) нужна
    исключительная, и пока кто-то собирает, она просто не начнётся.
    """
    import fcntl

    guard(cache_dir)
    base = cache_dir / SLICES
    base.mkdir(parents=True, exist_ok=True)
    with (base / LOCK).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def sweep_daily(cache_dir: Path) -> None:
    """Уборка кэша — не чаще раза в сутки: обход всех записей не бесплатен."""
    import time

    guard(cache_dir)
    mark = cache_dir / SLICES / ".swept"
    try:
        if time.time() - mark.stat().st_mtime < 86400:
            return
    except OSError:
        pass
    sweep(cache_dir)
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.touch()


def build(
    site: Site,
    site_root: Path,
    dist: Path,
    spec: ImagesSpec,
    collector: Collector,
    cache_dir: Path | None = None,
    strict: bool = False,
    progress=None,
    config=None,
    workers: int = 0,
) -> Manifest:
    """Нарезать всё, что можно нарезать, без оглядки на шаблоны.

    Сборка сайта так не делает: она планирует (`plan`), рендерит и режет
    только то, на что есть ссылки (`finish`). Этот вход нужен там, где
    шаблонов нет, — проверить нарезку саму по себе.
    """
    from heron.core import output

    with using(cache_dir or site_root / ".heron-cache"):
        manifest = plan(site, site_root, spec, collector, cache_dir, strict, config)
        outputs = output.Outputs()
        for item in finish(manifest, site_root, spec, None, workers, progress):
            entry = output.Entry(
                owner=item.owner or item.rel, kind="media", source=item.source, link=item.link
            )
            outputs.add(item.rel, entry, collector)
        output.commit(dist, outputs)
    if cache_dir is not None:
        sweep_daily(cache_dir)
    return manifest
