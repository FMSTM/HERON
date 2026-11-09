"""Адреса: единственное место, где к пути приклеивается домен."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote, unquote_to_bytes

from heron.contracts.site import SiteConfig


def absolute(config: SiteConfig, url: str) -> str:
    return f"https://{config.site.domain}{url}"


def slash(config: SiteConfig) -> bool:
    """Адреса страниц со слешем на конце (`urls.trailing_slash`, 20 §2)."""
    return config.urls.slash


def page_url(lang: str, default_lang: str, parts: list[str], slash: bool = True) -> str:
    """Адрес страницы из сегментов: со слешем или без, по режиму сайта.

    Корень сайта - `/` в обоих режимах: адреса короче не бывает.
    """
    prefix = [] if lang == default_lang else [lang]
    path = "/".join([*prefix, *parts])
    if not path:
        return "/"
    return f"/{path}/" if slash else f"/{path}"


def shape(path: str, slash: bool) -> str:
    """Путь страницы в форме режима сайта: `/x/` или `/x`; `/` - как есть."""
    stem = path.rstrip("/")
    if not stem:
        return "/"
    return stem + "/" if slash else stem


def twin(path: str) -> str:
    """Тот же путь в другой форме: `/x/` - `/x`, `/x` - `/x/`; `/` - `/`."""
    if path == "/" or not path:
        return "/"
    return path[:-1] if path.endswith("/") else path + "/"


def home_url(config: SiteConfig, lang: str) -> str:
    return page_url(lang, config.site.default_lang, [], slash(config))


def _file_like(path: str) -> bool:
    """Последний сегмент с точкой — файл (`/index.php`, `/page.html`): слеш ему не нужен."""
    return "." in path.rstrip("/").rsplit("/", 1)[-1]


def canonical_path(path: str, slash: bool = True) -> tuple[str, bool]:
    """Старый адрес в той форме, в какой его сравнивает nginx.

    nginx сверяет карты по `$uri` — пути, из которого уже убраны `%XX`.
    Поэтому `/новини/` и `/%D0%BD%D0%BE%D0%B2%D0%B8%D0%BD%D0%B8/` для него
    один адрес, и в карте он должен стоять один раз, в декодированном виде.

    Правила:

    - percent-encoding раскрывается, регистр шестнадцатеричных цифр не важен;
    - текст приводится к Unicode NFC: так кодируют адреса браузеры, а
      редактор мог сохранить «й» двумя символами;
    - регистр букв сохраняется: `/About/` и `/about/` — разные адреса;
    - завершающий слеш добавляется, если последний сегмент не похож на файл.
      Сервер отвечает и на вариант без слеша — его добавляет генератор
      конфига, сравнения же идут по форме со слешем. Для префиксов
      (`slash=False`) слеш не трогается: `/wp-*` — это не `/wp-/*`.

    Возвращает форму и признак «это корректный UTF-8». Слаг, обрезанный
    старой системой посреди буквы, после декодирования не является текстом;
    тогда остаётся percent-форма с заглавными цифрами, и сверять её
    приходится с сырым адресом запроса, а не с `$uri`.
    """
    raw = unquote_to_bytes(path)
    try:
        text = unicodedata.normalize("NFC", raw.decode("utf-8"))
        ok = True
    except UnicodeDecodeError:
        text = quote(raw, safe="/-._~!$&'()*+,;=:@")
        ok = False
    if slash and not text.endswith("/") and not _file_like(text):
        text += "/"
    return text, ok


# Адрес со своей схемой (`https:`, `mailto:`, `tel:`, `data:`) или без схемы,
# но с хостом (`//cdn…`): от адреса страницы он не зависит.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:|^//")


def relative(value: str) -> bool:
    """Ссылка, которую браузер разрешает от папки страницы: `pic.jpg`, `./x/`, `../y`.

    На адресе без слеша (`/ru/cases/x`) папка страницы - `/ru/cases/`, и
    `pic.jpg` ведёт на `/ru/cases/pic.jpg`, а не на файл рядом со страницей
    (20 §2, `urls.trailing_slash: never`). Не относительны: путь от корня
    (`/…`), адрес со схемой или хостом, `#якорь`, `?параметры`, пустая строка.
    """
    text = value.strip()
    if not text or text.startswith(("/", "#", "?")):
        return False
    return not _SCHEME.match(text)


# Атрибуты HTML с адресом: в них относительная ссылка уходит от папки страницы.
URL_ATTRS = ("href", "src", "srcset", "poster", "action", "data", "formaction")
_ATTR = re.compile(
    r"""(?<![\w:-])(href|src|srcset|poster|action|data|formaction)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
    re.I,
)


# Содержимое `<script>`: код, а не разметка. Адреса в нём не ищутся (как и
# версии файлов не подставляются, 21 §4): строка в комментарии или в коде
# - не ссылка страницы.
_SCRIPT_BODY = re.compile(r"(<script\b[^>]*>)(.*?)(</script\s*>|\Z)", re.I | re.S)
_STYLE_ATTR = re.compile(r"""(?<![\w:-])style\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_STYLE_BODY = re.compile(r"<style\b[^>]*>(.*?)(?:</style\s*>|\Z)", re.I | re.S)
# url() в стилях: в кавычках, в сущностях (атрибут style) или без них; @import "…".
_CSS_URL = re.compile(
    r"""url\(\s*(?:"([^"]*)"|'([^']*)'|&quot;(.*?)&quot;|&\#39;(.*?)&\#39;|([^"'()\s]+))\s*\)""",
    re.I | re.S,
)
_CSS_IMPORT = re.compile(r"""@import\s+(["'])([^"'\n]+)\1""", re.I)


def _blank(match: re.Match[str]) -> str:
    """Тело скрипта - пробелами той же длины: смещения и строки не сдвигаются."""
    body = "".join(char if char == "\n" else " " for char in match.group(2))
    return match.group(1) + body + match.group(3)


def css_urls(css: str, offset: int = 0) -> list[tuple[int, str]]:
    """Адреса `url(…)` и `@import "…"` в стилях: (смещение, значение)."""
    out: list[tuple[int, str]] = []
    for match in _CSS_URL.finditer(css):
        value = next(g for g in match.groups() if g is not None)
        out.append((offset + match.start(), value))
    for match in _CSS_IMPORT.finditer(css):
        out.append((offset + match.start(), match.group(2)))
    return out


def attr_urls(html: str) -> list[tuple[int, str]]:
    """Адреса из HTML: (смещение в тексте, значение).

    Атрибуты с адресом (srcset - по кандидатам), `url()` в атрибуте `style`
    и в `<style>`. Содержимое `<script>` пропускается: это код.
    """
    html = _SCRIPT_BODY.sub(_blank, html)
    out: list[tuple[int, str]] = []
    for match in _ATTR.finditer(html):
        group = next(g for g in (2, 3, 4) if match.group(g) is not None)
        value = match.group(group)
        if match.group(1).lower() == "srcset":
            for candidate in value.split(","):
                parts = candidate.strip().split()
                if parts:
                    out.append((match.start(), parts[0]))
        else:
            out.append((match.start(), value))
    for match in _STYLE_ATTR.finditer(html):
        group = 1 if match.group(1) is not None else 2
        out += css_urls(match.group(group), match.start(group))
    for match in _STYLE_BODY.finditer(html):
        out += css_urls(match.group(1), match.start(1))
    return sorted(out)
