# HERON ARCHITECTURE

**Concept:** the engine is separate from the site. Change history - CHANGELOG.md.

## Overview

HERON is a file-based site engine. The input is a folder with content, images, a theme and one config. The output is a static site in `dist/` or a ready nginx image with this site inside.

The engine is **not copied into the site**. It ships as one artifact, the image `ghcr.io/fmstm/heron:<channel>` (tags: channel branch, version) and the same code as a package for local development (`pip install git+https://github.com/FMSTM/HERON.git@<channel>`). The site declares the version it needs in `site.yaml`; the engine refuses to build a site whose version it does not support.

The engine is made for several different sites from the start: designed around one, it degenerates into that site with abstract variable names.

## Stack

Core: Python 3.12 · Jinja2 · markdown-it-py · PyYAML · pydantic · Pillow · click. Package manager `uv`, linter `ruff`, tests `pytest`.

Tooling: Docker · nginx · Bash.

Forms service (`heron-relay`, a separate component, later): FastAPI, no database; SQLite is used only as a spool for resending.

## Components

- **`heron/core/`** - markdown parser, tree and URLs, relation resolve, renderer, image processing
- **`heron/modules/`** - generators: sitemap, robots, llms.txt, JSON-LD, redirects, feed, the nginx config (`nginx.py`)
- **`heron/contracts/`** - pydantic schemas of `site.yaml`, `theme.yaml`, the frontmatter, the engine version; `schemas.py` - export of JSON Schema and the error registry (`heron schema`)
- **`heron/cli.py`** - the commands `new`, `init`, `check`, `serve`, `build`, `page`, `category`, `describe`, `setup`, `theme`, `docs`, `schema`, `recipe`
- **`heron/setup/`** - the `heron setup` configurator: the answer model, writing `site.yaml` and the publishing files, the local server, the sphere classifier
- **`heron/schemaorg/`** - the schema.org 29.3 vocabulary for markup checks (`SCH001`-`SCH006`)
- **`heron/themes/`** - installing and packing themes for `heron theme`: the built-in `starter` (files in `heron/scaffold/templates/`), a directory, a link, an archive
- **`heron/messages.py`**, **`heron/texts/`** - texts of the commands and engine messages in ru and en
- **`heron/scaffold/`** - the site skeleton: theme, starter pages, notes; `agents.py` - the agent kit (a copy of `docs/<lang>/`, schemas, manifest, root pointers)
- **`heron/docs.py`** - documentation inside the package by language: `heron docs --lang`, topics, fallback to the other language, export
- **`docs/{ru,en}/`** - the single source of documentation: the kit README, roles, samples, guides, specs; `docs/translation.yaml` - the translation state
- **`scripts/site.sh`** - build, packaging into an nginx image, preview and checks of sites from the engine repository; settings in `env/.env.<site>.<env>`
- **`Dockerfile`, `Dockerfile.site`** - the engine image and the site image (also `heron recipe`); **`.github/workflows/site-image.yml`** - the shared site image build; **`skills/`** - skills for agents; **`env/`** - `site.sh` settings
- **site folder** - `site.yaml`, `content/`, `data/`, `media/`, `static/`, `theme/`, `plugins/`, the kit `agents/` with the root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` (the build does not read them). There is no engine code, Dockerfile or compose in it. The `heron setup` configurator optionally adds the helpers `.heron/scripts/build.sh`, `.heron/scripts/publish.sh` and the workflow `.github/workflows/image.yml` or `pages.yml`; the long part of the build stays in the engine
- **`heron-relay`** - a separate service that receives forms: mail, a CRM webhook, Telegram. Deployed only where there are forms

## Decisions

Delivery, forms, the security model and the instruction channels are recorded in [`spec/23-distribution.md`](spec/23-distribution.md); the other decisions are recorded only here:

- a static site generator instead of Django/Wagtail - the site has nothing to serve at runtime
- the core ships as an image and a version, not as a copy in every site repository: three copies of the core mean three diverging engines
- forms are served by a separate service, not by the engine: the engine must stay "one pass, no state, exit"
- a database stores neither the content nor the site settings. The source of truth is files. Breaking this rule turns HERON into WordPress
- design mockups are translated into Jinja2, the mockup runtime does not go to production
- the build runs without network: `--network=none`, nothing is downloaded at the build stage
- instructions for agents - one source `docs/<lang>/`, four delivery channels (repository, image, site folder, engine site), a byte-for-byte copy; documentation in two languages with a parity test (`spec/23-distribution.md` §12)

## Diagram

```
                site folder
   site.yaml · content/ · data/ · media/ · static/ · theme/
   agents/ · AGENTS.md  (agent kit - the build does not read it)
                     |
                     v
ghcr.io/fmstm/heron:<channel>  (image or package; inside - docs/ru, docs/en → heron docs)
     contracts -> parser -> resolve -> render -> generators
                     |
          +----------+-----------+
          v                      v
        dist/               nginx image
      (to hosting)     (site.sh image on the host)
          |
          v
        nginx  ------>  visitor
                            |
                            v
                     heron-relay (later)
                       |    |     |
                     mail   CRM  Telegram

   docs/<lang>/ ──▶ heron new/init    ──▶ <site>/agents/        (copy, manifest with hashes)
                ──▶ package and image ──▶ heron docs --lang
                ──▶ engine site CI    ──▶ sitebuilder.heron.software/agents/<lang>/, /schema/
                        (planned, the raw files are not yet published on the site)
```

The site does not depend on `heron-relay`: if the service is down, the static files are still served; only form submission is lost.
