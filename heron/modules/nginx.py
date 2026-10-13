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
from dataclasses import dataclass

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
        location ~ /\. { return 404; }
        try_files $uri =404;
    }
    location ^~ /assets/ {
        add_header Cache-Control "public, max-age=86400" always;
        location ~ /\. { return 404; }
        try_files $uri =404;
    }
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


# Размер указателя и длины ключа в элементе хэша nginx (ngx_hash_elt_t) на
# 64-битной машине. Элемент: указатель на значение, длина ключа (2 байта) и
# сам ключ, выровненные по указателю; корзина — элементы плюс указатель-конец.
POINTER = 8
SAFE_BUCKET = 64
SAFE_MAX_SIZE = 2048


@dataclass(frozen=True, slots=True)
class HashSizes:
    """Размеры хэшей карт: что вписать в http {} и откуда это взялось."""

    bucket: int
    max_size: int
    longest: int  # самый длинный ключ, байт
    keys: int  # ключей во всех картах


def _power(value: int) -> int:
    size = 1
    while size < value:
        size *= 2
    return size


def _align(value: int) -> int:
    return (value + POINTER - 1) // POINTER * POINTER


def hash_sizes(keys: list[str]) -> HashSizes:
    """map_hash_bucket_size и map_hash_max_size для этих ключей.

    По умолчанию корзина равна кэш-линии процессора — обычно 64 байта, — и
    длинный кириллический адрес (2 байта на букву) в неё не помещается:
    nginx не стартует с «could not build map_hash». Запустится конфиг или
    нет, не должно зависеть от железа, поэтому движок считает размеры сам.
    Ключ, который ближе 16 байт к границе корзины, получает корзину вдвое
    больше: несколько ключей делят одну корзину, и впритык — это ненадёжно.
    """
    longest = max((len(key.encode("utf-8")) for key in keys), default=0)
    need = _align(POINTER + 2 + longest) + POINTER
    bucket = _power(max(SAFE_BUCKET, need))
    if bucket - need < 16:
        bucket *= 2
    max_size = _power(max(SAFE_MAX_SIZE, len(keys) * 2))
    return HashSizes(bucket=bucket, max_size=max_size, longest=longest, keys=len(keys))


def _hashed(plan: Plan) -> list[str]:
    """Ключи карт, которые nginx кладёт в хэш, — как они стоят в конфиге.

    Регулярки (`~^…`) в хэш не входят и не считаются. Ключ берётся в том
    виде, в каком он записан в кавычках: с экранированием — это не меньше
    того, что nginx хранит, и запас здесь только на пользу.
    """
    keys: list[str] = []
    for path in plan.gone:
        if path not in plan.raw:
            keys += _variants(path)
    for old in plan.moved:
        if old not in plan.raw:
            keys += _variants(old)
    return [quote(key)[1:-1] for key in keys]


def sizes(plan: Plan | None) -> HashSizes | None:
    """Размеры хэшей для карт этого сайта. Карт нет — нечего и задавать."""
    plan = plan or Plan()
    if not (plan.gone or plan.gone_prefixes or plan.gone_queries or plan.moved):
        return None
    return hash_sizes(_hashed(plan))


def _directives(found: HashSizes) -> str:
    return (
        f"# HERON: самый длинный ключ карт — {found.longest} байт, ключей — {found.keys}.\n"
        "# Значения посчитаны движком: по умолчанию корзина равна кэш-линии процессора,\n"
        "# и длинный кириллический адрес в неё может не поместиться. Если nginx.conf\n"
        "# хоста уже задаёт их — nginx: hash_sizes: off в site.yaml.\n"
        f"map_hash_bucket_size {found.bucket};\n"
        f"map_hash_max_size {found.max_size};\n\n"
    )


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
    found = sizes(plan)
    # Директивы — до первой карты и вне server: это контекст http, куда
    # файл подключают и образ (conf.d), и хост (sites-enabled).
    hashes = _directives(found) if found and config.nginx.hash_sizes == "auto" else ""
    parts = [hashes, maps + "\n" if maps else "", head]
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
