# 03 · Pages and content

How a page is built, how to add sections, links, images and translations. For those who run the site, a human or a content agent.

## Anatomy of a page

The file `content/en/services/roof.md` (a site with `default_lang: en`, address `/services/roof/`):

```markdown
---
# ================= 1. BASICS =================
title: "Roof repair in Springfield"     ← in search results, up to 60 characters
h1: "Roof repair, start to finish"      ← the heading on the page
description: "Patching, re-covering, one-year warranty."
…groups 2-8…
---

Intro: the first paragraph leads in.

The second paragraph is the promise. There is no third.

## What is included {#includes}

- **Inspection.** We come the day you call.
- **Repair.** Patching or full re-covering.

## FAQ {#faq}

### How much does it cost?

We quote after the inspection.
```

Its Russian translation is `content/ru/services/roof.md`: the same SEO block with Russian values, the same anchors `{#includes}` and `{#faq}`, Russian headings. The comments in the block are in the language chosen at `new --notes`, not in the language of the page.

Three parts, always in this order:

1. **SEO block** is the frontmatter of eight groups. `title`, `h1`, `description` are required; the rest as needed. All fields, their defaults and what the engine does with them are in one table: [`20` §4.2](../spec/20-data-contract.md#frontmatter).
2. **Intro** is the text before the first heading, no more than two paragraphs: the theme gets them as `lead` and `promise`.
3. **Sections** are `## Heading {#anchor}`. The visitor sees the heading, the anchor is the address of the section for the theme; the heading can be edited freely, the anchor cannot.

## A new page

Copy a ready file or run `heron page <type> <name>`: it puts the full SEO block and stubs of all sections the theme expects for this type. Then:

- change `title`, `h1`, `description`; fill in group 2, "search queries": the engine does not read it, but it keeps the rule "one intent, one page";
- write the intro and the sections. If you have no material for a section, **do not create it**: the theme does not draw an empty block, and the "Not filled" summary after the build will show what is missing;
- build. The page appears by itself in the section catalog, the sitemap, hreflang and `llms.txt`.

To delete a page, delete the file. If its address was in the index, put it into `redirect_from` of the replacement page (301) or into `gone` in `site.yaml` (410).

## Sections

A section is a folder with the page of the section itself, `_index.md`:

```
content/en/services/_index.md      →  /services/                catalog
content/en/services/roof.md        →  /services/roof/
content/en/services/gutter.md      →  /services/gutter/
content/ru/services/_index.md      →  /ru/uslugi/               slug: uslugi
content/ru/services/roof.md        →  /ru/uslugi/krovlya/       slug: krovlya
content/ru/services/gutter.md      →  /ru/uslugi/vodostok/      slug: vodostok
```

`slug` in `_index.md` changes the address of the section and of all pages in it: the Russian children end up under `/ru/uslugi/` by themselves.

In `_index.md` it is useful to set `children_type: service`, the type of all pages of the section, and the theme will draw them with its template. The catalog gets the children as `page.children`, sorted by `order`, then by `h1`. There is no pagination: a section is one page; a big section is split into subsections by folders.

A page that belongs to several sections is not nested in any of them: it is placed flat and linked with relation fields (below), so the address does not depend on how many places it is shown in.

## Section forms

The engine understands the form by the markup by itself and gives the theme parsed data:

| Markup | Form |
|---|---|
| paragraphs | `prose` |
| `- item`, `- **Term.** Explanation` | `list` |
| `1. **Step.** Text` | `steps` |
| `### Question?` and the answer under it | `faq` (and `FAQPage` in the markup) |
| `Key \| Value` line by line | `facts` |
| markdown table | `table` |
| two `###` groups with lists | `two-lists` |
| three or more `###` groups with lists | `checklist` |
| `> quote` without a list | `callout` |

Four more come only by class in the anchor: `{#flags .alert}` is `alert-list`, `{#plan .timeline}` is `timeline`, `{#photos .gallery}` is `gallery` (it needs a bulleted list of images: `- ![caption](media/a.png)`; a paragraph with an image gives prose and a warning), `{#options .tabs}` is `tabs` (`###` groups with any content). The full table, the order of recognition and what exactly the theme receives: [`20` §4.4](../spec/20-data-contract.md#section-forms).

### When the engine guesses wrong

The form is determined by the markup, and sometimes the markup says something other than what you meant. A class in the anchor is always stronger than a guess:

| You wrote | The engine decided | You meant | How to say it |
|---|---|---|---|
| text with `###` subheadings, no lists | `faq`: the subheading is the question, the text is the answer | prose with subheadings | `## About us {#about .prose}` |
| two `###` groups with lists | `two-lists`: "fits / does not fit" | a listing, for example documents in two groups | `## Documents {#docs .checklist}` |
| `key \| value` lines | `facts` | a "period - event" scale | `## Recovery {#recovery .timeline}` |
| a list and a quote under it | `list`, the quote goes to `section.callout` | - | works as intended |
| a list and a paragraph under it | `list`, the paragraph goes to `section.note` | text on the page | the starter theme does not draw `note`: the text will not reach the page; put the paragraph before the list (`section.lead`) or output `section.note` in your own module |

`facts` can have a lead-in: a paragraph before the "key | value" lines. The theme gets it as `section.lead`:

```markdown
## In short {#quick .facts}

The format in short:

Format | in person
Term   | about a month
```

If the theme in `theme.yaml` expects another form (`uses: ["docs:checklist"]`), the report after the build will say "expected checklist, got two-lists": fix it with a class in the anchor or with the form in `uses`, depending on who is right. If a template calls the module of this form directly (for example, `mod.steps("how")` on a prose section), the build fails with `E010`.

## Links

A link to your own page is written **from the root, without a language prefix**, best of all by key, the file path:

```markdown
[roof repair](/services/roof/)        in content/en/…  →  /services/roof/
[roof repair](/services/roof/)        in content/ru/…  →  /ru/uslugi/krovlya/
[home](/)                             in content/en/…  →  /
[home](/)                             in content/ru/…  →  /ru/
```

The engine substitutes the address in the language of the page, with all `slug`s: the same thing is written in both languages, the key. If there is no translation, the link leads to the version in the default language and the report has a warning. A link to nowhere is a warning with a file and a line. External addresses, `/media/…` and anchors are left alone.

→ [`20` §2, "Links inside content"](../spec/20-data-contract.md#links-relative-to-language)

## Relations between pages

"See also", "related services", "where it is mentioned" are not written as links by hand. The theme declares a relation field in `theme.yaml`, and the page lists file names in it:

```yaml
related:                 # in the SEO block, group 8
  - gutter
  - slug: inspection
    note: Not sure where to start? Begin here
```

The engine checks that such pages exist (`E006` if they do not), gives the theme cards with captions and builds a reverse list on the target pages.

→ [`20` §6, "Relations"](../spec/20-data-contract.md#theme-yaml)

## Images, video, documents

Everything goes in `media/`. The path is written from the site root, with or without a leading `/`: `media/a.png` and `/media/a.png` are resolved by the engine to the same address.

```yaml
image: media/services/roof.png        # preview in the catalog
image_alt: "Roof after the repair"
```

```markdown
![Gutter layout](media/services/gutter.png)
[Checklist in PDF](media/docs/memo.pdf)
```

The engine resizes the images to the proportions and widths of the theme, makes WebP and AVIF, and sets the sizes. Illustrations (with a transparent background) are fitted into the proportion, photos are cropped. A missing file is the error `E007` with the page name; a file in `media/` that nobody links to is a line in the report. Video uses the fields `video`, `video_poster`.

→ [`20` §7](../spec/20-data-contract.md#images)

## Languages and translations

A translation is a file with the same name in the folder of another language: `content/ru/services/roof.md`. Its own address is `slug: krovlya`. The link between translations is held by the file name, so changing `slug` does not break it: both versions get hreflang to each other, and `x-default` is the English one. If a language is not in `site.languages`, its folder is not read.

→ [`20` §3](../spec/20-data-contract.md#languages)

## What is not written in pages

- phone, address, hours, social networks go into the `contact` and `organization` blocks in `site.yaml`: the theme and the markup take them from there, and they do not diverge between the header and the footer;
- reviews, team, numbers go into `data/*.yaml`;
- the menu is `nav` in `site.yaml`;
- 410 for deleted addresses is `gone` in `site.yaml`.

---

Next: [04 · Theme and design](04-theme.md)
