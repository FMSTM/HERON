"""Адреса: единственное место, где к пути приклеивается домен."""

from __future__ import annotations

import unicodedata
from urllib.parse import quote, unquote_to_bytes

from heron.contracts.site import SiteConfig


def absolute(config: SiteConfig, url: str) -> str:
    return f"https://{config.site.domain}{url}"


def home_url(config: SiteConfig, lang: str) -> str:
    return "/" if lang == config.site.default_lang else f"/{lang}/"


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
