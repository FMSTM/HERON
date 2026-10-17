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

    # Сжатие: текст, стили, скрипты, svg, карты и разметка. Картинки и видео
    # уже сжаты, второй раз их жать — только тратить процессор.
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml application/javascript application/json
               application/xml application/rss+xml application/atom+xml
               application/manifest+json image/svg+xml;

    # Страницы — всегда спрашивать сервер: правка текста должна быть видна
    # сразу. Ответ «не изменилось» (ETag, Last-Modified) почти бесплатен.
    add_header Cache-Control "no-cache" always;

    # Картинки, стили и скрипты — сутки. Имена файлов не меняются при
    # замене содержимого, поэтому «навсегда» здесь значило бы неделю
    # показывать старую картинку тем, кто уже заходил.
    location ^~ /media/ {
        add_header Cache-Control "public, max-age=86400" always;
        location ~ /\\. { return 404; }
        try_files $uri =404;
    }
    location ^~ /assets/ {
        add_header Cache-Control "public, max-age=86400" always;
        location ~ /\\. { return 404; }
        try_files $uri =404;
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


def _locations(plan: Plan) -> str:
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
    return (
        ("\n    # 301 и 410: точные адреса, регистр важен\n" + "\n".join(rows) + "\n")
        if rows
        else ""
    )


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


def generate(config: SiteConfig, plan: Plan | None = None) -> dict[str, str]:
    """Конфиг под языки этого сайта. Основной язык в корень, прочие — в папки.

    301 и 410 — точными location в начале server; перед server — карты
    для сырых адресов и параметров, если они есть.
    """
    plan = plan or Plan()
    default = config.site.default_lang
    maps, checks = _maps(plan)
    head = HEAD.replace(
        "    absolute_redirect off;\n", "    absolute_redirect off;\n" + checks + _locations(plan)
    )
    parts = [maps + "\n" if maps else "", head]
    for lang in config.site.languages:
        if lang != default:
            parts.append(LANG.format(lang=lang))
    parts.append(TAIL)
    return {NAME: "".join(parts)}


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
        (root / "site.conf").write_text(conf, encoding="utf-8")
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
            "nginx -t не принял собранный конфиг: "
            + " ".join(line.strip() for line in output.splitlines() if "emerg" in line)[:400],
            path=NAME,
            kind="прочее",
        )
    return passed, output
