#!/usr/bin/env bash
# Сборка сайта. Без аргументов — папка dist/. С --image <tag> — образ nginx.
#
# Сборщику не нужно ничего: ни сети, ни прав, ни секретов. Так и запускаем.
set -euo pipefail

IMAGE="ghcr.io/fmstm/heron:{version}"
cd "$(dirname "$0")"

if [ "${{1:-}}" = "--image" ]; then
  tag="${{2:?укажите тег: ./build.sh --image мой-сайт:1.0}}"
  docker build -t "$tag" .
  echo "готов образ $tag"
  exit 0
fi

docker run --rm \
  --network=none \
  --read-only --tmpfs /tmp \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/site" \
  "$IMAGE" build --strict

echo "готово: dist/"
