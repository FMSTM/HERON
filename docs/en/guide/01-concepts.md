# 01 · Concepts

Here are the eight concepts that everything else in HERON stands on. Each one is explained with an example. Once you have read them, you can open any section of the documentation and understand what it is about.

If the engine is not installed yet, start with [00 · Installation](00-install.md). And if you would rather try it hands-on right away, go to [02 · First site](02-first-site.md) and come back here whenever something seems unclear.

## The engine and the site are separate

HERON has two parts, and they never mix.

The **engine** is the `heron` program. You get it in one of two ways: as the Docker image `ghcr.io/fmstm/heron:<tag>` or as a Python package installed with pipx. The engine is not copied into a site and not edited for a particular site: it is the same for everyone.

A **site** is an ordinary folder with your files. It does not contain a single line of engine code:

```
my-site/
├── site.yaml       config: domain, languages, theme, menu, SEO settings
├── content/        pages in markdown, one folder per language
├── media/          images, video, documents
├── data/           yaml reference data: reviews, team, requisites
├── static/         files at an exact address: favicon, .well-known
├── theme/          theme: Jinja2 templates, styles, interface strings
└── plugins/        your own plugins, usually empty
```

The engine reads this folder and builds a finished site from it. It does not change your files while building.

Which engine a site needs is written in the first key of `site.yaml`, for example `heron: ">=0.1,<0.2"` - "any 0.1 version will do". That is why one engine serves any number of sites, and each site can have its own version: an old site keeps running on the previous version while a new one tries the latest.

→ In detail: [`20` §0-1](../spec/20-data-contract.md#what-the-system-is)

## The contract

The contract is the agreement between the engine and the site folder. It records everything you can rely on: which files live where, which fields a page can have, which keys `site.yaml` can have, what the engine does by itself and what it answers with an error. The contract is the same for all sites; it is described in full in [`spec/20-data-contract.md`](../spec/20-data-contract.md).

Why this matters in practice: if something is wrong in the folder, you get not a silently broken page but a clear error with a code and a file - for example, `E002` or `E006` - and a line number where it is known. In such messages the path to a page file is counted from the `content/` folder: `en/about.md`, not `my-site/content/en/about.md`.

## Page, key and address

**A page is a markdown file, and the file path sets the address.** Put the file `content/en/about.md` in place - get the page `/about/`. Here is an example for a site whose main language is English and the second is Russian (`default_lang: en`, `languages: [en, ru]`):

```
content/en/index.md                →  /
content/en/about.md                →  /about/
content/en/services/_index.md      →  /services/              the section page itself
content/en/services/design.md      →  /services/design/
content/ru/about.md                →  /ru/o-nas/              slug: o-nas
content/ru/services/_index.md      →  /ru/uslugi/             slug: uslugi
content/ru/services/design.md      →  /ru/uslugi/dizajn/      slug: dizajn
```

The file `_index.md` inside a folder is the page of the section itself: `services/_index.md` opens at `/services/`, and the pages of the section at the addresses below it, for example `/services/design/`.

Every page has two things that match by default but mean different things:

- the **key** is the file path without `.md`, for example `services/design`. The key is the same in all languages. By it the engine knows the English and Russian pages are translations of each other, and by it the page is named in the menu and in links;
- the **address** is what the visitor sees in the browser. The `slug` field changes it, while the key stays the same. That is why the Russian version has the address `/ru/uslugi/dizajn/` and the same key - `services/design`.

Why keep them apart: the address can be made readable in every language, and links and menus written with keys do not break because of it.

The home page is the file `index.md`, its key is `/`. The "not found" page is the file `404.md`.

→ In detail: [`20` §2](../spec/20-data-contract.md#content-tree-and-urls)

## Languages

Each language of the site is a folder in `content/`: English pages live in `content/en/`, Russian ones in `content/ru/`. Which languages exist and which one is the main one is set by `site.yaml`:

```yaml
site:
  default_lang: en       # served from the root: /about/
  languages: [en, ru]    # the others get a prefix: /ru/o-nas/
```

Pages of the main language open at short addresses, the others with a language prefix.

A translation of a page is a file with the same name in the folder of another language. The translation can have its own address, through `slug`. Translated pages get hreflang tags to each other by themselves - this is how a search engine knows which version to show a person - and `x-default` points to the version in the main language.

Be careful with `default_lang`: changing it means changing the addresses of all the site's pages at once.

→ In detail: [`20` §3](../spec/20-data-contract.md#languages)

## SEO block and frontmatter

Every page file starts with an **SEO block** - the page settings in YAML between two `---` lines (in the markdown world such a block is called frontmatter). The block is split into eight groups, each with a comment: basics, search queries, Open Graph, Twitter, schema.org, card, service, relations.

Only three fields are required:

- `title` - the page title in search results and in the browser tab;
- `h1` - the main heading on the page itself;
- `description` - a short description the search engine shows under the title.

The rest is filled in as needed. Empty fields stay commented out - they hint at what else you can set.

Starter pages come with the full block, and the `page` command puts it into every new page. Or simpler: a new page is a copy of any file with the values edited.

→ In detail: [`20` §4.1-4.2](../spec/20-data-contract.md#page-overview)

## Sections and their forms

After the SEO block comes the page text. Everything before the first heading is the intro. Then come the **sections**, each starting with a `##` heading:

```markdown
## How we work {#how}

1. **Request.** You write or call.
2. **Meeting.** We discuss the task.
```

`{#how}` after the heading is an anchor, the name of the section for the theme. By the anchor the theme decides where on the page to show the section, so the order of sections in the file does not matter: the theme puts each one in its place by itself.

Besides its place, a section has a **form**, and the engine recognizes it by itself, from ordinary markdown. A numbered list is steps, `### Question?` headings are questions and answers (FAQ), `key | value` lines are facts, a table is a table. There are thirteen forms in all. You do not need to declare anything: write a numbered list - the theme gets steps.

→ In detail: [`20` §4.3-4.4](../spec/20-data-contract.md#sections)

## Page type and theme

The **theme** is the `theme/` folder: Jinja2 templates, modules, styles, interface strings. The theme decides how the site looks, and the content decides what is written on it. Change the theme - the texts stay the same, only the look changes.

The **page type** chooses which template draws the page: a page of type `service` is drawn by the template `theme/templates/service.html`. The type is set like this:

- with the `type` field in the page file itself;
- with the `children_type` field in the `_index.md` of a section - then the pages of the section get this type;
- by default: the home page has type `home`, the others `page`.

Which types exist is up to the theme: in the file `theme/theme.yaml` it describes its types, their sections, relations between pages and image proportions.

→ In detail: [`20` §6](../spec/20-data-contract.md#theme-yaml), [theme guide](04-theme.md)

## Build

The `build` command reads the site folder, checks it against the contract and builds the finished site into the `dist/` folder. Everything needed for publishing goes there: page HTML, `sitemap.xml`, `robots.txt`, `llms.txt`, JSON-LD markup for search engines, images resized for different screens, 301 and 410 redirect maps and the nginx config.

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site
```

There are two kinds of build:

- **the draft build** (dev) - the default. The site is closed to search engines and counters are not added: you can look at it and show it safely;
- **the production build** (prod) - with the `--env prod` flag. This is the version for publishing.

The result is published in one of two ways: put the `dist/` folder on any hosting, or pack it into an nginx image with the site inside.

→ In detail: [`21` §4](../spec/21-engine.md#build-pipeline), [deploy guide](06-deploy.md)

---

Next: [02 · First site](02-first-site.md)
