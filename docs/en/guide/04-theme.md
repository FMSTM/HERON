# 04 · Theme and design

How a theme is built, how to make your own and what the template sees. For the designer and the front-end developer, a human or an agent.

The theme decides **how the site looks**; the content decides **what is written on it**. The theme does not know a single page text, the content does not know a single CSS class. They meet by names: page type → template, section anchor → module.

## Where to get a theme

- **The starter theme** is already in a new site after `heron new`: white, light and dark, it draws all thirteen section forms; its demo pages in Russian and English are the home page, "Blocks" (every kind of block on one page), "Themes", "Documentation". To put it back over your own, use `heron theme get starter .`.
- **From the catalog**: `heron theme get <name> .`, the list is `heron theme list`.
- **By link or as an archive**: `heron theme get https://…/theme.tar.gz .` or `heron theme get ./theme.zip .`.
- **Your own into an archive**: `heron theme pack . --out theme.tar.gz`: the theme and the site content as its demo pages.

On installation the previous theme goes to `.heron-cache/setup/`, and the site pages are not overwritten: the demo pages of the theme are put only where there is no file. What an archive may and may not contain: [`21` §10](../spec/21-engine.md#heron-theme).

## What it consists of

```
theme/
├── theme.yaml            passport: page types, their sections, relations, images
├── base.html             frame: <head>, header, footer, the content block
├── templates/            one template per type: home.html, page.html, service.html, 404.html…
├── modules/              one file per module: prose.html, steps.html, faq.html…
├── partials/             pieces of the frame: header.html, footer.html, analytics.html
├── assets/               CSS, JS, fonts: copied to dist as they are
└── i18n/<lang>.yaml      interface strings: en.yaml, ru.yaml, "Read more" / "Читать далее"
```

`heron new` puts the starter theme: the types `home`, `page`, `404`, a module for every section form (`prose`, `list` and `alert-list`, `checklist` and `two-lists`, `steps`, `table`, `facts`, `faq`, `timeline`, `callout`, `gallery`, `tabs`), `breadcrumbs` and `children`, the cards of the child pages of a section. The layout of sections into modules is done by `partials/sections.html`. Tabs work without scripts, on radio buttons. Your own theme starts with a copy of it: change the variables at the start of `assets/site.css` and place the sections by anchors in `templates/`.

## `theme.yaml`

```yaml
name: main
version: "1.0"

requires: [contact.phone, organization.name]   # what the theme takes from site.yaml

modules: [breadcrumbs, prose, facts, list, steps, faq, cards]

types:
  home:
    uses: [intro, about, services, faq]
  service:
    uses: [intro, quick-facts, what, "how:steps", faq]
    jsonld: [Service]
  page:
    uses: [intro, "*"]            # "*" means any sections

links:                            # relations between pages
  - field: related
    type: service
    back: mentioned_in

images:
  widths: [400, 800, 1200, 1600]
  ratios: ["1:1", "16:9"]
  formats: [avif, webp]
```

- **`types.<type>.uses`** is which sections the type shows. This is an agreement with the content: `heron page service roof` puts stubs of exactly these sections, and the "Not filled" summary after the build names the empty ones. A section in the file that is not in `uses` is a line in the report: this is how a typo in an anchor is caught. `"how:steps"` means the theme expects the form `steps` in that section.
- **`requires`** are the paths in `site.yaml` without which the theme does not work: if they are not filled in, the error `E011` comes before rendering.
- **`links`** are relation fields. The core finds the pages, checks them and builds a reverse list (`back`). `type` in a relation limits **to pages of which type** the field leads: `related` with `type: service` will not link articles to each other. A relation without a limit has no `type`: `- {field: related, back: related_from}`.
- **`images`** are widths, proportions, resize formats and `fallback_width`, the width of the fallback PNG/JPEG. Only what the templates asked for is resized.

Every key in detail: [`20` §6](../spec/20-data-contract.md#theme-yaml).

## Type template

The type `service` is drawn by `templates/service.html`. The order of blocks reads top to bottom:

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

`mod.prose('what')` takes the section with the anchor `what`. **No section, nothing at all**: no heading, no empty frame, no conditions around it needed. That is why the order of sections in the content does not matter, and a page can lack sections without harm to the layout.

A template that does not know in advance which sections there will be chooses the module by form; this is how `page.html` of the starter theme is made:

```jinja
{% for section in page.sections.values() %}
  {% if section.kind == 'faq' %}{{ mod.faq(section.id) }}
  {% elif section.kind == 'steps' %}{{ mod.steps(section.id) }}
  {% else %}{{ mod.prose(section.id) }}{% endif %}
{% endfor %}
```

### Paths and macros

- **Paths in `extends`, `include` and `import` are counted from the theme root**, not from the template folder: `{% extends "base.html" %}`, `{% extends "templates/page.html" %}`, `{% include "partials/header.html" %}`. Writing `{% extends "page.html" %}` from `templates/landing.html` is the error `E008` with a hint where the file actually is.
- **`mod` is available in every template**, so there is no need to import modules. Your own macros are another matter: `{% import %}` in `base.html` is not visible to child templates (this is how Jinja2 works), so import them in every template where they are needed.

## Module

A module is a file `modules/<name>.html`, called as `mod.<name>(<anchor>)`. Inside, these are available:

| Variable | What it is |
|---|---|
| `section` | the section: `id`, `title`, `kind`, `lead`, `body`, `note`, `callout`, `links` |
| `items` | parsed data of the form: steps, question-answer pairs, facts… |
| `html` | ready markup of the whole content of the section |
| everything the template sees | `page`, `site`, `t`, `picture`… |

```jinja
<section id="{{ section.id }}" class="faq">
  {% if section.title %}<h2>{{ section.title }}</h2>{% endif %}
  {% for pair in items %}
    <details><summary>{{ pair.q }}</summary>{{ pair.a|safe }}</details>
  {% endfor %}
</section>
```

What is in `items` for each of the thirteen forms is in the table [`20` §4.4](../spec/20-data-contract.md#section-forms). Modules without an argument (`mod.breadcrumbs()`) take data from `page` and `site`.

## What the template sees

| Name | What it is |
|---|---|
| `page` | the page: `h1`, `title`, `url`, `type`, `intro`, `sections`, `children`, `parent`, `breadcrumbs`, `translations`, `related`, `meta.<field>` |
| `site` | the whole `site.yaml`, values already in the language of the page: `site.site.name`, `site.contact.phone` |
| `data` | the content of `data/*.yaml` |
| `nav` | the menu from `site.yaml`, already as pages: `item.url`, `item.nav_title` |
| `t` | interface strings of the current language: `t.read_more` |
| `lang`, `languages`, `hreflang` | the current language, all languages, addresses of translations |
| `page_of(key)` | a page by key in the current language; the home page is `page_of('/')` |
| `picture(src, ratio)` | a ready `<picture>` with `srcset`, WebP/AVIF and sizes |
| `media_url(src, ratio, width)` | the address of one rendition |
| `jsonld()` | the JSON-LD markup of the page, to insert into `<head>` |
| `env` | the build environment: `env.indexable`, `env.analytics` |

The full page model is [`21` §6](../spec/21-engine.md#page-model), the variables are [`21` §7](../spec/21-engine.md#rendering).

Reference to a variable that does not exist **fails the build** with the template name and line, instead of printing nothing: a typo in the theme is caught at once.

### Your own page fields

A theme can expect its own fields in the frontmatter: `topic`, `eyebrow`, anything. They do not need to be declared anywhere: the engine puts them into the page as they are.

```jinja
{% if page.meta.get('eyebrow') %}<p class="eyebrow">{{ page.meta.get('eyebrow') }}</p>{% endif %}
<span>{{ page.meta.get('topic', 'general') }}</span>
```

`page.meta.get('field', fallback)` does not fail if the page has no such field. `page.meta.topic` will fail: this is how typos in the engine's own fields are caught. All your own fields at once: `page.meta.extra`.

`fields` in `theme.yaml` is **only for engine fields** that the theme expects from a new version. Your own fields are not written there: the engine does not know them and answers `E023`.

### Values in the language of the page

The template gets `site.yaml` already in the language of the page, **all blocks, at any depth**: on a Russian page `site.contact.address` is `address_ru`, `site.site.name` is `name_ru`, `site.organization.about` is `about_ru`. If there is no language key, the key without the suffix is taken. There is no need to choose the language with a filter; the keys with the suffix are available too.

The same rule works in the substitutions of the markup (`{{ contact.address }}` in the `schema` block), so the address in the footer and in the markup do not diverge.

## Accumulating data in a template without `append` <a id="accumulate-data-without-append"></a>

Theme templates are built in an immutable sandbox ([`21` §7](../spec/21-engine.md#rendering)): methods that change a list or a dictionary, `.append`, `.extend`, `.insert`, `.update`, `.pop`, `.remove`, `.add`, `.setdefault`, `.clear`, `.sort`, `.reverse`, fail the build with `E033` and the template name. A template does not change a value but builds a new one.

Before, fails with `E033`:

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

After, the same without changes:

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

Techniques:

- **Selection by filter.** `rejectattr`, `selectattr`, `select`, `reject`, `map(attribute='url')`; at the end `|list` if you need the result as a list and not for one pass.
- **Without repeats, `unique`** with an attribute and always with `case_sensitive=True`, otherwise `/A/` and `/a/` merge into one address: `{% set links = (page.related.get('see_also', []) + more)|unique(case_sensitive=True, attribute='url')|list %}`.
- **To add an element, add lists:** `body + [x]`, `body + ([faq] if faq else [])`.
- **To add a key, make a new dictionary:** `dict(base, key=val)`; a key with a hyphen cannot be passed this way, so build the whole dictionary: `{'class': 'card', 'data-x': x}`.
- **Accumulating in a loop only through `namespace()`.** A plain `{% set %}` inside `for` lives until the end of the loop step: `{% set found = found + [p] %}` in the loop body does not change `found` outside, and after the loop the list is empty again. A `namespace` attribute (`acc.found`) survives the loop.
- **Careful with `StrictUndefined`.** `selectattr('meta.extra.cluster', ...)` fails on the first page that has no such key. For an optional key use a loop with `namespace` and `.get('cluster')`, as in the example.
- **Tags on the same lines as before.** A line with only `{% %}` prints nothing (`trim_blocks` and `lstrip_blocks`), so replacing a tag with a tag does not change the whitespace in the HTML.

To find such places before the build, use `heron check`: it parses the theme templates and names every `E033` call with the file, the line and a replacement recipe, including in a template that the theme does not render yet ([`21` §12](../spec/21-engine.md#check-report)).

To verify, run `heron build`: no `E033` at all, the pages are the same as before the edit.

## Interface strings

The texts that belong to the theme and not to a page are in `theme/i18n/<lang>.yaml`:

```yaml
# theme/i18n/en.yaml
read_more: Read more
faq: Questions and answers
```

```yaml
# theme/i18n/ru.yaml
read_more: "Читать далее"
faq: "(the Russian wording of the heading)"
```

In the template it is `{{ t.read_more }}`. If a string is missing, the build does not fail: the name of the key stays on the page and the report has a warning. Text hardcoded into a template makes the theme single-language; keep it in `i18n`.

## Images in the theme

```jinja
{{ picture(page.meta.image, '16:9', alt=page.meta.image_alt) }}
```

The engine gives renditions for the widths and proportions from `theme.yaml`, fits illustrations and crops photos. The path itself comes from the content; the theme decides only the proportion and the place.

**Only what the template asked for is resized.** `ratios` in `theme.yaml` are the proportions that the theme *may* ask for; only those that the templates really called through `picture()` or `media_url()` get into the build. A card asks for 16:9, so its image in the build will have only 16:9. The fallback file in the source format (for browsers without AVIF and WebP) is one per proportion, with the width `images.fallback_width` (800 by default). If you need a bigger width, ask for it explicitly: `media_url(src, '16:9', 1200)` for og:image. → [`20` §7](../spec/20-data-contract.md#images)

## How to check a theme

- `heron build`: the theme renders on every page; template errors name the file and the line;
- the report after the build: sections that are not in `uses`, forms of the wrong kind, missing `i18n` strings;
- `heron check` is the same report without a build.

---

Next: [05 · SEO](05-seo.md)
