# 01 · Concepts

Seven concepts that everything else stands on. Once you have read them, you can open any section of the documentation and understand what it is about.

## The engine and the site are separate

The **engine** is the `heron` program, delivered as the image `ghcr.io/fmstm/heron:<tag>` or as a pip package. It is not copied into a site and not edited for a site.

A **site** is a folder that does not contain a single line of engine code:

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

A site declares which engine it needs on the first line of `site.yaml`: `heron: ">=0.1,<0.2"`. One engine serves any number of sites, and each site can have its own version.

→ In detail: [`20` §0-1](../spec/20-data-contract.md#what-the-system-is)

## The contract

The contract is the agreement between the engine and the site folder: which files live where, which fields a page has, which keys `site.yaml` has, what the engine does by itself and what it answers with an error. It is the same for all sites and is written in [`spec/20-data-contract.md`](../spec/20-data-contract.md). A contract violation is a clear error with a code and a file (`E002`, `E006`...), with the line given where it is known, not a silently broken page. The path to content in messages is counted from `content/`.

## Page, key and address

**A page is a markdown file.** The file path sets the address. An example for `default_lang: en`, `languages: [en, ru]`:

```
content/en/index.md                →  /
content/en/about.md                →  /about/
content/en/services/_index.md      →  /services/              the section page itself
content/en/services/design.md      →  /services/design/
content/ru/about.md                →  /ru/o-nas/              slug: o-nas
content/ru/services/_index.md      →  /ru/uslugi/             slug: uslugi
content/ru/services/design.md      →  /ru/uslugi/dizajn/      slug: dizajn
```

A page has two different things that match by default:

- the **key** is the file path without `.md`: `services/design`. It is the same in all languages; the engine links translations by it, and the page is named by it in the menu and in links;
- the **address** is what the visitor sees. The `slug` field changes it, and the key stays the same. That is why the Russian version has the address `/ru/uslugi/dizajn/` and the same key, `services/design`.

The home page is `index.md`, its key is `/`. The "not found" page is `404.md`.

→ In detail: [`20` §2](../spec/20-data-contract.md#content-tree-and-urls)

## Languages

A language is a folder in `content/`. The list of languages and the default language are set by `site.yaml`:

```yaml
site:
  default_lang: en       # served from the root: /about/
  languages: [en, ru]    # the others get a prefix: /ru/o-nas/
```

A translation is a file with the same name in the folder of another language; its address can be its own (`slug`). Translated pages get hreflang to each other, and `x-default` is the version in the default language. Changing `default_lang` means changing the addresses of all pages.

→ In detail: [`20` §3](../spec/20-data-contract.md#languages)

## SEO block and frontmatter

Every page file starts with an **SEO block**: YAML between `---`, split into eight groups with comments: basics, search queries, Open Graph, Twitter, schema.org, card, service, relations. Three fields are required: `title`, `h1`, `description`. The rest are as needed, and empty fields stay commented out.

Starter pages come with the full block, and `heron page` puts it into every new one. A new page is a copy of a file with the values edited.

→ In detail: [`20` §4.1-4.2](../spec/20-data-contract.md#page-overview)

## Sections and their forms

After the SEO block comes the text. The text before the first heading is the intro. Then come the **sections**:

```markdown
## How we work {#how}

1. **Request.** You write or call.
2. **Meeting.** We discuss the task.
```

`{#how}` is an anchor, the address of the section for the theme. The order of sections in the file does not matter: the theme puts each one in its place by anchor. The engine recognizes the **form** of a section by its markup: a numbered list is steps, `### Question?` is an FAQ, `key | value` is facts, a table is a table. There are thirteen forms in all.

→ In detail: [`20` §4.3-4.4](../spec/20-data-contract.md#sections)

## Page type and theme

The **theme** is the `theme/` folder: Jinja2 templates, modules, styles, interface strings. It decides how the site looks; the content decides what is written on it.

The **page type** chooses the template: a page of type `service` is drawn by `theme/templates/service.html`. The type is set by the `type` field in the file or by `children_type` in the `_index.md` of a section; the home page has `home`, the default is `page`. In `theme/theme.yaml` the theme describes its types, their sections, relations between pages and image proportions.

→ In detail: [`20` §6](../spec/20-data-contract.md#theme-yaml), [theme guide](04-theme.md)

## Build

`heron build` reads the folder, checks it against the contract and builds `dist/`: page HTML, `sitemap.xml`, `robots.txt`, `llms.txt`, JSON-LD markup, resized images, 301/410 maps and the nginx config. The dev build (the default) is closed to search engines; the production build is `--env prod`. The result is either a folder for any hosting or an nginx image with the site inside.

→ In detail: [`21` §4](../spec/21-engine.md#build-pipeline), [deploy guide](06-deploy.md)

---

Next: [02 · First site](02-first-site.md)
