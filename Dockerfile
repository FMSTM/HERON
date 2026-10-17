# HERON — образ движка. Единственный артефакт поставки.
# Требования к нему — docs/spec/23-distribution.md, раздел 9:
#   не от рута, работает с произвольным uid, без сборочных инструментов в финальном слое,
#   базовый образ прибит по digest, ENTRYPOINT — сам движок.

# python:3.12-slim-bookworm, снят 2026-09-14. Обновляется осознанно, отдельным коммитом.
FROM python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src
# Зависимости — ровно те, что в uv.lock, с проверкой хешей: `pip install .`
# брал бы свежие версии на день сборки, и два образа одного коммита
# различались бы содержимым. Файлы выгружает scripts/lock.sh, их
# совпадение с uv.lock проверяет scripts/check.sh.
COPY requirements.lock requirements-build.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps \
      --target /install -r requirements.lock \
 && python -m pip install --no-cache-dir --require-hashes -r requirements-build.lock
COPY pyproject.toml README.md AGENTS.md ./
COPY heron ./heron
# текст документации для `heron docs`; картинки бренда в образ не идут
COPY docs/architecture.md ./docs/architecture.md
COPY docs/agents ./docs/agents
COPY docs/guide ./docs/guide
COPY docs/spec ./docs/spec
# Сам движок — без зависимостей (они уже стоят) и без изоляции сборки:
# бэкенд сборки тоже прибит хешами. --upgrade — чтобы bin/heron лёг рядом
# с bin/ зависимостей, а не был молча пропущен.
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation --upgrade \
      --target /install .

FROM python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/heron \
    PATH=/opt/heron/bin:$PATH \
    HOME=/tmp \
    HERON_IN_CONTAINER=1

COPY --from=build /install /opt/heron

# Гит нужен ровно для одного: узнать дату последнего изменения файла
# (`build.updated_from: git`). Без него движок соберёт сайт, но даты
# возьмёт из времени файлов, а оно врёт после любого копирования.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь. Флаг --user при запуске всё равно важнее:
# образ не должен зависеть от конкретного uid и конкретного $HOME.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin heron
USER 10001

# Что за сборка: `heron --version` → 0.1.0 (beta, 55249f0, 2026-10-05 19:12 UTC).
# Номер версии один на всю ветку, без этого вчерашнюю бету от сегодняшней
# не отличить. Значения передаёт CI; аргументы стоят в самом конце, чтобы
# не сбивать кэш слоёв выше.
# SOURCE_DATE_EPOCH (время коммита) BuildKit берёт для времён в слоях.
ARG SOURCE_DATE_EPOCH
ARG HERON_CHANNEL=""
ARG HERON_REVISION=""
ARG HERON_BUILT=""
ENV HERON_CHANNEL=$HERON_CHANNEL \
    HERON_REVISION=$HERON_REVISION \
    HERON_BUILT=$HERON_BUILT

WORKDIR /site
ENTRYPOINT ["heron"]
