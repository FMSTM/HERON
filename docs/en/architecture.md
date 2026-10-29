# HERON ARCHITECTURE

**Last edited:** 2026-10-29 · The concept "the engine is separate from the site", approved 2026-09-14. Edit of 2026-10-29: the setup, schemaorg, themes, messages and nginx components. Edit of 2026-10-25: documentation by language and the agent kit.

## Overview

HERON is a file-based site engine. The input is a folder with content, images, a theme and one config. The output is a static site in `dist/` or a ready nginx image with this site inside.

The engine is **not copied into the site**. It ships as one artifact, the image `heron:<version>` (and the same code as a pip package for local development). The site declares the version it needs in `site.yaml`; the engine refuses to build a site whose version it does not support.

The engine is made for several different sites from the start: designed around one, it degenerates into that site with abstract variable names.

## Stack

Core: Python 3.12 · Jinja2 · markdown-it-py · pydantic · Pillow · click. Package manager `uv`, linter `ruff`, tests `pytest`.

Tooling: Docker · nginx · Bash.

Forms service (`heron-relay`, a separate component, later): FastAPI, no database; SQLite is used only as a spool for resending.

## Components

- **`heron/core/`** - markdown parser, tree and URLs, relation resolve, renderer, image processing
- **`heron/modules/`** - generators: sitemap, robots, llms.txt, JSON-LD, redirects, feed, the nginx config (`nginx.py`)
- **`heron/contracts/`** - pydantic schemas of `site.yaml`, `theme.yaml`, the frontmatter, the engine version; `schemas.py` - export of JSON Schema and the error registry (`heron schema`)
- **`heron/cli.py`** - the commands `new`, `init`, `check`, `serve`, `build`, `page`, `setup`, `theme`, `docs`, `schema`, `recipe`
- **`heron/setup/`** - the `heron setup` questionnaire: the answer model, writing `site.yaml` and the publishing files, the local server, the sphere classifier
- **`heron/schemaorg/`** - the schema.org 29.3 vocabulary for markup checks (`SCH001`-`SCH006`)
- **`heron/themes/`** - built-in themes for `heron theme get`
- **`heron/messages.py`** - command texts in ru and en
- **`heron/scaffold/`** - the site skeleton: theme, starter pages, notes; `agents.py` - the agent kit (a copy of `docs/<lang>/`, schemas, manifest, root pointers)
- **`heron/docs.py`** - documentation inside the package by language: `heron docs --lang`, topics, fallback to the other language, export
- **`docs/{ru,en}/`** - the single source of documentation: the kit README, roles, samples, guides, specs; `docs/translation.yaml` - the translation state
- **`scripts/site.sh`** - build, packaging into an nginx image, preview and checks of sites from the engine repository; settings in `env/.env.<site>.<env>`
- **site folder** - `site.yaml`, `content/`, `data/`, `media/`, `static/`, `theme/`, `plugins/`, the kit `agents/` with the root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` (the build does not read them). There is no engine code, Dockerfile, compose or build scripts in it
- **`heron-relay`** - a separate service that receives forms: mail, a CRM webhook, Telegram. Deployed only where there are forms

## Decisions

Recorded in [`spec/23-distribution.md`](spec/23-distribution.md):

- a static site generator instead of Django/Wagtail - the site has nothing to serve at runtime
- the core ships as an image and a version, not as a copy in every site repository: three copies of the core mean three diverging engines
- forms are served by a separate service, not by the engine: the engine must stay "one pass, no state, exit"
- a database stores neither the content nor the site settings. The source of truth is files. Breaking this rule turns HERON into WordPress
- design mockups are translated into Jinja2, `support.js` (69 KB of React runtime) does not go to production
- the build runs without network: `--network=none`, nothing is downloaded at the build stage
- instructions for agents - one source `docs/<lang>/`, four delivery channels (repository, image, site folder, engine site), a byte-for-byte copy; documentation in two languages with a parity test (`spec/23-distribution.md` §12)

## Diagram

```
                site folder
   site.yaml · content/ · data/ · media/ · static/ · theme/
   agents/ · AGENTS.md  (agent kit - the build does not read it)
                     |
                     v
        heron:<version>   (image or pip package; inside - docs/ru, docs/en → heron docs)
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
```

The site does not depend on `heron-relay`: if the service is down, the static files are still served; only form submission is lost.
