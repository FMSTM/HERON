---
name: heron-designer
description: Make or change the theme of a HERON site - Jinja2 templates per page type, a module per section form, styles, interface strings - from a mockup or a description, or install a theme with heron theme get. Use for HERON theme and layout work.
---

# HERON designer

Read first: `$H docs agents` (role «Designer»), `$H docs theme`, `$H docs engine` (§6–7 what a template sees, §10 `heron theme`).
`H="docker run --rm -i -p 8000:8000 -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:beta"`

**You may write:** `theme/` only.
**You do not touch:** `content/`, `data/`, `site.yaml`, `scripts/`, `.github/`.

Start from what is there:

- the starter theme of a new site draws all thirteen forms; `partials/sections.html` maps forms to modules, tokens are at the top of `assets/site.css`;
- or install one: `$H theme get <name|https-url|archive> .` (the previous theme goes to `.heron-cache/setup/`).

Rules: no content text or site data in templates (texts are sections, details are `site.*`, interface strings are `t.*`); sections through `mod.<module>('<anchor>')`; images only through `picture()`; no scripts that load the text of the page.

Check after every change: `$H serve .` and open localhost:8000; `$H build . --env prod --strict`. Done when every type has a template, every form in `uses` a module, and the report lists no missing `i18n` strings. Share the theme: `$H theme pack . --out theme.tar.gz`.
