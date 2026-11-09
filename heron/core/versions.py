"""Версии файлов темы и ресурсов по хешу содержимого.

Файлы `/assets/` и `/media/` браузер держит сутки, а имена у них не меняются.
После обновления темы посетитель, заходивший вчера, получал новую страницу со
старым `site.css` - вёрстка разъезжалась на сутки. Поэтому ссылка на файл
несёт его версию - первые 10 знаков hex от sha256 итоговых байтов:

    /assets/site.css   ->  /assets/site.0123456789.css   (копия с хешем в имени)
    /media/photo.jpg   ->  /media/photo.jpg?v=0123456789  (метка в параметре)

Другие байты - другой адрес, поэтому nginx отдаёт версию на год с
`immutable` (22 §5), а адрес без версии - на срок `nginx.cache.assets` или
`nginx.cache.media`.

Почему по-разному. Файлы темы маленькие, а устаревший стиль ломает вёрстку:
им - копия с хешем в имени, она работает на любом кэше и CDN. Ресурсы
тяжёлые (фото, нарезки, видео), копия удвоила бы сборку и образ: Docker
COPY жёстких ссылок не сохраняет. Ресурсу - метка `?v=` на прежнем имени:
сборка не растёт, адрес открывается на любом хостинге (сервер параметр просто
не читает). Цена: часть CDN и прокси кэширует без учёта параметров, но
ресурс на месте меняют редко (обычно кладут новый файл).

Порядок в сборке:

1. до рендера - хеши файлов темы (`plan`): шаблону `asset('site.css')` нужно
   готовое имя. Стили переписываются раньше, чем считается их хеш: `url()` и
   `@import` ведут на версии, поэтому новый шрифт меняет и имя стилей;
2. после нарезки - копии с хешем файлов `assets/`, хеши файлов `media/`
   (`finish`) и ссылки в HTML (`rewrite_html`): `src`, `srcset`, `<link>`,
   `poster`, `style` и `<style>`. Тема с ручными `/assets/...` и `/media/...`
   получает версии без правки.

Не трогаются:

- ссылки `<a href>`, `<area href>`: их открывает и пересылает человек, файл
  (памятка, скан) должен жить по одному адресу и скачиваться под своим именем;
- og:image, twitter:image и разметка JSON-LD (`<script>`): кэши соцсетей и
  поисковиков ключуются адресом, стабильный адрес им полезнее свежего;
- `<script>` целиком и файлы `.js`: адрес в коде движок не находит надёжно
  (`heron check` предупреждает о строке `/assets/` в скрипте темы);
- в `assets/` - файлы без расширения, скрытые, тяжелее `HEAVY` и файлы, имя
  которых уже выглядит как имя с хешем (`x.0123456789.css` от сборщика темы):
  у такого nginx и так держит год, вторая копия не нужна. В `media/` имя
  ничего не значит: метку получает любой файл, даже `banner.1699999999.jpg`;
- параметр `v` в ссылке на `/media/`, написанный руками (`?v=2`), заменяется
  хешем: версия одна, и её знает сборка.

Спецификация: docs/spec/21-engine.md, «Версии файлов темы и ресурсов».
"""

from __future__ import annotations

import hashlib
import html
import posixpath
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from heron.core import notes, paths
from heron.core.errors import Collector, HeronError
from heron.messages import Msg

LENGTH = 10
ASSETS = "assets/"
MEDIA = "media/"
PREFIXES = (ASSETS, MEDIA)
CODE = "E045"
# Имя с хешем: `<имя>.<10 hex>.<расширение>`. Та же регулярка в конфиге nginx
# (только /assets/).
HASHED = re.compile(r"\.[0-9a-f]{10}\.[A-Za-z0-9]+\Z")
SUFFIX = re.compile(r"\.[A-Za-z0-9]+\Z")
# Метка ресурса: `?v=<10 hex>`. Та же регулярка в конфиге nginx (`map $arg_v`).
STAMP = re.compile(r"\A[0-9a-f]{10}\Z")
# Тяжёлый файл темы не удваивается в сборке: копия ничего не даёт, кроме
# веса образа. Порог тот же, что у предупреждения о весе ресурса.
HEAVY = 10 * 1024 * 1024


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:LENGTH]


def digest_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            sha.update(chunk)
    return sha.hexdigest()[:LENGTH]


def hashed_name(rel: str, digest: str) -> str:
    """`assets/site.css` -> `assets/site.<digest>.css`."""
    stem, ext = posixpath.splitext(rel)
    return f"{stem}.{digest}{ext}"


def versioned(rel: str, size: int | None = None) -> bool:
    """Получает ли файл темы (`assets/`) копию с хешем в имени."""
    if not rel.startswith(ASSETS):
        return False
    name = rel.rsplit("/", 1)[-1]
    if name.startswith(".") or notes.skip(name) or not SUFFIX.search(name):
        return False
    if HASHED.search(name):
        return False
    return size is None or size <= HEAVY


def stamped(rel: str) -> bool:
    """Получает ли ссылка на ресурс (`media/`) метку `?v=`: любой видимый файл."""
    if not rel.startswith(MEDIA):
        return False
    name = rel.rsplit("/", 1)[-1]
    return bool(name) and not name.startswith(".") and not notes.skip(name)


def known(rel: str, size: int | None = None) -> bool:
    """Есть ли у файла сборки версия: копия с хешем или метка."""
    return versioned(rel, size) or stamped(rel)


def looks_hashed(rel: str) -> bool:
    return bool(HASHED.search(rel.rsplit("/", 1)[-1]))


# --- ссылки в CSS ------------------------------------------------------------------

# url(...) в кавычках или без; в атрибуте style кавычки бывают сущностями.
CSS_URL = re.compile(
    r"""url\(\s*(?:(?P<q>"|'|&quot;|&\#34;|&\#39;|&\#x27;)(?P<qu>.*?)(?P=q)|(?P<u>[^"'()\s]+))\s*\)""",
    re.I | re.S,
)
CSS_IMPORT = re.compile(r"""@import\s+(?P<q>["'])(?P<u>[^"'\n]+)(?P=q)""", re.I)


def css_refs(text: str) -> list[tuple[int, int, str]]:
    """Ссылки CSS: (начало, конец, адрес как записан) - для url() и @import."""
    found: list[tuple[int, int, str]] = []
    for match in CSS_URL.finditer(text):
        group = "qu" if match.group("q") is not None else "u"
        found.append((match.start(group), match.end(group), match.group(group)))
    for match in CSS_IMPORT.finditer(text):
        found.append((match.start("u"), match.end("u"), match.group("u")))
    return sorted(found)


def _replace(text: str, edits: list[tuple[int, int, str]]) -> str:
    out: list[str] = []
    last = 0
    for start, end, new in sorted(edits):
        if start < last:
            continue
        out.append(text[last:start])
        out.append(new)
        last = end
    out.append(text[last:])
    return "".join(out)


@dataclass(slots=True)
class Ref:
    """Адрес, разобранный для подмены: что искать и как записать обратно."""

    rel: str  # путь файла в сборке: assets/site.css
    head: str  # всё до пути: пробелы, https://домен
    path: str  # путь как записан, без ? и #
    tail: str  # ?… #… и пробелы после


def parse_ref(
    raw: str, origins: tuple[str, ...] = (), base: str | None = None, escaped: bool = False
) -> Ref | None:
    """Разобрать адрес. Свой - от корня или с доменом сайта; `base` - папка
    файла стилей, тогда годится и относительный. `escaped` - адрес из HTML,
    в нём сущности (`&amp;`)."""
    text = raw.strip()
    if not text:
        return None
    lead = raw[: len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()) :]
    origin = next((o for o in origins if text.startswith(o + "/")), "")
    rest = text[len(origin) :]
    if rest.startswith("//"):
        return None
    cut = len(rest)
    for mark in ("?", "#"):
        spot = rest.find(mark)
        if spot != -1:
            cut = min(cut, spot)
    path, tail = rest[:cut], rest[cut:]
    plain = urllib.parse.unquote(html.unescape(path) if escaped else path)
    if plain.startswith("/"):
        rel = posixpath.normpath(plain).lstrip("/")
    elif base is not None and not origin:
        if not plain or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", plain):
            return None
        rel = posixpath.normpath(posixpath.join(base, plain))
    else:
        return None
    if rel.startswith("../") or rel == "..":
        return None
    return Ref(rel=rel, head=lead + origin, path=path, tail=tail + trail)


def swap(ref: Ref, digest: str) -> str | None:
    """Адрес с хешем перед расширением; путь записан не так, как имя файла, - None."""
    ext = posixpath.splitext(ref.rel)[1]
    if not ext or not ref.path.endswith(ext):
        return None
    return f"{ref.head}{ref.path[: -len(ext)]}.{digest}{ext}{ref.tail}"


# Параметр `v` в строке запроса: после `?` или `&` (в HTML - `&amp;`).
_V_PARAM = re.compile(r"(?:(?<=\?)|(?<=&)|(?<=&amp;))v=[^&#]*")


def stamp(tail: str, digest: str, escaped: bool = False) -> str:
    """`?…#…` с меткой `v=<хеш>`: параметры и якорь остаются.

    Нет параметров - `?v=…`; есть - `&v=…` в конец (в HTML - `&amp;v=…`);
    уже есть `v` - его значение заменяется: повторный проход даёт то же самое.
    """
    body = tail.rstrip()
    space = tail[len(body) :]
    cut = body.find("#")
    query, fragment = (body, "") if cut == -1 else (body[:cut], body[cut:])
    mark = f"v={digest}"
    if not query or query == "?":
        query = f"?{mark}"
    elif _V_PARAM.search(query):
        query = _V_PARAM.sub(mark, query, count=1)
    else:
        query = f"{query}{'&amp;' if escaped else '&'}{mark}"
    return f"{query}{fragment}{space}"


def version(ref: Ref, digest: str, escaped: bool = False) -> str | None:
    """Адрес с версией: ресурс - метка `?v=`, файл темы - хеш в имени."""
    if ref.rel.startswith(MEDIA):
        return f"{ref.head}{ref.path}{stamp(ref.tail, digest, escaped)}"
    return swap(ref, digest)


def rewrite_css(
    text: str,
    lookup: Callable[[str], str | None],
    origins: tuple[str, ...] = (),
    base: str | None = None,
    escaped: bool = False,
) -> str:
    """Ссылки url() и @import - на версии. `lookup(rel)` - хеш или None."""
    edits: list[tuple[int, int, str]] = []
    for start, end, raw in css_refs(text):
        ref = parse_ref(raw, origins, base, escaped)
        if ref is None:
            continue
        digest = lookup(ref.rel)
        new = version(ref, digest, escaped) if digest else None
        if new is not None:
            edits.append((start, end, new))
    return _replace(text, edits) if edits else text


# --- до рендера: файлы темы -------------------------------------------------------


@dataclass(slots=True)
class Versions:
    """Хеши файлов сборки: тема - до рендера, всё прочее - после нарезки.

    `media` - как узнать хеш файла `media/…` до рендера: исходник в папке
    сайта (кладётся в сборку байт в байт) или нарезка, закодированная
    сейчас (`media.ensure`). None - asset() для `media/` отвечает адресом без
    метки (проверка темы, демо: ресурсов сайта там нет).
    """

    digests: dict[str, str] = field(default_factory=dict)  # rel -> хеш (известные заранее)
    texts: dict[str, str] = field(default_factory=dict)  # переписанные стили темы
    theme: set[str] = field(default_factory=set)  # все файлы assets/ темы
    issued: set[str] = field(default_factory=set)  # media/, выданные asset()
    cycles: list[str] = field(default_factory=list)
    media: Callable[[str], Path | None] | None = None

    def media_digest(self, rel: str) -> str | None:
        if rel in self.digests:
            return self.digests[rel]
        if self.media is None:
            return None
        found = self.media(rel)
        if found is None or not found.is_file() or not stamped(rel):
            return None
        digest = digest_file(found)
        self.digests[rel] = digest
        return digest

    def asset(self, path: str) -> str:
        """Адрес файла темы или ресурса с версией - для шаблона.

        `asset('site.css')`, `asset('css/print.css')` - файлы `assets/` темы,
        хеш в имени; `asset('media/logo.svg')` - ресурс сайта, метка
        `?v=<хеш>`. Нет такого файла - E045.
        """
        if not isinstance(path, str) or not path.strip():
            raise HeronError(code=CODE, message=Msg("asset_unknown", path=repr(path)))
        text = path.strip()
        cut = min([i for i in (text.find("?"), text.find("#")) if i != -1] or [len(text)])
        name, tail = text[:cut], text[cut:]
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:|^//", name):
            raise HeronError(
                code=CODE,
                message=Msg("asset_external", path=path),
                hint=Msg("asset_unknown_hint"),
            )
        clean = posixpath.normpath(name.lstrip("/")) if name.strip("/") else ""
        if not clean or clean.startswith("..") or paths.escapes(clean):
            raise HeronError(
                code=CODE, message=Msg("asset_unknown", path=path), hint=Msg("asset_unknown_hint")
            )
        rel = clean if clean.startswith(PREFIXES) else f"assets/{clean}"
        if rel.startswith("assets/"):
            if rel not in self.theme:
                raise HeronError(
                    code=CODE,
                    message=Msg("asset_unknown", path=path),
                    hint=Msg("asset_unknown_hint"),
                )
            digest = self.digests.get(rel)
        else:
            if self.media is None:
                return f"/{rel}{tail}"
            found = self.media(rel)
            if found is None or not found.is_file():
                raise HeronError(
                    code=CODE,
                    message=Msg("asset_unknown", path=path),
                    hint=Msg("asset_unknown_hint"),
                )
            self.issued.add(rel)
            digest = self.media_digest(rel)
            return f"/{rel}{stamp(tail, digest) if digest else tail}"
        return f"/{hashed_name(rel, digest) if digest else rel}{tail}"


def plan(
    theme_assets: Path,
    media: Callable[[str], Path | None] | None = None,
    collector: Collector | None = None,
) -> Versions:
    """Хеши файлов `assets/` темы до рендера; стили - с переписанными ссылками.

    Стили зависят друг от друга (`@import`) и от шрифтов и картинок: хеш
    файла считается после хешей всего, на что он ссылается. Круг импортов
    (`a.css` -> `b.css` -> `a.css`) разрывается на ссылке, замыкающей круг:
    она остаётся без хеша, об этом предупреждение.
    """
    versions = Versions(media=media)
    files: dict[str, Path] = {}
    if theme_assets.is_dir():
        for rel, path in paths.files(theme_assets, where=str(theme_assets)):
            if any(notes.skip(part) for part in rel.split("/")):
                continue
            files[f"assets/{rel}"] = path
    versions.theme = set(files)
    sources: dict[str, str] = {}
    for rel, path in files.items():
        if rel.lower().endswith(".css"):
            try:
                sources[rel] = path.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue

    done: dict[str, str | None] = {}
    active: list[str] = []

    def digest_of(rel: str) -> str | None:
        if rel in done:
            return done[rel]
        if rel.startswith("media/"):
            return versions.media_digest(rel)
        if rel not in files:
            return None
        if rel in active:
            # круг импортов: ссылка, которая его замыкает, остаётся без хеша
            loop = " -> ".join([*active[active.index(rel) :], rel])
            if loop not in versions.cycles:
                versions.cycles.append(loop)
            return None
        active.append(rel)
        try:
            if rel in sources:
                base = posixpath.dirname(rel)
                text = rewrite_css(sources[rel], digest_of, base=base)
                if text != sources[rel]:
                    versions.texts[rel] = text
                data = text.encode("utf-8")
                size = len(data)
                digest = digest_bytes(data)
            else:
                size = files[rel].stat().st_size
                digest = digest_file(files[rel])
        finally:
            active.pop()
        result = digest if versioned(rel, size) else None
        done[rel] = result
        if result is not None:
            versions.digests[rel] = result
        return result

    for rel in sorted(files):
        digest_of(rel)
    if collector is not None:
        for loop in versions.cycles:
            collector.warn(Msg("asset_css_cycle", loop=loop), path=loop.split(" -> ")[0])
    return versions


# Вызов `asset('media/…')` со строкой в шаблоне: для отчёта о ненужных ресурсах.
_ASSET_MEDIA = re.compile(r"""\basset\(\s*(["'])/?(media/[^"'?#]+)[^"']*\1\s*\)""")


def template_media(theme_dir: Path) -> set[str]:
    """Ресурсы, которые тема называет через `asset('media/…')` строкой в шаблоне.

    Такой файл нужен сайту, хотя ни одна страница его не объявляет: `heron
    check` и отчёт сборки не должны звать его ненужным. Имя, собранное
    шаблоном из переменных, видно только при рендере (`Versions.issued`).
    """
    found: set[str] = set()
    theme_dir = Path(theme_dir)
    if not theme_dir.is_dir():
        return found
    for path in sorted(theme_dir.rglob("*.html")):
        if not paths.inside(theme_dir, path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _ASSET_MEDIA.finditer(text):
            rel = posixpath.normpath(urllib.parse.unquote(match.group(2)))
            if rel.startswith(MEDIA):
                found.add(rel)
    return found


# --- после нарезки: копии с хешем, метки и ссылки в HTML --------------------------


def finish(outputs, versions: Versions, origins: tuple[str, ...], collector: Collector) -> None:
    """Копии с хешем для `assets/`, хеши для меток `media/`, затем ссылки в HTML.

    Хеш считается по тому, что ляжет в сборку. Версия, выданная шаблону до
    рендера (`asset()`, стили), обязана совпасть с ним - иначе страница
    ссылалась бы на файл, которого нет, или на чужую версию: E045.
    """
    from heron.core import output

    table: dict[str, str] = {}
    for rel in sorted(outputs.entries):
        if not rel.startswith(PREFIXES):
            continue
        entry = outputs.entries[rel]
        if rel in versions.texts and entry.kind == "asset" and entry.text is None:
            entry.text = versions.texts[rel]
            entry.source = None
            entry.link = False
        if rel.startswith(ASSETS) and HASHED.search(rel.rsplit("/", 1)[-1]):
            if entry.kind != "versioned":
                collector.warn(Msg("asset_hash_like_name", rel=rel), path=entry.owner)
            continue
        if entry.text is not None:
            data = entry.text.encode("utf-8")
            size, digest = len(data), None
            if known(rel, size):
                digest = digest_bytes(data)
        elif entry.source is not None:
            try:
                size = entry.source.stat().st_size
            except OSError:
                continue
            digest = digest_file(entry.source) if known(rel, size) else None
        else:
            continue
        if digest is None:
            continue
        promised = versions.digests.get(rel)
        if promised is not None and promised != digest:
            collector.error(
                CODE,
                Msg("asset_changed", rel=rel),
                path=entry.owner,
                hint=Msg("asset_changed_hint"),
            )
            continue
        table[rel] = digest

    # Копия с хешем - только у файлов темы: ресурс получает метку `?v=` и
    # лежит в сборке один раз.
    for rel, digest in sorted(table.items()):
        if not rel.startswith(ASSETS):
            continue
        entry = outputs.entries[rel]
        twin = hashed_name(rel, digest)
        held = outputs.entries.get(twin)
        if held is not None and held.kind == "versioned":
            continue
        copy = output.Entry(
            owner=Msg("build_owner_versioned", owner=entry.owner),
            kind="versioned",
            text=entry.text,
            source=entry.source,
            link=entry.link,
        )
        outputs.add(twin, copy, collector)

    def lookup(rel: str) -> str | None:
        return table.get(rel)

    for rel, entry in outputs.entries.items():
        if entry.text is None or entry.kind in ("static", "versioned", "asset", "media"):
            continue
        if not rel.endswith((".html", ".htm")):
            continue
        entry.text = rewrite_html(entry.text, lookup, origins)


# --- HTML ------------------------------------------------------------------------

_TAG = re.compile(r"<([A-Za-z][A-Za-z0-9:-]*)")
_ATTR = re.compile(r"""([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""")
URL_ATTRS = {"href", "src", "poster", "data", "data-src", "xlink:href"}
SRCSET_ATTRS = {"srcset", "imagesrcset", "data-srcset"}
# Ссылки, которые открывает и пересылает человек: адрес должен жить дольше версии.
PEOPLE_LINKS = {"a", "area", "base"}
RAW_TEXT = {"script", "style", "textarea", "title"}
SOCIAL = re.compile(r"^(og:|twitter:)", re.I)


def _srcset(value: str, change: Callable[[str], str | None]) -> str:
    """Каждый кандидат srcset: адрес до пробела, затем описатель до запятой."""
    out: list[str] = []
    index = 0
    size = len(value)
    while index < size:
        start = index
        while index < size and (value[index].isspace() or value[index] == ","):
            index += 1
        out.append(value[start:index])
        if index >= size:
            break
        begin = index
        while index < size and not value[index].isspace():
            index += 1
        url = value[begin:index]
        trailing = ""
        while url.endswith(","):
            url, trailing = url[:-1], "," + trailing
        out.append(change(url) or url)
        out.append(trailing)
        if trailing:
            continue
        begin = index
        while index < size and value[index] != ",":
            index += 1
        out.append(value[begin:index])
    return "".join(out)


def rewrite_html(text: str, lookup: Callable[[str], str | None], origins=()) -> str:
    """Свои ссылки на `/assets/` и `/media/` - на версии: имя с хешем или `?v=`.

    Разбор по тегам и атрибутам, а не регуляркой по всему документу: текст
    страницы, комментарии и `<script>` не трогаются, а `<style>` и атрибут
    `style` переписываются по правилам CSS.
    """

    def change(raw: str) -> str | None:
        ref = parse_ref(raw, origins, escaped=True)
        if ref is None or not ref.rel.startswith(PREFIXES):
            return None
        digest = lookup(ref.rel)
        return version(ref, digest, escaped=True) if digest else None

    def css(raw: str, escaped: bool) -> str:
        return rewrite_css(raw, lookup, origins, escaped=escaped)

    edits: list[tuple[int, int, str]] = []
    index = 0
    size = len(text)
    while True:
        start = text.find("<", index)
        if start < 0:
            break
        if text.startswith("<!--", start):
            end = text.find("-->", start + 4)
            index = size if end < 0 else end + 3
            continue
        if text.startswith(("<!", "<?", "</"), start):
            end = text.find(">", start)
            index = size if end < 0 else end + 1
            continue
        tag = _TAG.match(text, start)
        if tag is None:
            index = start + 1
            continue
        name = tag.group(1).lower()
        pos = tag.end()
        attrs: list[tuple[str, int, int, str]] = []
        closed = False
        while pos < size:
            char = text[pos]
            if char.isspace():
                pos += 1
                continue
            if char == ">":
                pos += 1
                break
            if text.startswith("/>", pos):
                closed = True
                pos += 2
                break
            if char == "/":
                pos += 1
                continue
            attr = _ATTR.match(text, pos)
            if attr is None:
                pos += 1
                continue
            for group in (2, 3, 4):
                if attr.group(group) is not None:
                    attrs.append(
                        (
                            attr.group(1).lower(),
                            attr.start(group),
                            attr.end(group),
                            attr.group(group),
                        )
                    )
                    break
            pos = attr.end()
        names = {item[0]: item[3] for item in attrs}
        for attr_name, begin, end, value in attrs:
            new: str | None = None
            if attr_name in URL_ATTRS:
                if attr_name == "href" and name in PEOPLE_LINKS:
                    continue
                new = change(value)
            elif attr_name in SRCSET_ATTRS:
                new = _srcset(value, change)
            elif attr_name == "style":
                new = css(value, escaped=True)
            elif attr_name == "content" and name == "meta":
                kind = names.get("property") or names.get("name") or ""
                if SOCIAL.match(kind) or "itemprop" in names:
                    continue
                new = change(value)
            if new is not None and new != value:
                edits.append((begin, end, new))
        index = pos
        if name in RAW_TEXT and not closed:
            close = re.compile(rf"</{name}[\s/>]", re.I).search(text, pos)
            body_end = close.start() if close else size
            if name == "style":
                body = text[pos:body_end]
                new_body = css(body, escaped=False)
                if new_body != body:
                    edits.append((pos, body_end, new_body))
            index = body_end
    return _replace(text, edits) if edits else text
