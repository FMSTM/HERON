---
# ================= 1. ОСНОВНОЕ =================
title: "Themes - how to change the look"
# ↑ <title> в выдаче, до 60 знаков. Суффикс сайта (seo.title_suffix) добавит тема
h1: "Themes"
# ↑ заголовок на странице - для того, кто её уже открыл; не копия title
description: "How to change the theme of a HERON site and what comes with it."
# ↑ meta description, до 155 знаков: что человек получит на странице
nav_title: "Themes"
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
order: 20
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

The theme decides how the site looks. The page texts do not depend on it: change the theme and the pages stay, only the look changes.

## How to change the theme {#change}

1. **In the configurator.** `heron setup .`, the «Theme» group: pick a theme from the catalog, paste a link to an archive or upload your own.
2. **With a command.** By name from the catalog, by link or as an archive:

   ```bash
   heron theme list && heron theme get NAME .
   ```

3. **Check it.** `heron serve .` shows the site in the new theme at `localhost:8000`.

## What comes with a theme {#what}

- **The look.** Templates, styles and fonts, into the `theme/` folder.
- **Demo pages.** Example pages of the theme: a site structure for its topic. They go only where there is no page yet: your files are never overwritten.
- **The previous theme.** It is not deleted: it moves to `.heron-cache/setup/`.

## Your own theme {#own}

The white theme is a base for your own: change the colours at the top of `theme/assets/site.css`, place the blocks in `theme/templates/`. To pack the theme with its demo pages for another site: `heron theme pack . --out theme.tar.gz`.
