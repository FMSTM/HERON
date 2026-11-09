# 04 · Theme and design

This section covers the theme of a site from two sides. First - for whoever runs a site on a ready theme: how to choose and install a theme, what to do with its demo pages, where to see what it can do and how to choose the look of a section. Then - for whoever is responsible for how the site looks: a designer, a front-end developer or an AI agent in the designer role: how a theme is built and what data a template gets. How to describe a theme for people (block fields and hints), make its demo, pack the theme and move it from version 0.2 - in [07 · Your own theme](07-theme-author.md).

A HERON site is split into two independent parts. **The theme** decides how the site looks: templates, styles, fonts. **The content** decides what is written on it: the page texts in `content/`. The theme does not know a single page text, and the content does not know a single CSS class. They meet by names: a page type finds its template, and a section anchor finds its module. That is why you can replace the theme without touching the texts, and the other way round.

> **The commands in this section are written for Docker** and run from the site folder (`cd ~/sites/my-site`), so the path to the site in them is a dot. Installed the engine without Docker - replace everything up to and including the image name (`ghcr.io/fmstm/heron:…`) with the word `heron` ([more](00-install.md#without-docker)).

## Working with a ready theme <a id="ready-theme"></a>

### Where to get a theme

There are three ways:

- **The starter theme** is already in every new site after `new`. It is white, with a light and a dark mode, and can show all thirteen section forms. It comes with demo pages in Ukrainian, Russian and English: the home page, "Blocks" (every kind of block on one page), "Themes", "Documentation", the section "Structure" with two pages inside and the 404 page. You changed the theme and want the starter one back - the second command below.
- **A theme from the catalog** is installed by name: `theme get <name> .`. To see the catalog - the first command below. For now it has only `starter`.
- **A theme by link or from an archive** - an `https://…` address or a `.tar.gz` or `.zip` file the author of the theme sent you.

The commands in full (`theme list` needs no site folder):

```bash
docker run --rm ghcr.io/fmstm/heron:prod theme list
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme get starter .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme get ./theme.tar.gz .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme get https://example.com/theme.tar.gz .
```

When you install a new theme, the old one is not lost: it moves to `.heron-cache/setup/`, and the engine tells you exactly where. Site pages are not overwritten: the demo pages of the new theme are put only where there is no file yet. The engine lists every file it placed and says how many files it kept as they are:

```
Theme starter is in place.
  previous version: .heron-cache/setup/theme.20261108-051919
  the theme demo placed: 1 page, 1 file in all (your files untouched):
    content/ru/blocks.md
  kept as they are (the site already has such a file): 9 files
```

What an archive may and may not contain - [`21` §10](../spec/21-engine.md#heron-theme).

### The demo pages of a theme <a id="demo-pages"></a>

Every theme comes with its demo - pages that show everything it can do: every page type, every block, every section view. It is not just an example but a sample of presentation the author of the theme thought through: which pages a site of this kind needs, which blocks they have and in what order.

- **To understand it** - open a demo page in the editor on the left and the same page in the browser on the right: you see which markdown gives which block.
- **To use it** - replace the texts of the demo with your own. A page that fits by meaning can stay and be rewritten.
- **To remove it** - delete the page file in all language folders (`content/en/blocks.md`, `content/ru/blocks.md`…) and remove its key from the menu - `nav.main` in `site.yaml`. Your site has to show only yours: the ordinary `check` does not require the demo.
- **To bring it back** - install the same theme again: `theme get` puts the demo pages where there are no files and leaves the rest alone. If you changed `theme/`, mind that the theme is replaced, and your version moves to `.heron-cache/setup/`.

The theme reference (below) takes live examples from the demo pages: delete them - and the reference keeps the hints and the markdown samples from `theme.yaml`.

### What the theme can do: the reference <a id="theme-reference"></a>

Every theme has a reference - a page that gathers everything it can do: page types and their sections, every block with its hint, a live example and its markdown next to it, section views and the line that turns them on. Nobody writes the reference by hand - the engine builds it from the description of the theme and its demo. It opens in three ways:

- start the preview and open <http://localhost:8000/_heron/theme/> (in the other site languages - `/_heron/theme/<lang>/`);
- in the studio - the "Theme reference" tab ([03 · Pages and content](03-content.md#studio));
- as text in the terminal - the first command below. The second briefly lists the page types, the blocks and their fields with hints - what `page add` will ask about:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod docs theme-ref .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod describe
```

The reference is not in the production build (`--env prod`), in the sitemap or in search: only you see it, in the preview and a draft build.

### The look of a section <a id="category-views"></a>

A section page (the `_index.md` of its folder) shows the pages that lie inside. How exactly is decided by the **view**, and every theme has its own views: the starter one can do cards in a grid (`cards`, the default) and a list of rows (`list`). Which views your theme has is shown by the reference and `describe`. You choose the view like this:

- when creating the section - with a question of `category add` or the `--view` flag (the command below);
- in the studio - with the "View" field of the section;
- by hand - with the line `view: list` in the SEO block of `_index.md`; without the line - the default view.

```bash
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod category add services . --view list
```

If the section already exists, the same command opens it for editing: the view changes in all languages.

## What a theme consists of

A theme is the `theme/` folder inside the site folder:

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

The starter theme that `new` puts in has the page types `home`, `page` and `404` and a module for every section form: `prose`, `list` (it also draws `alert-list`), `checklist` (and `two-lists`), `steps`, `table`, `facts`, `faq`, `timeline`, `callout`, `gallery`, `tabs`. Two more modules are `breadcrumbs` and `children` (cards of the child pages of a section). Which module draws which section is decided by `partials/sections.html`. Tabs work without scripts, on radio buttons. The easiest way to start your own theme is a copy of the starter one: change the variables at the start of `assets/site.css` (colors, fonts, spacing) and place the sections by anchors in `templates/`.

## The theme passport: `theme.yaml`

`theme.yaml` describes which pages the theme can show and what it needs for that. An example:

```yaml
name: main
version: "1.0"
heron: ">=0.3"                                 # which engine version the theme is made for

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

What the keys mean:

- **`types.<type>.uses`** - which sections a page of this type shows. This is an agreement with the content. The command `page add roof --type service` (in a theme that has the `service` type, as in the example above) puts drafts of exactly these sections into a new page, and the "Not filled" summary after the build names the empty ones. If a page file has a section that is not in `uses`, a line appears in the report - this is how a typo in an anchor is caught. The entry `"how:steps"` means the theme expects the form `steps` (numbered steps) in the section `how`.
- **`requires`** - paths in `site.yaml` without which the theme does not work, for example the phone in the header. If they are not filled in, the build stops with the error `E011` before any page is drawn.
- **`links`** - fields by which pages refer to each other. The engine finds the pages by these fields, checks that they exist and builds a reverse list (`back`): a service gets a list of the articles where it is mentioned. `type` limits **to pages of which type** the field leads: `related` with `type: service` will not link articles to each other. A relation without a limit is written without `type`: `- {field: related, back: related_from}`.
- **`images`** - how to cut images: widths, proportions, formats. Also there: `fallback_width` - the width of the fallback PNG/JPEG for old browsers, `cover_width` - the cover width for search engines and social networks, `crop` and `as_is` - paths of images that must be cropped or copied without cutting. Only what the templates really asked for is cut.
- **`types.<type>.template`** - if a type is drawn not by `templates/<type>.html` but by another file: a path from `templates/`.
- **`forms`** - the forms the theme draws; their description must be in `site.yaml`, otherwise `E011`.
- **`heron`** - which engine version the theme is made for. A wrong version is error `E012`.
- **`modules`** - the blocks of the theme. The example has a short list of names, as in version 0.2; the description of every block with fields and hints - [below](#block-fields).

Every key in detail - [`20` §6](../spec/20-data-contract.md#theme-yaml).

## Block fields and hints <a id="block-fields"></a>

Templates tell the engine what a page looks like. But a person who will fill the page in needs something else: which blocks the page has, what to write in every field and how it affects the site and search. This is written in `theme.yaml` too - as the contract: the sections of every type, the fields of every block with their place in markdown, section views and the `hint` and `help` hints in every language of the theme. The questions of `page add` and `category add`, the studio, the theme reference and an agent (`describe --json`) work by it, and `check` makes sure the description is complete (`E041`).

The description is optional: a theme without it builds as before, only `check` warns once that the questions and the studio show just the SEO block. The starter theme is fully described - its `theme.yaml` is the best sample. How to describe a type, a block, a field and a view, how to write hints for a newcomer and a worked example - [07 · Your own theme](07-theme-author.md#types).

## The theme demo and reference <a id="theme-demo"></a>

Every theme has a demo - pages that show each of its types, blocks and section views. Without a complete demo the theme is not packed (`E037`), and it can be checked without packing - with the command `check . --theme`. From the description and the demo the engine builds the theme reference itself. What the demo must have, where it lives and how to write it - [07 · Your own theme](07-theme-author.md#demo); how to open the reference - [above](#theme-reference).

## A page type template

Every page type is drawn by its own template: the type `service` by the file `templates/service.html`. A template reads top to bottom, and the blocks end up on the page in the same order:

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

`mod.prose('what')` takes the section with the anchor `what` from the page and draws it with the `prose` module. The main rule: **no section - nothing at all**. If a page has no `what` section, there is neither a heading nor an empty frame in its place, and you need no conditions to check for it. That is why the order of sections in a content file does not matter, and a page that lacks some sections does not break the layout.

Sometimes a template does not know in advance which sections will come - for example, for an ordinary text page. Then the module is chosen by the form of the section. This is how `partials/sections.html` of the starter theme works (the file itself lists all forms):

```jinja
{% for section in page.sections.values() %}
  {% if section.kind == 'faq' %}{{ mod.faq(section.id) }}
  {% elif section.kind == 'steps' %}{{ mod.steps(section.id) }}
  {% else %}{{ mod.prose(section.id) }}{% endif %}
{% endfor %}
```

A module expects its own form of data. If you call `mod.steps('how')` while the `how` section is plain text, the build fails with `E010` (`'str object' has no attribute ...`), and the message names the template, not the module. So the report line "expected steps, got prose" is fixed before the build. And if the content can arrive in different forms, choose the module by `section.kind`, as in the example above.

### Paths and macros

- **Paths in `extends`, `include` and `import` are counted from the theme root**, not from the folder of the template: `{% extends "base.html" %}`, `{% extends "templates/page.html" %}`, `{% include "partials/header.html" %}`. If you write `{% extends "page.html" %}` from `templates/landing.html`, you get the error `E008` with a hint where the file actually is.
- **`mod` is available in every template** - there is no need to import modules. Your own macros are different: `{% import %}` in `base.html` is not visible to child templates (this is how Jinja2 works), so import them in every template where they are needed.

## What to output in `<head>` <a id="head-seo"></a>

The `base.html` frame is responsible for everything a search engine and a messenger read before the page itself. For images in search results and link previews to work, `<head>` needs three things:

- `<meta name="robots" content="{{ robots_meta }}">`. Whether a page is open to search engines or closed is decided not by the theme but by the engine: it puts a ready string into `robots_meta`. Without this line large previews in search results will not turn on, and a closed draft build will not get `noindex`;
- `og:image` and `twitter:image` - the cover address from `cover_url(page)`. Output them only when the address is not empty: an empty string means there is no cover, and an empty tag is worse than a missing one;
- the size and caption of the image: `page.cover.width`, `page.cover.height`, `page.cover.alt`. With the size a social network shows the preview at once without downloading the image, and `alt` is for those who cannot see the image.

The whole block as an example - this is how it is done in the starter theme:

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

The names `cover_url` and `robots_meta` are taken by the engine: do not create your own variables with these names in the theme. Which image becomes the cover and how to prepare it - [05 · SEO](05-seo.md#you-fill), the exact selection rules - [`20` §6](../spec/20-data-contract.md#page-cover).

## Module

A module draws one section. It is a file `modules/<name>.html`, and a template calls it as `mod.<name>(<anchor>)`. Inside a module these are available:

| Variable | What it is |
|---|---|
| `section` | the section: `id`, `title`, `kind`, `lead`, `body`, `note` (paragraphs after the main node), `note_title`, `callout`, `links` |
| `items` | parsed data of the form: steps, question-answer pairs, facts… |
| `html` | ready markup of the whole content of the section |
| everything the template sees | `page`, `site`, `t`, `picture`… |

For example, the questions-and-answers module:

```jinja
<section id="{{ section.id }}" class="faq">
  {% if section.title %}<h2>{{ section.title }}</h2>{% endif %}
  {% for pair in items %}
    <details><summary>{{ pair.q }}</summary>{{ pair.a|safe }}</details>
  {% endfor %}
</section>
```

What is in `items` for each of the thirteen forms - the table [`20` §4.4](../spec/20-data-contract.md#section-forms). Modules without an argument, for example `mod.breadcrumbs()`, take data not from a section but from `page` and `site`.

## What the template sees

Everything a template can use:

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
| `cover_url(page, min_width=1200)` | absolute address of a cover no narrower than `min_width`; no cover - an empty string. There is also a filter: `{{ page|cover_url }}` |
| `robots_meta` | the string for `<meta name="robots">`: large previews on an indexable page of a production build (prod), `noindex, nofollow` on a closed one |
| `env` | the build environment: `env.indexable`, `env.analytics` |
| `theme` | `theme.yaml` as a model: `theme.types`, `theme.images` |
| `pages` | the whole site: all pages of all languages (`pages.of_lang('ru')`, `pages.of_type('article', 'ru')`, `pages.by_url`); a page by key is more convenient through `page_of` |
| `absolute(url)` | an absolute address on the build domain; there is also a filter `{{ url|absolute }}` |

The full page model - [`21` §6](../spec/21-engine.md#page-model), all variables - [`21` §7](../spec/21-engine.md#rendering).

If a template refers to a variable that does not exist, **the build stops** with the error `E010` and the names of the page and the template, instead of silently printing nothing. This way a typo in the theme is caught at once, not on the live site.

### Your own page fields

A theme can expect its own fields in the SEO block of a page - for example, `topic` or `eyebrow` (a line above the heading). The engine puts them into the page as they are, and if you describe them on the type (`types.<type>.fields` - name, type, hints), `page add` and the studio ask them with hints, and `check` checks whether they are required and the allowed values - how to do it, [07 · Your own theme, "Own fields of a page"](07-theme-author.md#own-fields). The starter theme describes `eyebrow` this way on the type `page`.

```jinja
{% if page.meta.get('eyebrow') %}<p class="eyebrow">{{ page.meta.get('eyebrow') }}</p>{% endif %}
<span>{{ page.meta.get('topic', 'general') }}</span>
```

Read your own fields with `page.meta.get('field', fallback)`: this way the template does not fail if the page has no such field. `page.meta.topic`, however, will fail - this is on purpose, to catch typos in the engine's own fields. All your own fields of a page at once - `page.meta.extra`.

The **top-level** `fields` key in `theme.yaml` is **only for engine fields** that the theme expects from a new engine version (`fields: [date, updated]`). Your own fields are not written there: the engine does not know them and answers with the error `E023`. Own fields are described on the type - `types.<type>.fields`.

### Values in the language of the page

A template gets `site.yaml` already in the language of the page - **all blocks, at any depth**. On a Russian page `site.contact.address` is the value of `address_ru`, `site.site.name` is `name_ru`, `site.organization.about` is `about_ru`. If there is no key for the language, the key without the language suffix (`_ru`) is taken. There is no need to choose the language with a filter, although the keys with the suffix are available too.

The same rule works in the substitutions of the markup for search engines (`{{ contact.address }}` in the `schema` block), so the address in the footer and in the markup always match.

## Accumulating data in a template without `append` <a id="accumulate-data-without-append"></a>

Theme templates run in a protected environment where data cannot be changed ([`21` §7](../spec/21-engine.md#rendering)). Methods that change a list or a dictionary - `.append`, `.extend`, `.insert`, `.update`, `.pop`, `.remove`, `.add`, `.setdefault`, `.clear`, `.sort`, `.reverse` - stop the build with the error `E033` and the template name. A template does not change a value but builds a new one. Below is how to rewrite typical places.

Before - fails with `E033`:

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

After - the same result without changing data:

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

- **Select with a filter.** `rejectattr`, `selectattr`, `select`, `reject`, `map(attribute='url')`. Add `|list` at the end if you need the result as a list and not for one pass.
- **Remove repeats with `unique`**, with an attribute and always with `case_sensitive=True`, otherwise `/A/` and `/a/` merge into one address: `{% set links = (page.related.get('see_also', []) + more)|unique(case_sensitive=True, attribute='url')|list %}`.
- **Add an element by adding lists:** `body + [x]`, `body + ([faq] if faq else [])`.
- **Add a key with a new dictionary:** `dict(base, key=val)`. A key with a hyphen cannot be passed this way - build the whole dictionary: `{'class': 'card', 'data-x': x}`.
- **Accumulate in a loop only through `namespace()`.** A plain `{% set %}` inside `for` lives only until the end of the step: `{% set found = found + [p] %}` in the loop body does not change `found` outside, and after the loop the list is empty again. A `namespace` attribute (`acc.found`) survives the loop.
- **Careful with `StrictUndefined`.** `selectattr('meta.extra.cluster', ...)` fails on the very first page that has no such key. For an optional key - a loop with `namespace` and `.get('cluster')`, as in the example.
- **Put the tags on the same lines where the old ones were.** A line with only `{% %}` prints nothing (`trim_blocks` and `lstrip_blocks`), so replacing a tag with a tag does not change the whitespace in the HTML.

`check` helps to find such places before the build: it parses the theme templates and names every call that would give `E033`, with the file, the line and a replacement recipe - even in a template that the theme does not use yet ([`21` §12](../spec/21-engine.md#check-report)). The full command is in "How to check a theme" below.

The check after the edit is `build`: no `E033` at all, and the pages are the same as before the edit.

## Interface strings

The texts that belong to the theme and not to a page - "Read more", the heading of the questions block, button labels - live in `theme/i18n/<lang>.yaml`, one file per language:

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

In a template a string is output like this: `{{ t.read_more }}`. If a string is missing for some language, the build does not fail: the name of the key stays on the page, and the report gets a warning. Text hardcoded right into a template makes the theme single-language - keep it in `i18n`.

## Images in the theme

```jinja
{{ picture(page.meta.image, '16:9', alt=page.meta.image_alt) }}
```

This line outputs a ready `<picture>` tag. The engine cuts the image for the widths and proportions from `theme.yaml`: it fits illustrations whole and crops photos. The image path comes from the content, and the theme decides only the proportion and the place on the page.

**Only what the template asked for is cut.** `ratios` in `theme.yaml` are the proportions the theme *may* ask for, and only those that the templates really called through `picture()` or `media_url()` get into the build. A card asks for 16:9 - so its image in the build will have only 16:9. The fallback file in the source format (for browsers without AVIF and WebP) is one per proportion, with the width `images.fallback_width` (800 by default). If you need a bigger width, ask for it explicitly: `media_url(src, '16:9', 1200)` for og:image. → [`20` §7](../spec/20-data-contract.md#images)

## How to include theme files: `asset()` <a id="asset"></a>

Include the styles, scripts, fonts and pictures of a theme through `asset()`:

```jinja
<link rel="stylesheet" href="{{ asset('site.css') }}">
<script src="{{ asset('site.js') }}" defer></script>
<link rel="preload" href="{{ asset('fonts/inter.woff2') }}" as="font" type="font/woff2" crossorigin>
<img src="{{ asset('media/logo.svg') }}" alt="">
```

`asset('site.css')` gives the address `/assets/site.0123456789.css`: the name carries the hash of the file content. The file changed - the name changed, and after a theme update the visitor's browser takes the new file, not yesterday's one from its cache. nginx serves a hashed file for a year and a file under its plain name for a day ([06 · "Browser cache"](06-deploy.md#browser-cache)). The path is written from the theme's `assets/` folder, a site resource - from the root: `asset('media/logo.svg')` gives `/media/logo.svg?v=0123456789` - resources carry the version at the end of the address, and the build holds one file (pictures are heavy, a copy under a new name would double the image). A typo in the name is build error `E045` with the file name, not a broken link on the site.

What else to know:

- **hand-written addresses work too.** The build rewrites `href="/assets/site.css"` to the hashed name itself and `src="/media/logo.svg"` to the address with `?v=`, as it does with the addresses the engine draws (`picture()`, `media_url()`). But `check` warns about `/assets/`: `asset()` is checked, a hand-written address is not. Inside a template's `<script>` the build rewrites nothing - `check` has a separate warning for that;
- **links inside styles** (`url(fonts/a.woff2)`, `@import "base.css"`) are written as usual, relative or from the root: the engine rewrites them itself, and a new font changes the name of the styles that refer to it;
- **inside `.js` the engine does not rewrite addresses.** A script that takes `'/assets/icons.svg'` as a string gets the file without a hash: the browser keeps it for a day, and after a theme update an old version is possible for up to a day. Pass the address from the template in an attribute: `<script src="{{ asset('site.js') }}" data-icons="{{ asset('icons.svg') }}">`, and in the script read `document.currentScript.dataset.icons`. A module with a relative `import './chunk.js'` works, but `chunk.js` itself is cached without a version. `check` warns about a `/assets/` or `/media/` string in a theme script;
- **og:image and the markup stay without a version:** social and search caches key on the URL, a stable address serves them better. `<a href="/media/…">` links too: the file is downloaded under its own name and forwarded as a link.

## Strict CSP: the rules for a theme <a id="strict-csp"></a>

The engine serves pages with the browser security rule (CSP) `script-src 'self'`, and the rule is strict: the browser runs and loads only what lies on the site itself. For a theme this means:

- **scripts only as files.** `<script src="{{ asset('site.js') }}">` works, and a `<script>` with code right in the HTML (an inline script) the browser will not run. The exception is the markup `<script type="application/ld+json">`: it is data, not code;
- **no handlers in the markup.** `onclick=`, `onload=`, `onsubmit=` and `javascript:` links do not work: attach handlers from the script file (`addEventListener`);
- **data for a script goes in `data-*` attributes** on the `<script src=…>` tag or on an element, as in `base.html` of the starter theme;
- **everything is your own.** Fonts, pictures, styles and scripts come from `assets/` of the theme and `media/` of the site. A font from another server, a script or a picture from a CDN the browser will not load: download the file and put it into `assets/`;
- **styles are fine** both as a file and as a `style=` attribute;
- **analytics counters** are the only exception: the engine allows their addresses itself, for the counters turned on in `site.yaml`. Include them as `partials/analytics.html` of the starter theme does.

If your theme is of an older version and has an inline script:

1. move the code into a theme file (`assets/site.js`);
2. pass data (counter numbers and the like) as `data-*` attributes on the `<script src="{{ asset('site.js') }}">` tag;
3. run `check`: it shows an inline script in the theme as a warning.

## How to check a theme

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check . --theme
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build .
```

- `check` - a report without a build: it quickly shows errors and warnings, including those in templates;
- `check --theme` - the theme description and demo too: every type has a page, every block and section view is shown ([07 · Your own theme](07-theme-author.md#demo));
- `build` - the theme draws every page; a template error names the page and the template;
- the report after the build shows sections that are not in `uses`, forms of the wrong kind and missing `i18n` strings.

---

Next: [05 · SEO](05-seo.md)
