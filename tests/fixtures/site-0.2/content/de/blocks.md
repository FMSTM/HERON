---
# ================= 1. ОСНОВНОЕ =================
title: "Page blocks - what the theme draws"
# ↑ <title> в выдаче, до 60 знаков. Суффикс сайта (seo.title_suffix) добавит тема
h1: "Page blocks"
# ↑ заголовок на странице - для того, кто её уже открыл; не копия title
description: "Every kind of HERON block on one page: list, steps, table, facts, questions, tabs and more."
# ↑ meta description, до 155 знаков: что человек получит на странице
nav_title: "Blocks"
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
order: 10
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

Every block below is a part of one text file. HERON knows what kind of block it is by how it is written: a list, steps, a table, questions. The theme draws each kind of block its own way.

Open `blocks.md` in the language folder inside `content/` next to this page: the file and the page side by side are the whole manual.

## Plain text {#text}

A block without a list, a table or a quote is plain text. **Bold**, *italic*, [links](/) and `code` work as usual.

## A list {#list}

- **Term first.** A bold start with a full stop makes a pair: the theme gets the term and the text apart.
- **Any length.** A list item can hold a sentence or a short paragraph.
- A plain item without a bold start is fine too.

## Warning signs {#warning .alert}

- The class `.alert` in the heading turns a list into a warning.
- Use it for what must not be missed.

## Steps {#steps}

1. **Create the site.** One command, and the folder is ready:

   ```bash
   heron new my-site
   ```

2. **[MOST OFTEN] Fill in the configurator.** A tag in square brackets, in capitals, marks a step.
3. **Build.** The final build opens the site to search engines.

## Two lists {#compare}

### Fits

- A site of texts and pictures
- Pages you edit in any editor

### Does not fit

- A shop with a cart
- A forum

## Checklist {#checklist}

### Before you start

- Docker
- A text editor

### To publish

- A domain
- Git

### Later

- Analytics
- A second language

## Table {#table}

| What | Where | How often |
|---|---|---|
| Texts | `content/` | Any time |
| Photos | `media/` | When needed |
| Look | `theme/` | Rarely |

## Facts {#facts}

Short facts are lines with a bar, without a table header:

Format | text files
Output | a static site
Languages | as many as you need

## Timeline {#timeline .timeline}

Day 1 | Create the site and fill in the configurator
Week 1 | Write the pages
Week 2 | Publish

## Questions {#faq}

### Is this a real page?

Yes. Every block on it is drawn by the white theme from this file.

### Can I delete it?

Delete `blocks.md` and remove `blocks` from `nav.main` in `site.yaml`.

## A quote {#quote}

> A quote becomes a callout: a short note the theme sets apart.

## Gallery {#gallery .gallery}

- ![A light square](media/demo/light.svg)
- ![A dark square](media/demo/dark.svg)

## Tabs {#tabs .tabs}

### Git {#git}

Send the changes to git, and GitHub builds the image of the site.

```bash
git push
```

### Files {#files}

Copy the `dist/` folder to any hosting.

### Image {#image}

Run the image of the site on any server with Docker.
