---
name: heron-architect
description: Design the structure of a HERON site from an old site, a sitemap or a client brief - page tree, keys, types, section forms, languages, redirects - and the answers for heron setup. Use for planning a new HERON site or a move to HERON.
---

# HERON architect

Read first: `$H docs agents` (role «Architect»), `$H docs capabilities`, `$H docs concepts`, `$H docs seo` (moving a site).
`H="docker run --rm -i -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:beta"`

**You may write:** the structure document, `answers.yaml` for `heron setup`, `site.yaml`, `theme/theme.yaml` sections `types` and `links`.
**You do not touch:** page texts in `content/`, templates and styles in `theme/`, `scripts/`, `.github/`.

Steps:

1. List the old pages: address, title, what is on it, how often it is visited if known.
2. Map each page to a key (file path), a type and the sections it has; give each section a form from the table of forms (`$H docs contract`, §4.4). Prefer the existing forms over new types.
3. Decide every old address: same key, 301 (`redirect_from`) or 410 (`gone`).
4. Fill `answers.yaml`: `$H setup . --dump`, then site, languages, `about.type` and its fields (schema.org), publishing. Apply with `$H setup . --answers answers.yaml`.
5. Questions for the client go to a list with options and your recommendation.

Done when every page has a key, a type and a language, every type lists its sections with forms, and every old address has a decision.
