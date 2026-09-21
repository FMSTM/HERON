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
from heron.core.errors import Collector
from heron.core.models import Site

# Путь к картинке в произвольном поле фронтматтера: тема вправе объявить
# своё поле (вторая фотография, обложка), и такой файл тоже надо нарезать.
IMAGE_FIELD = re.compile(r"^\.?/?img/[^\s]+\.(?:png|jpe?g|webp|avif|gif|svg)$", re.I)

REFERENCE = re.compile(r"""(?:\(|["'\s])((?:\./)?img/[^)"'\s]+\.[a-zA-Z0-9]+)""")
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


def declared_by(site: Site) -> dict[str, list[str]]:
    """Кто ссылается на картинку: путь → страницы, где он объявлен.

    Нужно для внятного предупреждения: «нет на диске» без имени страницы
    заставляет искать объявление руками по всему контенту.
    """
    where: dict[str, list[str]] = {}
    for page in site.pages:
        for src in _page_images(page):
            where.setdefault(src, []).append(page.source)
    return where


def _page_images(page) -> set[str]:
    """Картинки одной страницы: поля фронтматтера и пути из текста."""
    found: set[str] = set()
    for value in (page.meta.image, page.meta.og_image):
        if value:
            found.add(value.lstrip("./"))
    for _name, value in (page.meta.model_extra or {}).items():
        if isinstance(value, str) and IMAGE_FIELD.match(value):
            found.add(value.lstrip("./"))
        elif isinstance(value, list):
            found.update(
                item.lstrip("./")
                for item in value
                if isinstance(item, str) and IMAGE_FIELD.match(item)
            )
    chunks = [page.intro.raw if page.intro else "", *(s.raw for s in page.sections.values())]
    for chunk in chunks:
        found.update(match.group(1).lstrip("./") for match in REFERENCE.finditer(chunk))
    return found


def references(site: Site) -> set[str]:
    """Все картинки, на которые ссылается контент."""
    found: set[str] = set()
    for page in site.pages:
        found.update(_page_images(page))
    return found


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


def build(
    site: Site,
    site_root: Path,
    dist: Path,
    spec: ImagesSpec,
    collector: Collector,
    cache_dir: Path | None = None,
    strict: bool = False,
    progress=None,
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

    sources = sorted(references(site))
    declared = declared_by(site)
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

        if source.suffix.lower() not in KEEP:
            (dist / src).parent.mkdir(parents=True, exist_ok=True)
            (dist / src).write_bytes(source.read_bytes())
            continue

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
