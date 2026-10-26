# Role: Designer

Make a theme that draws every page type of the structure and does not break on incomplete content. Common rules - [`README.md`](../README.md); how a theme works, in plain words - the guide [04 · Theme and design](../guide/04-theme.md).

**Input:** page types and their sections from the architect (or an existing `theme.yaml`), a mockup or a description of the look.
**Output:** the `theme/` folder: `theme.yaml`, `base.html`, type templates, form modules, `partials/`, `assets/`, `i18n/<lang>.yaml`.

**Limits.** You write only to `theme/`. `content/`, `data/`, `site.yaml`, `.github/`, scripts are not yours. A theme by link or archive is installed only if the human named it. The report is `agents/work/report.md` in the form of [`templates/report.md`](../templates/report.md). Done when the build passes on the starter and on the full content and the report has no missing `i18n` strings.

## 1. Start with the starter theme

`heron new` puts a working starter theme: the types `home`, `page`, `404`, a module for each of the thirteen section forms, `breadcrumbs` and `children`, the section layout in `partials/sections.html`, its demo pages - the home page, `blocks.md` (every form), `themes.md`, `docs.md`; a light and a dark scheme. It builds from the first minute - change it step by step and build after each step. To install a theme from the catalog, by link or as an archive - `heron theme get` (`21` §10).

## 2. `theme.yaml`

The sample is [`templates/theme.yaml`](../templates/theme.yaml), all keys are in `20` §6.

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

- `uses` - **all** sections of the type, optional ones included; after the colon, the expected form (`20` §4.4). `"*"` - any sections. From `uses` the `heron page` command puts the stubs, and the report names the empty sections;
- `jsonld` - markup types for pages of this type;
- `requires` - paths in `site.yaml` the theme does not work without (`E011` if empty);
- `links` - relation fields; `back` builds the reverse list.

## 3. Type templates

For each type - `templates/<type>.html` (otherwise `E008`):

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

- `mod.<module>('<anchor>')` draws the section, or **nothing** if there is none: no conditions around it are needed;
- `page_of('<key>')` - a page by key; `data.<file>` - reference data; `site.*` - `site.yaml` in the page language; `t.*` - interface strings;
- paths in `extends`/`include`/`import` are **from the theme root**: `{% extends "templates/page.html" %}`, not `"page.html"`;
- your own macros are imported in each template: an import in `base.html` is not visible to child templates. `mod` does not need to be imported;
- your own page fields - `page.meta.get('topic')`, without declaring them; do not list them in `fields` (`E023`);
- `site.*` is already in the page language in all blocks: `site.contact.address` on a Russian page is `address_ru`, there is no need to pick the language by hand;
- the full list of variables is in `21` §7, the page model in `21` §6.

## 4. Modules

For each form the theme draws - `modules/<name>.html`. Inside: `section` (the section with `title`, `kind`, `lead`, `note`, `callout`), `items` (the parsed data of the form), `html` (the ready content). What `items` holds for each form - `20` §4.4.

## 5. Images and assets

- only `picture(src, ratio, alt=…)` - renditions, WebP/AVIF, sizes; building `<picture>` by hand means losing the variants;
- the ratios you use go in `images.ratios`;
- CSS, JS, fonts - in `theme/assets/`; favicon and `.well-known` - in the site's `static/`.

## 6. Interface strings

Everything that belongs to the theme and not to the page ("Read more", "Questions and answers") goes in `theme/i18n/<lang>.yaml`, and in a template it is `t.<key>`. Each site language has its own file; `init` puts a stub. The keys `on`, `off`, `yes`, `no` go in quotes.

## 7. What a theme does not do

- it holds no content texts and no site details: texts are in sections, phone and address are in `site.contact.*`;
- it does not load content with a script: text and numbers must be in the HTML;
- it does not show the build stamp in production: `{% if not env.is_prod %}{{ env.stamp }}{% endif %}`;
- it renders counters only with `env.analytics` and only after the visitor's consent - like `partials/analytics.html` of the white starter theme: not a single counter script before the choice.

## Checklist

- [ ] every type of the structure has an entry in `types` and a template
- [ ] every form from `uses` has a module
- [ ] the build passes both on the starter and on the full content
- [ ] templates hold no texts or site details; interface strings go through `t`
- [ ] the report has no missing `i18n` strings and no template errors
- [ ] images go through `picture()`; ratios are declared
