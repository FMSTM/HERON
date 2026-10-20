"""Файлы, которые конфигуратор кладёт рядом с `site.yaml`.

Выбор способа публикации решает, что появится в папке сайта:

| способ    | файлы                                                             |
|-----------|-------------------------------------------------------------------|
| всегда    | `scripts/build.sh` — итоговая сборка одной командой                |
| GitHub    | `scripts/publish.sh`, `.gitignore`; с автосборкой — `.github/workflows/image.yml` |
| Docker Hub| `scripts/publish.sh`                                               |
| статика   | `scripts/publish.sh` (на сервер) или `.github/workflows/pages.yml`  |

Длинная часть сборки живёт в HERON: workflow сайта зовёт общий
`site-image.yml` той же ветки, что и движок, а рецепт образа nginx скрипт
берёт у самого движка (`heron recipe`). В папке сайта нет ни Dockerfile, ни
копий логики — обновил HERON, и сборка сайта обновилась вместе с ним.

Ключей в этих файлах нет: Docker Hub берёт вход из `docker login` на
компьютере, workflow — короткоживущий токен, который GitHub выдаёт сборке.
"""

from __future__ import annotations

from dataclasses import dataclass

from heron.setup.answers import Answers

IMAGE = "ghcr.io/fmstm/heron"
REPO = "FMSTM/HERON"

# Строки .gitignore, без которых в git уезжает мусор или ключ.
IGNORE = ("dist/", ".heron-cache/", ".heron-docs/", ".env", "*.env", ".DS_Store")


@dataclass(frozen=True, slots=True)
class Generated:
    rel: str
    text: str
    executable: bool = False


T = {
    "ru": {
        "image_head": (
            "# Образ сайта на каждый push в {branch}: сборка движком HERON, nginx,\n"
            "# дымовая проверка, отправка в ghcr.io/<владелец>/<репозиторий>:<окружение>.\n"
            "# Длинная часть живёт в HERON и обновляется вместе с ним. Записал heron setup.\n"
        ),
        "image_env": "# dev — закрыт от поисковиков; prod — когда домен готов",
        "image_engine": "# канал движка; закрепить версию: prod@sha256:<digest>",
        "pages_head": (
            "# Сайт на GitHub Pages на каждый push в {branch}: сборка движком HERON\n"
            "# и публикация папки dist/. Записал heron setup.\n"
        ),
        "build_head": (
            "# Итоговая сборка сайта одной командой: открыт поисковикам, предупреждения —\n"
            "# ошибки. Результат — папка dist/. Окружение: ./scripts/build.sh dev\n"
            "# Записал heron setup; движок — {engine}.\n"
        ),
        "publish_git": "# Публикация: отправить изменения в git — образ соберёт GitHub.",
        "publish_hub": "# Публикация: собрать сайт, упаковать в образ, отправить в Docker Hub.",
        "publish_static": "# Публикация: собрать сайт и выложить папку dist/ на сервер.",
        "publish_pages": "# Публикация: отправить изменения в git — GitHub Pages соберёт сам.",
        "written": "# Записал heron setup: перезапуск конфигуратора перепишет файл.",
        "dirty": "есть несохранённые изменения: сначала git add и git commit",
        "hub_login": "вход в Docker Hub — один раз на компьютере: docker login",
        "publish_push": "# Публикация: отправить изменения в git. Автосборки на GitHub нет.",
    },
    "en": {
        "image_head": (
            "# Image of the site on every push to {branch}: HERON build, nginx,\n"
            "# smoke check, push to ghcr.io/<owner>/<repository>:<environment>.\n"
            "# The long part lives in HERON and updates with it. Written by heron setup.\n"
        ),
        "image_env": "# dev is closed to search engines; prod when the domain is ready",
        "image_engine": "# engine channel; pin the version: prod@sha256:<digest>",
        "pages_head": (
            "# The site on GitHub Pages on every push to {branch}: HERON build\n"
            "# and publishing of dist/. Written by heron setup.\n"
        ),
        "build_head": (
            "# Final build of the site in one command: open to search engines, warnings\n"
            "# are errors. The result is dist/. Another environment: ./scripts/build.sh dev\n"
            "# Written by heron setup; engine {engine}.\n"
        ),
        "publish_git": "# Publish: send the changes to git, GitHub builds the image.",
        "publish_hub": "# Publish: build the site, pack it into an image, push to Docker Hub.",
        "publish_static": "# Publish: build the site and upload dist/ to the server.",
        "publish_pages": "# Publish: send the changes to git, GitHub Pages builds by itself.",
        "written": "# Written by heron setup: running the configurator again rewrites it.",
        "dirty": "there are unsaved changes: git add and git commit first",
        "hub_login": "Docker Hub sign-in, once per computer: docker login",
        "publish_push": "# Publish: send the changes to git. No automatic build on GitHub.",
    },
}


def engine_ref(engine: str) -> str:
    """Ветка или тег HERON с рецептом той же версии, что движок."""
    channel = engine.split("@", 1)[0]
    return channel if channel in ("prod", "beta", "dev") else f"v{channel}"


def engine_image(engine: str) -> str:
    return f"{IMAGE}:{engine}"


def _engine_run(engine: str) -> str:
    return (
        'docker run --rm -v "$PWD":/site -w /site --user "$(id -u):$(id -g)" '
        f'"${{HERON_IMAGE:-{engine_image(engine)}}}"'
    )


def build_sh(answers: Answers, lang: str) -> Generated:
    t = T[lang]
    engine = answers.publish.engine
    text = (
        "#!/usr/bin/env bash\n"
        + t["build_head"].format(engine=engine_image(engine))
        + "set -euo pipefail\n"
        + 'cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
        + 'env="${1:-prod}"\n'
        + 'strict=""\n'
        + '[ "$env" = prod ] && strict="--strict"\n'
        + _engine_run(engine)
        + ' build . --env "$env" $strict\n'
    )
    return Generated("scripts/build.sh", text, executable=True)


def publish_sh(answers: Answers, lang: str, ident: str) -> Generated | None:
    t = T[lang]
    p = answers.publish
    if p.way == "none":
        return None
    head = "#!/usr/bin/env bash\n" + t["written"] + "\n"
    body = "set -euo pipefail\n" + 'cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
    if p.way == "github" or (p.way == "static" and p.static_target == "pages"):
        note = t["publish_git"] if p.way == "github" and p.auto else t["publish_pages"]
        if p.way == "github" and not p.auto:
            note = t["publish_push"]
        body += (
            f'if [ -n "$(git status --porcelain)" ]; then echo "{t["dirty"]}" >&2; exit 1; fi\n'
            f"git push origin {p.branch or 'main'}\n"
        )
        return Generated("scripts/publish.sh", head + note + "\n" + body, executable=True)
    if p.way == "dockerhub":
        image = f"{p.dockerhub_user}/{p.image}"
        body += (
            f'env="${{1:-{p.env}}}"\n'
            + './scripts/build.sh "$env"\n'
            + 'recipe="$(mktemp)"\n'
            + "trap 'rm -f \"$recipe\"' EXIT\n"
            + _engine_run(p.engine)
            + ' recipe > "$recipe"\n'
            + f'docker build -f "$recipe" -t "{image}:$env" dist\n'
            + f"# {t['hub_login']}\n"
            + f'docker push "{image}:$env"\n'
        )
        return Generated("scripts/publish.sh", head + t["publish_hub"] + "\n" + body, True)
    target = f"{p.server}:{(p.path or '/var/www').rstrip('/')}/"
    body += (
        f'env="${{1:-{p.env}}}"\n'
        './scripts/build.sh "$env"\n'
        f'rsync -az --delete --exclude .heron-nginx.conf dist/ "{target}"\n'
    )
    return Generated("scripts/publish.sh", head + t["publish_static"] + "\n" + body, True)


def image_yml(answers: Answers, lang: str) -> Generated:
    t = T[lang]
    p = answers.publish
    branch = p.branch or "main"
    text = (
        t["image_head"].format(branch=branch)
        + "name: image\n"
        + "on:\n"
        + "  push:\n"
        + f"    branches: [{branch}]\n"
        + "  workflow_dispatch:\n\n"
        + "jobs:\n"
        + "  image:\n"
        + f"    uses: {REPO}/.github/workflows/site-image.yml@{engine_ref(p.engine)}\n"
        + "    permissions:\n"
        + "      contents: read\n"
        + "      packages: write\n"
        + "    with:\n"
        + f"      env: {p.env}          {t['image_env']}\n"
        + f"      engine: {p.engine}       {t['image_engine']}\n"
    )
    return Generated(".github/workflows/image.yml", text)


def pages_yml(answers: Answers, lang: str) -> Generated:
    t = T[lang]
    p = answers.publish
    branch = p.branch or "main"
    image = engine_image(p.engine)
    text = (
        t["pages_head"].format(branch=branch)
        + "name: pages\n"
        + "on:\n"
        + "  push:\n"
        + f"    branches: [{branch}]\n"
        + "  workflow_dispatch:\n\n"
        + "permissions:\n"
        + "  contents: read\n"
        + "  pages: write\n"
        + "  id-token: write\n\n"
        + "jobs:\n"
        + "  pages:\n"
        + "    runs-on: ubuntu-26.04\n"
        + "    environment:\n"
        + "      name: github-pages\n"
        + "    steps:\n"
        + "      - uses: actions/checkout@v7\n"
        + "        with:\n"
        + "          fetch-depth: 0\n"
        + "      - name: build\n"
        + "        run: |\n"
        + '          docker run --rm --network=none -v "$PWD":/site -w /site \\\n'
        + '            --user "$(id -u):$(id -g)" '
        + f"{image} build . --env {p.env}"
        + (" --strict" if p.env == "prod" else "")
        + "\n"
        + "      - uses: actions/upload-pages-artifact@v4\n"
        + "        with:\n"
        + "          path: dist\n"
        + "      - uses: actions/deploy-pages@v5\n"
    )
    return Generated(".github/workflows/pages.yml", text)


def gitignore(current: str) -> str | None:
    """Дописать недостающие строки. Всего хватает — None."""
    have = {line.strip() for line in current.splitlines()}
    missing = [line for line in IGNORE if line not in have]
    if not missing:
        return None
    tail = "" if not current or current.endswith("\n") else "\n"
    return current + tail + "\n".join(missing) + "\n"


def plan(answers: Answers, lang: str, ident: str = "") -> list[Generated]:
    """Что записать для этих ответов."""
    out = [build_sh(answers, lang)]
    p = answers.publish
    if p.way == "github" and p.auto:
        out.append(image_yml(answers, lang))
    if p.way == "static" and p.static_target == "pages":
        out.append(pages_yml(answers, lang))
    publish = publish_sh(answers, lang, ident)
    if publish:
        out.append(publish)
    return out


# Файлы, которые конфигуратор писал сам и вправе переписать или убрать, когда
# способ публикации меняется. Чужой файл с тем же именем не трогается: в нём
# нет нашей отметки.
MARK = "heron setup"
OWNED = (
    "scripts/build.sh",
    "scripts/publish.sh",
    "scripts/keys.sh",
    ".github/workflows/image.yml",
    ".github/workflows/pages.yml",
)
