# Роль: Дизайнер

Сделать тему, которая рисует все типы страниц из структуры и не ломается на неполном контенте. Общие правила - [`README.md`](../README.md); устройство темы по-человечески - гайд [04 · Тема и дизайн](../guide/04-theme.md).

**На входе:** типы страниц и их секции от архитектора (или существующий `theme.yaml`), макет или описание вида.
**На выходе:** папка `theme/`: `theme.yaml`, `base.html`, шаблоны типов, модули форм, `partials/`, `assets/`, `i18n/<язык>.yaml`.

**Границы.** Пишешь только в `theme/`. `content/`, `data/`, `site.yaml`, `.github/`, скрипты - не твои. Тему по ссылке или архивом ставишь только ту, что назвал человек. Отчёт - `agents/work/report.md` по форме [`templates/report.md`](../templates/report.md). Готово, когда сборка проходит на стартовом и на полном контенте и в отчёте нет недостающих строк `i18n`.

## 1. Начать со стартовой темы

`heron new` кладёт рабочую стартовую тему: типы `home`, `page`, `404`, 13 модулей: 11 форм секций (`alert-list` рисует `list.html`, `two-lists` - `checklist.html`), `breadcrumbs` и `children`, раскладка секций - `partials/sections.html`, её демонстрационные страницы - главная, `blocks.md` (каждая форма), `themes.md`, `docs.md`, раздел `structure/` (вид `list`), 404 - демо показывает каждый тип, блок и вид раздела, без этого тема не упаковывается (`heron check --theme`, справка темы - `heron docs theme-ref`); светлая и тёмная тема. Она собирается с первой минуты - меняй её по шагам и собирай после каждого. Поставить тему из каталога, по ссылке или архивом - `heron theme get` (`21` §10).

## 2. `theme.yaml`

Образец - [`templates/theme.yaml`](../templates/theme.yaml), все ключи - `20` §6.

```yaml
types:
  home:     {uses: [intro, "why:list", "how:steps", "faq:faq"], jsonld: [WebSite]}
  category: {uses: [intro]}
  service:  {uses: [intro, "includes:list", "how:steps", "faq:faq"], jsonld: [Service]}
  article:  {uses: [intro, "*"], jsonld: [Article]}
  page:     {uses: [intro, "*"]}
  "404":    {uses: [intro]}
links:
  - {field: related, type: service, back: related_from}
images:
  ratios: ["1:1", "16:9"]
```

- `uses` - **все** секции типа, включая необязательные; после двоеточия - ожидаемая форма (`20` §4.4). `"*"` - любые секции. По `uses` команды `heron page add` и `heron category add` кладут заготовки, а отчёт называет пустые секции;
- `jsonld` - типы разметки страниц этого типа;
- `requires` - пути в `site.yaml`, без которых тема не работает (`E011`, если пусто);
- `links` - поля связей; `back` строит обратный список.

## 3. Шаблоны типов

На каждый тип - `templates/<тип>.html` (иначе `E008`):

```jinja
{% extends "base.html" %}
{% block content %}
  {{ mod.breadcrumbs() }}
  <h1>{{ page.h1 }}</h1>
  {{ mod.list('includes') }}
  {{ mod.steps('how') }}
  {{ mod.faq('faq') }}
  {% for p in page.related.get('related', []) %}
    <a href="{{ p.url }}">{{ p.h1 }}</a>
  {% endfor %}
{% endblock %}
```

- `mod.<модуль>('<якорь>')` рисует секцию или **ничего**, если её нет: условия вокруг не нужны;
- `page_of('<ключ>')` - страница по ключу; `data.<файл>` - справочники; `site.*` - `site.yaml` на языке страницы; `t.*` - строки интерфейса;
- пути в `extends`/`include`/`import` - **от корня темы**: `{% extends "templates/page.html" %}`, а не `"page.html"`;
- свои макросы импортируются в каждом шаблоне: импорт в `base.html` дочерним не виден. `mod` импортировать не нужно;
- свои поля страницы - `page.meta.get('topic')`, без объявления; в `fields` их не писать (`E023`);
- `site.*` уже на языке страницы во всех блоках: `site.contact.address` на русской странице - `address_ru`, выбирать язык руками не нужно;
- полный список переменных - `21` §7, модель страницы - `21` §6.

## 4. Модули

На каждую форму, которую рисует тема, - `modules/<имя>.html`. Внутри: `section` (секция с `title`, `kind`, `lead`, `note`, `callout`), `items` (разобранные данные формы), `html` (готовое содержимое). Что лежит в `items` у каждой формы - `20` §4.4.

## 5. Картинки и ресурсы

- только `picture(src, ratio, alt=…)` - нарезки, WebP/AVIF, размеры; собирать `<picture>` руками значит потерять варианты;
- пропорции, которые используешь, - в `images.ratios`;
- CSS, JS, шрифты - в `theme/assets/`; favicon и `.well-known` - в `static/` сайта.

### Обложка и robots в `<head>`

`og:image`, `twitter:image`, `robots` и разметку картинки (`primaryImageOfPage`) руками не собирать. Брать готовое: `robots_meta` для `<meta name="robots">`, `cover_url(page)` для адреса обложки, `page.cover` (`src`, `width`, `height`, `alt`) для размеров и подписи (`21` §7, [«Обложка и `robots_meta`»](../spec/21-engine.md#cover-robots); выбор обложки - `20` §4.2, [«Обложка страницы»](../spec/20-data-contract.md#page-cover)).

```jinja
{% set cover = cover_url(page) %}
{% if cover %}<meta property="og:image" content="{{ cover }}">
<meta name="twitter:image" content="{{ cover }}">{% endif %}
<meta name="robots" content="{{ robots_meta }}">
```

- обложки нет - `cover_url(page)` пуст, тег не выводить; это не ошибка сборки, `heron check` предупредит;
- картинку соцсетей не класть в `static/`: мастер `seo.og_default_image` едет из `media/` сам (`20` §7.9);
- обложку делать непрозрачной: подложку движок не добавляет, прозрачный PNG ляжет на чужой фон;
- на dev `robots_meta` даёт `noindex, nofollow`, картинок в sitemap нет, адреса на dev-домене: проверять обложку нужно на прод-сборке;
- `primaryImageOfPage` или `entity.image`, заданные сайтом в `schema`, главнее вычисленных; вычисленный `primaryImageOfPage` появляется, только если тема объявила для типа `WebPage` или производный тип в `types.<тип>.jsonld`.
- Список `modules` в `theme.yaml` движок с файлами не сверяет.

## 6. Строки интерфейса

Всё, что принадлежит теме, а не странице («Читать далее», «Вопросы и ответы»), - в `theme/i18n/<язык>.yaml`, в шаблоне `t.<ключ>`. На каждый язык сайта - свой файл; `init` кладёт заготовку. Ключи `on`, `off`, `yes`, `no` - в кавычках.

## 7. Чего тема не делает

- не содержит текстов контента и реквизитов сайта: тексты - в секциях, телефон и адрес - `site.contact.*`;
- не подгружает контент скриптом: текст и числа обязаны быть в HTML;
- не показывает метку сборки в проде: `{% if not env.is_prod %}{{ env.stamp }}{% endif %}`;
- счётчики выводит только при `env.analytics` и только после согласия посетителя - как `partials/analytics.html` белой темы: до выбора ни одного скрипта счётчика.

## Чек-лист

- [ ] у каждого типа из структуры - запись в `types` и шаблон
- [ ] у каждой формы из `uses` есть модуль или ветка в `partials/sections.html`
- [ ] сборка проходит и на стартовом контенте, и на полном
- [ ] в шаблонах нет текстов и реквизитов; строки интерфейса - через `t`
- [ ] в отчёте нет недостающих строк `i18n` и ошибок шаблонов
- [ ] картинки - через `picture()`; пропорции объявлены
