<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/heron-lockup-dark.png">
  <img src="docs/brand/heron-lockup.png" alt="HERON" width="420">
</picture>

### With HERON, building sites is simple.

A site is a folder of markdown. HERON turns it into a ready static site or an nginx image.

[![ci](https://github.com/FMSTM/HERON/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/FMSTM/HERON/actions/workflows/ci.yml)
[![image](https://img.shields.io/badge/ghcr.io-heron-2563eb)](https://github.com/FMSTM/HERON/pkgs/container/heron)
[![python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)

English | [Русский](README.ru.md)

</div>

---

## What HERON is

HERON is a static site engine delivered as a single image, `ghcr.io/fmstm/heron`. The image does two things:

1. **create a site**: lay out a folder with a config, a theme and starter pages;
2. **build a site**: read the folder and produce HTML, a sitemap, markup, redirects and an nginx config.

The site itself is an ordinary folder: texts in markdown, images, a Jinja2 theme and one config, `site.yaml`. No database, no admin panel, no PHP. How the folder is organized, what the engine does with it and what it requires from it is written in the **contract**: [`docs/en/spec/20-data-contract.md`](docs/en/spec/20-data-contract.md).

```
     site folder                         HERON                          result
 ┌──────────────────┐          ┌───────────────────────┐        ┌─────────────────────┐
 │ site.yaml        │          │ contract check        │        │ dist/  - static      │
 │ content/<lang>/  │  ──────▶ │ markdown parsing      │ ─────▶ │   for any hosting    │
 │ media/  data/    │          │ links, languages, SEO │        │ or an nginx image    │
 │ theme/           │          │ theme rendering       │        │   with the site      │
 └──────────────────┘          └───────────────────────┘        └─────────────────────┘
```

## How you work with a site

**A page is a file, the engine works out the address.** How a file turns into an address is decided by three keys of `site.yaml`:

```yaml
site:
  domain: example.com        # domain: canonical, hreflang and sitemap are built from it
  default_lang: en           # the language served from the root
  languages: [en, ru]        # which content/ folders are read; the others live under /<lang>/
```

| File | with `default_lang: en` | with `default_lang: ru` |
|---|---|---|
| `content/en/index.md` | `/` | `/en/` |
| `content/en/about.md` | `/about/` | `/en/about/` |
| `content/ru/about.md` | `/ru/about/` | `/about/` |
| `content/ru/about.md` with `slug: o-nas` | `/ru/o-nas/` | `/o-nas/` |

- **Translations are linked by file name.** `en/about.md` and `ru/about.md` are one page in two languages, even if the Russian one has its own `slug`. Both get hreflang to each other, and `x-default` points to the version in the default language. No translation means no hreflang, and the language is grayed out in the switcher.
- **A language that is not in `languages` is not read.** The folder `content/de/` without `de` in the list is silently skipped.
- **`default_lang` changes all addresses at once.** On a live site this is a migration: the old addresses must be listed in `redirect_from` ([05 · SEO](docs/en/guide/05-seo.md#migrate-from-old-site)).

**Every file starts with a service block**, the SEO block of eight groups: basics, search queries, Open Graph, Twitter, markup, card, service, relations. The comments are hints: what the field means, when to fill it, what the engine fills in itself. The language of the comments is chosen when the site is created (`--notes ru|en`). Three fields are required: `title`, `h1`, `description`. The home page and the 404 page come with this block, a new page is `heron page` or a copy of a ready file with the values edited.

**After the block comes the text.** An intro, then sections `## Heading {#anchor}`, blocks that the theme puts in its places. A list, steps, questions and answers, a table are ordinary markdown; the engine understands the form by itself and gives the theme parsed data.

In detail: [concepts](docs/en/guide/01-concepts.md) · [first site](docs/en/guide/02-first-site.md) · [pages and content](docs/en/guide/03-content.md) · all `site.yaml` keys are in [`20` §5](docs/en/spec/20-data-contract.md#site-yaml).

## Commands

Eleven commands. The path to the site defaults to the current folder.

| Command | What it does |
|---|---|
| `heron new <folder>` | creates a site: asks for the notes language, name, domain, languages and lays out the folder |
| `heron init <folder>` | builds the missing folders after the languages in `site.yaml` changed |
| `heron page <type> <slug>` | adds a page with a ready SEO block |
| `heron check <folder>` | checks the site against the contract without building; `--strict` turns warnings into errors |
| `heron build <folder>` | builds `dist/`: HTML, sitemap, markup, redirects, nginx config; `--env prod` for a production build |
| `heron serve <folder>` | local preview with rebuild, the port is set by `--port` |
| `heron docs [topic]` | documentation of the same version as the engine; `--search <text>`, `--export <folder>` |
| `heron setup <folder>` | questionnaire in the browser: domains, languages, schema.org, publishing, theme; `--answers file` without a browser, `--dump` - current answers |
| `heron theme get\|list\|pack` | install a theme (starter, from the catalog, by link, from an archive), list, pack your own |
| `heron schema` | JSON Schema of the contracts of this version; `--export <folder>` |
| `heron recipe` | Dockerfile of the nginx image for the built `dist/` |

In a container it is the same call through `$H` from "Quick start". Error codes (`E002`, `E006`, `E012`...) and their causes are in [`docs/en/spec/21-engine.md`](docs/en/spec/21-engine.md).

## The site folder contract

```
my-site/
├── site.yaml       config: domain, languages, theme, menu, SEO settings; the first line is heron: ">=0.1,<0.2"
├── content/<lang>/ pages in markdown, one folder per language
├── media/          images, video, documents
├── data/           yaml reference data: reviews, team, requisites
├── static/         files at an exact address: favicon, .well-known
├── theme/          theme: Jinja2 templates, styles, interface strings
└── plugins/        your own plugins, usually empty
```

The engine reads only these folders and writes only to `dist/` and `.heron-cache/`. What is allowed in each file is listed in the [data contract](docs/en/spec/20-data-contract.md).

## Theme

A theme is the `theme/` folder inside the site: `theme.yaml` (which page types and modules exist), Jinja2 templates, styles and interface strings. A template receives already parsed page data; you do not parse markdown yourself. The theme is developed right in the site; a finished one can be moved into a `heron-theme-<name>` package without changing the content. A local `theme/` always wins over an installed one. In detail: [04 · Theme and design](docs/en/guide/04-theme.md).

## Plugins

Plugins extend the **build**: your own section types, links between pages, Jinja filters, generators. They are ordinary pip packages (entry point group `heron.plugins`) installed into the site image with one Dockerfile line. For one-off needs of a single site, use the `plugins/<name>/` folder next to the content. A plugin from `site.yaml` that is not installed or failed on loading gives error `E014`. The engine has no runtime: form intake lives in a separate image, `heron-relay`. How themes and plugins are resolved: [`docs/en/spec/23-distribution.md`](docs/en/spec/23-distribution.md#theme-plugin-resolver).

## Safe run

A build needs nothing but the site folder, so everything else can be taken away from it:

```bash
docker run --rm \
  --network=none \
  --read-only --tmpfs /tmp \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/site" -w /site \
  ghcr.io/fmstm/heron:prod build . --strict
```

No network, a read-only root, no privileges, your own user, no `.env` and no docker socket. Raw HTML in markdown is off by default (`E015`). The finished site is served by `nginx-unprivileged` on port 8080. Full model: [`docs/en/spec/23-distribution.md`](docs/en/spec/23-distribution.md#security-model).

## What HERON does by itself and what you do

| By itself, without a single line | By hand, once or as you go |
|---|---|
| addresses from file paths, language prefixes | `site.yaml`: domain, languages, name, menu, counters |
| menu, section catalogs, breadcrumbs | page texts and the SEO block of every page |
| `sitemap.xml`, `robots.txt`, canonical addresses | theme: page type templates, modules, styles |
| hreflang and the language switcher | images go into `media/`, the engine resizes them itself |
| JSON-LD: page, breadcrumbs, FAQ, the site-wide node | data for the markup: the `schema` block in `site.yaml` |
| `llms.txt` and full texts for AI models | the facts about the site for them: `seo.llms_note` |
| image variants, WebP/AVIF, `srcset`, sizes | `alt` for images |
| 301 from old addresses, 410 for deleted ones | old addresses go to `redirect_from`, deleted ones to `gone` |
| a 404 page in every language, the nginx config | the 404 text: `content/<lang>/404.md` |
| a dev build closed to indexing | `--env prod` for the production one |
| a check of all this with clear errors | fix what the report points at |

What the engine can do, topic by topic: [`docs/en/roles/capabilities.md`](docs/en/roles/capabilities.md).

**For AI agents**: [`AGENTS.md`](AGENTS.md): roles, rules and boundaries are in `docs/<lang>/README.md`; the same folder lies in every new site as `agents/` and in the image (`heron docs --lang ru|en`).

## Quick start: one site, one engine

The usual case is one site and the stable `:prod` image. All you need is docker.

```bash
H="docker run --rm -it -p 127.0.0.1:8000:8000 -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"

$H new my-site         # asks for the working language, name, domain, languages, and lays out the folder
$H setup my-site       # questionnaire: the address with a key is printed in the terminal: domains, schema.org, publication, theme
$H serve my-site       # preview at localhost:8000 with a rebuild on every save
$H build my-site       # → my-site/dist/
```

The engine in the container sees only the current folder, so the path to the site is relative to it: `my-site`, or `.` if you are already in the site folder (for example in your own git repository: `.git` and `README` do not get in the way). Without questions, for agents and CI: `$H new my-site --notes en --name Workshop --domain workshop.com --lang en,ru -y`.

The answers go into `site.yaml`: comments written by hand and keys the questionnaire does not manage stay in place on save; the `setup` questionnaire adds the rest and puts the publication scripts, and you can edit `site.yaml` by hand too. If you changed the languages, `$H init my-site` builds up the folders. A new site comes with the white theme and its demo pages: the home page, "Blocks" (every kind of block), "Themes", "Documentation".

To look at the result:

```bash
docker run --rm -p 127.0.0.1:8080:8080 -v "$PWD/my-site/dist:/usr/share/nginx/html:ro" \
  nginxinc/nginx-unprivileged:1.30.6-alpine
```

Then write pages and build again. The dev build is closed to search engines and does not insert counters; the production one is `$H build my-site --env prod --strict`. Image resizing runs in several processes; where cores are shared with other tasks or processes are forbidden, set `--workers N` (`1` means no pool) or `HERON_WORKERS=N`. If the process pool is unavailable, the engine falls back to sequential resizing with the same result.

Step by step, with every step explained: [`docs/en/guide/02-first-site.md`](docs/en/guide/02-first-site.md). Without docker: `pip install git+https://github.com/FMSTM/HERON.git@prod`, then the same commands through `heron`. The package is not published to PyPI yet.

## Several sites and engine versions

When there is more than one site or they need to be shipped as images, it is more convenient to work from a clone of this repository: `scripts/site.sh` keeps the settings of each site in its own file and does everything with one command.

```bash
git clone https://github.com/FMSTM/HERON.git && cd HERON
./scripts/site.sh mysite new ~/sites/my-site     # create a site and its dev and prod environments
./scripts/site.sh mysite build dev               # build into out/mysite-dev
./scripts/site.sh mysite serve dev               # look at it on localhost:8080
./scripts/site.sh mysite image prod              # pack into an nginx image
./scripts/site.sh mysite smoke prod              # start the image and check the answers: 200, 404, 301, 410
./scripts/site.sh mysite push prod               # push the image to the registry
./scripts/site.sh mysite init                    # complete the folder for site.yaml
./scripts/site.sh mysite stop dev                # stop the preview
./scripts/site.sh mysite check dev               # check the content without building
```

How it differs from one site:

| | One site | Several sites |
|---|---|---|
| What to run | `docker run … heron:prod` or `heron` from pip | `scripts/site.sh` from a repository clone |
| Where the build settings are | command flags | `env/.env.<site>.<environment>`: path to the content, environment, engine, image and tag, strictness, port, registry and the folder with its login (keys: `env/.env.example`) |
| Where it builds | `dist/` inside the site folder | `out/<site>-<environment>`, the site folder is not touched |
| Which engine | the one you started | `ENGINE` in env: an exact version, `:prod` or sources next to it |
| Site image | build by hand | `site.sh image`, check with `site.sh smoke` |

**The engine version is pinned in the site itself**: the first line of `site.yaml` is `heron: ">=0.1,<0.2"`. An engine that does not fit refuses to build (`E012`). This way two sites can live on different versions, and updating the engine is changing one line.

**Which images exist.** Sites are built with the tag `:prod` or an exact version `:X.Y.Z`. `:beta` and `:dev` are development branches of the engine itself; a dev build of a site is the `--env` flag, not a different image.

**A site in its own repository** builds an image without a HERON clone and without its own Dockerfile, with the reusable workflow `FMSTM/HERON/.github/workflows/site-image.yml`, with a single `uses:` line.

In detail: [`docs/en/guide/06-deploy.md`](docs/en/guide/06-deploy.md).

## Documentation

The documentation in a branch corresponds to the image with the same name: `prod` is `:prod`, `beta` is `:beta`. Which image you have is shown by `heron --version` (branch and commit). The same documentation is in the image itself: `heron docs` is the table of contents, `heron docs <topic>`, `heron docs --search <text>`, `heron docs --export <folder>`.

**The path for a newcomer, in order:**

| | |
|---|---|
| [01 · Concepts](docs/en/guide/01-concepts.md) | site = folder, key and address, type, section, theme, the engine separate |
| [02 · First site](docs/en/guide/02-first-site.md) | from an empty folder to an image |
| [03 · Pages and content](docs/en/guide/03-content.md) | SEO block, sections, links, images, catalogs, languages |
| [04 · Theme and design](docs/en/guide/04-theme.md) | `theme.yaml`, templates, modules, what the template sees |
| [05 · SEO](docs/en/guide/05-seo.md) | what is generated by itself, what to fill in, moving from an old site |
| [06 · Build and deploy](docs/en/guide/06-deploy.md) | folder or image, several sites, engine versions |

**Reference: the contract and the design:**

| | |
|---|---|
| [20 · Data contract](docs/en/spec/20-data-contract.md) | site folder, URL, languages, markdown, all fields and keys, `theme.yaml`, images |
| [21 · Engine](docs/en/spec/21-engine.md) | build pipeline, page model, generators, commands, error codes |
| [22 · Deploy](docs/en/spec/22-deploy.md) | nginx, site CI, migration |
| [23 · Distribution](docs/en/spec/23-distribution.md) | image, commands, site image, themes and plugins, security |
| [Architecture](docs/en/architecture.md) | what consists of what, on one page |

**For agents:** [`AGENTS.md`](AGENTS.md) is the instruction by roles: architect, content and SEO, designer, builder.

## Engine development

```bash
git clone git@github.com:FMSTM/HERON.git && cd HERON
uv sync --group dev
./scripts/check.sh          # core boundary, format, linter, tests: the same as in CI
```

Branches: `dev` is development, each feature in its own branch; `beta` is trying out on live sites; `prod` is what the sites run on. A release is the tag `vX.Y.Z`.

**The core boundary:** the engine knows nothing about any particular site: no names, no domains, no sections. It is checked by `scripts/check-boundaries.sh` on every commit and in CI.

## Status and license

Version 0.1. Until 1.0 the contract of `site.yaml` and `theme.yaml` may change in minor versions; a site pins a version range in `site.yaml` and moves deliberately.

The license has not been chosen yet: until it appears, all rights are reserved.

## Third-party data

The markup check uses the schema.org vocabulary, release 29.3 (a compact index in `heron/schemaorg/schemaorg-29.3.json`). Source: https://schema.org. License: [Creative Commons Attribution-ShareAlike 3.0](https://creativecommons.org/licenses/by-sa/3.0/) (CC BY-SA 3.0). The data keeps this license and is not covered by the license of the engine.
