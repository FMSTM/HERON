# {name}

Site content for the [HERON](https://github.com/FMSTM/HERON) engine. Content
only: text, media, theme, configuration. There is no engine code in this
folder: building, environments and image packaging are done by the HERON
image. No Dockerfile, no compose, no `.env` is needed here.

## Start here

`site.yaml` is the single source of truth about the site. It holds everything
that concerns the site as a whole:

- domain, languages, theme, menu structure, engine version;
- details for social networks and for AI agents;
- schema.org markup - who you are and what you do;
- basic SEO: what is filled in while a page is still a draft, and what is
  added to every page (for example, the ending of the title).

Folders follow the config, not the other way round: add a language to
`languages`, run `init`, and `content/<lang>/` and
`theme/i18n/<lang>.yaml` appear.

It is best to fill in `site.yaml` with the built-in tools: `new` and `init`
create it with comments, and the configurator (`setup`, command below) asks
for the name, domains, site details, publishing and theme and writes the
answers here. Take this path and follow the advice in the file comments. If
you are sure you understand what you are doing, you can write `site.yaml` by
hand too - with the reference:

- every setting explained - [data contract, §5](https://github.com/FMSTM/HERON/blob/prod/docs/en/spec/20-data-contract.md#site-yaml);
- a full sample - [templates/site.yaml](https://github.com/FMSTM/HERON/blob/prod/docs/en/templates/site.yaml);
- step by step - ["First site", step 3](https://github.com/FMSTM/HERON/blob/prod/docs/en/guide/02-first-site.md).

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

Every command goes through the HERON Docker image. Run them from the site folder.

### Which image to use

The engine version is the last word of the image name `ghcr.io/fmstm/heron:<version>`:

- `:prod` - **the default**. The latest stable release:
  features are worked out, backward compatibility is tested. Always use it
  for live sites;
- `:beta` - new things before release. They may stay the
  same for a long time and then something breaks at once. This version is
  for experimenters.

HERON is an open project. Found a bug or want to add something - send fixes
to the `dev` branch of the [repository](https://github.com/FMSTM/HERON): we
will review the code and take it in.

### Commands

Each command can simply be copied as a whole line:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod setup .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod init .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check .
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add about .
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod category add services .
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod studio .
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod serve .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build . --env prod --strict
```

- `setup` - the configurator: name, domains, publishing, theme. Open the
  address it prints in full - with the key after "#";
- `init` - folders catch up with `site.yaml`;
- `check` - what to fill in and what to fix, without a build;
- `page add` - a page in every language at once: missing - create it, there -
  open it for editing. The engine asks the fields with hints, `?` - detailed help;
- `category add` - a section (a folder with its own page `_index.md`), the same;
- `studio` - the same with a mouse in the browser, plus the theme reference:
  every block with an example. Open the address in full, with the key after "#";
- `serve` - look at the site in the browser at <http://localhost:8000>;
- `build . --env prod --strict` - build the working version into `dist/`.

`setup`, `studio` and `serve` have `-p 127.0.0.1:8000:8000` in the command: it forwards
port 8000 from the container to your computer, otherwise the page does not
open in the browser. The other commands need no port. `-it` is for the
commands that ask questions or run until Ctrl+C.

### Shorter: the name `heron` while you work

To avoid copying the long line every time, set a short name once in the
terminal - an alias:

```bash
alias heron='docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod'
```

Now `heron` at the start of a command stands for that whole line: `heron init .`,
`heron check .`, `heron build . --env prod --strict`. The name has no port,
so still run `setup` and `serve` with the full command from the list above.

The name lives while this terminal is open. To remove it earlier - `unalias heron`.
Need it for good - the "If you build sites regularly" section in
["Installation"](https://github.com/FMSTM/HERON/blob/prod/docs/en/guide/00-install.md).
Installed the engine without Docker - you already have the `heron` command, no alias needed.

### With several sites

For those who keep several sites on one server, the engine repository has
the script `site.sh` (the `scripts/` folder). It keeps the settings of each site in a separate
file in the `env/` folder of the repository and starts dev and prod containers
for the site. You need a clone of the HERON repository: from its folder run
`cp env/.env.example env/.env.{slug}.dev` once, fill in the file, and then work
through `./scripts/site.sh {slug} <command>`. Details - in
["Build and deploy"](https://github.com/FMSTM/HERON/blob/prod/docs/en/guide/06-deploy.md).
With a single site you do not need the script.

There may be no content at all: an empty site builds in dev and serves
robots.txt and a sitemap. A production build (prod) without pages fails with
E017. You can work on the theme before writing a single page.

## If you need an agent

If you work with an AI agent, give it a link to the site repository and to
the open [HERON repository](https://github.com/FMSTM/HERON) and the phrase
"read AGENTS.md". The HERON repository has all the instructions and
[ready skills](https://github.com/FMSTM/HERON/tree/prod/skills) for every
role: with them the result is above average even with basic prompting
skills. The agent hands in its report in `agents/work/`.
