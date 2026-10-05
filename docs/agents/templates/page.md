---
# ================= 1. ОСНОВНОЕ =================
title: "Interior design"
# ↑ <title> в выдаче, до 60 знаков. Суффикс сайта (seo.title_suffix) добавит тема
h1: "Apartment design, start to finish"
# ↑ заголовок на странице — для того, кто её уже открыл; не копия title
description: "We plan the space and pick the materials."
# ↑ meta description, до 155 знаков: что человек получит на странице
# nav_title: Design          # короткое имя в меню и хлебных крошках
# slug:                      # адрес, если должен отличаться от имени файла. Ключ — имя файла;
#                            # в русском переводе этой страницы — slug: dizajn
# canonical:                 # не заполнять: движок ставит канонический адрес сам
# robots:                    # не заполнять: индексацию решает noindex

# ================= 2. КЛЮЧЕВЫЕ ЗАПРОСЫ =================
# основной: interior design
# дополнительные: apartment design
# всего: 2
# Движок эту группу не читает. Один интент — одна страница

# ================= 3. OPEN GRAPH =================
# og_title:                  # пусто — берётся title
# og_description:            # пусто — берётся description
# og_image:                  # пусто — seo.og_default_image из site.yaml
# og_image_alt:

# ================= 4. TWITTER / X =================
# twitter_title:             # пусто — из Open Graph
# twitter_description:
# twitter_image:

# ================= 5. SCHEMA.ORG =================
# schema:                    # уточнения разметки этой страницы, поверх site.yaml
#   Service:
#     serviceType: interior design

# ================= 6. КАРТОЧКА И КАТАЛОГ =================
# image: media/services/design.png   # превью в каталоге: путь в media/
# image_alt:                 # обязательно, если задан image
order: 10
# ↑ порядок в каталоге и меню, по возрастанию
# type: service              # тип, если не задан разделом (children_type в _index.md)

# ================= 7. СЛУЖЕБНОЕ =================
# date: 2026-03-14           # дата публикации, ГГГГ-ММ-ДД
# updated: 2026-09-02        # дата правки; без неё — build.updated_from из site.yaml
published: true
# ↑ false — страница не собирается
# noindex: true              # закрыть от поисковиков и убрать из sitemap

# ================= 8. СВЯЗИ =================
related:
  - planning
# ↑ поле связи из theme.yaml: имена файлов без .md
redirect_from:
  - "/старый-адрес/"
# ↑ старые адреса, с которых нужен 301 сюда; кириллица или %D0%… — всё равно
---

Intro: who we help and with what.

Promise: what the work ends with.

## What is included {#includes}

- **Measurements.** We measure the rooms.
- **Project.** Drawings and a material list.

## How we work {#how}

1. **Request.** Call or write to us.
2. **Meeting.** We discuss the task.

## FAQ {#faq}

### How long does it take?

Usually two to three weeks.
