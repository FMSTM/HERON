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
COPY pyproject.toml README.md ./
COPY heron ./heron
RUN python -m pip install --no-cache-dir --target /install .

FROM python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/heron \
    PATH=/opt/heron/bin:$PATH \
    HOME=/tmp

COPY --from=build /install /opt/heron

# Непривилегированный пользователь. Флаг --user при запуске всё равно важнее:
# образ не должен зависеть от конкретного uid и конкретного $HOME.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin heron
USER 10001

WORKDIR /site
ENTRYPOINT ["heron"]
