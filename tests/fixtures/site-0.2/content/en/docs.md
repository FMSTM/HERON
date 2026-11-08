---
# ================= 1. ОСНОВНОЕ =================
title: "Documentation - the main HERON commands"
# ↑ <title> в выдаче, до 60 знаков. Суффикс сайта (seo.title_suffix) добавит тема
h1: "Documentation"
# ↑ заголовок на странице - для того, кто её уже открыл; не копия title
description: "The main HERON commands: create, set up, look, check, build."
# ↑ meta description, до 155 знаков: что человек получит на странице
nav_title: "Documentation"
# ↑ короткое имя в меню и хлебных крошках
# slug:                      # адрес, если должен отличаться от имени файла. Ключ - имя файла
# canonical:                 # не заполнять: движок ставит канонический адрес сам
# robots:                    # не заполнять: индексацию решает noindex

# ================= 2. КЛЮЧЕВЫЕ ЗАПРОСЫ =================
# основной:
# дополнительные:
# всего: 0
# Движок эту группу не читает. Один интент - одна страница

# ================= 3. OPEN GRAPH =================
# og_title:                  # пусто - берётся title
# og_description:            # пусто - берётся description
# og_image:                  # пусто - seo.og_default_image из site.yaml
# og_image_alt:
# ↑ обложка страницы: og_image, затем image, затем первая картинка текста, затем картинка героя, затем seo.og_default_image. Делайте обложку непрозрачной, от 1200 px по ширине

# ================= 4. TWITTER / X =================
# twitter_title:             # пусто - из Open Graph
# twitter_description:
# twitter_image:

# ================= 5. SCHEMA.ORG =================
# schema:                    # уточнения разметки этой страницы, поверх site.yaml

# ================= 6. КАРТОЧКА И КАТАЛОГ =================
# image:                     # превью в каталоге: путь в media/
# image_alt:                 # обязательно, если задан image
# children_type:             # только в _index.md: тип дочерних страниц
order: 30
# ↑ порядок в каталоге раздела и в связях, по возрастанию. Порядок меню - в nav.main файла site.yaml
# type:                      # тип, если не задан папкой (children_type)

# ================= 7. СЛУЖЕБНОЕ =================
# date:                      # дата публикации, ГГГГ-ММ-ДД
# updated:                   # дата правки; без неё - build.updated_from из site.yaml
published: true
# ↑ false - страница не собирается
# noindex: true              # закрыть от поисковиков и убрать из sitemap

# ================= 8. СВЯЗИ =================
# redirect_from:             # старые адреса, с которых нужен 301 сюда
#   - /old-address/
# адреса, которых больше нет (410) - ключ gone в site.yaml, не здесь
---

The main HERON commands and where to read more. The documentation lives in the engine repository and in the image itself, the same version your site is built with.

## How to run the commands {#run}

Every command below starts with `heron` - this is how they look when the engine is installed without Docker. With Docker, write the full command instead of `heron`, for example:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD":/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod serve .
```

## The main commands {#commands}

1. **Create a site.** Asks a few questions and creates the site folder:

   ```bash
   heron new my-site
   ```

2. **Set it up.** The configurator in the browser - open the address the engine prints, with the key after `#`: name, domains, who the site is about, publishing, theme. Run it from the site folder:

   ```bash
   cd my-site && heron setup .
   ```

3. **Look.** The site at `localhost:8000` rebuilds on every save:

   ```bash
   heron serve .
   ```

4. **Check.** What to fill in and what to fix, without a build:

   ```bash
   heron check .
   ```

5. **Build for checking.** The dev version: closed to search engines, no counters:

   ```bash
   heron build . --env dev
   ```

6. **Build the working version.** The prod version: open to search engines, warnings count as errors. The result is the `dist/` folder:

   ```bash
   heron build . --env prod --strict
   ```

Instructions for an AI agent sit in the site root: the `AGENTS.md` file and the `agents/` folder.

## Where to read {#where}

- **In the repository.** [The guides in order](https://github.com/FMSTM/HERON/tree/prod/docs/en/guide): concepts, first site, pages, theme, search, publishing.
- **For AI agents.** [AGENTS.md](https://github.com/FMSTM/HERON/blob/prod/AGENTS.md): roles, rules and the map of the documentation.
- **In the terminal.** Offline, the same version as the engine:

  ```bash
  heron docs
  ```
