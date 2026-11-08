---
name: heron-content
description: Write and move page texts into a HERON site - markdown files with the SEO block, sections with anchors, images in media - and fix SEO and translations. Use when asked to write pages, transfer texts, add a translation or fix titles and descriptions on a HERON site.
---

# HERON content and SEO

Read first: `$H docs --lang en kit` (role «Content and SEO»), `$H docs content` (the role), `$H docs pages`, `$H docs seo`, and `blocks.md` from the white theme demo site: it shows every section form next to its markdown.
Inside a HERON site the same documentation sits in `agents/` (start with `AGENTS.md`); your deliverables go to `agents/work/`.
`H="docker run --rm -i -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:beta"`

**You may write:** `content/`, `media/`, `data/`.
**You do not touch:** `theme/`, `.heron/`, `.github/`, the structure of `site.yaml` (languages, theme, menu). Contacts and company details belong in `site.yaml` through `heron setup`, not in page text.

Rules:

- A new page: `$H page add <key> . --type <type> --category <section>` - it is created in every language of `site.yaml` at once (an existing key opens for editing, nothing is created). Fill it without questions: `$H page add <key> . --dump > p.yaml`, edit, `$H page add <key> . --answers p.yaml`; field paths and hints - `$H describe --json .`. A section: `$H category add <path> .`. A language you do not translate yet: `<lang>: pending` - it keeps `translation: pending` and stays out of production until translated. The old form `page <type> <name>` is gone (`E038`). Keep the SEO block whole, comments included.
- `title` (search result, up to 60 characters) differs from `h1` (the page heading); `description` up to 155.
- Links to own pages by key from the root: `[About](/about/)`, without a language prefix.
- No material for a section — no section. Never invent facts.
- Images go to `media/`, every image has alt text.

Done when `$H check .` shows no errors and every page has `title`, `h1`, `description`.
