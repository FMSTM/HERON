"""Конфиг nginx для готовой статики.

Статика сама по себе не умеет отвечать 404: сервер по умолчанию отдаёт свою
страницу, и нарисованную темой не видит никто. Поэтому конфиг собирается
вместе с сайтом — тогда он знает языки этого сайта и не расходится с тем,
что реально лежит в папке.

Писать список языков руками нельзя: основной язык живёт в корне, остальные
в своих папках, и при смене основного языка руками написанный конфиг начнёт
отправлять посетителя в несуществующую папку.

Спецификация: docs/spec/23-distribution.md, раздел 5.
"""

from __future__ import annotations

import re

from heron.contracts.site import AnalyticsBlock, SiteConfig
from heron.core.errors import HeronError
from heron.messages import Msg
from heron.modules.redirects import Plan

NAME = ".heron-nginx.conf"

# Комментарии конфига — на языке пояснений сайта (build.notes): конфиг читает
# тот, кто публикует сайт. В шаблонах ниже на месте комментария метка
# `#@ключ` с отступом; `_comments` ставит вместо неё строки `# …` с тем же
# отступом. Директивы от языка не зависят: меняются только строки комментариев.
COMMENTS = {
    "ru": {
        "built": "Собран движком вместе с сайтом. Правки здесь переживут одну сборку.",
        "types": (
            "Типы файлов. `types` на уровне server не дополняет http-уровень, а\n"
            "заменяет его целиком, поэтому стоковый список подключается сам, а\n"
            "недостающее (markdown, yaml) объявляется рядом: записи в одном блоке\n"
            "nginx сливает. Без этого .md уезжает как application/octet-stream."
        ),
        "charset": (
            "`charset` касается только типов из этого списка. Стоковый перечень\n"
            "повторён целиком (директива заменяет его, а не дополняет), плюс markdown.\n"
            "text/html nginx включает сам: упомянутый здесь, он даёт предупреждение."
        ),
        "gzip": (
            "Сжатие: текст, стили, скрипты, svg, карты и разметка. Картинки и видео\n"
            "уже сжаты, второй раз их жать — только тратить процессор."
        ),
        "pages": (
            "Страницы — всегда спрашивать сервер: правка текста должна быть видна\n"
            "сразу. Ответ «не изменилось» (ETag, Last-Modified) почти бесплатен."
        ),
        "assets": (
            "Стили, скрипты и шрифты темы под прежними именами — сутки (nginx.cache.assets):\n"
            "имя не меняется при замене содержимого, поэтому «навсегда» здесь значило бы\n"
            "показывать старое тем, кто уже заходил. Страницы ссылаются на копии\n"
            "с хешем в имени, эти имена — запасные."
        ),
        "media": (
            "Ресурсы сайта лежат один раз, версия — в параметре: /media/x.jpg?v=0123456789.\n"
            "С меткой из 10 знаков hex — долгий срок и immutable (nginx.cache.versioned),\n"
            "без неё или с чужой — nginx.cache.media. Срок выбирает карта перед server."
        ),
        "mediamap": (
            "Срок кэша ресурса по метке ?v= (/media/). Имя переменной несёт оба срока:\n"
            "два сайта в одном http с разными сроками не перепишут карту друг друга."
        ),
        "versioned": (
            "Копия с хешем содержимого в имени (site.0123456789.css): под этим\n"
            "именем байты не меняются никогда, поэтому срок долгий и immutable\n"
            "(nginx.cache.versioned). Новая версия файла — новое имя."
        ),
        "hidden": (
            "Скрытые файлы наружу не отдаём. Рядом со статикой лежит служебное —\n"
            "например, этот самый конфиг: образ забирает его себе, но папку могут\n"
            "разложить и руками на чужой сервер. Проверку домена оставляем."
        ),
        "root": "Корень — основной язык сайта, его 404 лежит рядом с index.html.",
        "security": (
            "Безопасность: версия nginx не показывается, заголовки ставит образ сайта.\n"
            "add_header в location заменяет заголовки server, поэтому там они повторены."
        ),
        "health": "Проверка живости для healthcheck: отвечает без обращения к файлам.",
        "exact": "301 и 410: точные адреса, регистр важен",
        "noslash": (
            "Адреса без слеша (urls.trailing_slash: never): /x отдаётся из x/index.html.\n"
            "Не $uri/ - он дал бы 301 на /x/. Форма со слешем - 301 на форму без него,\n"
            "параметры запроса сохраняются."
        ),
        "langhome": "Главная языка без слеша: /{lang} отдаётся из {lang}/index.html.",
    },
    "en": {
        "built": "Built by the engine together with the site. Edits here survive one build.",
        "types": (
            "File types. `types` at the server level does not extend the http level,\n"
            "it replaces it entirely, so the stock list is included here, and what\n"
            "is missing (markdown, yaml) is declared next to it: nginx merges entries\n"
            "of one block. Without this, .md goes out as application/octet-stream."
        ),
        "charset": (
            "`charset` applies only to the types in this list. The stock list is\n"
            "repeated in full (the directive replaces it, it does not extend it),\n"
            "plus markdown. nginx adds text/html itself: listed here, it gives a warning."
        ),
        "gzip": (
            "Compression: text, styles, scripts, svg, maps and markup. Images and video\n"
            "are already compressed; compressing them again only wastes the processor."
        ),
        "pages": (
            "Pages: always ask the server, an edit of the text must show at once.\n"
            'A "not modified" answer (ETag, Last-Modified) costs almost nothing.'
        ),
        "assets": (
            "Theme styles, scripts and fonts under their plain names: one day\n"
            "(nginx.cache.assets). The name does not change when the content is replaced,\n"
            '"forever" here would mean showing the old file to those who visited before.\n'
            "Pages link to the copies with a hash in the name; plain names are the fallback."
        ),
        "media": (
            "Site resources lie once, the version is in a parameter: /media/x.jpg?v=0123456789.\n"
            "With a mark of 10 hex characters: a long time and immutable (nginx.cache.versioned);\n"
            "without it or with another one: nginx.cache.media. The map before server chooses."
        ),
        "mediamap": (
            "Cache time of a resource by its ?v= mark (/media/). The variable name carries\n"
            "both times: two sites in one http with different times do not overwrite the map."
        ),
        "versioned": (
            "A copy with the content hash in the name (site.0123456789.css): under this\n"
            "name the bytes never change, so the time is long and immutable\n"
            "(nginx.cache.versioned). A new version of the file is a new name."
        ),
        "hidden": (
            "Hidden files are not served. Service files lie next to the static ones,\n"
            "for example this very config: the image takes it for itself, but the\n"
            "folder can also be laid out by hand on another server. Domain checks stay."
        ),
        "root": "The root is the main language of the site, its 404 lies next to index.html.",
        "security": (
            "Security: the nginx version is hidden, the site image sets the headers.\n"
            "add_header in a location replaces the server ones, so they are repeated there."
        ),
        "health": "Liveness check for healthcheck: answers without touching files.",
        "exact": "301 and 410: exact addresses, case matters",
        "noslash": (
            "Addresses without a slash (urls.trailing_slash: never): /x is served from\n"
            "x/index.html. Not $uri/ - it would give a 301 to /x/. The form with a slash\n"
            "gets a 301 to the form without it, the query string is kept."
        ),
        "langhome": "The language home without a slash: /{lang} is served from {lang}/index.html.",
    },
}
MARK = re.compile(r"^( *)#@([a-z]+)\n", re.M)


def _comments(text: str, lang: str) -> str:
    """Метки `#@ключ` — строками комментария на языке `lang`."""
    table = COMMENTS.get(lang, COMMENTS["en"])
    return MARK.sub(
        lambda m: "".join(f"{m[1]}# {line}\n" for line in table[m[2]].split("\n")), text
    )


# Домены счётчиков по ключам `analytics` в site.yaml. Google Tag Manager и GA4
# загружают и шлют данные через одни и те же домены.
GOOGLE_COUNTER = (
    "https://*.googletagmanager.com",
    "https://*.google-analytics.com",
    "https://*.analytics.google.com",
)
COUNTER_DOMAINS = {
    "gtm": GOOGLE_COUNTER,
    "ga4": GOOGLE_COUNTER,
    "metrika": ("https://mc.yandex.ru",),
}


def _counter_domains(analytics: AnalyticsBlock) -> str:
    """Домены включённых счётчиков, через пробел и с пробелом впереди."""
    enabled = [
        domain
        for key, domains in COUNTER_DOMAINS.items()
        if getattr(analytics, key)
        for domain in domains
    ]
    return "".join(f" {domain}" for domain in dict.fromkeys(enabled))


def _csp(analytics: AnalyticsBlock) -> str:
    """CSP строгий: скрипты только свои, чужие домены — только включённых счётчиков."""
    extra = _counter_domains(analytics)
    connect = f"connect-src 'self'{extra}; " if extra else ""
    return (
        f"default-src 'self'; script-src 'self'{extra}; {connect}"
        f"style-src 'self' 'unsafe-inline'; img-src 'self' data:{extra}; font-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
    )


# Заголовки безопасности (спецификация 22, раздел 5). HSTS на http-ответе браузер
# игнорирует, а за TLS-прокси он нужен, поэтому ставится всегда.
def _security(indent: int, analytics: AnalyticsBlock) -> str:
    pad = " " * indent
    lines = (
        'add_header X-Content-Type-Options "nosniff" always;',
        'add_header Referrer-Policy "strict-origin-when-cross-origin" always;',
        f'add_header Content-Security-Policy "{_csp(analytics)}" always;',
        'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;',
    )
    return "".join(f"{pad}{line}\n" for line in lines)


HEAD = """server {
    listen       8080;
    server_name  _;

    root   /usr/share/nginx/html;
    index  index.html;

    charset utf-8;
    absolute_redirect off;
    server_tokens off;

    #@security
@SECURITY@
    #@health
    location = /healthz {
        access_log off;
@SECURITY8@
        default_type text/plain;
        return 200 "ok";
    }

    #@types
    include /etc/nginx/mime.types;
    types {
        text/markdown    md;
        application/yaml yaml yml;
    }
    #@charset
    charset_types text/xml text/plain text/vnd.wap.wml
                  application/javascript application/rss+xml text/markdown;

    #@gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml application/javascript application/json
               application/xml application/rss+xml application/atom+xml
               application/manifest+json image/svg+xml text/markdown application/yaml;

    #@pages
    add_header Cache-Control "no-cache" always;

    #@media
    location ^~ /media/ {
        add_header Cache-Control $@MEDIAVAR@ always;
@SECURITY8@
        location ~ /\\. { return 404; }
        try_files $uri =404;
    }
    #@assets
    location ^~ /assets/ {
        add_header Cache-Control "public, max-age=@ASSETS@" always;
@SECURITY8@
        location ~ /\\. { return 404; }
@VERSIONED@
        try_files $uri =404;
    }
"""

# Имя с хешем содержимого: `<имя>.<10 знаков hex>.<расширение>` (heron/core/versions.py),
# только у файлов темы. Регулярка вложена в префиксный location: `^~` отключает
# регулярки уровня server. В /media/ её нет: имя ресурса ничего не значит, его
# версия - параметр `?v=` (карта MEDIA_MAP), и файл `x.0123456789.jpg` без метки
# кэшируется как любой другой.
VERSIONED = """        #@versioned
        location ~ "\\.[0-9a-f]{10}\\.[A-Za-z0-9]+$" {
            add_header Cache-Control "public, max-age=@AGE@, immutable" always;
@SECURITY12@
            try_files $uri =404;
        }
"""

# Срок кэша ресурса по метке `?v=<10 hex>` (heron/core/versions.py, STAMP).
# Карта, а не `if` в location: `if` в location не наследует try_files, а
# add_header внутри него заменил бы заголовки безопасности. Карта стоит в
# контексте http, как и сам конфиг (23 §5); `$arg_v` - первый параметр `v`.
MEDIA_MAP = """#@mediamap
map $arg_v $@MEDIAVAR@ {
    "~^[0-9a-f]{10}$" "public, max-age=@AGE@, immutable";
    default           "public, max-age=@MEDIA@";
}
"""


# Язык в своей папке: и страница 404, и всё остальное лежат под префиксом.
# `^~` отключает регулярные location уровня server — поэтому запрет скрытых
# файлов повторён внутри, иначе `/ru/.secret` отдавался бы как обычный файл.
LANG = """
    location ^~ /{lang}/ {{
        location ~ /\\. {{ return 404; }}
        error_page 404 /{lang}/404/index.html;
        location = /{lang}/404/index.html {{ internal; }}
        try_files $uri $uri/ =404;
    }}
"""

# Адреса без слеша (`urls.trailing_slash: never`, 20 §2). `/x` отдаётся из
# `x/index.html` через `$uri/index.html`, а не `$uri/`: `$uri/` - это проверка
# папки, и nginx ответил бы на неё своим 301 на `/x/`. Форма со слешем -
# 301 на форму без него: `rewrite … permanent` дописывает параметры запроса сам.
LANG_NEVER = """
    #@langhome
    location = /{lang} {{
        error_page 404 /{lang}/404/index.html;
        try_files /{lang}/index.html =404;
    }}
    location ^~ /{lang}/ {{
        location ~ /\\. {{ return 404; }}
        location ~ ^(.+)/$ {{ rewrite ^(.+)/$ $1 permanent; }}
        error_page 404 /{lang}/404/index.html;
        location = /{lang}/404/index.html {{ internal; }}
        try_files $uri $uri/index.html =404;
    }}
"""

TAIL_NEVER = """
    #@hidden
    location ^~ /.well-known/ { try_files $uri =404; }
    location ~ /\\.           { return 404; }

    #@root
    error_page 404 /404.html;
    location = /404.html { internal; }

    #@noslash
    location / {
        location ~ /\\. { return 404; }
        location ~ ^(.+)/$ { rewrite ^(.+)/$ $1 permanent; }
        try_files $uri $uri/index.html =404;
    }
}
"""

TAIL = """
    #@hidden
    location ^~ /.well-known/ { try_files $uri =404; }
    location ~ /\\.           { return 404; }

    #@root
    error_page 404 /404.html;
    location = /404.html { internal; }

    location / {
        try_files $uri $uri/ =404;
    }
}
"""


# Чего в строке конфига nginx быть не может: управляющие C0 и C1, DEL и
# разделители строк U+2028/U+2029. Перевод строки внутри кавычек nginx принял
# бы как часть значения, а следующая директива начиналась бы с адреса сайта.
UNSAFE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def quote(value: str) -> str:
    """Строка для конфига nginx: в кавычках, с экранированными `"` и `\\`.

    Ключи карты — литералы, переменные в них не раскрываются, поэтому `$`
    экранировать не нужно. Управляющий символ — `E022`, а не экранирование:
    адреса проверены раньше (E002, E022), и сюда он может попасть только мимо
    проверок — тогда конфиг не собирается вовсе.
    """
    if UNSAFE.search(value):
        raise HeronError(
            code="E022",
            message=Msg("redirects_nginx_control", value=value),
            path=NAME,
            hint=Msg("redirects_control_hint"),
        )
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _variants(path: str) -> list[str]:
    """Адрес и он же без завершающего слеша: сервер отвечает на оба."""
    if path != "/" and path.endswith("/"):
        return [path, path[:-1]]
    return [path]


def _raw_pattern(path: str, prefix: bool = False) -> str:
    """Регулярка по сырому адресу: регистр букв важен, регистр `%xx` — нет.

    `%D0%B0` и `%d0%b0` — один и тот же байт, браузеры шлют оба. Буквы же
    адреса различаются: `/About/` и `/about/` — разные страницы, как и везде
    в движке.
    """
    out: list[str] = []
    index = 0
    # У точного адреса слеш необязателен (`/?` добавляет вызывающий), у
    # префикса он — граница: `/%D0/*` не должен захватывать `/%D0extra/`.
    stem = path if prefix else path.rstrip("/")
    while index < len(stem):
        chunk = stem[index : index + 3]
        if (
            len(chunk) == 3
            and chunk[0] == "%"
            and all(c in "0123456789abcdefABCDEF" for c in chunk[1:])
        ):
            out.append(
                "%" + "".join(f"[{c.upper()}{c.lower()}]" if c.isalpha() else c for c in chunk[1:])
            )
            index += 3
        else:
            out.append(re.escape(stem[index]))
            index += 1
    return "".join(out)


def _block(head: str, default: str, rows: list[str]) -> str:
    return head + " {\n    default " + default + ";\n" + "\n".join(rows) + "\n}\n"


def _locations(plan: Plan, lang: str = "en") -> str:
    """301 и 410 точными и префиксными location.

    Строковые ключи `map` nginx сравнивает без учёта регистра, а адреса в
    движке регистр различают: `/Page/` из redirect_from превращался в
    редирект `/page/` на самого себя, `/Gone/` в gone закрывал живую
    `/gone/`, а `/A/` и `/a/` вместе роняли конфиг. Точное (`location =`)
    и префиксное (`location ^~`) сравнение у nginx регистр различает,
    работает по тому же декодированному `$uri` и не требует хэш-таблиц.
    """
    rows: list[str] = []
    for old, new in sorted(plan.moved.items()):
        if old in plan.raw:
            continue
        for variant in _variants(old):
            rows.append(f"    location = {quote(variant)} {{ return 301 {quote(new)}; }}")
    for path in plan.gone:
        if path in plan.raw:
            continue
        for variant in _variants(path):
            rows.append(f"    location = {quote(variant)} {{ return 410; }}")
    for path in plan.gone_prefixes:
        if path not in plan.raw:
            rows.append(f"    location ^~ {quote(path)} {{ return 410; }}")
    return (_comments("\n    #@exact\n", lang) + "\n".join(rows) + "\n") if rows else ""


def _maps(plan: Plan) -> tuple[str, str]:
    """Карты для того, что location не выразить, и проверки в начале server.

    Остаются регулярки: адреса, которые после декодирования не текст (слаг
    обрезан посреди буквы, — сверяются с сырым `$request_uri`), и адреса с
    параметром (`/?p=*`, по `$uri?$args`). Регулярка в `map` чувствительна
    к регистру, хэш-таблиц у неё нет — размеры корзин не нужны.
    """
    maps: list[str] = []
    checks: list[str] = []

    raw_gone = [g for g in plan.gone if g in plan.raw]
    raw_prefixes = [g for g in plan.gone_prefixes if g in plan.raw]
    if raw_gone or raw_prefixes:
        rows = [f"    {quote('~^' + _raw_pattern(path) + '/?(?:[?].*)?$')} 1;" for path in raw_gone]
        rows += [f"    {quote('~^' + _raw_pattern(path, prefix=True))} 1;" for path in raw_prefixes]
        maps.append(_block("map $request_uri $heron_gone_raw", "0", rows))
        checks.append("    if ($heron_gone_raw) { return 410; }\n")

    if plan.gone_queries:
        rows = []
        for path, name, value in plan.gone_queries:
            tail = "[^&]*" if value is None else re.escape(value)
            stem = re.escape(path.rstrip("/"))
            pattern = f"~^{stem}/?\\?(?:.*&)?{re.escape(name)}={tail}(?:&|$)"
            rows.append(f"    {quote(pattern)} 1;")
        maps.append(_block('map "$uri?$args" $heron_gone_query', "0", rows))
        checks.append("    if ($heron_gone_query) { return 410; }\n")

    raw_moved = {old: new for old, new in sorted(plan.moved.items()) if old in plan.raw}
    if raw_moved:
        rows = [
            f"    {quote('~^' + _raw_pattern(old) + '/?(?:[?].*)?$')} {quote(new)};"
            for old, new in raw_moved.items()
        ]
        maps.append(_block("map $request_uri $heron_moved_raw", '""', rows))
        checks.append("    if ($heron_moved_raw) { return 301 $heron_moved_raw; }\n")

    return "".join(maps), "".join(checks)


def media_variable(age: int, media: int) -> str:
    """Имя переменной карты сроков `/media/`: с обоими сроками внутри.

    Карта живёт в общем http; две одинаковые карты nginx принимает молча,
    и побеждает последняя. Сайты с одинаковыми сроками делят одну карту
    без вреда, с разными - получают разные имена.
    """
    return f"heron_media_cache_{age}_{media}"


def generate(config: SiteConfig, plan: Plan | None = None) -> dict[str, str]:
    """Конфиг под языки этого сайта. Основной язык в корень, прочие — в папки.

    301 и 410 — точными location в начале server; перед server — карты
    для сырых адресов и параметров, если они есть.
    """
    plan = plan or Plan()
    default = config.site.default_lang
    maps, checks = _maps(plan)
    # Комментарии — по build.notes, без HERON_NOTES: те же исходники дают тот
    # же конфиг на любой машине. Метки раскрываются в шаблоне до вставки
    # адресов: строка сайта меткой не станет.
    notes = config.build.notes
    cache = config.nginx.cache
    age, media = cache.seconds("versioned"), cache.seconds("media")
    variable = media_variable(age, media)
    versioned = (
        _comments(VERSIONED, notes)
        .replace("@SECURITY12@\n", _security(12, config.analytics))
        .replace("@AGE@", str(age))
    )
    media_map = (
        _comments(MEDIA_MAP, notes)
        .replace("@MEDIAVAR@", variable)
        .replace("@AGE@", str(age))
        .replace("@MEDIA@", str(media))
    )
    head = (
        _comments(HEAD, notes)
        .replace("@VERSIONED@\n", versioned)
        .replace("@SECURITY8@\n", _security(8, config.analytics))
        .replace("@SECURITY@\n", _security(4, config.analytics))
        .replace("@MEDIAVAR@", variable)
        .replace("@ASSETS@", str(cache.seconds("assets")))
    )
    head = head.replace(
        "    absolute_redirect off;\n",
        "    absolute_redirect off;\n" + checks + _locations(plan, notes),
    )
    parts = [_comments("#@built\n", notes) + "\n", maps, media_map + "\n", head]
    slash = config.urls.slash
    for lang in config.site.languages:
        if lang != default:
            block = LANG.format(lang=lang) if slash else _comments(LANG_NEVER, notes)
            parts.append(block if slash else block.format(lang=lang))
    parts.append(_comments(TAIL if slash else TAIL_NEVER, notes))
    return {NAME: "".join(parts)}


MIME_INCLUDE = "include /etc/nginx/mime.types;"
MIME_STUB = "types {\n  text/html html htm;\n  text/css css;\n}\n"


def _mime_types(binary: str, subprocess) -> str | None:
    """Где у этого nginx лежит mime.types: рядом с его главным конфигом.

    В образе и на пакетных системах это /etc/nginx; на Homebrew, FreeBSD и у
    nginx из исходников — свой каталог, его знает `nginx -V` (--conf-path).
    """
    from pathlib import Path

    if Path("/etc/nginx/mime.types").is_file():
        return "/etc/nginx/mime.types"
    try:
        info = subprocess.run(
            [binary, "-V"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"--conf-path=(\S+)", info.stderr + info.stdout)
    if match:
        candidate = Path(match.group(1)).parent / "mime.types"
        if candidate.is_file():
            return str(candidate)
    return None


def check(conf: str | None, collector=None) -> tuple[bool, str] | None:
    """Прогнать `nginx -t` на собранном конфиге, если nginx есть под рукой.

    Конфиг подключается так же, как его подключают образ и хост: в контекст
    http. Падение — предупреждение сборки (при --strict, значит, ошибка):
    битый конфиг не должен уезжать дальше машины, на которой его собрали.
    Нет nginx — проверки нет, и это не повод ругаться.
    """
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    binary = shutil.which("nginx")
    if not conf or not binary:
        return None
    with tempfile.TemporaryDirectory(prefix="heron-nginx-") as tmp:
        root = Path(tmp)
        # Собранный конфиг не меняется: подставляется только его копия для
        # проверки, чтобы абсолютный путь образа не ронял её на других системах.
        mime = _mime_types(binary, subprocess)
        if mime is None:
            mime = str(root / "mime.types")
            (root / "mime.types").write_text(MIME_STUB, encoding="utf-8")
        (root / "site.conf").write_text(conf.replace(MIME_INCLUDE, f"include {mime};"), "utf-8")
        temp = "\n".join(
            f"  {name} {root}/{name};"
            for name in (
                "client_body_temp_path",
                "proxy_temp_path",
                "fastcgi_temp_path",
                "uwsgi_temp_path",
                "scgi_temp_path",
            )
        )
        (root / "nginx.conf").write_text(
            f"pid {root}/nginx.pid;\nerror_log {root}/error.log;\nevents {{}}\n"
            f"http {{\n  access_log off;\n{temp}\n  include {root}/site.conf;\n}}\n",
            encoding="utf-8",
        )
        command = [binary, "-t", "-q", "-p", str(root), "-c", str(root / "nginx.conf")]
        try:
            done = subprocess.run(
                [*command[:1], "-e", "stderr", *command[1:]],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if done.returncode != 0 and "invalid option" in done.stderr:
                # nginx старше 1.19.5 не знает -e
                done = subprocess.run(
                    command, capture_output=True, text=True, timeout=15, check=False
                )
        except (OSError, subprocess.SubprocessError):
            return None
    output = (done.stderr or done.stdout).strip()
    passed = done.returncode == 0
    if not passed and collector is not None:
        collector.warn(
            Msg(
                "redirects_nginx_rejected",
                emerg=" ".join(line.strip() for line in output.splitlines() if "emerg" in line)[
                    :400
                ],
            ),
            path=NAME,
            kind="прочее",
        )
    return passed, output
