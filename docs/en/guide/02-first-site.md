# 02 · First site

An end-to-end example: from an empty folder to a built site in two languages, English as the main one and Russian as the second. You need docker; without it, use `pip install git+https://github.com/FMSTM/HERON.git@prod` and `heron` instead of `$H`.

```bash
H="docker run --rm -it -p 127.0.0.1:8000:8000 -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"
```

In zsh (the macOS default) run `setopt sh_word_split` first, otherwise `$H` will not start.

- `-p 127.0.0.1:8000:8000` is for the `setup` questionnaire and for `serve` preview: inside the container they listen on all interfaces of the container, and the leading `127.0.0.1:` publishes the port only to your machine, not to the network. Without this prefix docker opens the port on all interfaces of the computer. The page opens at `localhost:8000`; the engine prints the questionnaire address together with the key after `#`, so open it in full;
- `-v $PWD:/site` means the engine sees **only the current folder**. That is why the path to the site in commands is relative to it: `my-site`, or `.` if you are already in the site folder. A path like `~/SOURCE/…` does not exist inside the container, and the engine will say so;
- `-it` lets `new` ask questions. Without it, it quietly takes the defaults;
- `--user` is needed, otherwise the files end up owned by root and you will not be able to edit them.

Without a terminal (an agent, CI) and for commands next to a running `serve` you need another variable: `-it` does not start without a terminal, and a second container with the same `-p` will not start while the port is busy.

```bash
H="docker run --rm -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"
```

## 1. Create a site

```bash
$H new my-site           # a new folder next to you
$H new .                 # or in the current one, for example in a freshly cloned git repository
```

The folder may be under git: `.git`, `.gitignore`, `README` and other service files do not get in the way and are not overwritten. Any other file means a refusal with a list of what is in the way.

`new` asks a few questions; Enter accepts the value in brackets:

```
Language you prefer to work in: hints, messages, comments in files
(the engine prints this prompt in both English and Russian)
  › (en, ru) [en] en
Site name - what people call the site: header, <title>, structured data
  › [my-site] Workshop
Domain - no https:// and no slashes, e.g. example.com. Not sure - Enter keeps a placeholder
  › [workshop.example] workshop.example
Site languages - comma-separated codes: en or en, ru. Each language is a content/<code>/ folder
  › [en] en, ru
Main language - served from the root (/about/), the others with a prefix (/ru/about/)
  › [en] en
Summary: ...
Create the site? [Y/n]
```

The main language is asked only if there are several languages. After the questions `new` prints a "Summary" block and asks for confirmation: Enter creates the site.

- **working language** is the language you are more comfortable in: the comments in all files the engine creates and the messages on screen will be in it. It is saved in `site.yaml` (`build.notes`). To set it in advance: `--notes en` or `-e HERON_NOTES=en`;
- **without questions**, with flags: `$H new my-site --notes en --name Workshop --domain workshop.example --lang en,ru -y`. This is how agents and CI work; run the command through the `H` variable without `-it` (see above).

At the end `new` prints what it created and a "What next" block with ready commands. What appeared:

```
my-site/
├── site.yaml                  config with a comment on every key
├── .gitignore                 what does not go into git
├── heron-readme.md            a note on what this folder is; every folder has one
├── AGENTS.md                  instructions for an AI agent: roles, rules, "done when"
├── CLAUDE.md  GEMINI.md       one line each, "@AGENTS.md", for agents with their own file names
├── agents/                    the agent kit in your language: README, roles, samples, guides,
│                              specs, schemas; it does not go into the build or onto the site
├── content/en/index.md        home page with the full SEO block
├── content/en/404.md          the "not found" page
├── content/en/blocks.md       the demo site: "Blocks", every kind of block on one page,
├── content/en/themes.md       "Themes", how to change the look,
├── content/en/docs.md         "Documentation", where to read and the main commands
├── content/ru/…               the same for each language from the answer
├── media/cover.png            default cover (seo.og_default_image)
├── media/demo/                two images for the gallery on the "Blocks" page
├── data/  static/  plugins/
└── theme/                     the starter theme: white, draws all forms: theme.yaml, templates, modules, styles
```

The demo pages come with the theme: the white theme puts the home page and three instruction pages into every language (texts in Russian and English, other languages get the English ones). Open `blocks.md` next to `/blocks/` in the browser: the file and the page side by side. If you chose another theme in the questionnaire, its demo pages arrive, and your files are not overwritten. Delete the pages you do not need together with their keys in `nav.main`.

The site already builds, and without a single warning, so you can check right away: `$H build my-site`.

**Instructions for the agent.** If an AI agent will write the pages, a link to the site repository and the phrase "read `AGENTS.md` and work in the content role" is enough: `agents/` holds the engine documentation of exactly that version and in the language you chose, and `agents/work/` is the place for its report and questions to you. The folder is invisible to the build and weighs nothing on the site; commit it together with the content. If you do not need it, use `$H new my-site --no-agents` (it is remembered in `site.yaml` as `build.agents: false`). When a new engine version is out, `$H init my-site --agents` updates the files you have not edited. In detail: [`agents/README.md`](../README.md).

## 2. Describe the site: questionnaire or `site.yaml`

The easiest way is the questionnaire:

```bash
$H setup my-site
```

Open the address the engine printed, `http://localhost:8000/#key`, in full, with the key after `#`: without it the questionnaire will not open the settings. Then come the name and domains, languages, who the site is about (who you are, field and specialization by schema.org, address, contacts), search, AI assistants, analytics, the way of publication, keys, theme. "Save" writes `site.yaml` without erasing your comments and the keys the questionnaire does not manage, and, if you want, helpers: `.heron/scripts/build.sh`, `.heron/scripts/publish.sh`, `.gitignore` and a GitHub workflow. A repeated run shows what was written; the previous version of the file is kept in `.heron-cache/setup/`. The questionnaire page is bilingual (EN and RU buttons). An agent fills in the same fields with a file: `$H setup my-site --dump > answers.yaml`, edit, `$H setup my-site --answers answers.yaml`. In detail: [`21` §10](../spec/21-engine.md#heron-setup).

`site.yaml` is the single source of truth about the site, and you can edit it by hand too. The answers to the questions are already there; open it and add the rest: the name in the second language, the title suffix, the menu:

```yaml
site:
  domain: example.com
  name: Workshop
  name_ru: Мастерская         # name for the Russian pages
  theme: main
  default_lang: en            # served from the root: /about/
  languages: [en, ru]         # the second language lives under /ru/
seo:
  title_suffix: " | Workshop"
  title_suffix_ru: " | Мастерская"
nav:
  main: ["/", about]          # page keys: home and about, each language has its own address
```

All keys with explanations: [`20` §5](../spec/20-data-contract.md#site-yaml) and the sample [`templates/site.yaml`](../templates/site.yaml).

## 3. Languages changed: catch up the structure

```bash
$H init my-site
```

`init` reads `site.yaml` and adds what is missing: if you added the language `de` to `languages`, `content/de/` with the starter and demo pages of the theme and `theme/i18n/de.yaml` appear. It does not touch content, theme and config (to overwrite, use `--force`); `AGENTS.md`, where the site languages are written, is updated together with the manifest `agents/heron-kit.yaml`. If the site was created with the right languages from the start, this step is not needed.

`init` in a folder without `site.yaml`, for example one with ready content from elsewhere, asks the same questions as `new` and suggests languages from the folders that already lie in `content/`.

## 4. Write the home page

Open `content/en/index.md`. At the top is the SEO block: change `title` (for search results), `h1` (for the one already on the page), `description` (the snippet). Do not delete the comments: they are a hint for whoever edits the file after you.

Below are the intro and the sections:

```markdown
We repair roofs since 2010.

We come to measure on the day you call.

## What we do {#about}

- **Roof repair.** Patching and re-covering.
- **Gutters.** Installation and cleaning.
```

The Russian home page is `content/ru/index.md`: the same anchor `{#about}`, its own text. The anchor is the name of the section for the theme and is the same in all languages; the heading is translated.

Which sections the home page draws and in what form is decided by the theme. The starter one outputs the intro and all sections in a row, except `section.note` (a paragraph under a list is not drawn in the starter theme); on your own theme every section will have its own place and its own module: [04 · Theme and design](04-theme.md).

## 5. Add a page

Two ways, the same result:

```bash
cp my-site/content/en/index.md my-site/content/en/about.md   # and fix the values
$H page page about my-site                                   # type page, file content/en/about.md
```

`heron page <type> <name>` puts a file with the full SEO block and stubs of all sections the theme expects for this type. The page appears in the sitemap and `llms.txt` by itself; in the menu because its key `about` is written in `nav.main`.

A translation is a file with the same name in `content/ru/` (`$H page page about my-site --lang ru`). The translation can have its own address: `slug: o-nas` in its SEO block:

```
content/en/about.md   →  /about/
content/ru/about.md   →  /ru/o-nas/      slug: o-nas
```

Both versions get hreflang to each other, and the `about` menu item on Russian pages will lead to `/ru/o-nas/` by itself.

## 6. Build and look

With a rebuild on every save, use `$H serve my-site` and <http://localhost:8000>. The final build goes to `dist/`:

```bash
$H build my-site
docker run --rm -p 127.0.0.1:8080:8080 -v "$PWD/my-site/dist:/usr/share/nginx/html:ro" \
  nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:782bb89768cc87b7f95c18b95baa1af250e5d451f26794f59363540161147c01
```

Open <http://localhost:8080>. After the build the engine prints a report: how many pages per language, warnings by group (images, relations, links, translations...) and a summary of unfilled sections. Errors stop the build and name the code and the file, and the line where it is known. This is a bare nginx without the site config: it has no own 404, 301 and 410, they are checked by `smoke` on the image: [06](06-deploy.md).

`$H check my-site` is the same report without a build.

## 7. Production build

```bash
$H build my-site --env prod --strict
```

If you added a page in §5, before `build --env prod --strict` it needs its translation and different `title` and `h1`, otherwise the build returns rc=1.

`--env prod` opens indexing and turns on the counters from `analytics`. `--strict` turns warnings into errors: a site with a broken link or an image without `alt` will not go to production. The finished `dist/` folder goes to any hosting; for how to build an nginx image with the site, see [06 · Build and deploy](06-deploy.md).

## Where to read next

Documentation of the same version as the engine is in the image: `$H docs` is the table of contents, `$H docs --lang ru seo` is a topic, `$H docs --search E023` is a search. Contract schemas for the editor and the agent: `$H schema --export <folder>`.

---

Next: [03 · Pages and content](03-content.md)
