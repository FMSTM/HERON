#!/usr/bin/env bash
#
# Дымовая проверка поднятого сайта: коды ответа по тому, что собрал движок.
# Одна на всех: её зовут scripts/site.sh smoke и переиспользуемый workflow
# сборки образа сайта (.github/workflows/site-image.yml).
#
#   scripts/smoke-site.sh <адрес> <папка сборки>
#   scripts/smoke-site.sh http://localhost:18080 out/мойсайт-prod
#
# Сама проверка — scripts/smoke_site.py (только стандартная библиотека):
# языки из конфига сборки, 200/404 на каждом, скрытые пути, конечные цели
# 301 без цепочек и петель, 410.
#
# Здесь же — Content-Type сырых файлов (23 §5): если в сборке есть *.md,
# *.yaml или *.yml, первый по алфавиту файл каждого вида запрашивается и
# должен прийти 200 с text/markdown или application/yaml. Без объявления
# типов в конфиге nginx отдаёт их application/octet-stream, и инструмент
# чтения у агента принимает инструкции за бинарь. Нет таких файлов — шаг
# молча пропускается.

set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rc=0
python3 "$here/smoke_site.py" "$@" || rc=$?
[ "$#" -eq 2 ] || exit "$rc"

python3 - "$1" "$2" <<'PY' || rc=1
import http.client
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

base, out = urlsplit(sys.argv[1].rstrip("/")), Path(sys.argv[2])
WANT = {".md": "text/markdown", ".yaml": "application/yaml", ".yml": "application/yaml"}
SKIP = {"404.html"}


def first(suffix: str) -> Path | None:
    found = sorted(
        p.relative_to(out)
        for p in out.rglob(f"*{suffix}")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(out).parts)
    )
    return found[0] if found else None


failed = checked = 0
for suffix, want in WANT.items():
    rel = first(suffix)
    if rel is None:
        continue
    path = "/" + quote(rel.as_posix())
    conn = http.client.HTTPConnection(base.hostname or "localhost", base.port or 80, timeout=10)
    try:
        conn.request("GET", path, headers={"Accept-Encoding": "identity"})
        resp = conn.getresponse()
        resp.read()
        status, ctype = resp.status, resp.getheader("Content-Type") or ""
    finally:
        conn.close()
    checked += 1
    if status != 200 or ctype.split(";")[0].strip() != want:
        failed += 1
        print(f"\033[31m  ✗ {path} → {status} {ctype or '(нет Content-Type)'}, ждали 200 {want}\033[0m")
    else:
        print(f"  ✓ {path} → {ctype}")
if checked:
    print(f"  Content-Type сырых файлов: проверено {checked}, не так: {failed}")
sys.exit(1 if failed else 0)
PY

if [ "$rc" -ne 0 ]; then
  echo -e "\033[31mдымовая проверка не прошла\033[0m" >&2
fi
exit "$rc"
