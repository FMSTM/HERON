#!/usr/bin/env bash
#
# Единая точка входа для сборки сайтов.
#
#   ./scripts/site.sh <сайт> <команда> [окружение]
#
#   new     создать папку сайта по указанному пути и завести его окружения
#   init    достроить папку сайта под то, что написано в его site.yaml
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
команды: new <путь> | init | build | image | serve | stop | push | check"

do_new() {
  local target="${3:-}"
  [ -n "$target" ] || die "нужно: ./scripts/site.sh $SITE new <путь к папке сайта>"
  target="${target/#\~/$HOME}"
  [ -e "$target" ] && [ -n "$(ls -A "$target" 2>/dev/null)" ] \
    && die "папка $target не пуста — для готового контента есть команда init"

  local parent base
  parent="$(cd "$(dirname "$target")" && pwd)" || die "нет папки $(dirname "$target")"
  base="$(basename "$target")"

  local engine="$STABLE"
  if is_source_checkout; then
    engine="heron:local"
    note "движок из исходников: $HERON_ROOT"
    docker build -q -t "$engine" "$HERON_ROOT" >/dev/null || die "не собрался образ движка"
  fi
  note "создаю папку сайта $parent/$base"
  docker run --rm --network=none --cap-drop=ALL --security-opt=no-new-privileges \
    --user "$(id -u):$(id -g)" --tmpfs /tmp \
    -v "$parent":/work -w /work \
    "$engine" new "$base"

  local written=0
  for name in dev prod; do
    local file="env/.env.${SITE}.${name}"
    if [ -e "$file" ]; then note "уже есть $file — не трогаю"; continue; fi
    sed -e "s|^SITE_PATH=.*|SITE_PATH=$parent/$base|" \
        -e "s|^SITE_ENV=.*|SITE_ENV=$name|" \
        -e "s|^IMAGE_NAME=.*|IMAGE_NAME=heron-site-$SITE|" \
        -e "s|^IMAGE_TAG=.*|IMAGE_TAG=$name|" \
        env/.env.example > "$file"
    [ "$name" = prod ] && sed -i.bak -e "s|^STRICT=.*|STRICT=true|" "$file" && rm -f "$file.bak"
    written=1
  done
  [ "$written" = 1 ] && ok "заведены env/.env.${SITE}.dev и env/.env.${SITE}.prod"

  cat <<TXT

дальше:
  1. заполните $parent/$base/site.yaml — домен, языки, тема, меню
  2. ./scripts/site.sh $SITE init
  3. разложите контент и: ./scripts/site.sh $SITE build dev
TXT
}

if [ "$CMD" = "new" ]; then
  command -v docker >/dev/null || die "нужен docker"
  do_new "$@"
  exit 0
fi

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

SITE_ENV="${SITE_ENV:-$ENV_NAME}"
IMAGE_NAME="${IMAGE_NAME:-heron-site-$SITE}"
IMAGE_TAG="${IMAGE_TAG:-$ENV_NAME}"
PORT="${PORT:-8080}"
OUT="$HERON_ROOT/out/${SITE}-${ENV_NAME}"
CONTAINER="heron-serve-${SITE}-${ENV_NAME}"

command -v docker >/dev/null || die "нужен docker"

# Каким движком собирать.
#
# Одна настройка, и она принимает ровно две вещи:
#
#   ENGINE=source                       собрать из исходников рядом с этим
#                                       скриптом. Для тех, кто правит движок.
#   ENGINE=ghcr.io/fmstm/heron:prod     готовый образ. Пишется полным именем,
#                                       чтобы было видно: это образ, а не ветка.
#
# Короткие слова dev и prod тут не принимаются намеренно: человек читает их
# как ветки репозитория, и это недоразумение стоит дороже экономии букв.
#
# Не задано — по порядку: точная версия из site.yaml сайта; иначе исходники,
# если они лежат рядом; иначе стабильный ghcr.io/fmstm/heron:prod.
STABLE="ghcr.io/fmstm/heron:prod"

is_source_checkout() {
  [ -f "$HERON_ROOT/Dockerfile" ] && [ -d "$HERON_ROOT/heron" ] && [ -f "$HERON_ROOT/pyproject.toml" ]
}

# Точная версия, объявленная сайтом. Диапазон версией не считаем.
site_engine_version() {
  local spec
  spec="$(sed -n 's/^heron:[[:space:]]*["'"'"']\{0,1\}\([^"'"'"']*\)["'"'"']\{0,1\}[[:space:]]*$/\1/p' \
          "$SITE_PATH/site.yaml" 2>/dev/null | head -1 | tr -d ' ')"
  printf '%s' "$spec" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' && printf '%s' "$spec"
}

engine_is_source() { [ "$(engine_choice)" = "source" ]; }

engine_choice() {
  if [ -n "${ENGINE:-}" ]; then
    case "$ENGINE" in
      source) echo "source" ;;
      */*|*:*) echo "$ENGINE" ;;
      *) die "ENGINE=$ENGINE непонятно. Ожидается либо source — собрать из
исходников рядом, либо полное имя образа, например $STABLE" ;;
    esac
    return
  fi
  local pinned; pinned="$(site_engine_version)"
  if [ -n "$pinned" ]; then echo "ghcr.io/fmstm/heron:$pinned"; return; fi
  if is_source_checkout; then echo "source"; return; fi
  echo "$STABLE"
}

engine_image() {
  if engine_is_source; then echo "heron:local"; else engine_choice; fi
}

# Приготовить движок: собрать из исходников или стянуть опубликованный.
#
# Теги dev, stage и prod подвижные: за одним и тем же именем завтра стоит
# другой образ. docker run этого не знает и молча берёт локальную копию,
# поэтому свежий движок надо стянуть явно. Точная версия не двигается
# никогда — её тянем только если её ещё нет. Чистить докер руками не нужно
# ни в одном из случаев: и сборка, и докачка идут по слоям, меняется только
# то, что изменилось.
pull_engine() {
  local image; image="$(engine_image)"

  if engine_is_source; then
    note "движок из исходников: $HERON_ROOT"
    docker build -q -t "$image" "$HERON_ROOT" >/dev/null || die "не собрался образ движка"
    local ver
    ver="$(docker run --rm --entrypoint heron "$image" --version 2>/dev/null | tr -d '\r')"
    ok "движок: $image ${ver:+($ver)}"
    return
  fi

  case "$image" in
    *:dev|*:stage|*:prod|*:latest)
      note "проверяю движок $image"
      docker pull -q "$image" >/dev/null || die "не удалось стянуть $image"
      ;;
    *)
      docker image inspect "$image" >/dev/null 2>&1 || docker pull -q "$image" >/dev/null \
        || die "не удалось стянуть $image"
      ;;
  esac
  local built
  built="$(docker image inspect --format '{{.Created}}' "$image" 2>/dev/null | cut -c1-19 | tr T ' ')"
  ok "движок: $image (собран $built)"
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
    -e SITE_ENV="$SITE_ENV" \
    ${SITE_INDEXABLE:+-e SITE_INDEXABLE="$SITE_INDEXABLE"} \
    ${SITE_ANALYTICS:+-e SITE_ANALYTICS="$SITE_ANALYTICS"} \
    -v "$SITE_PATH":/site:ro \
    -v "$HERON_ROOT/out":/out \
    "$(engine_image)" "$@"
}

strict_flag() {
  case "${STRICT:-false}" in true|1|yes|on) echo "--strict" ;; *) echo "" ;; esac
}

do_build() {
  pull_engine
  note "сборка $SITE [$ENV_NAME]"
  note "контент: $SITE_PATH (только чтение)"
  rm -rf "$OUT"
  # shellcheck disable=SC2046
  run_engine build --env "$SITE_ENV" $(strict_flag) --out "/out/${SITE}-${ENV_NAME}" /site
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
  pull_engine
  run_engine check /site
}

do_init() {
  pull_engine
  note "достраиваю $SITE_PATH по его site.yaml"
  # Единственная команда, которой папка сайта нужна на запись:
  # она в эту папку и кладёт недостающее.
  docker run --rm --network=none --cap-drop=ALL --security-opt=no-new-privileges \
    --user "$(id -u):$(id -g)" --tmpfs /tmp \
    -v "$SITE_PATH":/site -w /site \
    "$(engine_image)" init /site
  ok "готово"
}

case "$CMD" in
  init)  do_init  ;;
  build) do_build ;;
  image) do_image ;;
  serve) do_serve ;;
  stop)  do_stop  ;;
  push)  do_push  ;;
  check) do_check ;;
  *) die "не знаю команду $CMD. Есть: new, init, build, image, serve, stop, push, check" ;;
esac
