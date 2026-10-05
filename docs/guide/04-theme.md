# 04 · Тема и дизайн

Как устроена тема, как сделать свою и что видит шаблон. Для дизайнера и верстальщика — человека или агента.

Тема решает, **как выглядит** сайт; контент решает, **что на нём написано**. Тема не знает ни одного текста страницы, контент не знает ни одного класса CSS. Встречаются они по именам: тип страницы → шаблон, якорь секции → модуль.

## Из чего состоит

```
theme/
├── theme.yaml            паспорт: типы страниц, их секции, связи, картинки
├── base.html             каркас: <head>, шапка, подвал, блок content
├── templates/            по шаблону на тип: home.html, page.html, service.html, 404.html…
├── modules/              по файлу на модуль: prose.html, steps.html, faq.html…
├── partials/             куски каркаса: header.html, footer.html, analytics.html
├── assets/               CSS, JS, шрифты — копируются в dist как есть
└── i18n/<язык>.yaml      строки интерфейса: «Читать далее», «Вопросы и ответы»
```

`heron new` кладёт стартовую тему: типы `home`, `page`, `404` и модули `breadcrumbs`, `cards`, `facts`, `faq`, `list`, `prose`, `steps`. Её задача — чтобы сайт собирался с первой минуты, а не чтобы на ней жить. Своя тема начинается с её копии.

## `theme.yaml`

```yaml
name: main
version: "1.0"

requires: [contact.phone, organization.name]   # что тема берёт из site.yaml

modules: [breadcrumbs, prose, facts, list, steps, faq, cards]

types:
  home:
    uses: [intro, about, services, faq]
  service:
    uses: [intro, quick-facts, what, "how:steps", faq]
    jsonld: [Service]
  page:
    uses: [intro, "*"]            # "*" — любые секции

links:                            # связи между страницами
  - field: related
    type: service
    back: mentioned_in

images:
  widths: [400, 800, 1200, 1600]
  ratios: ["1:1", "16:9"]
  formats: [avif, webp]
```

- **`types.<тип>.uses`** — какие секции тип показывает. Это договор с контентом: `heron page service roof` положит заготовки ровно этих секций, а сводка «Не заполнено» после сборки назовёт пустые. Секция в файле, которой нет в `uses`, — строка в отчёте: так ловится опечатка в якоре. `"how:steps"` — тема ждёт у секции форму `steps`.
- **`requires`** — пути в `site.yaml`, без которых тема не работает: не заполнены — ошибка `E011` до рендера.
- **`links`** — поля связей. Ядро найдёт страницы, проверит их и построит обратный список (`back`).
- **`images`** — ширины, пропорции, форматы нарезки.

Каждый ключ подробно — [`20` §6](../spec/20-data-contract.md#6-themeyaml).

## Шаблон типа

Тип `service` рисуется `templates/service.html`. Порядок блоков читается сверху вниз:

```jinja
{% extends "base.html" %}
{% block content %}
  {{ mod.breadcrumbs() }}
  <h1>{{ page.h1 }}</h1>
  {{ mod.facts('quick-facts') }}
  {{ mod.prose('what') }}
  {{ mod.steps('how') }}
  {{ mod.faq('faq') }}
  {% for p in page.related.get('related', []) %}
    <a href="{{ p.url }}">{{ p.h1 }}</a>
  {% endfor %}
{% endblock %}
```

`mod.prose('what')` берёт секцию с якорем `what`. **Нет секции — нет ничего**: ни заголовка, ни пустой рамки, условия вокруг не нужны. Поэтому в контенте порядок секций не важен, а у страницы может не хватать секций без вреда для вёрстки.

Шаблон, который не знает заранее, какие секции будут, выбирает модуль по форме — так сделан `page.html` стартовой темы:

```jinja
{% for section in page.sections.values() %}
  {% if section.kind == 'faq' %}{{ mod.faq(section.id) }}
  {% elif section.kind == 'steps' %}{{ mod.steps(section.id) }}
  {% else %}{{ mod.prose(section.id) }}{% endif %}
{% endfor %}
```

## Модуль

Модуль — файл `modules/<имя>.html`, вызывается как `mod.<имя>(<якорь>)`. Внутри доступны:

| Переменная | Что это |
|---|---|
| `section` | секция: `id`, `title`, `kind`, `lead`, `body`, `note`, `callout`, `links` |
| `items` | разобранные данные формы: шаги, пары вопрос-ответ, факты… |
| `html` | готовая вёрстка всего содержимого секции |
| всё, что видит шаблон | `page`, `site`, `t`, `picture`… |

```jinja
<section id="{{ section.id }}" class="faq">
  {% if section.title %}<h2>{{ section.title }}</h2>{% endif %}
  {% for pair in items %}
    <details><summary>{{ pair.q }}</summary>{{ pair.a|safe }}</details>
  {% endfor %}
</section>
```

Что лежит в `items` у каждой из двенадцати форм — таблица [`20` §4.4](../spec/20-data-contract.md#44-формы-секций-kind). Модули без аргумента (`mod.breadcrumbs()`) берут данные из `page` и `site`.

## Что видит шаблон

| Имя | Что это |
|---|---|
| `page` | страница: `h1`, `title`, `url`, `type`, `intro`, `sections`, `children`, `parent`, `breadcrumbs`, `translations`, `related`, `meta.<поле>` |
| `site` | весь `site.yaml`, значения уже на языке страницы: `site.site.name`, `site.contact.phone` |
| `data` | содержимое `data/*.yaml` |
| `nav` | меню из `site.yaml`, уже страницами: `item.url`, `item.nav_title` |
| `t` | строки интерфейса текущего языка: `t.read_more` |
| `lang`, `languages`, `hreflang` | текущий язык, все языки, адреса переводов |
| `page_of(key)` | страница по ключу на текущем языке; главная — `page_of('/')` |
| `picture(src, ratio)` | готовый `<picture>` с `srcset`, WebP/AVIF и размерами |
| `media_url(src, ratio, width)` | адрес одной нарезки |
| `jsonld()` | разметка JSON-LD страницы, вставить в `<head>` |
| `env` | окружение сборки: `env.indexable`, `env.analytics` |

Полная модель страницы — [`21` §6](../spec/21-engine.md#6-модель-страницы), переменные — [`21` §7](../spec/21-engine.md#7-рендеринг).

Обращение к несуществующей переменной **валит сборку** с именем шаблона и строки, а не выводит пустоту: опечатка в теме ловится сразу.

## Строки интерфейса

Тексты, которые принадлежат теме, а не странице, — в `theme/i18n/<язык>.yaml`:

```yaml
read_more: Читать далее
faq: Вопросы и ответы
```

В шаблоне — `{{ t.read_more }}`. Не хватает строки — сборка не падает: на странице останется имя ключа, в отчёте будет предупреждение. Зашитый в шаблон текст делает тему одноязычной; держите его в `i18n`.

## Картинки в теме

```jinja
{{ picture(page.meta.image, '16:9', alt=page.meta.image_alt) }}
```

Движок отдаёт нарезки под ширины и пропорции из `theme.yaml`, иллюстрации вписывает, фотографии кропает. Сам путь — из контента; тема решает только пропорцию и место. → [`20` §7](../spec/20-data-contract.md#7-картинки)

## Как проверить тему

- `heron build` — тема рендерится на каждой странице; ошибки шаблона называют файл и строку;
- отчёт после сборки: секции, которых нет в `uses`, формы не того вида, недостающие строки `i18n`;
- `heron check` — тот же отчёт без сборки.

---

Дальше: [05 · SEO](05-seo.md)
