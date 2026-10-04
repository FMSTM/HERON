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

from heron.contracts.site import SiteConfig
from heron.modules.redirects import Plan

NAME = ".heron-nginx.conf"

HEAD = """# Собран движком вместе с сайтом. Правки здесь переживут одну сборку.
server {
    listen       8080;
    server_name  _;

    root   /usr/share/nginx/html;
    index  index.html;

    charset utf-8;
    absolute_redirect off;
"""

# Язык в своей папке: и страница 404, и всё остальное лежат под префиксом.
LANG = """
    location ^~ /{lang}/ {{
        error_page 404 /{lang}/404/index.html;
        location = /{lang}/404/index.html {{ internal; }}
        try_files $uri $uri/ =404;
    }}
"""

TAIL = """
    # Скрытые файлы наружу не отдаём. Рядом со статикой лежит служебное —
    # например, этот самый конфиг: образ забирает его себе, но папку могут
    # разложить и руками на чужой сервер. Проверку домена оставляем.
    location ^~ /.well-known/ { try_files $uri =404; }
    location ~ /\\.           { return 404; }

    # Корень — основной язык сайта, его 404 лежит рядом с index.html.
    error_page 404 /404.html;
    location = /404.html { internal; }

    location / {
        try_files $uri $uri/ =404;
    }
}
"""


def quote(value: str) -> str:
    """Строка для конфига nginx: в кавычках, с экранированными `"` и `\\`.

    Ключи карты — литералы, переменные в них не раскрываются, поэтому `$`
    экранировать не нужно.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _variants(path: str) -> list[str]:
    """Адрес и он же без завершающего слеша: сервер отвечает на оба."""
    if path != "/" and path.endswith("/"):
        return [path, path[:-1]]
    return [path]


def _raw_exact(path: str) -> str:
    """Регулярка по сырому адресу запроса: регистр `%xx` и слеш не важны."""
    return f"~*^{re.escape(path.rstrip('/'))}/?(?:\\?.*)?$"


def _block(head: str, default: str, rows: list[str]) -> str:
    return head + " {\n    default " + default + ";\n" + "\n".join(rows) + "\n}\n"


def _maps(plan: Plan) -> tuple[str, str]:
    """Карты 301 и 410 и проверки в начале server.

    Карты сравнивают `$uri` — декодированный и нормализованный путь без
    параметров, поэтому кириллический адрес и его percent-форма попадают в
    одну строку. Адрес с параметром (`/?p=*`) сверяется отдельной картой по
    `$uri?$args`. Адреса, которые после декодирования не текст (слаг обрезан
    посреди буквы), сверяются с сырым `$request_uri`. Проверки стоят на
    уровне server, до выбора location: ответ уходит без обращения к файлам.
    """
    maps: list[str] = []
    checks: list[str] = []

    gone = [g for g in plan.gone if g not in plan.raw]
    prefixes = [g for g in plan.gone_prefixes if g not in plan.raw]
    if gone or prefixes:
        rows = [f"    {quote(v)} 1;" for path in gone for v in _variants(path)]
        rows += [f"    {quote('~^' + re.escape(path))} 1;" for path in prefixes]
        maps.append(_block("map $uri $heron_gone", "0", rows))
        checks.append("    if ($heron_gone) { return 410; }\n")

    raw_gone = [g for g in plan.gone if g in plan.raw]
    raw_prefixes = [g for g in plan.gone_prefixes if g in plan.raw]
    if raw_gone or raw_prefixes:
        rows = [f"    {quote(_raw_exact(path))} 1;" for path in raw_gone]
        rows += [f"    {quote('~*^' + re.escape(path))} 1;" for path in raw_prefixes]
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

    moved = {old: new for old, new in sorted(plan.moved.items()) if old not in plan.raw}
    if moved:
        rows = [
            f"    {quote(v)} {quote(new)};" for old, new in moved.items() for v in _variants(old)
        ]
        maps.append(_block("map $uri $heron_moved", '""', rows))
        checks.append("    if ($heron_moved) { return 301 $heron_moved; }\n")

    raw_moved = {old: new for old, new in sorted(plan.moved.items()) if old in plan.raw}
    if raw_moved:
        rows = [f"    {quote(_raw_exact(old))} {quote(new)};" for old, new in raw_moved.items()]
        maps.append(_block("map $request_uri $heron_moved_raw", '""', rows))
        checks.append("    if ($heron_moved_raw) { return 301 $heron_moved_raw; }\n")

    return "".join(maps), "".join(checks)


def generate(config: SiteConfig, plan: Plan | None = None) -> dict[str, str]:
    """Конфиг под языки этого сайта. Основной язык в корень, прочие — в папки.

    Перед server — карты 301 и 410, если они есть; в начале server —
    проверки по ним.
    """
    default = config.site.default_lang
    maps, checks = _maps(plan or Plan())
    head = HEAD.replace("    absolute_redirect off;\n", "    absolute_redirect off;\n" + checks)
    parts = [maps + "\n" if maps else "", head]
    for lang in config.site.languages:
        if lang != default:
            parts.append(LANG.format(lang=lang))
    parts.append(TAIL)
    return {NAME: "".join(parts)}
