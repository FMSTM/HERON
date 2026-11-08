# 03 · Pages and content

This section is all about pages: what a page file consists of, how to add a new page and a whole section, how to write sections, links, images and translations. It is for those who run the site and write the texts - a person or an AI agent.

We continue the site from [02 · First site](02-first-site.md): commands run from the `~/sites` folder, and the site is in `my-site`.

> **Installed the engine without Docker?** Then in every command replace everything up to and including the image name (`ghcr.io/fmstm/heron:…`) with the word `heron`. More - [in the installation section](00-install.md#without-docker).

## What a page consists of

Every page is one markdown file in the `content/<language>/` folder. The file path sets the page address. For example, the file `content/en/services/roof.md` on a site with `default_lang: en` opens at `/services/roof/`. This is what it looks like:

```markdown
---
# ================= 1. BASICS =================
title: "Roof repair in Springfield"     # in search results, up to 60 characters
h1: "Roof repair, start to finish"      # the heading on the page
description: "Patching, re-covering, one-year warranty."
…groups 2-8…
---

We have been repairing roofs in Springfield since 2010.

We come out to inspect the roof the same day you call.

## What is included {#includes}

- **Inspection.** We come the day you call.
- **Repair.** Patching or full re-covering.

## FAQ {#faq}

### How much does it cost?

We quote after the inspection.
```

Its Russian translation is the file `content/ru/services/roof.md`: the same SEO block, but with Russian values, the same anchors `{#includes}` and `{#faq}`, Russian headings. The comments in the SEO block are written in the working language you chose when creating the site (`new --notes`), not in the language of the page.

The file has three parts, always in this order:

1. **The SEO block** - everything between the `---` lines at the start of the file. It is split into eight groups. Only `title`, `h1` and `description` are required; the rest is filled in as needed. All fields, their defaults and what the engine does with them - in one table: [`20` §4.2](../spec/20-data-contract.md#frontmatter).
2. **The intro** - the text before the first heading, no more than two paragraphs. The theme gets the first paragraph as `lead` and the second as `promise`.
3. **Sections** - each starts with a line `## Heading {#anchor}`. The visitor sees the heading, and the anchor is the section name for the theme: by it the theme knows where and how to show the section. You can change the heading as you like, but not the anchor.

## A new page

The easiest way to create a page is the `page add` command:

```bash
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add about my-site
```

After `page add` come the page **key** (`about`; if the page lies in a section folder, the key is the folder plus the name, for example `services/roof`) and the site folder. The command has one rule: no page - it is created in all languages of the site at once, the page exists - it opens for editing. The file gets a full SEO block and drafts of every section the theme expects for this type: each already in its form (a list, steps, questions) with sample text from the theme, the section heading is the marker `TODO heading`. You can build and look at the draft at once, but the production build (`--env prod`) does not release a page with `TODO` markers and placeholder text: error `E040` names the file and the field. You can also do without the command: copy a ready file under a new name into every language folder.

### How to answer the questions <a id="questions"></a>

`-it` in the command is needed so that the engine can ask questions. It asks field after field, and every field has the same rules:

- in square brackets - the value that stays if you just press **Enter**: from `site.yaml`, from the theme or from the stub;
- next to the field name - a one-line hint, and **`?`** instead of an answer shows detailed help: what it is, what it affects on the site and in search, a good example and common mistakes. The help on blocks is written by the author of the theme;
- **`-`** clears the field, **Ctrl+C** - quit without writing;
- an answer with an error is marked at once and asked again: an empty required field, a value not from the list, a picture not from `media/` or without a file. A remark is shown and the engine goes on, the answer is written: `title` longer than 60 characters, `description` longer than 155, `title` equals `h1`, a text shorter or longer than the theme asks. The rules are the same as for `check`;
- a list (items, `redirect_from`) is asked one item per line: type the first item, then the next ones, an empty line ends the list, Enter at once keeps it as it is. For items with fields (a question and an answer, a term and a text) first `+`, then the fields of each item in turn; an empty first field ends the list.

The order of questions: the category - a number from the list (`0` - the root of the site, `1+` - a new category inside the first one, `+` - a new one at the top), the page type if the theme has several, then the fields by groups. "Search: title and description" and "Address and type" are always asked, "Menu and order", "Cover", "Social networks and messengers" and "Publishing" - with the question "Change? [y/N]": Enter leaves the group as it is. The blocks of the page come last - in the order the theme expects them. This is how it looks (shortened):

```
New page about - languages: en (main), ru
Enter - keep the value in brackets, ? - help on the field, - - clear the field, Ctrl+C - quit without writing
Category - the section of the site the page lives in; the address of the page starts with it
    0  / - the root of the site, no category
    1  structure  Structure
  › [/]
  title (required) - The title in search results and on the browser tab, up to 60 characters
  › [About] About the workshop and the people
  h1 (required) - The heading on the page itself - for someone who has already opened it
  › [About] About us
Menu and order
  menu: no; nav_title: About us; order: 999 - Change? [y/N]
```

### Translations in the questions <a id="questions-translation"></a>

The engine asks the main language in full. Then, for every other language, - only the fields with text: the headings, the description, the texts of the blocks. Under the question you see the text of the main language: type the translation or press Enter to skip the field. A skipped field keeps the text of the main language in the file, and the language gets the mark `translation: pending` (below). Open the page again - the engine asks for the translation once more, and at the end offers to remove the mark. At the very end - "Summary" by files and "Write?": the files appear only after the answer Enter or `y`.

### Without questions: an agent and scripts <a id="answers"></a>

Agents and scripts do not need questions, and there is no `-it` in their commands. `--dump` prints all fields of the page as YAML, `--answers file` writes the answers from a file (the same fields per language; a language without a translation - `pending`), and `--lang de` edits one language only. Without a terminal and without answers the command creates a page from the stub and leaves an existing one alone. `key` in the answers wins over `category`: a new key moves the page as a whole, and `category` from the same dump is then not applied (changed only `category` - a move into that category with the same name). Field paths and hints - `describe --json`:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add about my-site --dump > about.yaml
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add about my-site --answers about.yaml
```

### When the page is created <a id="after-page-add"></a>

Then:

- change `title`, `h1` and `description`. Fill in group 2, "key queries": the engine does not read it, but it helps keep the rule "one query - one page", so that two pages do not compete in search for the same thing;
- write the intro and the sections. If there is no material for a section - **do not create it**: the theme does not draw an empty block, and the "Not filled in" summary after the build shows what is missing;
- build the site. The page appears by itself in the catalog of its section, in the sitemap, in the links between translations (hreflang) and in `llms.txt`.

**Translation pending.** If a translation is skipped while creating, the language file gets the text of the main language and the line `translation: pending` in group 7 of the SEO block. A draft build and the preview show such a page with a yellow "translation pending" banner, and a production build (`--env prod`) does not publish it in this language: neither the page nor links to it in the menu, the sitemap and hreflang; the build report names such pages in a list, and with `--strict` it is an error. Once translated, delete the line, and the page appears. A category that is not translated (`_index.md` with the mark) - the production build does not publish it in that language, nor any page inside, even translated ones: they are in the report list too and in `pending` of `check --json`.

To delete a page, delete its file. If the old address was already in search, do not abandon it: add this address to `redirect_from` of the page that replaces it (the visitor is redirected, code 301), or to `gone` in `site.yaml` (the address answers "gone for good", code 410).

## The studio in a browser <a id="studio"></a>

The same - creating a page or a section, editing fields, translating, moving - can be done with the mouse, in the studio. The `studio` command opens it:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -p 127.0.0.1:8001:8001 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod studio my-site
```

The engine prints an address like `http://localhost:8000/#key` - open it whole, together with the part after `#`: this is the access key, without it the studio shows nothing. The studio is open on your computer only and closes with Ctrl+C in the terminal. The `--web` flag of `page add` and `category add` opens it right on the page or section you need - with the same `-it -p 127.0.0.1:8000:8000 -p 127.0.0.1:8001:8001`. Port 8001 is for the page preview and the theme reference: the studio shows them from a port of their own, apart from the page with the key, so that theme scripts cannot reach the key:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -p 127.0.0.1:8001:8001 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add about my-site --web
```

What you will see:

- three tabs: Site - the `site.yaml` configurator, Pages - the work with content, Theme reference - what the theme can do: every block with its hint, a live example and its markdown next to it ([more](04-theme.md#theme-reference));
- on the left - the tree of sections and pages. Each shows the languages of the site: `RU` - the file exists, `DE!` - the translation is not ready, struck through - there is no file. A page or a section can be dragged into another section: the files move in all languages, the old addresses get a 301;
- on the right - the fields of the page by groups, as in the questions of `page add`: titles and description for search, the address, the menu, the cover, social networks, publishing, then the blocks of the page. Hover over the name of a field - a short hint; the `?` button opens help with an example. Errors and remarks show right at the field, by the same rules as `check`. A section also has its view here (cards, a list - what the theme can do) and the type of the pages inside;
- language tabs above the fields. The main language has all fields, the others - only the texts. In a new language file an empty field means "not translated yet": the language gets the mark `translation: pending`, and the production build does not publish it until the translation is there;
- "+ Page" and "+ Category" (that is, a section) create a draft in all languages at once, "+ Block" adds a section of the form you need in all languages (on languages already translated it gets the "translation pending" mark, and before saving the studio asks: "en, de will leave publication until translated - continue?"; `page add` asks the same), "Upload" at a picture puts the file into `media/` and checks its width and proportions, "Check" and "Preview" do what `check` and `serve` do.

The studio writes the same files as the commands, and only what you changed: your comments, the order of the fields and the hand-written markup stay as they were. The files appear on disk with the Save button.

## Sections

A section is a folder of pages plus a separate page of the section itself, the file `_index.md`. For example, the "Services" section:

```
content/en/services/_index.md      →  /services/                catalog
content/en/services/roof.md        →  /services/roof/
content/en/services/gutter.md      →  /services/gutter/
content/ru/services/_index.md      →  /ru/uslugi/               slug: uslugi
content/ru/services/roof.md        →  /ru/uslugi/krovlya/       slug: krovlya
content/ru/services/gutter.md      →  /ru/uslugi/vodostok/      slug: vodostok
```

A section (a category) is created by `category add` - in all languages at once, with its page `_index.md`, the view of the list of pages and the type of the pages inside; a nested section - by a path with `/`:

```bash
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod category add services my-site
```

The `--category` flag puts a page straight into the right section (if there is no section, it is created):

```bash
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add roof --category services my-site
```

The same flag on an existing page is a move: the files move in all languages, and a 301 is set from the old addresses (`redirect_from`). A whole section, with all pages inside, is moved the same way: by dragging in the studio tree or with a new key (`key`) in the `--answers` of the `category add` command. Moved a page back to where it already was - its former address leaves `redirect_from`, otherwise it would point to itself (`E009`). A section anchor changes in all languages at once: it is part of the page structure, and `check` warns if the anchors differ in some language.

What matters about sections:

- `slug` in `_index.md` changes the address of the section itself and of all pages in it: the Russian pages of the section end up under `/ru/uslugi/` by themselves. If you change `slug` with `page add`, `category add` or in the studio, every page with a new address gets the old one in `redirect_from` - the old addresses answer 301;
- in `_index.md` you can set the type for all pages of the section, for example `children_type: service` - if the theme has such a type (the white starter theme has only `home`, `page` and `404`; with an unknown type the build stops with error `E008`). Then the theme draws them with its own template;
- how the section page shows its pages - as cards, a list or otherwise - is decided by the **view** (`view` in `_index.md`, the `--view` flag of `category add`, a field in the studio). Every theme has its own views - [04 · Theme and design](04-theme.md#category-views);
- the section page gets the list of its pages as `page.children`. They are sorted by the `order` field, and with equal `order` - by `h1`;
- there is no pagination: a section is one page. A large section is split into subsections - nested folders.

If a page belongs to several sections at once, it is not nested in any of them. It is put at the top level and linked to the sections with relation fields (see below) - this way the page address does not depend on how many places it is shown in.

## Section forms

You write a section in ordinary markdown, and the engine works out from the markup what it is - a list, steps, questions and answers - and hands the theme already parsed data. This kind of section is called a **form**:

| Markup | Form |
|---|---|
| paragraphs | `prose` |
| `- item`, `- **Term.** Explanation` | `list` |
| `1. **Step.** Text` | `steps` |
| `### Question?` with the answer under it | `faq` (and `FAQPage` in the markup) |
| `Key \| Value` line by line | `facts` |
| a markdown table | `table` |
| two `###` groups with lists | `two-lists` |
| three or more `###` groups with lists | `checklist` |
| `> quote` without a list | `callout` |

Four more forms the engine does not guess from the markup - they are set with a class in the anchor:

- `{#flags .alert}` - `alert-list`;
- `{#plan .timeline}` - `timeline`;
- `{#photos .gallery}` - `gallery`. It needs a bulleted list of images: `- ![caption](media/a.png)`; a paragraph with an image gives prose and a warning;
- `{#options .tabs}` - `tabs`: `###` groups with any content.

The full table of forms, the order in which the engine recognizes them and what exactly the theme gets - [`20` §4.4](../spec/20-data-contract.md#section-forms).

### When the engine guesses wrong

The form is decided by the markup, and the markup sometimes says something other than what you meant. A class in the anchor always beats the engine's guess:

| You wrote | The engine decided | You meant | How to say it |
|---|---|---|---|
| text with `###` subheadings, no lists | `faq`: the subheading is the question, the text is the answer | prose with subheadings | `## About us {#about .prose}` |
| two `###` groups with lists | `two-lists`: "fits / does not fit" | a listing, for example documents in two groups | `## Documents {#docs .checklist}` |
| `key \| value` lines | `facts` | a "period - event" scale | `## Recovery {#recovery .timeline}` |
| a list and a quote under it | `list`, the quote goes to `section.callout` | - | works as intended |
| a list and a paragraph under it | `list`, the paragraph goes to `section.note` | text on the page | the starter theme does not draw `note`: the text will not reach the page; put the paragraph before the list (`section.lead`) or output `section.note` in your own module |

`facts` can have a lead-in - a paragraph before the "key | value" lines. The theme gets it as `section.lead`:

```markdown
## In short {#quick .facts}

The format in short:

Format | in person
Term   | about a month
```

A theme can say in advance which form it expects for a section - in `theme.yaml` (`uses: ["docs:checklist"]`). If a different one arrives, the report after the build says "expected checklist, got two-lists". Fix the class in the anchor or the form in `uses` - whichever is right. And if a theme template calls a form module directly (for example, `mod.steps("how")` on a section that is actually prose), the build stops with error `E010`.

## Links

Write a link to your own page **from the site root and without a language prefix**. Best of all - with the key, that is, the file path:

```markdown
[roof repair](/services/roof/)        in content/en/…  →  /services/roof/
[roof repair](/services/roof/)        in content/ru/…  →  /ru/uslugi/krovlya/
[home](/)                             in content/en/…  →  /
[home](/)                             in content/ru/…  →  /ru/
```

In both languages you write the same thing - the key, and the engine puts in the address in the page language by itself, with all `slug` values. What else it does:

- no translation of the page - the link leads to the main language version, and the report has a warning;
- the link leads nowhere - a warning with the file and the line;
- external addresses, links to `/media/…` and anchors are left alone.

More - [`20` §2, "Links inside content"](../spec/20-data-contract.md#links-relative-to-language).

## Relations between pages

Blocks like "See also", "Related services", "Mentioned in" do not have to be put together with links by hand. The theme declares a relation field in `theme.yaml`, and a page lists the file names of other pages in it:

```yaml
related:                 # in the SEO block, group 8
  - gutter
  - slug: inspection
    note: Not sure where to start? Begin here
```

In the second form - `slug:` with `note:` - a caption is added to the link. Here `slug` is not an address but the same key (file name) of the page: the field is called that for historical reasons. The engine does the rest: it checks that such pages exist (if not - error `E006`), hands the theme cards with captions and builds the reverse list on the pages that were referenced.

More - [`20` §6, "Relations"](../spec/20-data-contract.md#theme-yaml).

## Images, video, documents

All files go into the `media/` folder. The path to them is written from the site root, with or without a leading slash: the engine treats `media/a.png` and `/media/a.png` as one address.

The preview image of a page for the catalog is set in the SEO block:

```yaml
image: media/services/roof.png        # preview in the catalog
image_alt: "Roof after the repair"
```

In the page text, images and documents use ordinary markdown:

```markdown
![Gutter layout](media/services/gutter.png)
[Checklist in PDF](media/docs/memo.pdf)
```

The engine handles images by itself:

- it cuts them to the ratios and widths the theme asks for, makes WebP and AVIF versions and sets the sizes;
- illustrations (with a transparent background) are fitted into the ratio whole, photos are cropped;
- if the file is missing - error `E007` with the page name; if a file is in `media/` but nothing links to it - a line in the report.

Video is set with the `video` and `video_poster` fields (the image you see before playback). More - [`20` §7](../spec/20-data-contract.md#images).

## Languages and translations

A translation of a page is a file with the same name in the folder of another language, for example `content/ru/services/roof.md`. The translation gets its own address with the field `slug: krovlya`.

Translations are tied together by the file name, so changing `slug` does not break the tie. Both versions get links to each other for search engines (hreflang), and the version of the main language counts as the default (`x-default`) - in our example, English. If a language is not in `site.languages`, the engine does not read its folder.

More - [`20` §3](../spec/20-data-contract.md#languages).

## What does not go into pages

Some things repeat on many pages, so they are kept in one place:

- phone, address, opening hours, social links - the `contact` and `organization` blocks in `site.yaml`. The theme and the markup for search engines take them from there, so they are always the same in the header and the footer;
- reviews, team, figures - the `data/*.yaml` files;
- the menu - `nav` in `site.yaml`;
- deleted addresses that must answer 410 - `gone` in `site.yaml`.

---

Next: [04 · Theme and design](04-theme.md)
