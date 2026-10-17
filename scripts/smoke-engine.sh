#!/usr/bin/env bash
#
# Дымовая проверка образа движка: создать временный сайт и собрать его
# строго, как прод, — тем самым образом, который потом уйдёт в реестр.
#
#   scripts/smoke-engine.sh <образ> [ожидаемый коммит]
#
# Ограничения контейнера те же, что у site.sh и у workflow образа сайта:
# без сети, корень только на чтение, без capabilities, чужой uid. Папка
# сайта монтируется на чтение; писать можно только в /out и /tmp.

set -euo pipefail

IMAGE="${1:?нужно: smoke-engine.sh <образ> [коммит]}"
REVISION="${2:-}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/site" "$WORK/out"

engine() {
  docker run --rm --network=none --read-only --tmpfs /tmp \
    --cap-drop=ALL --security-opt=no-new-privileges \
    --user "$(id -u):$(id -g)" \
    -e SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}" \
    "$@"
}

version="$(engine "$IMAGE" --version)"
echo "$version"
if [ -n "$REVISION" ]; then
  grep -q "${REVISION::7}" <<<"$version" || { echo "в образе нет коммита $REVISION" >&2; exit 1; }
fi

# new пишет в папку сайта — единственный шаг, которому она нужна на запись
engine -v "$WORK/site":/work -w /work "$IMAGE" \
  new . --notes en --name "Smoke" --domain smoke.example --lang en,ru -y

engine -v "$WORK/site":/site:ro -v "$WORK/out":/out -w /site "$IMAGE" \
  build . --env prod --strict --out /out/dist

for file in index.html ru/index.html 404.html sitemap.xml robots.txt .heron-nginx.conf; do
  [ -s "$WORK/out/dist/$file" ] || { echo "в сборке нет $file" >&2; exit 1; }
done
grep -q 'Disallow: /$' "$WORK/out/dist/robots.txt" && { echo "прод закрыт от индексации" >&2; exit 1; }
echo "образ движка создал и строго собрал сайт"
