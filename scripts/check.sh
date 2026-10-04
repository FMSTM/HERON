#!/usr/bin/env bash
#
# Те же проверки, что гоняет CI, одной командой.
#
#   ./scripts/check.sh
#
# Заводится ровно потому, что дважды подряд вышло одинаково: локально
# гонялась часть проверок, а падало на GitHub. Набор должен быть один,
# и жить он должен в одном месте.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
note() { printf '\033[36m%s\033[0m\n' "$*"; }
die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

# uv, если он есть; иначе тот python, которым пользуются на этой машине.
if command -v uv >/dev/null 2>&1; then
  run() { uv run "$@"; }
else
  run() { python3 -m "$@"; }
  note "uv не найден — гоню через python3 -m"
fi

note "граница ядра"
git ls-files -z | xargs -0 bash scripts/check-boundaries.sh || die "граница ядра нарушена"

note "формат"
run ruff format --check . || die "ruff format: есть неотформатированные файлы, поправит ruff format ."

note "линтер"
run ruff check . || die "ruff check: есть замечания"

note "тесты"
run pytest || die "тесты не прошли"

ok "всё чисто"
