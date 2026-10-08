#!/usr/bin/env bash
#
# Дымовая проверка поднятого сайта: коды ответа по картам, которые собрал
# движок. Одна на всех: её зовут scripts/site.sh smoke и переиспользуемый
# workflow сборки образа сайта (.github/workflows/site-image.yml).
#
#   scripts/smoke-site.sh <адрес> <папка сборки>
#   scripts/smoke-site.sh http://localhost:18080 out/мойсайт-prod
#
# Проверяет: корень и robots.txt — 200, несуществующее — 404 (и на языке),
# служебный конфиг — 404, каждый адрес redirects.map — 301 туда, куда
# объявлено, каждый точный адрес gone.map — 410.

set -uo pipefail

BASE="${1:?нужно: smoke-site.sh <адрес> <папка сборки>}"
BASE="${BASE%/}"
OUT="${2:?нужно: smoke-site.sh <адрес> <папка сборки>}"
failed=0

ok() { printf '\033[32m%s\033[0m\n' "$*"; }

main() {
  check_code() {
    local path="$1" want="$2" got
    got="$(curl -s -o /dev/null -w '%{http_code}' "$BASE${path}")"
    if [ "$got" = "$want" ]; then
      ok "  $path → $got"
    else
      printf '\033[31m%s\033[0m\n' "  $path → $got, ждали $want" >&2
      failed=1
    fi
  }

  check_code "/" 200
  check_code "/robots.txt" 200
  check_code "/heron-smoke-нет-такой-страницы/" 404
  # язык из сборки: первая папка с index.html внутри
  local lang
  lang="$(find "$OUT" -mindepth 2 -maxdepth 2 -name index.html -print -quit 2>/dev/null)"
  if [ -n "$lang" ]; then
    lang="$(basename "$(dirname "$lang")")"
    check_code "/${lang}/" 200
    check_code "/${lang}/heron-smoke-нет-такой/" 404
  fi
  # служебное наружу не отдаём
  check_code "/.heron-nginx.conf" 404

  # Каждый старый адрес из карты редиректов: 301 туда, куда объявлено, и
  # цель отвечает 200. Это единственное, что защищает индекс при переезде.
  # Кириллицу curl сам не кодирует — кодируем питоном, если он есть.
  enc() {
    if command -v python3 >/dev/null 2>&1; then
      python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1], safe="/%?=&"))' "$1"
    else
      printf '%s' "$1"
    fi
  }
  if [ -s "$OUT/redirects.map" ]; then
    local line old new got location count=0
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      # «старый  новый;» — в старом адресе бывают пробелы, новый их не имеет
      new="${line##* }"; new="${new%;}"
      old="${line% *}"; old="${old%"${old##*[! ]}"}"
      got="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE$(enc "$old")")"
      location="${got#* }"; got="${got%% *}"
      if [ "$got" = 301 ] && [ "${location#$BASE}" = "$(enc "$new")" -o "${location#$BASE}" = "$new" ]; then
        count=$((count + 1))
      else
        printf '\033[31m%s\033[0m\n' "  $old → $got $location, ждали 301 на $new" >&2
        failed=1
      fi
    done < "$OUT/redirects.map"
    ok "  301: $count адресов из redirects.map"
  fi
  # точные адреса из gone.map — 410; префиксы и параметры проверяет тест движка
  if [ -s "$OUT/gone.map" ]; then
    local gone count=0
    while IFS= read -r line; do
      gone="${line% *}"; gone="${gone%"${gone##*[! ]}"}"
      case "$gone" in *'*'*|*'?'*|'') continue ;; esac
      got="$(curl -s -o /dev/null -w '%{http_code}' "$BASE$(enc "$gone")")"
      if [ "$got" = 410 ]; then count=$((count + 1)); else
        printf '\033[31m%s\033[0m\n' "  $gone → $got, ждали 410" >&2
        failed=1
      fi
    done < "$OUT/gone.map"
    ok "  410: $count точных адресов из gone.map"
  fi


}

main
[ "$failed" = 0 ] || { printf '\033[31m%s\033[0m\n' "дымовая проверка не прошла" >&2; exit 1; }
ok "сайт отвечает как надо"
