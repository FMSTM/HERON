# What HERON already does

Before you write "the engine needs a change", look for the need in this table. If it is here, do it with the site and the theme. If it is not, see "What is missing" at the bottom: some things are absent on purpose.

References: `20` = [`spec/20-data-contract.md`](../spec/20-data-contract.md), `21` = [`spec/21-engine.md`](../spec/21-engine.md), `22` = [`spec/22-deploy.md`](../spec/22-deploy.md), `23` = [`spec/23-distribution.md`](../spec/23-distribution.md).

## Structure and addresses

| What the site needs | How in HERON | Where it is described |
|---|---|---|
| A page at the address `/about/` | the file `content/<lang>/about.md` | `20` §2 |
| A section with a catalog of children | a folder with `_index.md`; the children are files next to it; the template gets `page.children` | `20` §2, `21` §4 |
| The address differs from the file name | the `slug` field | `20` §2 |
| Different addresses in different languages (`/guides/` and `/ru/rukovodstva/`) | the same file name, `slug` in the file of the second language | `20` §2 |
| A page type and its own template | `type` in the file or `children_type` in the section's `_index.md`; the template `templates/<type>.html` | `20` §4.2 |
| A single page with its own layout (`about.md`) | `type: about` in the file, `templates/about.html` in the theme | `20` §4.2 |
| Order in the catalog and the menu | `order` | `20` §4.2 |
| Menus | `nav` in `site.yaml`, by keys; the home page is `"/"` | `20` §4.2, §5 |
| A short name in menus and breadcrumbs | `nav_title` | `20` §4.2 |
| Breadcrumbs | built automatically: `page.breadcrumbs` | `21` §6 |
| A draft that is not built | `published: false` (`--drafts` includes it) | `20` §4.2 |
| A new page with the full SEO block and the stubs of the type's sections - in all languages at once | `heron page add <key>` (editing with the same command, `--answers`/`--dump`); the home page and 404 are put by `new`/`init` | `21` §10 |
| A new section of any depth: the page `_index.md`, the view, the type of pages inside | `heron category add <path>` | `21` §10 |
| Moving a page or a section with a 301 from the old addresses | `heron page add <key> --category <path>`, `key` in `--answers` | `21` §10 |
| The tree of pages, languages, what is not translated | `heron page list --json` | `21` §10 |
| The fields of a page and its blocks with hints - for an agent and programs | `heron describe [type\|module] --json` | `21` §10 |
| Create and edit pages with a mouse, for a human | `heron studio`, `--web` of `page add` and `category add` | `21` §10 |
| Messages, help and comments in site files in Russian or in English | `--notes ru\|en`, `HERON_NOTES`, `build.notes` | `23` §4 |
| A section of 100+ pages | one catalog page, without pagination; the theme does the grouping | `21` §4 |

## Languages

| What the site needs | How in HERON | Where it is described |
|---|---|---|
| One language, two, N | `site.languages`, `site.default_lang` | `20` §3 |
| The main language at the root, the others under `/<lang>/` | always like this | `20` §3 |
| hreflang, `x-default` | generated automatically | `20` §3 |
| A language switcher, an inactive item without a translation | `languages`, `lang`, `page.translations` in the template | `20` §3 |
| The second language is written before the main one | a dev build passes with a warning; production with an empty main language - `E021` | `20` §3 |
| A link in the text leads to the page of its own language | write it by key without a prefix: `[x](/guides/x/)` | `20` §2 |
| The site name and the `title` suffix per language | `site.name_<lang>`, `seo.title_suffix_<lang>` | `20` §5 |
| Address, phone, company description per language | `contact.address_ru` and the like in their blocks; substitutions and the theme pick the language themselves | `20` §5 |
| Theme interface strings ("Read more" / "Читать далее") | `theme/i18n/<lang>.yaml`, in the template `t.<key>` | `21` §7 |

## Page content

| What the site needs | How in HERON | Where it is described |
|---|---|---|
| Intro and subheading | the text before the first section: `lead` and `promise` | `20` §4.3 |
| A block the theme puts in the right place | a section `## Heading {#anchor}` | `20` §4.3 |
| A list, "term - explanation" pairs | `list` | `20` §4.4 |
| Warning signs | `list` with the class `.alert` → `alert-list` | `20` §4.4 |
| "How we work" steps, with labels | a numbered list → `steps` | `20` §4.4 |
| FAQ (and `FAQPage` in the markup) | groups `### Question?` without lists → `faq` | `20` §4.4 |
| A checklist of documents | three or more `###` groups with lists → `checklist` | `20` §4.4 |
| "Suits / does not suit" | two `###` groups with lists → `two-lists` | `20` §4.4 |
| Short facts "format - in person" | lines `key \| value` → `facts` | `20` §4.4 |
| A comparison table | a markdown table → `table` | `20` §4.4 |
| A timeline | `facts` or a numbered list with the class `.timeline` | `20` §4.4 |
| A tip box | a `>` quote → `callout` (and `section.callout` on any section) | `20` §4.4 |
| A gallery | a list of images with the class `.gallery` | `20` §4.4 |
| Tabs | `###` groups with the class `.tabs` on the section | `20` §4.4 |
| A command inside a step | a code block under an item of a numbered list → the step's `more` | `20` §4.4 |
| Shared data: reviews, trust figures, company details | yaml in `data/`, in the template `data.<file name>` | `20` §1 |
| Raw HTML in markdown | forbidden by default (`E015`); `build.allow_raw_html: true` | `20` §5 |

## Relations

| What the site needs | How in HERON | Where it is described |
|---|---|---|
| "Related services", "articles on the topic" | a relation field in the frontmatter, declared in `theme.yaml` `links` | `20` §6 |
| A reverse list ("where it is mentioned") | `back:` on the relation | `20` §6 |
| A relation within one type | allowed | `20` §6 |
| A caption for a relation | `{slug: name, note: "…"}` | `20` §6 |
| Warn if a relation is not filled in | `required` and `on` | `20` §6 |

## Images and files

| What the site needs | How in HERON | Where it is described |
|---|---|---|
| Responsive images, WebP/AVIF | a path in `media/`, in the template `picture()` | `20` §7, `21` §8 |
| Card ratios | `images.ratios` in `theme.yaml`; illustrations are fitted, photos are cropped | `20` §7.6 |
| PDF, video, any file | in `media/`, the address is `media_url()` | `20` §7.2, §7.4 |
| A page video | `video`, `video_poster`, `video_title` | `20` §7.5 |
| Scans without renditions | `images.as_is` | `20` §7.3 |
| favicon, webmanifest, `.well-known` | `static/` | `20` §7.8 |

## SEO and service

| What the site needs | How in HERON | Where it is described |
|---|---|---|
| sitemap | generated: one file or an index by language | `21` §9 |
| robots.txt | generated; dev - `Disallow: /` | `21` §9 |
| `llms.txt`, full texts for AI models | generated; facts about the site - `seo.llms_note` | `21` §9, `20` §5 |
| JSON-LD | types - `theme.yaml` `types.<type>.jsonld`; data - `schema` in `site.yaml` and in the page | `20` §5 |
| Markup check against the schema.org 29.3 vocabulary (`SCH001`-`SCH006`) | `heron check`, `heron build`; in `prod` a finding is an error, otherwise a warning. Do not assemble markup by hand around the `heron setup` configurator: the `schema.entity` and `schema.<Type>` nodes are set by the configurator. An exception only with a reason: `schema_exceptions` in `site.yaml` (`key`, `reason`, `until`) or a one-off `--allow-schema KEY`. An exception written by the configurator has no expiry (the `until` term is removed; set it by hand if needed) | `20` §5, `21` §10, §11 |
| Prices in the markup | forbidden while `seo.allow_prices: false`; to allow - `true` | `20` §5 |
| Publication and update date | `date`, `updated`, `build.updated_from: git` | `20` §4.2, §5 |
| An Atom feed | `seo.feed: <type>` | `21` §9 |
| Open Graph, a default image per language | `og_*` in the page, `seo.og_default_image[_<lang>]` | `20` §4.2, §5 |
| A picture in search results and social networks (one cover for `og:image`, `twitter:image`, sitemap; `primaryImageOfPage` appears only if the theme declared `WebPage` or a derived type for the page type in `types.<type>.jsonld`, the starter theme does not do this) | the `og_image` or `image` field; in the theme `cover_url(page)`, `page.cover`, not by hand | `20` §4.2 "Page cover", §7.9, `21` §7 |
| `max-image-preview:large` and closing dev | `robots_meta` in `<meta name="robots">` | `21` §7 |
| Images in the sitemap | generated by themselves, the cover first, up to 20 per page; none on dev | `21` §9 |
| Other spellings of the site name (`WebSite.alternateName`) | `site.alternate_names[_<lang>]` | `20` §5 |
| Checking old addresses after a move | `heron check --old-urls <file>` | `21` §10, §11 |
| 301 from old addresses, Cyrillic and `%D0%…` | `redirect_from` in the page | `20` §2 |
| 410 for archives, service paths, doorway pages | `gone` in `site.yaml`: exact ones, `/wp/*`, `/?p=*` | `20` §5 |
| A 404 page in each language | `content/<lang>/404.md` | `20` §2 |
| Analytics counters only in production | `analytics` in `site.yaml` (`ga4`, `gtm`, `metrika`); the starter theme renders them after the visitor's consent, dev does not render them | `20` §5 |
| Keep dev out of the index | the default; production - `build --env prod` | `21` §10 |
| An nginx image with the site, a smoke check | `scripts/site.sh <site> image\|smoke\|push` | `23` §5 |

## Setup and publication

| What the site needs | How in HERON | Where described |
|---|---|---|
| Set up the site and publication with a configurator | `heron setup`; without a browser - `--answers <file>`, the saved answers - `--dump` | `21` §10 |
| An image without a clone of the engine | the shared workflow `site-image.yml`, the image recipe - `heron recipe` | `23` §5 |
| Build and publication helpers, a workflow in the site folder | written by the configurator: `.heron/scripts/`, `.github/workflows/` | `21` §10 |
| Install a theme, show the catalog, pack your own | `heron theme get`, `list`, `pack` | `21` §10 |
| Describe a theme for people: block fields, hints, section views | `theme.yaml`: `fields`, `hint_<lang>`, `help_<lang>`, `views`, `children_type` | `21` §7 |
| Check the theme demo, the theme reference | `heron check --theme`; `heron docs theme-ref`, `/_heron/theme/` in `heron serve` | `21` §7, §10 |
| A preview with rebuilding | `heron serve` | `21` §10 |
| Documentation and schemas of this version | `heron docs`, `heron schema` | `21` §10 |

## What is missing - on purpose or for now

| What is missing | Why, and what to do |
|---|---|
| Catalog pagination | on purpose: one section - one page. Split large sections into subsections as folders (`21` §4) |
| Site search, comments, user accounts | a static site; there is no runtime. An external service is a decision of the theme |
| Loading content with a script | forbidden: numbers and text must be in the HTML (`20` §10) |
| Sitelinks (extra links in Google) | cannot be switched on with markup: Google decides what to show; influenced by HTML navigation, breadcrumbs, unique `title` values, no duplicates (guide [05](../guide/05-seo.md)) |
| Form handling | there will be a separate service `heron-relay`, **not implemented yet**. The engine checks a form description in `site.yaml` (`forms`, `sinks`), but nobody receives the POST. For now - phone, mail, messengers, an external form |
| An admin panel | on purpose: the source of truth is files |
| A database | it is not part of the build and will not be: the build is static. An external database, CRM or another CMS is an **optional bridge module, in development**: the site and the database talk with a private key, the data does not get into the HTML at build time. For now - `data/` (yaml at build time). The module key field already exists in `heron setup`, but it connects nothing |
| Scheduled publication by date | none: `published` is a flag, `date` is only a date. Publication = a commit and a build |
| Building on a server (`install.sh`, `deploy.sh`) | described in `22` as the target scheme, there are no scripts yet. Today - an image through `site.sh`, the shared workflow `site-image.yml` or the configurator helper `.heron/scripts/publish.sh` |

If the need is in none of the tables, it is an engine task. The template for writing it up is in [`architect.md`](architect.md), the section "Engine task".
