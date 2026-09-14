#!/usr/bin/env bash
# Сборка сайта.
#
#   ./build.sh                    → dist/, мягко: посмотреть на работу
#   ./build.sh --strict           → dist/, строго: как соберёт прод
#   ./build.sh --image мой:1.0    → образ nginx с сайтом внутри (всегда строго)
#
# Сборщику не нужно ничего: ни сети, ни прав, ни секретов. Так и запускаем.
set -euo pipefail

IMAGE="ghcr.io/fmstm/heron:{version}"
cd "$(dirname "$0")"

if [ "${{1:-}}" = "--image" ]; then
  tag="${{2:?укажите тег: ./build.sh --image мой-сайт:1.0}}"
  docker build -t "$tag" .
  echo "готов образ $tag"
  echo "запустить: docker run --rm -p 8080:8080 $tag"
  exit 0
fi

docker run --rm \
  --network=none \
  --read-only --tmpfs /tmp \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/site" \
  "$IMAGE" build "$@"

echo "готово: dist/"
echo "посмотреть: docker compose up -d web  →  http://localhost:8080"
