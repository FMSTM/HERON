---
name: heron
description: Build or move a website on HERON, the markdown static site engine. Use when asked to make a site with HERON, copy an existing site onto it, fill its content, make its theme, or build and publish it. Covers all four roles; the heron-architect, heron-content, heron-designer and heron-builder skills hold one role each.
---

# HERON

HERON builds a static site from a folder: `site.yaml`, `content/<lang>/*.md`, `media/`, `data/`, `theme/`. You never edit the engine; everything a site can do is in its documentation, shipped inside the image of the same version.

```bash
H="docker run --rm -i -p 8000:8000 -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:beta"
$H docs                      # table of contents
$H docs architect            # one topic in full
$H docs --search "E015"      # search
```

Use `:prod` for a live site, `:beta` to try the next version. Read `$H docs agents` (AGENTS.md) before the first step: it is the single instruction for agents and wins over this file if they ever differ.

## The usual job: «here is a site, make the same on HERON»

1. **Architect** (`heron-architect`). From the old site, its sitemap and texts, write the structure: page tree, keys, types, sections with their forms, languages, old address → new address or 410. Output: a structure document and the answers for the questionnaire.
2. **Create and set up.** `$H new my-site -y --lang en,de`, then `$H setup my-site --dump > answers.yaml`, fill it from the structure (name, domains, type by schema.org and its fields, publishing), `$H setup my-site --answers answers.yaml`. Check the draft against `$H schema` / `$H schema --setup`.
3. **Content and SEO** (`heron-content`). One markdown file per page, the SEO block on top, sections `## Title {#anchor}`. The theme demo pages (`index.md`, `blocks.md`, `themes.md`, `docs.md` of the white theme) shows every section form; replace it with the site's pages.
4. **Designer** (`heron-designer`). Start from the starter theme or `$H theme get <name|url|archive> my-site`; change only `theme/`.
5. **Builder** (`heron-builder`). `$H check my-site`, `$H serve my-site` (localhost:8000), `$H build my-site --env prod --strict`, then `.heron/scripts/publish.sh`.

## Rules for every role

- Facts are never invented: phones, addresses, prices, names come from the client. No fact — the field stays empty and goes to the questions list.
- `site.yaml` is the single source of truth. The questionnaire (`setup`) writes it; editing by hand is fine.
- The site folder holds content only: no Dockerfile, no compose, no `.env`, no tokens. `heron setup` writes the only scripts allowed there.
- A missing engine feature is a task for the engine, written up in the report, not a workaround in the site.
- Every warning is either content debt or an error; a production build is `--strict`.
