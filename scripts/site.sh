#!/usr/bin/env bash
#
# Единая точка входа для сборки сайтов.
#
#   ./scripts/site.sh <сайт> <команда> [окружение]
#
#   build   собрать в out/<сайт>-<окружение>
#   image   упаковать собранное в образ nginx
#   serve   поднять nginx на собранной папке
#   stop    погасить просмотр
#   push    отправить образ в реестр
#   check   проверить контент, ничего не собирая
#
# Окружение по умолчанию dev. Настройки берутся из env/.env.<сайт>.<окружение>,
# пример — env/.env.example.
#
# Папка контента монтируется ТОЛЬКО НА ЧТЕНИЕ и ничем не пачкается:
# ни dist, ни кэшем. Всё, что производит сборка, живёт в out/.

set -euo pipefail

HERON_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERON_ROOT"

die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
note() { printf '\033[36m%s\033[0m\n' "$*"; }
ok()   { printf '\033[32m%s\033[0m\n' "$*"; }

SITE="${1:-}"
CMD="${2:-}"
ENV_NAME="${3:-dev}"

[ -n "$SITE" ] && [ -n "$CMD" ] || die "нужно: ./scripts/site.sh <сайт> <команда> [окружение]
команды: build | image | serve | stop | push | check"

ENV_FILE="env/.env.${SITE}.${ENV_NAME}"
[ -f "$ENV_FILE" ] || die "нет файла $ENV_FILE
скопируйте пример и заполните:  cp env/.env.example $ENV_FILE"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

[ -n "${SITE_PATH:-}" ]  || die "в $ENV_FILE не задан SITE_PATH"
[ -d "$SITE_PATH" ]      || die "папки контента нет: $SITE_PATH"
[ -f "$SITE_PATH/site.yaml" ] || die "в $SITE_PATH нет site.yaml — это не папка сайта"

HERON_ENV="${HERON_ENV:-$ENV_NAME}"
IMAGE_NAME="${IMAGE_NAME:-heron-site-$SITE}"
IMAGE_TAG="${IMAGE_TAG:-$ENV_NAME}"
PORT="${PORT:-8080}"
OUT="$HERON_ROOT/out/${SITE}-${ENV_NAME}"
CONTAINER="heron-serve-${SITE}-${ENV_NAME}"

command -v docker >/dev/null || die "нужен docker"

# Версия движка берётся из site.yaml: сайт сам знает, чем собирается.
# Точная версия — точный тег; диапазон — подвижный тег окружения.
engine_image() {
  if [ -n "${HERON_IMAGE:-}" ]; then echo "$HERON_IMAGE"; return; fi
  local spec
  spec="$(sed -n 's/^heron:[[:space:]]*["'"'"']\{0,1\}\([^"'"'"']*\)["'"'"']\{0,1\}[[:space:]]*$/\1/p' \
          "$SITE_PATH/site.yaml" | head -1 | tr -d ' ')"
  if printf '%s' "$spec" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "ghcr.io/fmstm/heron:$spec"
  else
    echo "ghcr.io/fmstm/heron:prod"
  fi
}

# Сборка идёт без сети, без прав, не от рута и не может писать никуда,
# кроме out. Сокет докера внутрь не пробрасывается никогда.
run_engine() {
  mkdir -p "$OUT"
  docker run --rm \
    --network=none \
    --read-only \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --user "$(id -u):$(id -g)" \
    --tmpfs /tmp \
    -e HERON_ENV="$HERON_ENV" \
    ${HERON_INDEXABLE:+-e HERON_INDEXABLE="$HERON_INDEXABLE"} \
    ${HERON_ANALYTICS:+-e HERON_ANALYTICS="$HERON_ANALYTICS"} \
    -v "$SITE_PATH":/site:ro \
    -v "$HERON_ROOT/out":/out \
    "$(engine_image)" "$@"
}

strict_flag() {
  case "${STRICT:-false}" in true|1|yes|on) echo "--strict" ;; *) echo "" ;; esac
}

do_build() {
  note "сборка $SITE [$ENV_NAME] движком $(engine_image)"
  note "контент: $SITE_PATH (только чтение)"
  rm -rf "$OUT"
  # shellcheck disable=SC2046
  run_engine build --env "$HERON_ENV" $(strict_flag) --out "/out/${SITE}-${ENV_NAME}" /site
  ok "готово: out/${SITE}-${ENV_NAME}"
}

do_image() {
  [ -d "$OUT" ] || do_build
  note "упаковка в $IMAGE_NAME:$IMAGE_TAG"
  docker build -f "$HERON_ROOT/Dockerfile.site" -t "$IMAGE_NAME:$IMAGE_TAG" "$OUT"
  ok "готов образ $IMAGE_NAME:$IMAGE_TAG"
}

do_serve() {
  [ -d "$OUT" ] || do_build
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker run -d --rm --name "$CONTAINER" \
    -p "${PORT}:8080" \
    -v "$OUT":/usr/share/nginx/html:ro \
    nginxinc/nginx-unprivileged:1.27-alpine >/dev/null
  ok "смотрите: http://localhost:${PORT}"
  note "погасить: ./scripts/site.sh $SITE stop $ENV_NAME"
}

do_stop() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 && ok "просмотр погашен" || note "не запущен"
}

do_push() {
  [ -n "${REGISTRY:-}" ] || die "в $ENV_FILE пусто REGISTRY — push из этого окружения запрещён.
Так дев-сборка не уедет в реестр по опечатке. Пушить нужно из prod-окружения."
  docker image inspect "$IMAGE_NAME:$IMAGE_TAG" >/dev/null 2>&1 || do_image
  local remote="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
  docker tag "$IMAGE_NAME:$IMAGE_TAG" "$remote"
  note "отправка $remote"
  docker push "$remote" || die "не отправилось. Если реестр не пускает — авторизуйтесь:
  docker login ${REGISTRY%%/*}"
  ok "отправлено: $remote"
}

do_check() {
  run_engine check /site
}

case "$CMD" in
  build) do_build ;;
  image) do_image ;;
  serve) do_serve ;;
  stop)  do_stop  ;;
  push)  do_push  ;;
  check) do_check ;;
  *) die "не знаю команду $CMD. Есть: build, image, serve, stop, push, check" ;;
esac
