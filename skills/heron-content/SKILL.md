---
name: heron-content
description: Write and move page texts into a HERON site - markdown files with the SEO block, sections with anchors, images in media - and fix SEO and translations. Use when asked to write pages, transfer texts, add a translation or fix titles and descriptions on a HERON site.
---

# HERON content and SEO

Read first: `$H docs content` (the role), `$H docs pages`, `$H docs seo`, and `blocks.md` from the white theme demo site: it shows every section form next to its markdown.
`H="docker run --rm -i -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:beta"`

**You may write:** `content/`, `media/`, `data/`.
**You do not touch:** `theme/`, `scripts/`, `.github/`, the structure of `site.yaml` (languages, theme, menu). Contacts and company details belong in `site.yaml` through `heron setup`, not in page text.

Rules:

- A new page: `$H page <type> <name> .` or a copy of an existing file. Keep the SEO block whole, comments included.
- `title` (search result, up to 60 characters) differs from `h1` (the page heading); `description` up to 155.
- Links to own pages by key from the root: `[About](/about/)`, without a language prefix.
- No material for a section — no section. Never invent facts.
- Images go to `media/`, every image has alt text.

Done when `$H check .` shows no errors and every page has `title`, `h1`, `description`.
