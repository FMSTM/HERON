# {name}

Site content for the [HERON](https://github.com/FMSTM/HERON) engine. Content
only: text, media, theme, configuration. Building, environments and image
packaging live in HERON — no Dockerfile, no compose, no `.env` here.

## Start here

`site.yaml` is the single source of truth: domain, languages, theme, menu,
engine version. Folders follow the config, not the other way round: add a
language to `languages`, run `init`, and `content/<lang>/` and
`theme/i18n/<lang>.yaml` appear.

Never put passwords or tokens in `site.yaml`: the build is static, and
anything it sees can end up in the HTML.

## What goes where

| Folder | What's inside |
|---|---|
| `content/<lang>/` | pages in markdown, the file path is the page address |
| `media/` | everything the content shows: images, video, documents |
| `theme/` | how the site looks: templates, styles, interface strings |
| `data/` | shared reference data in yaml, reaches templates as `data.<name>` |
| `static/` | files that must sit at an exact address |
| `plugins/` | build extensions for this site |

Every folder holds a `heron-readme.md` — a short note on what belongs there
and what does not. The engine ignores these files and never ships them.

## Working with the site

From the HERON folder:

```bash
./scripts/site.sh {slug} init          # folders catch up with site.yaml
./scripts/site.sh {slug} build dev     # build
./scripts/site.sh {slug} serve dev     # look at it on localhost:8080
./scripts/site.sh {slug} stop  dev
```

There may be no content at all — an empty site still builds and serves
robots.txt and a sitemap.
