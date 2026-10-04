# HERON для агентов

Ты работаешь с HERON — файловым движком статических сайтов. Сайт — это папка: `site.yaml`, `content/`, `data/`, `media/`, `static/`, `theme/`. Движок приходит образом `ghcr.io/fmstm/heron:<тег>` или pip-пакетом и в папку сайта не копируется.

**Начни с `docs/agents/README.md`.** Там два сценария и правила, которые нельзя нарушать.

| Задача | Документ |
|---|---|
| Собрать сайт по готовой структуре контента | [`docs/agents/build-site.md`](docs/agents/build-site.md) |
| По отчёту о старом сайте спроектировать структуру контента и `site.yaml` | [`docs/agents/plan-site.md`](docs/agents/plan-site.md) |
| Что движок уже умеет — до того, как предлагать задачу на движок | [`docs/agents/capabilities.md`](docs/agents/capabilities.md) |
| Контракт папки сайта: URL, языки, markdown, `site.yaml`, `theme.yaml`, картинки | [`docs/spec/20-data-contract.md`](docs/spec/20-data-contract.md) |
| Конвейер, модель страницы, генераторы, коды ошибок | [`docs/spec/21-engine.md`](docs/spec/21-engine.md) |
| Образ сайта, nginx, 404, 301, 410 | [`docs/spec/23-distribution.md`](docs/spec/23-distribution.md) |

Если ты меняешь сам движок (этот репозиторий), а не сайт: `uv sync --group dev`, `./scripts/check.sh` перед каждым коммитом, никаких имён сайтов, доменов и слагов в коде, тестах и доках (`scripts/check-boundaries.sh`), документация меняется в том же коммите, что и поведение.
