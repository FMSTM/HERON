# HERON для агентов · HERON for agents

**RU.** Это репозиторий движка статических сайтов HERON. Инструкция для агента, который делает **сайт** на HERON, — [`docs/ru/README.md`](https://github.com/FMSTM/HERON/blob/prod/docs/ru/README.md): роли (архитектор, контент и SEO, дизайнер, сборщик), общие правила, границы полномочий, критерии «готово», карта документации. Та же папка лежит в каждом сайте как `agents/` и в образе движка:

```bash
docker run --rm ghcr.io/fmstm/heron:prod docs --lang ru        # оглавление
docker run --rm ghcr.io/fmstm/heron:prod docs --lang ru kit    # инструкция для агента
```

**EN.** This is the repository of HERON, a static site engine. The instruction for an agent that builds a **site** on HERON is [`docs/en/README.md`](https://github.com/FMSTM/HERON/blob/prod/docs/en/README.md): roles (architect, content and SEO, designer, builder), common rules, what the agent may decide alone, done criteria, a map of the documentation. The same folder sits in every site as `agents/` and inside the engine image:

```bash
docker run --rm ghcr.io/fmstm/heron:prod docs --lang en        # table of contents
docker run --rm ghcr.io/fmstm/heron:prod docs --lang en kit    # the instruction for agents
```

| Что нужно · What you need | Где · Where |
|---|---|
| роли, правила, границы, «готово» · roles, rules, limits, done | `docs/<lang>/README.md`, `docs/<lang>/roles/` |
| образцы · samples | `docs/<lang>/templates/` — `structure.md`, `site.yaml`, `theme.yaml`, `page.md`, `report.md`, `questions.md` |
| гайды · guides | `docs/<lang>/guide/01–06` |
| контракт, движок, развёртывание, поставка · spec | `docs/<lang>/spec/20–23` |
| машиночитаемые схемы · JSON Schema | `heron schema --export <папка>` |
| навыки · skills | [`skills/`](https://github.com/FMSTM/HERON/tree/prod/skills) — `npx skills add FMSTM/HERON` |

## Если меняешь сам движок · If you change the engine itself

Это репозиторий движка, а не сайта. Правила для того, кто правит код и документацию здесь:

- `uv sync --group dev`, `./scripts/check.sh` перед каждым коммитом: граница ядра, формат, линтер, тесты, состояние перевода, сообщения коммитов.
- **Документация меняется в том же коммите, что и поведение.** Источник — `docs/ru/`; английский перевод (`docs/en/`) обновляется после того, как русский текст прошёл тесты, и отмечается в `docs/translation.yaml` (`spec/23` §10). Тест паритета следит, чтобы деревья совпадали файл в файл.
- Никаких имён сайтов, доменов, слагов и предметной лексики в коде, тестах и доках — проверяет `scripts/check-boundaries.sh`.
- Тексты документации агент-нейтральны: «агент», не имя конкретного инструмента; имена инструментов — только в перечне «какой файл кто читает».
- **Сообщение коммита — о правке, не об инструменте.** Строк атрибуции помощников (`Co-Authored-By` на имя нейросети, «generated with …») и названий их разработчиков в сообщениях нет; `scripts/check.sh` это проверяет.
- Публикация образов, теги и push в `beta`/`prod` — только человек.
