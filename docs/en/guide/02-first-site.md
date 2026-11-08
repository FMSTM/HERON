# 02 · First site

In this section we build a small site from scratch, in two languages: English as the main one and Russian as the second. At every step we look at what the command does, what it prints and what appears in the folder. It takes about twenty minutes.

You need Docker - how to install it is described in [00 · Installation](00-install.md). Every command below is written in full: copy it into the terminal as is.

> **Installed the engine without Docker?** Then in every command replace everything up to and including the image name (`ghcr.io/fmstm/heron:…`) with the word `heron`. For example, `docker run … ghcr.io/fmstm/heron:prod build my-site` becomes `heron build my-site`. More - [in the installation section](00-install.md#without-docker).

## Step 0. A folder for your sites

Open a terminal and create a folder where your sites will live, for example `sites` in your home folder. Then go into it:

```bash
mkdir -p ~/sites
cd ~/sites
```

Run every command below **from this folder**. Docker shows the engine only the current folder and what is inside it, so it matters where you are (more - [in the installation section](00-install.md#docker-current-folder)).

## Step 1. Create the site

```bash
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod new my-site
```

The engine creates the folder `my-site` inside the current one - you get `~/sites/my-site` - and puts everything the site needs into it. The folder name can be anything; it does not affect the site address.

What the parts of the command mean - once, since they repeat from here on:

- `docker run --rm` - run the engine and clean up after it when the command finishes;
- `-it` - attach the terminal. For `new`, `page add` and `category add` - so the engine can ask questions, for the configurator, the studio and the preview - so you can stop them with Ctrl+C;
- `-v "$PWD:/site" -w /site` - show the engine the current folder and work in it;
- `--user "$(id -u):$(id -g)"` - create files under your name. Without it they would belong to the system user root, and you would have to edit them with `sudo`;
- `ghcr.io/fmstm/heron:prod` - the engine itself, the stable version;
- `new my-site` - the engine command and its parameters. Only this part changes.

Tired of copying the long line - set the short name `heron` while you work, as described [in the installation section](00-install.md#alias).

**If the folder for the site already exists** - say, you created an empty repository on GitHub and cloned it - go into it and create the site right there. The dot at the end means "in the current folder":

```bash
cd ~/sites/my-repo
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod new .
```

`.git`, `.gitignore`, `README` and other service files do not get in the way and are not overwritten. If the folder holds anything else, the engine refuses and lists the files in the way: this way it never overwrites anything. In this case run all the following commands from this folder (`~/sites/my-repo`) and write `.` instead of `my-site`; in the nginx command from step 6 the path becomes `$PWD/dist`.

### Questions

`new` asks a few questions. The answer in square brackets is the default: if it suits you, press Enter.

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

What is asked and what it affects:

- **working language** - the engine writes its messages and the comments in files in it. It is not tied to the languages of the site itself: you can work in English on a site that is only in Russian;
- **name** - what people call the site: in the header and in the browser tab;
- **domain** - the address the site will open at, for example `workshop.example`. Don't know it yet - press Enter and change it later;
- **site languages** - which languages the pages will be in. Each language gets its own folder of texts;
- **main language** - its pages open at short addresses (`/about/`), the pages of other languages with a prefix (`/ru/about/`). This question is asked only if there is more than one language.

At the end the engine shows a "Summary" and asks you to confirm. Enter - and the site is created.

### What the engine prints

```
Site created: my-site
Created:
  + config: site.yaml, .gitignore
  + content en: home page, blocks.md, themes.md, docs.md, structure/_index.md, structure/one-intent.md, structure/categories.md, 404 page
  + content ru: home page, blocks.md, themes.md, docs.md, structure/_index.md, structure/one-intent.md, structure/categories.md, 404 page
  + theme: 25 files - theme.yaml, templates, modules, styles
  ...

What next:
  1. Set the site up in the configurator:
      docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod setup my-site
    name, domain, who you are, publishing. Or by hand in my-site/site.yaml.
  ...
```

In the "What next" block the engine suggests the next steps - we go through them in order below. Every hint is a ready command on its own line: select the whole line and paste it into the terminal. If the engine is installed without Docker, the hints are short - for example, `heron setup my-site`.

### What appeared in the folder

```
my-site/
├── site.yaml          site settings: domain, languages, menu, theme. The main file
├── content/
│   ├── en/            pages in English: index.md - home page, 404.md - "not found"
│   └── ru/            the same in Russian
├── media/             images, video, documents
├── theme/             the look: templates and styles. For now - the white starter theme
├── data/  static/  plugins/    empty for now, needed later
├── heron-readme.md    a note on what is in the folder. Every folder has one
└── AGENTS.md, CLAUDE.md, GEMINI.md, agents/   instructions for an AI agent, if it writes the texts (see below)
```

Besides the home page, `content/` holds demo pages:

- "Blocks" (`blocks.md`) - every kind of block the theme can show;
- "Themes" (`themes.md`) - how to change the look;
- "Documentation" (`docs.md`) - where to read next;
- "Structure" (the folder `structure/`) - a section with its own page `_index.md` and two pages inside: how to lay a site out as pages and sections.

They are handy to look at like this: the file in the editor on the left, the same page in the browser on the right. The demo pages have texts in Russian and English; other languages get the English ones. This is the demo of the theme - a sample its author thought through: which pages a site needs and which blocks they have. Replace the texts with your own or, when you no longer need the pages, delete the files and remove them from the menu - `nav.main` in `site.yaml`. How to remove the demo and how to bring it back - [04 · Theme and design](04-theme.md#demo-pages).

**If an AI agent writes the texts.** Give it a link to the site repository and the task: "Read `AGENTS.md` and write the page texts." `AGENTS.md` describes the agent roles; texts and SEO are the "Content and SEO" role. The `agents/` folder holds the engine documentation of the same version and in the same language you chose; it does not get onto the site. If you do not need agents, create the site with the `--no-agents` flag at the end of the `new` command - the engine remembers it in `site.yaml`. When a new engine version comes out, the command `init my-site --agents` updates the instructions you have not edited. More - [`agents/README.md`](../README.md).

## Step 2. Look at the site in the browser

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod serve my-site
```

Here `-p 127.0.0.1:8000:8000` is added: it forwards port 8000 from the container so the page can be opened in a browser. `127.0.0.1` means the page is visible only on your computer, not to the whole network.

The engine builds the site and prints:

```
open: http://localhost:8000/  (Ctrl+C to stop)
HERON runs in a container: open the address on your computer. ...
```

Open <http://localhost:8000> in the browser. It is already a working site: home page, menu, language switch, demo pages. And at <http://localhost:8000/_heron/theme/> there is the theme reference: every block the theme can do, with its hint, a live example and its markdown next to it. The reference is seen only in the preview: it does not get onto the site.

While the preview is running, the engine watches the files: you save an edit - the page is rebuilt, refresh the browser tab. So it is handy to keep the preview running the whole time you work and to run other commands **in another terminal tab** (don't forget to go to `~/sites` there too). To stop the preview - Ctrl+C.

## Step 3. Set the site up

All site settings live in one file - `my-site/site.yaml`. There are two ways to fill it in.

### Way 1: the configurator in the browser

If the preview is running (in any tab), stop it first with Ctrl+C: the configurator needs the same port 8000. Then:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod setup my-site
```

The engine prints an address like this:

```
The configurator is open: http://localhost:8000/#eeRjEhS4PDDywTrtEWihlUwHRyY3mvzx  - open the whole address, with the key after “#”.
```

Open this address in the browser **in full, with the long key after `#`**. The key is a password for this run of the configurator: without it the configurator does not show the settings, and nobody but you can change them.

The configurator has the name and domains, languages, details about you or your organization (field, address, contacts - this goes into the markup for search engines), analytics, the way of publishing, the theme. The interface is in two languages, switched with the EN and RU buttons.

The "Save" button writes the answers to `site.yaml` and, if you tick it in the configurator, also publishing helpers: the scripts `.heron/scripts/build.sh` and `.heron/scripts/publish.sh`, `.gitignore` and an automatic build workflow for GitHub. Your comments and the settings the configurator does not have stay in place, and the previous version of the file is kept in `my-site/.heron-cache/setup/`. You can run the configurator as many times as you like - it shows what is already written. Done - Ctrl+C in the terminal.

An AI agent or CI does not need a browser: the same fields are filled in with a file. The command `setup my-site --dump > answers.yaml` exports the current answers, and after editing, `setup my-site --answers answers.yaml` writes them. More - [`21` §10](../spec/21-engine.md#heron-setup).

### Way 2: by hand in `site.yaml`

`site.yaml` is an ordinary text file, and every setting in it has a comment. The answers to the `new` questions are already there. For example, let's add the site name in Russian, the ending of the tab title and the menu:

```yaml
site:
  domain: example.com
  name: Workshop
  name_ru: Мастерская         # the name on Russian pages
  theme: main
  default_lang: en            # main language: addresses like /about/
  languages: [en, ru]         # second language: addresses like /ru/about/
seo:
  title_suffix: " - Workshop"          # added to the title of every page
  title_suffix_ru: " - Мастерская"
nav:
  main: ["/", about]          # menu: the home page and the about page
```

Note the menu: it holds not addresses but **page keys**. A key is the file name without `.md`: `about` is `content/en/about.md` in English and `content/ru/about.md` in Russian. The engine puts in the right address for each language by itself.

All settings with explanations - [`20` §5](../spec/20-data-contract.md#site-yaml), a full sample - [`templates/site.yaml`](../templates/site.yaml).

### If you changed the languages

Added a language - for example, `de` to `languages` - run:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod init my-site
```

`init` adds what is missing: it creates `content/de/` with the starter pages and the theme labels in German, and updates the languages in `AGENTS.md`. It does not touch your texts, theme or settings (to overwrite them with the starter files - the `--force` flag). If the languages did not change, you do not need this step.

And if there is no `site.yaml` in the folder - say, you brought ready texts from somewhere else - `init` asks the same questions as `new` (add `-it` to the command, as for `new`) and suggests languages by the folders already in `content/`.

## Step 4. Write the home page

Open `my-site/content/en/index.md` in the editor. The file has two parts.

**At the top is the SEO block** between the `---` lines. Search engines and the browser read it:

- `title` - the title in search results and in the browser tab;
- `h1` - the main heading on the page itself, for someone who has already opened it;
- `description` - a short description the search engine shows under the title.

Replace them with your own. Do not delete the comments in the block: they tell you, and whoever edits the file after you, what goes where.

**Below is the page text.** First the intro - ordinary paragraphs. Then the sections: each starts with a `##` heading, followed in curly braces by an **anchor**, a short Latin name of the section:

```markdown
We have been repairing roofs since 2010.

We come out to measure the same day you call.

## What we do {#about}

- **Roof repair.** Patching and re-covering.
- **Gutters.** Installation and cleaning.
```

By the anchor the theme knows what the section is and where to show it. So the Russian home page (`content/ru/index.md`) has the same anchor, while the heading and text are in Russian: `{#about}` stays, `What we do` is translated.

Save the files. If the preview is running, refresh the browser tab and look at the result. Which sections the home page shows and how is up to the theme - more in [04 · Theme and design](04-theme.md).

## Step 5. Add a page

Let's add an "About us" page with the key `about`:

```bash
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add about my-site
```

How to read the end of the command: `page add` - "create a page, and if it already exists - open it for editing", `about` - its **key** (the file name and the address come from it), `my-site` - the site folder. `-it` is needed because the engine asks questions: which category the page lives in, the title for search, the heading on the page itself, the description and the other fields. Every question shows in brackets the value that stays if you just press Enter, next to it - a one-line hint, and `?` shows the detailed help. An answer with a mistake (for example, a title that is too long) is flagged at once and asked again. First the engine asks everything in the main language, then for every other language - a translation of the same texts: type the translation or press Enter to skip the field. How to answer the questions, with an example, - [03 · Pages and content](03-content.md#questions).

At the end the engine shows a summary and asks "Write?". The page appears in all languages at once: `my-site/content/en/about.md` and `my-site/content/ru/about.md` - with a ready SEO block and drafts of the sections. If you skipped the translation, the Russian file keeps the English text and the line `translation: pending`: a draft build and the preview show such a page with a yellow "translation pending" banner, and a production build does not publish it in Russian until you translate the text and delete this line.

The same command a second time opens the page for editing and creates nothing. All pages, their languages and what is not translated (marked with `!`) are shown by `page list`:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page list my-site
```

File names are the same in every language - this is how the engine knows they are translations of one page. The addresses can differ, though: to make the Russian page open at `/ru/o-nas/`, add `slug: o-nas` to its SEO block (`page add` asks this field too).

```
content/en/about.md   →  /about/
content/ru/about.md   →  /ru/o-nas/      (in the SEO block: slug: o-nas)
```

The new page gets into the sitemap for search engines by itself. It appears in the menu if its key `about` is in `nav.main` (step 3), and on Russian pages this item leads to `/ru/o-nas/` by itself.

You can also do without the command: copy any page file under a new name and edit it. The result is the same.

Or with a mouse, in the studio in the browser: the page tree on the left, the fields with hints on the right, languages as tabs. Stop the preview (Ctrl+C) - the studio needs the same port - and run:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod studio my-site
```

Open the address the engine prints in full - with the key after `#`, as for the configurator. What is in the studio - [03 · Pages and content](03-content.md#studio).

## Step 6. Check and build

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site
```

The engine builds the finished site into the folder `my-site/dist/` and prints a report: how many pages there are in each language and whether there are remarks. For example, if you have not edited the new pages from step 5 yet:

```
Warnings - 2:
  other - 2:
    en/about.md: title and h1 are the same: title is written for search results, h1 for the reader who has already opened the page
    ru/about.md: title and h1 are the same: title is written for search results, h1 for the reader who has already opened the page
```

Messages come in two kinds:

- **a warning** - the site is built, but something is worth fixing. Here the engine points out that the title for the search engine and the heading on the page are the same, and it is better to make them different;
- **an error** - the site is not built. The engine gives the error code (for example, `E006`), the file and, where it can, the line number. What the codes mean - in [`21-engine.md`](../spec/21-engine.md).

To only check without building anything, replace `build` with `check` in the command: the report is the same, and it runs faster.

### Look at the built site

The preview from step 2 builds the site into a temporary folder. To look at exactly what is in `dist/`, serve it with a plain nginx web server:

```bash
docker run --rm -p 127.0.0.1:8080:8080 -v "$PWD/my-site/dist:/usr/share/nginx/html:ro" nginxinc/nginx-unprivileged:1.30.6-alpine
```

and open <http://localhost:8080>. Without Docker, `python3 -m http.server 8080 -d my-site/dist` does the same.

This is a server without the site's settings: the site's own "not found" page and the redirects from old addresses do not work here. How to check the whole site - in [06 · Build and deploy](06-deploy.md).

## Step 7. The production build

So far all builds were draft builds (dev): the site is closed to search engines and analytics counters are not added. Publishing needs a production build (prod):

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site --env prod --strict
```

- `--env prod` - production mode: the site is open to search engines, the counters from the settings are added;
- `--strict` - strict mode: any warning counts as an error, and the build stops. This way a broken link or an image without a description never reaches the live site.

If the strict build stopped, the engine lists what to fix. The `dist/` folder then stays from the last successful build - a broken site never gets into it. For example, the page from step 5 will not build while its `title` and `h1` are the same.

The finished `dist/` folder can be put on any hosting. How to pack it into a Docker image with nginx and deploy it to your own server - in [06 · Build and deploy](06-deploy.md).

## What next

- [03 · Pages and content](03-content.md) - all about pages: sections, images, links, translations;
- [04 · Theme and design](04-theme.md) - a ready theme: demo, reference, section views; how to change the look;
- [07 · Your own theme](07-theme-author.md) - if you make a theme yourself: block fields, hints, demo, packing;
- [05 · SEO](05-seo.md) - what the engine does for search engines by itself and what you can set.

The documentation of the same version as your engine is built into the engine itself:

```bash
docker run --rm ghcr.io/fmstm/heron:prod docs --lang en                    # contents
docker run --rm ghcr.io/fmstm/heron:prod docs --lang en seo                # the SEO section
docker run --rm ghcr.io/fmstm/heron:prod docs --lang en --search E023      # where an error code is mentioned
```

---

Next: [03 · Pages and content](03-content.md)
