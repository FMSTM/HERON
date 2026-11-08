---
name: heron
description: Build or move a website on HERON, the markdown static site engine. Use when asked to make a site with HERON, copy an existing site onto it, fill its content, make its theme, or build and publish it. Covers all four roles; the heron-architect, heron-content, heron-designer and heron-builder skills hold one role each.
---

# HERON

HERON builds a static site from a folder: `site.yaml`, `content/<lang>/*.md`, `media/`, `data/`, `theme/`. You never edit the engine; everything a site can do is in its documentation, shipped inside the image of the same version.

Every command is written in full, ready to copy; run it from the site folder (`.` is the site). No `-it`: an agent has no terminal, so commands that would ask questions take flags and `--answers` files instead. `-p 127.0.0.1:8000:8000` only for `serve`, it publishes the port.

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs                      # table of contents
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs architect            # one topic in full
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs --search "E015"      # search
```

Use `:prod` for a live site, `:beta` to try the next version. Read `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs --lang en kit` before the first step: it is the single instruction for agents and wins over this file if they ever differ.
Inside a HERON site the same documentation sits in `agents/` (start with `AGENTS.md`); your deliverables go to `agents/work/`.

## The usual job: «here is a site, make the same on HERON»

1. **Architect** (`heron-architect`). From the old site, its sitemap and texts, write the structure: page tree, keys, types, categories and their views, sections with their forms, languages, old address → new address or 410. Output: a structure document and the answers for the configurator.
2. **Create and set up.** `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta new my-site -y --lang en,de` (add `--notes ru` for comments and the agent kit in Russian, default en), then `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta setup my-site --dump > answers.yaml`, fill it from the structure (name, domains, type by schema.org and its fields, publishing), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta setup my-site --answers answers.yaml`. Check the draft against `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta schema` / `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta schema --setup`.
3. **Content and SEO** (`heron-content`). Pages and categories through `page add` / `category add` with `--dump` and `--answers` (every language at once); field paths and the hints of the theme - `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta describe --json my-site`. The theme demo pages (`index.md`, `blocks.md`, `themes.md`, `docs.md`, `structure/` of the white theme) show every section form; replace them with the site's pages.
4. **Designer** (`heron-designer`). Start from the starter theme or `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta theme get <name|url|archive> my-site`; change only `theme/`. A theme describes its contract (fields and hints in every language) and ships a demo that passes `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta check my-site --theme`.
5. **Builder** (`heron-builder`). `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta check my-site`, `docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta serve my-site` (localhost:8000), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta build my-site --env prod --strict`, then hand over to the human: the agent prepares settings and the build, the human runs publishing (`.heron/scripts/publish.sh`, `git push`).

## Rules for every role

- Facts are never invented: phones, addresses, prices, names come from the client. No fact — the field stays empty and goes to the questions list.
- `site.yaml` is the single source of truth. The configurator (`setup`) writes it; editing by hand is fine.
- The site folder holds content only: no Dockerfile, no compose, no `.env`, no tokens. `heron setup` writes the only scripts allowed there.
- The questions in the console and the studio in the browser (`heron studio`) are for a human; an agent uses flags, `--dump` and `--answers`. The old form `heron page <type> <key>` is gone (`E038`).
- A missing engine feature is a task for the engine, written up in the report, not a workaround in the site.
- Every warning is either content debt or an error; a production build is `--strict`.
