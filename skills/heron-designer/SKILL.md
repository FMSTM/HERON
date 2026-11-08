---
name: heron-designer
description: Make or change the theme of a HERON site - Jinja2 templates per page type, a module per section form, styles, interface strings, and the theme contract in theme.yaml (block fields, hints for newcomers, category views) with a complete demo - from a mockup or a description, or install a theme with heron theme get. Use for HERON theme and layout work.
---

# HERON designer

Read first: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs --lang en kit` (role «Designer»), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs theme`, `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs theme-author` (the contract, hints, demo, packing, moving a theme from 0.2), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs engine` (§6–7 what a template sees and the theme contract, §10 `heron theme`).
Inside a HERON site the same documentation sits in `agents/` (start with `AGENTS.md`); your deliverables go to `agents/work/`.
Every command is written in full, ready to copy; run it from the site folder. No `-it`: an agent has no terminal. `-p 127.0.0.1:8000:8000` only for `serve`: it publishes the port.

**You may write:** `theme/` only; for the theme demo - its pages in `content/` and pictures in `media/` when the task is a theme for others.
**You do not touch:** `data/`, `site.yaml`, `.heron/`, `.github/`; the content of a client site.

Start from what is there:

- the starter theme of a new site draws all thirteen forms and is fully described: its `theme.yaml` is the sample of the contract; `partials/sections.html` maps forms to modules, tokens are at the top of `assets/site.css`;
- or install one: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta theme get <name|https-url|archive> .` (the previous theme goes to `.heron-cache/setup/`).

The contract in `theme.yaml` (people fill pages by it in the console and the studio, agents by `describe --json`, the theme reference is built from it):

- `languages`; for every type `hint_<lang>` and `help_<lang>`, `sections.<anchor>` with `required` and hints (`fields` for a section without a form, like `intro`); a category type has `children_type` and `views` (`key`, `default`, `options` - only the views the templates draw from `page.meta.get('view')`);
- every module described: `scope` (`section` or `page`), `kinds`, `schemaorg`, `example_<lang>`, `fields` - each field with `name`, `type`, `md` (a place from the dictionary in engine §7), limits; page modules have `fields: []`;
- own front matter fields a template reads (`page.meta.get('status')`) - in `types.<type>.fields`: the same keys as a block field but no `md`, a name that is not an engine field (otherwise `E041`); `check` gives `E042` for a required one left empty or a value outside `values`. The top-level `fields` is a different thing - names of engine fields only (`E023`);
- a `hint` in every language for every type, section, module, field and view (otherwise `E041`; `E008` is a missing template); `help` written for a newcomer: what it is, what it changes on the site and in search, a good example, common mistakes;
- service fields (`title`, `h1`, `description`, the address, the menu, the cover) belong to the engine: do not describe them.

The demo (the site content the theme is packed from) shows every type (a page from a file, `404.md` too), every module (a non-empty render) and every view (a category with pages inside and `view: <view>`): plausible texts of the niche, created with `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta category add <path> .` and `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta page add <key> . --answers p.yaml`.

Rules: no content text or site data in templates (texts are sections, details are `site.*`, interface strings are `t.*`); sections through `mod.<module>('<anchor>')`; images only through `picture()`; no scripts that load the text of the page; strict CSP - no inline scripts and no `on*=` handlers, code in `assets/*.js`, fonts and scripts from `assets/`, not from other servers.

Check after every change: `docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta serve .` and open localhost:8000 and the theme reference at `/_heron/theme/`; `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta check . --theme` (no `E008`, `E041`, `E037`); `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta build . --env prod --strict`. Done when every type has a template, every form in `uses` a module, the contract has hints in every language, the demo passes `--theme`, and the report lists no missing `i18n` strings. Share the theme: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta theme pack . --out theme.tar.gz`.
