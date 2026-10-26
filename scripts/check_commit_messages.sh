#!/usr/bin/env bash
#
# Сообщения коммитов ветки, которых ещё нет в prod, — о правке, а не об
# инструменте (docs/ru/spec/23-distribution.md §9, AGENTS.md).
#
#   bash scripts/check_commit_messages.sh     # из корня репозитория
#
# Нарушение — строка атрибуции помощника или название компании-разработчика:
#   co-authored-by:                  (любой регистр, любое имя)
#   anthropic, openai                с начала слова (noreply@anthropic.com — да,
#                                    philanthropic — нет)
#   generated with|by … <помощник>   claude, chatgpt, copilot, codex, gemini
#                                    отдельным словом («Generated with Claude Code»,
#                                    «Generated with GitHub Copilot.», «generated
#                                    by claude.ai»); cursor — только «Cursor AI»
#                                    и «Cursor IDE» («cursor-based» — не подпись)
# Имена файлов CLAUDE.md, GEMINI.md нарушением не считаются: после имени
# помощника допустима любая точка, кроме «.md». Отдельное «Claude» без
# «generated with|by» — тоже не нарушение.
#
# База: origin/prod, если есть, иначе prod. Нет ни той ни другой или нет
# истории git (архив, копия без .git) — проверка пропускается с пометкой.
# Код выхода: 0 — чисто или пропуск, 1 — есть нарушения.

set -euo pipefail

note() { printf '\033[36m%s\033[0m\n' "$*"; }
bad()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }

# Классы с обоими регистрами: grep -i в BSD (macOS) и GNU одинаково.
WORD_START='(^|[^a-zA-Z0-9])'
TOOL='(claude|chatgpt|copilot|codex|gemini|cursor (ai|ide))'
NOT_MD='([^.a-zA-Z0-9]|\.([^mM]|$)|\.[mM]([^dD]|$)|$)'
PATTERN="co-authored-by:|${WORD_START}(anthropic|openai)|generated (with|by) (.*[^a-zA-Z0-9])?${TOOL}${NOT_MD}"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  note "сообщения коммитов: истории git нет — пропуск"
  exit 0
fi

base=""
for ref in origin/prod prod; do
  if git rev-parse --verify -q "$ref^{commit}" >/dev/null; then
    base=$ref
    break
  fi
done
if [ -z "$base" ]; then
  note "сообщения коммитов: нет ни origin/prod, ни prod — пропуск"
  exit 0
fi
if ! git rev-parse --verify -q "HEAD^{commit}" >/dev/null; then
  note "сообщения коммитов: в ветке нет коммитов — пропуск"
  exit 0
fi

found=0
checked=0
while read -r sha; do
  checked=$((checked + 1))
  lines=$(git log -1 --format=%B "$sha" | grep -Ein -e "$PATTERN" || true)
  if [ -n "$lines" ]; then
    found=$((found + 1))
    bad "коммит $(git rev-parse --short "$sha") «$(git log -1 --format=%s "$sha")»:"
    while IFS= read -r line; do
      bad "    строка ${line%%:*}: ${line#*:}"
    done <<< "$lines"
  fi
done < <(git rev-list "$base..HEAD")

if [ "$found" -gt 0 ]; then
  bad "сообщения коммитов: $found из $checked после $base с атрибуцией помощника или названием компании."
  bad "Сообщение — о правке, не об инструменте (spec/23 §9). Поправить до слияния: git rebase -i $base, reword."
  exit 1
fi
note "сообщения коммитов: $checked после $base — чисто"
