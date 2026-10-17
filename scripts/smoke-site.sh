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

set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/smoke_site.py" "$@"
