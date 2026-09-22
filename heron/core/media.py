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
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from heron.contracts.theme import ImagesSpec
from heron.core import notes
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

# Порог веса. Тяжёлый файл — не ошибка: бывает и репортаж на двадцать минут.
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

REFERENCE = re.compile(rf"""(?:\(|["'\s])((?:\./)?(?:{_IN})/[^)"'\s]+\.[a-zA-Z0-9]+)""")
CACHE = "media.json"
KEEP = {".jpg", ".jpeg", ".png", ".webp"}


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
    """Что движок нарезал: адрес исходника -> пропорция -> вариант."""

    items: dict[str, dict[str, Rendition]] = field(default_factory=dict)

    def get(self, src: str, ratio: str) -> Rendition | None:
        return self.items.get(src.lstrip("./"), {}).get(ratio)


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
            found.add(value.lstrip("./"))
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
            found.add(value.lstrip("./"))
    walk(page.meta.model_extra or {}, found)
    chunks = [page.intro.raw if page.intro else "", *(s.raw for s in page.sections.values())]
    for chunk in chunks:
        found.update(match.group(1).lstrip("./") for match in REFERENCE.finditer(chunk))
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
        if not (site_root / src).is_file():
            collector.error(
                "E007",
                f"нет файла {src}",
                path=_owner(declared, src),
                hint="поправьте путь во фронтматтере или положите картинку",
            )


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
) -> Manifest:
    """Нарезать все картинки, на которые ссылается контент.

    Отсутствующая картинка в проде дороже упавшей сборки — поэтому
    в `--strict`, которым собирают CI и прод, это ошибка. Но страницу
    пишут раньше, чем рисуют иллюстрацию, и блокировать работу над текстом
    очередью художника незачем: при обычной сборке это предупреждение.
    """
    manifest = Manifest()
    cache_path = (cache_dir or site_root / ".heron-cache") / CACHE
    known: dict[str, str] = {}
    if cache_path.is_file():
        try:
            known = json.loads(cache_path.read_text(encoding="utf-8"))
        except ValueError:
            known = {}
    fresh: dict[str, str] = {}

    sources = sorted(references(site, config))
    declared = declared_by(site, config)
    for index, src in enumerate(sources, 1):
        if progress is not None:
            progress.tick(index, len(sources), src)
        source = site_root / src
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
            (dist / src).parent.mkdir(parents=True, exist_ok=True)
            (dist / src).write_bytes(source.read_bytes())
            continue

        # Мастер кладём как есть рядом с вариантами. Ссылка «открыть скан»,
        # адрес для скачивания, картинка в разметке для соцсетей — всё это
        # просит адрес файла, а не набор нарезок. Без копии такого адреса
        # в сборке просто нет, и его приходится дублировать через static/.
        (dist / src).parent.mkdir(parents=True, exist_ok=True)
        (dist / src).write_bytes(source.read_bytes())

        digest = _digest(source, spec)
        fresh[src] = digest
        unchanged = known.get(src) == digest

        with Image.open(source) as opened:
            image = _opaque(opened.convert("RGBA" if opened.mode in ("RGBA", "LA", "P") else "RGB"))

            stem = Path(src)
            # Иллюстрацию вписываем, фотографию кропаем. Признак —
            # прозрачность: у фотографии её нет и поля взять неоткуда.
            fits = _has_alpha(image) and not any(src.startswith(rule) for rule in spec.crop)
            for ratio in spec.ratios:
                cropped = (_fit if fits else _crop)(image, _ratio_of(ratio))
                widths = [w for w in spec.widths if w <= cropped.width] or [cropped.width]
                rendition = Rendition(
                    ratio=ratio,
                    width=widths[-1],
                    height=round(widths[-1] * cropped.height / cropped.width),
                )

                for fmt in [*spec.formats, stem.suffix.lstrip(".").lower()]:
                    variants: list[tuple[int, str]] = []
                    for width in widths:
                        name = f"{stem.stem}-{_label(ratio)}-{width}.{fmt}"
                        out = dist / stem.parent / name
                        rel = f"{stem.parent.as_posix()}/{name}"
                        variants.append((width, rel))
                        if unchanged and out.is_file():
                            continue
                        out.parent.mkdir(parents=True, exist_ok=True)
                        height = round(width * cropped.height / cropped.width)
                        resized = cropped.resize((width, height), Image.LANCZOS)
                        if fmt in ("jpg", "jpeg") and resized.mode == "RGBA":
                            resized = resized.convert("RGB")
                        options: dict[str, object] = {}
                        if fmt in ("webp", "avif", "jpg", "jpeg"):
                            options["quality"] = 82
                        if fmt == "webp":
                            # method=6 — самый медленный режим кодировщика. На
                            # пилоте он давал 7 секунд на вариант вместо 0.1 при
                            # выигрыше в размере около двух процентов: сборка
                            # сайта на полсотни картинок уезжала в часы. Четыре —
                            # умолчание кодировщика и разумный размен.
                            options["method"] = 4
                        resized.save(out, **options)
                    if fmt in spec.formats:
                        rendition.sources[fmt] = variants
                    else:
                        rendition.fallback = variants[-1][1]
                        rendition.sources.setdefault("origin", variants)

                manifest.items.setdefault(src, {})[ratio] = rendition

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(fresh, indent=2), encoding="utf-8")
    return manifest
