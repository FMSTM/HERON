# 04 · Тема и дизайн

Как устроена тема, как сделать свою и что видит шаблон. Для дизайнера и верстальщика - человека или агента.

Тема решает, **как выглядит** сайт; контент решает, **что на нём написано**. Тема не знает ни одного текста страницы, контент не знает ни одного класса CSS. Встречаются они по именам: тип страницы → шаблон, якорь секции → модуль.

## Откуда взять тему

- **Стартовая** - уже в новом сайте после `heron new`: белая, светлая и тёмная, рисует все тринадцать форм секций; её демонстрационные страницы на русском и английском - главная, «Блоки» (каждый вид блока на одной странице), «Темы», «Документация». Вернуть её поверх своей - `heron theme get starter .`.
- **Из каталога** - `heron theme get <имя> .`, список - `heron theme list`.
- **По ссылке или архивом** - `heron theme get https://…/theme.tar.gz .` или `heron theme get ./theme.zip .`.
- **Своя в архив** - `heron theme pack . --out theme.tar.gz`: тема и контент сайта как её демонстрационные страницы.

Прежняя тема при установке уезжает в `.heron-cache/setup/`, страницы сайта не перезаписываются: демонстрационные страницы темы кладутся только туда, где файла нет. Что можно в архиве и что нет - [`21` §10](../spec/21-engine.md#heron-theme).

## Из чего состоит

```
theme/
├── theme.yaml            паспорт: типы страниц, их секции, связи, картинки
├── base.html             каркас: <head>, шапка, подвал, блок content
├── templates/            по шаблону на тип: home.html, page.html, service.html, 404.html…
├── modules/              по файлу на модуль: prose.html, steps.html, faq.html…
├── partials/             куски каркаса: header.html, footer.html, analytics.html
├── assets/               CSS, JS, шрифты - копируются в dist как есть
└── i18n/<язык>.yaml      строки интерфейса: en.yaml, ru.yaml - «Read more» / «Читать далее»
```

`heron new` кладёт стартовую тему: типы `home`, `page`, `404`, модуль на каждую форму секции (`prose`, `list` - и `alert-list`, `checklist` - и `two-lists`, `steps`, `table`, `facts`, `faq`, `timeline`, `callout`, `gallery`, `tabs`), `breadcrumbs` и `children` - карточки дочерних страниц раздела. Раскладку секций по модулям делает `partials/sections.html`. Вкладки - без скриптов, на радиокнопках. Своя тема начинается с её копии: поменяйте переменные в начале `assets/site.css` и расставьте секции по якорям в `templates/`.

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
    uses: [intro, "*"]            # "*" - любые секции

links:                            # связи между страницами
  - field: related
    type: service
    back: mentioned_in

images:
  widths: [400, 800, 1200, 1600]
  ratios: ["1:1", "16:9"]
  formats: [avif, webp]
```

- **`types.<тип>.uses`** - какие секции тип показывает. Это договор с контентом: `heron page service roof` положит заготовки ровно этих секций, а сводка «Не заполнено» после сборки назовёт пустые. Секция в файле, которой нет в `uses`, - строка в отчёте: так ловится опечатка в якоре. `"how:steps"` - тема ждёт у секции форму `steps`.
- **`requires`** - пути в `site.yaml`, без которых тема не работает: не заполнены - ошибка `E011` до рендера.
- **`links`** - поля связей. Ядро найдёт страницы, проверит их и построит обратный список (`back`). `type` в связи ограничивает, **на страницы какого типа** ведёт поле: `related` с `type: service` не свяжет статьи между собой. Связь без ограничения - без `type`: `- {field: related, back: related_from}`.
- **`images`** - ширины, пропорции, форматы нарезки, `fallback_width` - ширина запасного PNG/JPEG, `cover_width` - ширина обложки для краулеров, `crop` и `as_is` - пути для принудительного кропа и для копирования без нарезки. Режется только то, что шаблоны попросили.
- **`types.<тип>.template`** - другой файл шаблона вместо `templates/<тип>.html`, путь от `templates/`.
- **`forms`** - формы, которые рисует тема; их описание обязано быть в `site.yaml` (`E011`).
- **`heron`** - версия движка, на которую рассчитана тема: не та - `E012`.

Каждый ключ подробно - [`20` §6](../spec/20-data-contract.md#theme-yaml).

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

`mod.prose('what')` берёт секцию с якорем `what`. **Нет секции - нет ничего**: ни заголовка, ни пустой рамки, условия вокруг не нужны. Поэтому в контенте порядок секций не важен, а у страницы может не хватать секций без вреда для вёрстки.

Шаблон, который не знает заранее, какие секции будут, выбирает модуль по форме - так сделан `page.html` стартовой темы:

```jinja
{% for section in page.sections.values() %}
  {% if section.kind == 'faq' %}{{ mod.faq(section.id) }}
  {% elif section.kind == 'steps' %}{{ mod.steps(section.id) }}
  {% else %}{{ mod.prose(section.id) }}{% endif %}
{% endfor %}
```

### Пути и макросы

- **Пути в `extends`, `include` и `import` считаются от корня темы**, а не от папки шаблона: `{% extends "base.html" %}`, `{% extends "templates/page.html" %}`, `{% include "partials/header.html" %}`. Написать `{% extends "page.html" %}` из `templates/landing.html` - ошибка `E008` с подсказкой, где файл на самом деле.
- **`mod` доступен в каждом шаблоне** - импортировать модули не нужно. Свои макросы - другое дело: `{% import %}` в `base.html` дочерним шаблонам не виден (так устроен Jinja2), импортируйте их в каждом шаблоне, где они нужны.

## Что вывести в `<head>` <a id="head-seo"></a>

Каркас `base.html` отвечает за всё, что поисковик и мессенджер читают до страницы. Для картинок и индексации нужны три вещи:

- `<meta name="robots" content="{{ robots_meta }}">`: тема не решает, открыта страница или закрыта, это делает движок. Если строки нет, крупные превью не включатся, а закрытая дев-сборка не получит `noindex`;
- `og:image` и `twitter:image` по `cover_url(page)`. Выводите их только когда адрес не пуст: пустая строка значит, что обложки нет, и пустой тег хуже отсутствующего;
- размеры и подпись картинки: `page.cover.width`, `page.cover.height`, `page.cover.alt`. Размеры позволяют соцсети показать превью сразу, а `alt` нужен тем, кто картинку не видит.

Пример блока целиком:

```jinja
<title>{{ page.title }}{{ site.seo.title_suffix }}</title>
<meta name="description" content="{{ page.meta.description }}">
<link rel="canonical" href="{{ absolute(page.url) }}">
<meta property="og:title" content="{{ page.meta.og_title or page.title }}">
<meta property="og:description" content="{{ page.meta.og_description or page.meta.description }}">
{% set cover = page.cover %}
{% set cover_src = cover_url(page) if cover else "" %}
{% if cover_src %}
<meta property="og:image" content="{{ cover_src }}">
{% if cover.width %}<meta property="og:image:width" content="{{ cover.width }}">{% endif %}
{% if cover.height %}<meta property="og:image:height" content="{{ cover.height }}">{% endif %}
{% if cover.alt %}<meta property="og:image:alt" content="{{ cover.alt }}">{% endif %}
<meta name="twitter:image" content="{{ cover_src }}">
{% endif %}
<meta name="robots" content="{{ robots_meta }}">
{% for code, href in hreflang %}<link rel="alternate" hreflang="{{ code }}" href="{{ href }}">{% endfor %}
{% set ld = jsonld() %}
{% if ld %}<script type="application/ld+json">{{ ld }}</script>{% endif %}
```

Имена `cover_url` и `robots_meta` зарезервированы за движком: свои переменные с такими именами в теме не заводите. Какая картинка станет обложкой и как её готовить - [05 · SEO](05-seo.md#you-fill), правила выбора - [`20` §6](../spec/20-data-contract.md#page-cover).

## Модуль

Модуль - файл `modules/<имя>.html`, вызывается как `mod.<имя>(<якорь>)`. Внутри доступны:

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

Что лежит в `items` у каждой из тринадцати форм - таблица [`20` §4.4](../spec/20-data-contract.md#section-forms). Модули без аргумента (`mod.breadcrumbs()`) берут данные из `page` и `site`.

## Что видит шаблон

| Имя | Что это |
|---|---|
| `page` | страница: `h1`, `title`, `url`, `type`, `intro`, `sections`, `children`, `parent`, `breadcrumbs`, `translations`, `related`, `meta.<поле>` |
| `site` | весь `site.yaml`, значения уже на языке страницы: `site.site.name`, `site.contact.phone` |
| `data` | содержимое `data/*.yaml` |
| `nav` | меню из `site.yaml`, уже страницами: `item.url`, `item.nav_title` |
| `t` | строки интерфейса текущего языка: `t.read_more` |
| `lang`, `languages`, `hreflang` | текущий язык, все языки, адреса переводов |
| `page_of(key)` | страница по ключу на текущем языке; главная - `page_of('/')` |
| `picture(src, ratio)` | готовый `<picture>` с `srcset`, WebP/AVIF и размерами |
| `media_url(src, ratio, width)` | адрес одной нарезки |
| `jsonld()` | разметка JSON-LD страницы, вставить в `<head>` |
| `cover_url(page, min_width=1200)` | абсолютный адрес обложки не уже `min_width`; обложки нет - пустая строка. Есть и фильтр: `{{ page|cover_url }}` |
| `robots_meta` | строка для `<meta name="robots">`: крупные превью на индексируемой странице прод-сборки, `noindex, nofollow` на закрытой |
| `env` | окружение сборки: `env.indexable`, `env.analytics` |
| `theme` | `theme.yaml` моделью: `theme.types`, `theme.images` |
| `pages` | весь сайт: все страницы всех языков (`pages.of_lang('ru')`, `pages.of_type('article', 'ru')`, `pages.by_url`); страница по ключу удобнее через `page_of` |
| `absolute(url)` | абсолютный адрес на домене сборки; есть и фильтр `{{ url|absolute }}` |

Полная модель страницы - [`21` §6](../spec/21-engine.md#page-model), переменные - [`21` §7](../spec/21-engine.md#rendering).

Обращение к несуществующей переменной **валит сборку** с именем шаблона и строки, а не выводит пустоту: опечатка в теме ловится сразу.

### Свои поля страницы

Тема может ждать во фронтматтере свои поля - `topic`, `eyebrow`, что угодно. Объявлять их нигде не нужно: движок кладёт их в страницу как есть.

```jinja
{% if page.meta.get('eyebrow') %}<p class="eyebrow">{{ page.meta.get('eyebrow') }}</p>{% endif %}
<span>{{ page.meta.get('topic', 'general') }}</span>
```

`page.meta.get('поле', запасное)` не падает, если у страницы поля нет. `page.meta.topic` упадёт - так ловятся опечатки в полях самого движка. Все свои поля разом - `page.meta.extra`.

`fields` в `theme.yaml` - **только для полей движка**, которые тема ждёт от новой версии. Свои поля туда не пишут: движок их не знает и ответит `E023`.

### Значения на языке страницы

Шаблон получает `site.yaml` уже на языке страницы - **все блоки, на любой глубине**: на русской странице `site.contact.address` - это `address_ru`, `site.site.name` - `name_ru`, `site.organization.about` - `about_ru`. Нет языкового ключа - берётся ключ без хвоста. Выбирать язык фильтром не нужно; ключи с хвостом при этом тоже доступны.

То же правило работает в подстановках разметки (`{{ contact.address }}` в блоке `schema`), так что адрес в подвале и в разметке не разойдутся.

## Накопление данных в шаблоне без `append` <a id="accumulate-data-without-append"></a>

Шаблоны темы собираются в неизменяемой песочнице ([`21` §7](../spec/21-engine.md#rendering)): методы, которые меняют список или словарь, - `.append`, `.extend`, `.insert`, `.update`, `.pop`, `.remove`, `.add`, `.setdefault`, `.clear`, `.sort`, `.reverse` - валят сборку с `E033` и именем шаблона. Шаблон не меняет значение, а строит новое.

Было - падает с `E033`:

```jinja
{% set body = [] %}
{% for s in page.sections.values() %}
  {% if s.id not in ['short', 'faq'] %}{% set _ = body.append(s) %}{% endif %}
{% endfor %}
{% if page.sections.get('faq') %}{% set _ = body.append(page.sections['faq']) %}{% endif %}
{% set found = [] %}
{% for p in page.children %}
  {% if p.meta.extra.get('cluster') %}{% set _ = found.append(p) %}{% endif %}
{% endfor %}
{% set attrs = {'class': 'card'} %}
{% if page.meta.get('accent') %}{% set _ = attrs.update({'accent': page.meta.get('accent')}) %}{% endif %}
```

Стало - то же самое без изменений:

```jinja
{% set faq = page.sections.get('faq') %}
{% set body = page.sections.values()|rejectattr('id', 'in', ['short', 'faq'])|list %}
{% set toc = body + ([faq] if faq else []) %}
{% set acc = namespace(found=[]) %}
{% for p in page.children %}
  {% if p.meta.extra.get('cluster') %}{% set acc.found = acc.found + [p] %}{% endif %}
{% endfor %}
{% set found = acc.found %}
{% set attrs = {'class': 'card'} %}
{% if page.meta.get('accent') %}{% set attrs = dict(attrs, accent=page.meta.get('accent')) %}{% endif %}
```

Приёмы:

- **Отбор - фильтром.** `rejectattr`, `selectattr`, `select`, `reject`, `map(attribute='url')`; в конце `|list`, если результат нужен списком, а не одним проходом.
- **Без повторов - `unique`** с атрибутом и обязательно с `case_sensitive=True`, иначе `/A/` и `/a/` склеятся в один адрес: `{% set links = (page.related.get('see_also', []) + more)|unique(case_sensitive=True, attribute='url')|list %}`.
- **Добавить элемент - сложением списков:** `body + [x]`, `body + ([faq] if faq else [])`.
- **Добавить ключ - новым словарём:** `dict(base, key=val)`; ключ с дефисом так не передать - соберите словарь целиком: `{'class': 'card', 'data-x': x}`.
- **Накопление в цикле - только через `namespace()`.** Обычный `{% set %}` внутри `for` живёт до конца шага цикла: `{% set found = found + [p] %}` в теле цикла не меняет `found` снаружи, и после цикла список снова пуст. Атрибут `namespace` (`acc.found`) цикл переживает.
- **Осторожно со `StrictUndefined`.** `selectattr('meta.extra.cluster', ...)` падает на первой странице, где такого ключа нет. Необязательный ключ - цикл с `namespace` и `.get('cluster')`, как в примере.
- **Теги - на тех же строках, что и раньше.** Строка, на которой только `{% %}`, ничего не выводит (`trim_blocks` и `lstrip_blocks`), поэтому замена тега на тег не меняет пробелы в HTML.

Найти такие места до сборки - `heron check`: он разбирает шаблоны темы и называет каждый вызов `E033` с файлом, строкой и рецептом замены, в том числе в шаблоне, который тема пока не рендерит ([`21` §12](../spec/21-engine.md#check-report)).

Проверка - `heron build`: ни одного `E033`, страницы те же, что до правки.

## Строки интерфейса

Тексты, которые принадлежат теме, а не странице, - в `theme/i18n/<язык>.yaml`:

```yaml
# theme/i18n/en.yaml
read_more: Read more
faq: Questions and answers
```

```yaml
# theme/i18n/ru.yaml
read_more: Читать далее
faq: Вопросы и ответы
```

В шаблоне - `{{ t.read_more }}`. Не хватает строки - сборка не падает: на странице останется имя ключа, в отчёте будет предупреждение. Зашитый в шаблон текст делает тему одноязычной; держите его в `i18n`.

## Картинки в теме

```jinja
{{ picture(page.meta.image, '16:9', alt=page.meta.image_alt) }}
```

Движок отдаёт нарезки под ширины и пропорции из `theme.yaml`, иллюстрации вписывает, фотографии кропает. Сам путь - из контента; тема решает только пропорцию и место.

**Режется только то, что попросил шаблон.** `ratios` в `theme.yaml` - пропорции, которые тема *может* попросить; в сборку попадают только те, что шаблоны действительно вызвали через `picture()` или `media_url()`. Карточка просит 16:9 - у её картинки в сборке будет только 16:9. Запасной файл в исходном формате (для браузеров без AVIF и WebP) - один на пропорцию, шириной `images.fallback_width` (по умолчанию 800). Нужна ширина больше - попросите её явно: `media_url(src, '16:9', 1200)` для og:image. → [`20` §7](../spec/20-data-contract.md#images)

## Обновление темы до строгого CSP <a id="strict-csp"></a>

Страницы отдаются с `script-src 'self'`, поэтому инлайн-скрипт в теме не выполнится. Если ваша копия темы старее и содержит такой скрипт:

1. перенесите код в файл темы (`assets/site.js`);
2. данные (номера счётчиков и подобное) передавайте атрибутами `data-*` на теге `<script src="/assets/site.js">`, как в `base.html` стартовой темы;
3. запустите `heron check`: инлайн-скрипт в теме он называет предупреждением.

## Как проверить тему

- `heron build` - тема рендерится на каждой странице; ошибки шаблона называют файл и строку;
- отчёт после сборки: секции, которых нет в `uses`, формы не того вида, недостающие строки `i18n`;
- `heron check` - тот же отчёт без сборки.

---

Дальше: [05 · SEO](05-seo.md)
