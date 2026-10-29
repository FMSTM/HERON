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

Never put passwords or tokens in `site.yaml`: the build is static, and
anything it sees can end up in the HTML.

## What goes where

| Folder or file | What's inside |
|---|---|
| `content/<lang>/` | pages in markdown, the file path is the page address |
| `media/` | everything the content shows: images (covers and the social sharing image included, from 1200 px), video, documents |
| `theme/` | how the site looks: templates, styles, interface strings |
| `data/` | shared reference data in yaml, reaches templates as `data.<name>` |
| `static/` | files that must sit at an exact address |
| `plugins/` | build extensions for this site |
| `agents/` | instructions for AI agents and the place for their reports, `agents/work/`; not part of the build |
| `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | the agent's entry point and two pointers to it; not part of the build |

The content folders hold a `heron-readme.md` - a short note on what belongs
there and what does not. The engine ignores these files and never ships them.

## Working with the site

Every command goes through the HERON image. Set a short name once:

```bash
H="docker run --rm -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"
```

Then, from the site folder:

```bash
$H init .                        # folders catch up with site.yaml
$H check .                       # what to fill in and what to fix, no build
$H serve .                       # look at it on localhost:8000 (needs -p 127.0.0.1:8000:8000)
$H build . --env prod --strict   # build the working version into dist/
```

To look at the site, `serve` needs a published port: add
`-p 127.0.0.1:8000:8000` to the `docker run` command in `H`.

With several sites and a clone of the engine you can work through
`./scripts/site.sh {slug} <command>` from the HERON folder.

There may be no content at all - an empty site still builds and serves
robots.txt and a sitemap.

## If you need an agent

Give it the link to the site repository and the phrase "read AGENTS.md". It
hands in its report in `agents/work/`.
