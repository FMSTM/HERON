---
name: heron-architect
description: Design the structure of a HERON site from an old site, a sitemap or a client brief - page tree, keys, types, section forms, languages, redirects - and the answers for heron setup. Use for planning a new HERON site or a move to HERON.
---

# HERON architect

Read first: `$H docs --lang en kit` (role «Architect»), `$H docs capabilities`, `$H docs concepts`, `$H docs seo` (moving a site).
Inside a HERON site the same documentation sits in `agents/` (start with `AGENTS.md`); your deliverables go to `agents/work/`.
`H="docker run --rm -i -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:beta"`

**You may write:** the structure document, `answers.yaml` for `heron setup`, `site.yaml`, `theme/theme.yaml` sections `types` and `links`.
**You do not touch:** page texts in `content/`, templates and styles in `theme/`, `.heron/`, `.github/`.

Steps:

1. List the old pages: address, title, what is on it, how often it is visited if known.
2. Map each page to a key (file path), a type and the sections it has; give each section a form from the table of forms (`$H docs contract`, §4.4). Prefer the existing forms over new types.
3. Decide every old address: same key, 301 (`redirect_from`) or 410 (`gone`).
4. Fill `answers.yaml`: `$H setup . --dump`, then site, languages, `about.type` and its fields (schema.org), publishing. Apply with `$H setup . --answers answers.yaml`.
5. Write one sentence about the project to `organization.about` in `site.yaml` (`about_<lang>` per language): `AGENTS.md` takes it from there on the next `init`.
6. Questions for the client go to `agents/work/questions.md` (`$H docs template questions.md`), each with options and your recommendation.

Done when every page has a key, a type and a language, every type lists its sections with forms, and every old address has a decision.
