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

import hashlib
import json
import os
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import notes, paths
from heron.core.errors import Collector, HeronError
from heron.core.models import Site

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
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:)?//", re.I)

# Предел вложенности обхода. YAML-якоря дают общие объекты, и без предела
# один дурной файл данных уводит обход в бесконечность.
MAX_DEPTH = 8

# Путь в тексте страницы: `media/x.png`, `./media/x.png` и `/media/x.png` —
# один и тот же файл. Абсолютный от корня раньше не находился, и картинка
# из markdown молча не доезжала до сборки.
REFERENCE = re.compile(rf"""(?:\(|["'\s])((?:\./|/)?(?:{_IN})/[^)"'\s]+\.[a-zA-Z0-9]+)""")
CACHE = "media.json"
KEEP = {".jpg", ".jpeg", ".png", ".webp"}

# Нарезки живут в кэше, а в сборку попадают жёсткой ссылкой. Иначе кэш
# бесполезен: `dist` стирают перед каждой сборкой (он расходный — так и
# задумано), digest в записи совпадает, файла нет, и всё кодируется заново.
# Состояние должно лежать там, где его никто не стирает.
SLICES = "media"

# Версия формата кэша. Запись хранит digest и план мастера (имена и размеры
# нарезок) — иначе, чтобы узнать имена, пришлось бы открывать мастер: список
# ширин зависит от ширины исходника. В третьей версии запасной формат режется
# одной шириной, и план другой. Старый кэш другого формата протухает один раз.
CACHE_VERSION = 3

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
    # что лежит в кэше нарезок: digest и план мастера — для уборки и записи кэша
    entries: dict[str, dict] = field(default_factory=dict)
    # мастера, нужные целиком по объявлению: картинка из текста, og, постер
    raw: set[str] = field(default_factory=set)

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
        found.update(paths.normalize(match.group(1)) for match in REFERENCE.finditer(chunk))
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
            found.update(paths.normalize(match.group(1)) for match in REFERENCE.finditer(chunk))
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


def _digest(path: Path, spec: ImagesSpec) -> str:
    payload = hashlib.sha1(path.read_bytes())
    payload.update(json.dumps(spec.model_dump(), sort_keys=True).encode())
    return payload.hexdigest()


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


def _as_dict(renditions: dict[str, Rendition]) -> dict:
    """Кусок манифеста одного мастера в вид, который переживёт json."""
    return {
        ratio: {
            "width": r.width,
            "height": r.height,
            "sources": {fmt: [[w, rel] for w, rel in items] for fmt, items in r.sources.items()},
            "fallback": r.fallback,
        }
        for ratio, r in renditions.items()
    }


def _from_dict(data: dict) -> dict[str, Rendition]:
    return {
        ratio: Rendition(
            ratio=ratio,
            width=int(node["width"]),
            height=int(node["height"]),
            sources={
                fmt: [(int(w), rel) for w, rel in items]
                for fmt, items in node.get("sources", {}).items()
            },
            fallback=node.get("fallback", ""),
        )
        for ratio, node in data.items()
    }


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


def plan_master(src: str, source: Path, spec: ImagesSpec) -> dict[str, Rendition]:
    """Имена и размеры всех нарезок мастера, ничего не кодируя.

    Мастер декодируется один раз — только чтобы узнать, есть ли в нём
    настоящая прозрачность: от этого зависит, вписывать его или кропать.
    """
    stem = Path(src)
    origin = stem.suffix.lstrip(".").lower()
    with Image.open(source) as opened:
        image = _opaque(opened.convert("RGBA" if opened.mode in ("RGBA", "LA", "P") else "RGB"))
        fits = _has_alpha(image) and not any(src.startswith(rule) for rule in spec.crop)
        width, height = image.width, image.height

    def named(ratio: str, fmt: str, size: int) -> str:
        return f"{stem.parent.as_posix()}/{stem.stem}-{_label(ratio)}-{size}.{fmt}"

    out: dict[str, Rendition] = {}
    for ratio in spec.ratios:
        frame_w, frame_h = _geometry(width, height, ratio, fits)
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
    slices: Path,
    wanted: list[tuple[str, str, int, str]] | None = None,
) -> dict[str, Rendition]:
    """Закодировать нарезки одного мастера в кэш и вернуть его план.

    `wanted` — что именно кодировать: (пропорция, формат, ширина, имя).
    Не задано — всё, что есть в плане. Работает целиком внутри себя, без
    общего состояния: эту функцию зовут в отдельных процессах. Задача —
    мастер, а не вариант: открывать и декодировать исходник на каждую
    нарезку значило бы делать это сотни раз вместо одного.
    """
    renditions = plan_master(src, source, spec)
    if wanted is None:
        wanted = [
            (rendition.ratio, fmt, width, rel)
            for rendition in renditions.values()
            for fmt, variants in rendition.sources.items()
            for width, rel in variants
        ]
    if not wanted:
        return renditions
    origin = Path(src).suffix.lstrip(".").lower()
    with Image.open(source) as opened:
        image = _opaque(opened.convert("RGBA" if opened.mode in ("RGBA", "LA", "P") else "RGB"))
        # Иллюстрацию вписываем, фотографию кропаем. Признак — прозрачность:
        # у фотографии её нет и поля взять неоткуда.
        fits = _has_alpha(image) and not any(src.startswith(rule) for rule in spec.crop)
        frames: dict[str, Image.Image] = {}
        for ratio, fmt, width, rel in wanted:
            if ratio not in frames:
                frames[ratio] = (_fit if fits else _crop)(image, _ratio_of(ratio))
            frame = frames[ratio]
            # Пишем всегда, даже если файл с таким именем лежит: задача
            # заводится только для того, чего в кэше нет или что устарело.
            kept = slices / rel
            kept.parent.mkdir(parents=True, exist_ok=True)
            height = round(width * frame.height / frame.width)
            resized = frame.resize((width, height), Image.LANCZOS)
            real = origin if fmt == "origin" else fmt
            if real in ("jpg", "jpeg") and resized.mode == "RGBA":
                resized = resized.convert("RGB")
            resized.save(kept, **_options(real))
    return renditions


def _place(kept: Path, out: Path) -> None:
    """Положить нарезку в сборку жёсткой ссылкой, а не копией.

    Копия — это ещё гигабайт на диске и минута на запись при каждой сборке.
    Ссылка не стоит ничего. Файловая система может её не дать — сетевой том,
    другой раздел, FAT — тогда копируем и молчим: это не повод падать.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    try:
        os.link(kept, out)
    except OSError:
        shutil.copyfile(kept, out)


def _sweep(slices: Path, used: set[str]) -> None:
    """Убрать из кэша нарезки, которых нет в манифесте этой сборки.

    Мусор копится в двух случаях: мастер удалили из контента или из спека
    темы убрали ширину. На сайт это не влияет — в сборку попадает только то,
    что в манифесте, — но место занимает бесконечно.

    Уборка идёт по манифесту, а не по списку пересчитанного: сборка могла
    упасть раньше, и тогда сносить нечего.
    """
    if not slices.is_dir():
        return
    for path in sorted(slices.rglob("*"), reverse=True):
        if path.is_file():
            if path.relative_to(slices).as_posix() not in used:
                path.unlink(missing_ok=True)
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def _encode(
    jobs: list[tuple[str, Path, list[tuple[str, str, int, str]]]],
    spec: ImagesSpec,
    slices: Path,
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
            slice_master(src, source, spec, slices, wanted)
        return

    with ProcessPoolExecutor(max_workers=count) as pool:
        futures = [
            pool.submit(slice_master, src, source, spec, slices, wanted)
            for src, source, wanted in jobs
        ]
        for index, ((src, _, _), future) in enumerate(zip(jobs, futures, strict=True), 1):
            future.result()
            if progress is not None:
                progress.tick(index, total, src)


def _paths(root: Path) -> tuple[Path, Path]:
    return root / CACHE, root / SLICES


def plan(
    site: Site,
    site_root: Path,
    dist: Path,
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

    План мастера (имена нарезок, размеры) лежит в кэше рядом с digest:
    мастер, который не менялся, не открывается вовсе.
    """
    manifest = Manifest()
    manifest.raw = raw_references(site, config)
    cache_path, slices = _paths(cache_dir or site_root / ".heron-cache")

    known: dict[str, dict] = {}
    if cache_path.is_file():
        try:
            stored = json.loads(cache_path.read_text(encoding="utf-8"))
        except ValueError:
            stored = {}
        if isinstance(stored, dict) and stored.get("version") == CACHE_VERSION:
            known = stored.get("masters", {})

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
            out = paths.target(dist, src)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(source.read_bytes())
            continue

        digest = _digest(source, spec)
        entry = known.get(src)
        if entry is not None and entry.get("digest") == digest and entry.get("renditions"):
            renditions = _from_dict(entry["renditions"])
        else:
            if entry is not None:
                # Мастер изменился: его старые нарезки в кэше больше не правда.
                # Имена от содержимого не зависят, поэтому удалить их надо
                # явно — иначе новая сборка подхватит старую картинку.
                for old in _from_dict(entry.get("renditions", {})).values():
                    for variants in old.sources.values():
                        for _, rel in variants:
                            (slices / rel).unlink(missing_ok=True)
            renditions = plan_master(src, source, spec)
        manifest.add(src, renditions)
        manifest.entries[src] = {"digest": digest, "renditions": _as_dict(renditions)}
    return manifest


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


def finish(
    manifest: Manifest,
    site_root: Path,
    dist: Path,
    spec: ImagesSpec,
    used: set[str] | None = None,
    cache_dir: Path | None = None,
    workers: int = 0,
    progress=None,
) -> list[str]:
    """Вторая половина: закодировать и положить в сборку то, что нужно.

    `used` — пути, на которые ссылается собранный сайт. Кодируется и
    кладётся только их пересечение с планом; мастер кладётся целиком, только
    если на него самого есть ссылка (og:image, ссылка из текста, разметка).
    `used=None` — всё, что есть в плане: так режет `build`.

    Нарезки хранятся в кэше и попадают в сборку жёсткой ссылкой. Кэш может
    держать больше, чем ушло в эту сборку: правка шаблона, которая вернёт
    пропорцию, не должна кодировать её заново.
    """
    cache_path, slices = _paths(cache_dir or site_root / ".heron-cache")
    wanted = set(manifest.planned) if used is None else set(manifest.planned) & used
    masters = set(manifest.masters) if used is None else manifest.masters & (used | manifest.raw)

    jobs: dict[str, list[tuple[str, str, int, str]]] = {}
    for rel in sorted(wanted):
        if (slices / rel).is_file():
            continue
        src, ratio, fmt, width = manifest.planned[rel]
        jobs.setdefault(src, []).append((ratio, fmt, width, rel))
    _encode(
        [(src, site_root / src, items) for src, items in jobs.items()],
        spec,
        slices,
        workers,
        progress,
    )

    placed = []
    for rel in sorted(wanted):
        _place(slices / rel, paths.target(dist, rel))
        placed.append(rel)
    # Мастер рядом с нарезками — только по ссылке: «открыть целиком»,
    # og:image, картинка из текста. Без ссылки это мегабайты в каждой сборке.
    for src in sorted(masters):
        out = paths.target(dist, src)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(paths.source(site_root, src).read_bytes())
        placed.append(src)

    _sweep(slices, set(manifest.planned))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"version": CACHE_VERSION, "masters": manifest.entries}, indent=2),
        encoding="utf-8",
    )
    return placed


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
    manifest = plan(site, site_root, dist, spec, collector, cache_dir, strict, config)
    finish(manifest, site_root, dist, spec, None, cache_dir, workers, progress)
    return manifest
