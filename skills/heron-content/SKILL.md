---
name: heron-content
description: Write and move page texts into a HERON site - pages and categories in every language with heron page add and category add, the SEO block, sections with anchors, images in media - and fix SEO and translations. Use when asked to write pages, transfer texts, add a translation or fix titles and descriptions on a HERON site.
---

# HERON content and SEO

Read first: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs --lang en kit` (role «Content and SEO»), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs content` (the role), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs pages`, `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs seo`, and `blocks.md` from the white theme demo site: it shows every section form next to its markdown.
Inside a HERON site the same documentation sits in `agents/` (start with `AGENTS.md`); your deliverables go to `agents/work/`.
Every command is written in full, ready to copy; run it from the site folder. No `-it`: an agent has no terminal.

**You may write:** `content/`, `media/`, `data/`.
**You do not touch:** `theme/`, `.heron/`, `.github/`, the structure of `site.yaml` (languages, theme, menu). Contacts and company details belong in `site.yaml` through `heron setup`, not in page text.

Rules:

- What the theme expects: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta describe --json .` - every service field and every block field with its path, place in markdown, limits and hints; `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta describe <type> .` for one type with help and a markdown sample; `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs theme-ref .` for live examples from the theme demo.
- A new page: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta page add <key> . --type <type> --category <section> --dump > p.yaml`, fill the fields, then `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta page add <key> . --answers p.yaml` - it is created in every language of `site.yaml` at once; an existing key opens for editing, the same files.
- A category: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta category add <path> . --children-type <type> --view <view>` (the views come from `describe`); the same `--dump` / `--answers`. Moving a page or a category: `--category` of another one or a new `key` in the answers - files move in every language, 301 from the old addresses.
- A language you do not translate yet: `<lang>: pending` in the answers - it keeps `translation: pending` and stays out of production until translated; `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta page list . --json` shows what is pending.
- The old form `page <type> <name>` is gone (`E038`). Keep the SEO block whole, comments included.
- `title` (search result, up to 60 characters) differs from `h1` (the page heading); `description` up to 155.
- Links to own pages by key from the root: `[About](/about/)`, without a language prefix.
- No material for a section — no section. Never invent facts.
- Images go to `media/`, every image has alt text. The cover (`image`, `og_image`) is per language: a language file without `image` uses the main language's cover; give a language its own `image` (and `image_alt`) when the picture has text on it, clear it to follow the main one again.

Done when `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta check .` shows no errors and every page has `title`, `h1`, `description`.
