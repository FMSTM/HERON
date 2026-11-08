---
name: heron-architect
description: Design the structure of a HERON site from an old site, a sitemap or a client brief - page tree, keys, types, categories and their views, section forms, languages, redirects - and the answers for heron setup. Use for planning a new HERON site or a move to HERON.
---

# HERON architect

Read first: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs --lang en kit` (role «Architect»), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs capabilities`, `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs concepts`, `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs seo` (moving a site).
Inside a HERON site the same documentation sits in `agents/` (start with `AGENTS.md`); your deliverables go to `agents/work/`.
Every command is written in full, ready to copy; run it from the site folder. No `-it`: an agent has no terminal.

**You may write:** the structure document, `answers.yaml` for `heron setup`, `site.yaml`, `theme/theme.yaml` sections `types` and `links`.
**You do not touch:** page texts in `content/`, templates and styles in `theme/`, `.heron/`, `.github/`.

Steps:

1. List the old pages: address, title, what is on it, how often it is visited if known.
2. Map each page to a key (file path), a type and the sections it has; give each section a form from the table of forms (`docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs contract`, §4.4). Prefer the existing forms over new types. What the current theme already offers - types, blocks, fields, category views - is in `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta describe .`.
3. Group pages into categories (a folder with `_index.md`): for each, the type of pages inside (`children_type`) and the view the theme draws it with (`views`).
4. Decide every old address: same key, 301 (`redirect_from`) or 410 (`gone`).
5. Fill `answers.yaml`: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta setup . --dump > answers.yaml`, then site, languages, `about.type` and its fields (schema.org), publishing. Apply with `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta setup . --answers answers.yaml`.
6. Write one sentence about the project to `organization.about` in `site.yaml` (`about_<lang>` per language): `AGENTS.md` takes it from there on the next `init`.
7. Questions for the client go to `agents/work/questions.md` (`docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs template questions.md`), each with options and your recommendation.

Done when every page has a key, a type and a language, every category has a type of pages inside and a view, every type lists its sections with forms, and every old address has a decision.
