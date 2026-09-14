# Сборка сайта и упаковка в nginx. Движок приходит образом, в репозитории
# сайта его кода нет.
FROM ghcr.io/fmstm/heron:{version} AS build
COPY . /site
RUN heron build --strict

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /site/dist /usr/share/nginx/html
