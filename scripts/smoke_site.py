#!/usr/bin/env python3
"""Дымовая проверка поднятого сайта по тому, что собрал движок.

    python3 scripts/smoke_site.py <адрес> <папка сборки>
    python3 scripts/smoke_site.py http://localhost:18080 out/мойсайт-prod

Только стандартная библиотека: скрипт зовут и site.sh, и переиспользуемый
workflow образа сайта на голом раннере.

Проверяет, по-настоящему отправляя запросы:

- корень, robots.txt и главная каждого языка из конфига сборки — 200;
- несуществующий адрес в корне и под каждым языком — 404;
- скрытые файлы — 404 в корне, под каждым языком, в media/ и assets/,
  включая настоящие служебные файлы сборки (.heron-nginx.conf и манифест);
- каждый адрес redirects.map — 301 ровно туда, куда объявлено, цель
  отвечает 200 сама, без второго редиректа (цепочки и петли — ошибка);
- каждый точный адрес gone.map — 410.

Языки берутся из собранного конфига nginx (`location ^~ /<язык>/`) — тем
же, что отдаёт сайт, а не угадываются по папкам.
"""

from __future__ import annotations

import http.client
import re
import sys
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

LANG = re.compile(r"location \^~ /([a-z]{2,3}(?:-[a-z0-9]+)?)/ \{")
HOPS = 5


class Smoke:
    def __init__(self, base: str, out: Path) -> None:
        parts = urlsplit(base)
        self.host = parts.hostname or "localhost"
        self.port = parts.port or 80
        self.out = out
        self.failed = 0
        self.passed = 0

    def get(self, path: str) -> tuple[int, str]:
        """Код и Location. Путь кодируется так, как его шлёт браузер."""
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request("GET", quote(path, safe="/%?=&:@!$'()*+,;~-._"))
            response = connection.getresponse()
            response.read()
            return response.status, response.getheader("Location") or ""
        finally:
            connection.close()

    def expect(self, path: str, want: int) -> None:
        got, _ = self.get(path)
        self.result(got == want, f"{path} → {got}, ждали {want}")

    def result(self, ok: bool, problem: str) -> None:
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            print(f"\033[31m  {problem}\033[0m", file=sys.stderr)

    def languages(self) -> list[str]:
        conf = self.out / ".heron-nginx.conf"
        text = conf.read_text(encoding="utf-8") if conf.is_file() else ""
        return sorted(set(LANG.findall(text)))

    def final(self, start: str) -> tuple[int, list[str]]:
        """Пройти редиректы от адреса: последний код и цепочка адресов."""
        chain = [start]
        status, location = self.get(start)
        while status in (301, 302, 307, 308) and len(chain) <= HOPS:
            target = urlsplit(urljoin(f"http://{self.host}:{self.port}{chain[-1]}", location))
            nxt = target.path + (f"?{target.query}" if target.query else "")
            if nxt in chain:
                return -1, [*chain, nxt]  # петля
            chain.append(nxt)
            status, location = self.get(nxt)
        return status, chain

    def run(self) -> int:
        langs = self.languages()
        self.expect("/", 200)
        self.expect("/robots.txt", 200)
        self.expect("/heron-smoke-нет-такой-страницы/", 404)
        for lang in langs:
            self.expect(f"/{lang}/", 200)
            self.expect(f"/{lang}/heron-smoke-нет-такой/", 404)

        hidden = ["/.heron-nginx.conf", "/.heron-manifest.json", "/.heron-smoke", "/.git/config"]
        for prefix in ["/media", "/assets", *(f"/{lang}" for lang in langs)]:
            hidden += [f"{prefix}/.heron-smoke", f"{prefix}/x/.heron-smoke"]
        for path in hidden:
            self.expect(path, 404)

        moved = 0
        for line in _lines(self.out / "redirects.map"):
            old, new = line.rsplit(" ", 1)
            old, new = old.strip(), new.rstrip(";").strip()
            status, location = self.get(old)
            landed = urlsplit(urljoin(f"http://{self.host}:{self.port}{old}", location)).path
            self.result(
                status == 301 and _same(landed, new),
                f"{old} → {status} {location}, ждали 301 на {new}",
            )
            code, chain = self.final(old)
            self.result(
                code == 200 and len(chain) == 2,
                f"{old}: цель должна отвечать 200 сразу, а цепочка {' → '.join(chain)} даёт {code}",
            )
            moved += 1

        gone = 0
        for line in _lines(self.out / "gone.map"):
            path = line.rsplit(" ", 1)[0].strip()
            if "*" in path or "?" in path:
                continue  # префиксы и параметры проверяют тесты движка
            self.expect(path, 410)
            gone += 1

        print(
            f"\033[32m  проверено: {self.passed}, 301: {moved}, 410: {gone}, языки: "
            f"{', '.join(langs) or 'один'}\033[0m"
        )
        return 1 if self.failed else 0


def _lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _same(path: str, declared: str) -> bool:
    from urllib.parse import unquote

    return unquote(path) == unquote(declared)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("нужно: smoke_site.py <адрес> <папка сборки>", file=sys.stderr)
        return 2
    code = Smoke(argv[1].rstrip("/"), Path(argv[2])).run()
    if code:
        print("\033[31mдымовая проверка не прошла\033[0m", file=sys.stderr)
    else:
        print("\033[32mсайт отвечает как надо\033[0m")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
