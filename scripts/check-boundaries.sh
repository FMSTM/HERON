#!/usr/bin/env bash
# Граница ядра: движок не знает ни про один конкретный сайт.
# Логика и пояснения — scripts/check_boundaries.py.
set -euo pipefail
exec python3 "$(dirname "$0")/check_boundaries.py" "$@"
