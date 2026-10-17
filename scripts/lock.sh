#!/usr/bin/env bash
#
# Выгрузить зафиксированные зависимости для образа движка.
#
#   ./scripts/lock.sh            переписать requirements*.lock по uv.lock
#   ./scripts/lock.sh --check    только сверить: расходятся — код 1
#
# Образ ставит зависимости pip-ом с проверкой хешей (--require-hashes) из
# requirements.lock — выгрузки uv.lock без dev-группы. Сборочный бэкенд
# (hatchling и его зависимости) — в requirements-build.lock, тоже с хешами.

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HEAD="# Выгружено из uv.lock: ./scripts/lock.sh. Руками не править."

runtime() {
  echo "$HEAD"
  uv export --frozen --no-dev --no-emit-project --no-header --format requirements-txt \
    2>/dev/null </dev/null
}

if [ "${1:-}" = "--check" ]; then
  if ! runtime | cmp -s - requirements.lock; then
    echo "requirements.lock расходится с uv.lock — выполните ./scripts/lock.sh" >&2
    exit 1
  fi
  exit 0
fi

runtime > requirements.lock
build="$(mktemp)"
trap 'rm -f "$build"' EXIT
echo hatchling > "$build"
{
  echo "# Сборочный бэкенд образа движка (pip --no-build-isolation): ./scripts/lock.sh."
  uv pip compile "$build" --generate-hashes --python-version 3.12 \
    --python-platform x86_64-unknown-linux-gnu --no-header -q </dev/null 2>/dev/null
} > requirements-build.lock
echo "requirements.lock и requirements-build.lock обновлены"
