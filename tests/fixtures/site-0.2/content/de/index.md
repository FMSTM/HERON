---
# ================= 1. ОСНОВНОЕ =================
title: "Старый сайт - a site on HERON"
# ↑ <title> в выдаче, до 60 знаков. Суффикс сайта (seo.title_suffix) добавит тема
h1: "Старый сайт"
# ↑ заголовок на странице - для того, кто её уже открыл; не копия title
description: "The demo site of the HERON white theme: how pages are made and what to edit."
# ↑ meta description, до 155 знаков: что человек получит на странице
nav_title: "Home"
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
order: 0
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

This is the demo site of the HERON white theme. Every page is a text file in the `content/` folder: open it in any editor, change the text and save.

Replace the texts with yours, delete the pages you do not need, add new ones as a copy of any file.

## How a page is made {#how}

1. **The file header.** Between the `---` lines is the description for search engines: `title`, `description`, `h1`. It is not shown on the page, search results show it.
2. **The intro.** The text before the first heading: one or two paragraphs under the main heading.
3. **Blocks.** Every `## Heading {#anchor}` is a block. The theme puts it in place by its anchor, and the way it is written decides what it is: a list, steps, a table, questions.

## What next {#next}

- **Page blocks.** Every kind of block the theme draws is on the page [«Blocks»](/blocks/).
- **The look.** Change the theme in the configurator or with a command - [«Themes»](/themes/).
- **Help.** The main commands and where to read the documentation - [«Documentation»](/docs/).

## Questions {#faq}

### Where do I change the site name, the domain and the contacts?

In the configurator: `heron setup .`. It writes everything to `site.yaml`, which you can also edit by hand.

### How do I look at the site?

Run `heron serve .` and open `localhost:8000` in the browser. The site rebuilds on every save.

### Light and dark?

The white theme follows the system setting, and the button in the header switches it by hand.
