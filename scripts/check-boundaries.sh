#!/usr/bin/env bash
# Граница ядра: движок не знает ни про один конкретный сайт.
# Хук падает, если в коммит попало упоминание клиента, домена или телефона.
# Обоснование: docs/spec/23-distribution.md, раздел 9.
set -euo pipefail

patterns_file="$(dirname "$0")/boundary-patterns.txt"
[ -f "$patterns_file" ] || { echo "нет файла образцов: $patterns_file" >&2; exit 1; }

files=("$@")
[ ${#files[@]} -eq 0 ] && exit 0

found=0
while IFS= read -r pattern; do
  [[ -z "$pattern" || "$pattern" == \#* ]] && continue
  for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    case "$f" in scripts/boundary-patterns.txt|scripts/check-boundaries.sh) continue ;; esac
    if matches=$(grep -nEi -- "$pattern" "$f" 2>/dev/null); then
      echo "ГРАНИЦА ЯДРА НАРУШЕНА: образец '$pattern' в $f" >&2
      echo "$matches" | sed 's/^/    /' >&2
      found=1
    fi
  done
done < "$patterns_file"

if [ "$found" -ne 0 ]; then
  cat >&2 <<'MSG'

Ядро не должно знать о конкретных сайтах. Варианты:
  - вынести специфичное в тему, content/ или site.yaml сайта;
  - если это тестовые данные — использовать вымышленные имена и домены example.com;
  - если образец устарел — править scripts/boundary-patterns.txt осознанно, отдельным коммитом.
MSG
  exit 1
fi
