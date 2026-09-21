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

from heron.contracts.site import SiteConfig

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


def generate(config: SiteConfig) -> dict[str, str]:
    """Конфиг под языки этого сайта. Основной язык в корень, прочие — в папки."""
    default = config.site.default_lang
    parts = [HEAD]
    for lang in config.site.languages:
        if lang != default:
            parts.append(LANG.format(lang=lang))
    parts.append(TAIL)
    return {NAME: "".join(parts)}
