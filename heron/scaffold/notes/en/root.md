# {name}

Site content for the [HERON](https://github.com/FMSTM/HERON) engine. Content
only: text, media, theme, configuration. There is no engine code in this
folder: building, environments and image packaging are done by the HERON
image. No Dockerfile, no compose, no `.env` is needed here.

## Start here

`site.yaml` is the single source of truth: domain, languages, theme, menu,
engine version. Folders follow the config, not the other way round: add a
language to `languages`, run `init`, and `content/<lang>/` and
`theme/i18n/<lang>.yaml` appear.

The easiest way to fill it in is the questionnaire: `$H setup .` (needs a
published port, like `serve`) asks for the name, domains, site details,
publishing and theme and writes them here. Editing the file by hand is fine
too.

Never put passwords or tokens in `site.yaml`: the build is static, and
anything it sees can end up in the HTML.

## What goes where

| Folder or file | What's inside |
|---|---|
| `site.yaml` | site settings: domain, languages, menu, contacts, publishing |
| `content/<lang>/` | pages in markdown, the file path is the page address |
| `media/` | everything the content shows: images (covers and the social sharing image included, from 1200 px), video, documents |
| `theme/` | how the site looks: templates, styles, interface strings |
| `data/` | shared reference data in yaml, reaches templates as `data.<name>` |
| `static/` | files that must sit at an exact address |
| `plugins/` | build extensions for this site |
| `agents/` | instructions for AI agents and the place for their reports, `agents/work/`; not part of the build |
| `.heron/scripts/`, `.github/workflows/` | scripts and the auto-build, written by `heron setup` |
| `dist/` | the build result, never goes into git |
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | the agent's entry point and two pointers to it; not part of the build |

The content folders hold a `heron-readme.md` - a short note on what belongs
there and what does not. The engine ignores these files and never ships them.

## Working with the site

Every command goes through the HERON image. Set short names once: `$H` for ordinary commands, `$HP` for `setup` and `serve` (it publishes the port):

```bash
H="docker run --rm -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"
HP="docker run --rm -i -p 127.0.0.1:8000:8000 -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"
```

In zsh (the macOS default) run `setopt sh_word_split` first, otherwise `$H`
and `$HP` will not start.

Then, from the site folder:

```bash
$HP setup .                      # questionnaire: name, domains, publishing, theme
$H init .                        # folders catch up with site.yaml
$H check .                       # what to fill in and what to fix, no build
$HP serve .                      # look at it on localhost:8000
$H build . --env prod --strict   # build the working version into dist/
```

With several sites and a clone of the engine, from the HERON folder run
`cp env/.env.example env/.env.{slug}.dev` once, fill it in, then work through
`./scripts/site.sh {slug} <command>`.

There may be no content at all: an empty site builds in dev and serves
robots.txt and a sitemap. A production build with no pages fails with E017.
You can work on the theme before writing a single page.

## If you need an agent

Give it the link to the site repository and the phrase "read AGENTS.md". It
hands in its report in `agents/work/`.
