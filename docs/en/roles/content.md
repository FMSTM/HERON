# Role: Content and SEO

Write and move pages, fill in the SEO block, keep translations and old addresses. Common rules - [`README.md`](../README.md); how a page works, in plain words - the guide [03 · Pages and content](../guide/03-content.md); what is generated automatically - [05 · SEO](../guide/05-seo.md).

**Input:** the site structure (keys, types, sections per type, languages) and the client's texts or facts. For an existing site, the folder itself.
**Output:** files `content/<lang>/…md`, images in `media/`, reference data in `data/`, `redirect_from` on pages, a list of content debts and questions.

**Limits.** You write only to `content/`, `media/`, `data/`. `theme/`, the structure of `site.yaml` (languages, theme, menus), `.github/`, scripts are not yours. Facts that are not in the source go to `agents/work/questions.md`, the field stays empty. The report is `agents/work/report.md` in the form of [`templates/report.md`](../templates/report.md). Done when `heron check . --strict --json` exits with code 0.

## 1. Create a file

```bash
heron describe --json my-site                                     # the fields and hints of the theme
heron page add roof --type service --category services my-site --dump > roof.yaml
heron page add roof --type service --category services my-site --answers roof.yaml
```

One command - a page in **all** languages of `site.yaml`: `content/<lang>/services/roof.md`. Exists - edit, missing - create. `--dump` prints all fields per language (for a new page - the stub), you fill them in and pass them back with `--answers`; the path of a field is as in `heron describe --json` (`title`, `sections.faq.items`). A language you do not translate yet is `de: pending` or one without fields: the file gets the main-language text and `translation: pending`, the production build does not publish it (`20` §4.2). `heron page list my-site --json` shows where the translation is pending. A section is `heron category add services my-site`, moving a page is `--category` of another section (the 301 from the old addresses is set by itself). Answer errors are `E039`, the old form `heron page <type> <name>` is `E038`. An agent works only this way - with flags, `--dump` and `--answers`, without `-it`; the questions in the console and the studio in the browser (`heron studio`) are for a human, they write the same files. What the theme expects from every block, with an example and markdown, - `heron describe <type>` and `heron docs theme-ref .`; section views - the `--view` flag of `heron category add`.

The type must be declared in the theme's `types`. The starter theme has only `home`, `page`, `404`; another type gives `E041` for `page add` and `E008` in the build, the designer adds it first.

`heron page add` puts the full SEO block and stubs of **all** sections the theme declared for the type (`types.<type>.uses`). You can also copy a ready file - the result is the same. A sample of a filled-in page - [`templates/page.md`](../templates/page.md).

The file name is the page key: Latin letters, digits, hyphen; **the same in all languages**. A different address for a translation is the `slug` field.

## 2. SEO block

Eight groups; the order and the comments are kept; empty optional fields stay commented out.

| Group | What to fill in |
|---|---|
| 1. Basics | `title` (up to 60 characters, for search results), `h1` (for someone who opened the page; not a copy of `title`), `description` (up to 155 characters: what the visitor gets). `slug` if the address differs from the file name. Do not touch `canonical` and `robots` |
| 2. Search queries | the main one and additional ones. The engine does not read them; the rule is one intent, one page |
| 3-4. Open Graph, Twitter | only if it differs from `title`/`description`/the default image |
| 5. Schema.org | markup refinements for this page; organization data goes not here but in `site.yaml` |
| 6. Card | `image` + `image_alt` for the catalog; `order`; `type` if the section does not set it |
| 7. Service | `date`, `updated`, `published`, `noindex` |
| 8. Relations | the theme's relation fields (file names without `.md`) and `redirect_from` |

All fields and default values - `20` §4.2.

## 3. Text

- **intro** - before the first `##`, no more than two paragraphs: the lead and the promise;
- **sections** - `## Heading {#anchor}`, anchors come from the type's `uses`. A typo in an anchor shows up as a "the theme does not use" line in the report;
- the section **form** is set by markup: a list, `1.` steps, `### Question?` FAQ, `key | value` facts, a table, `>` a tip; the classes `.alert`, `.timeline`, `.gallery` go in the anchor. The table is in `20` §4.4;
- **no material - no section.** Delete the stub from `heron page add`, do not fill it with generic words.

## 4. Links and relations

- to your own pages - by key from the root without a language prefix: `[roof](/services/roof/)`, the home page is `(/)`. The engine puts in the address of the right language;
- "see also", "on the topic" - relation fields from `theme.yaml` (`related: [gutter]`), not hand-made lists of links;
- phone, address, hours, social networks - not in the text but in `contact`/`organization` in `site.yaml`.

## 5. Images

Files go to `media/`, the path is from the site root: `media/services/roof.png`. Illustrations - PNG/WebP with a transparent background, photos - JPEG; the engine makes the renditions itself. Every image has `alt` (`image_alt`, the caption in `![…]`).

**The page cover** (the picture in search results and social networks) is chosen by a field: `og_image` (caption `og_image_alt`), otherwise `image`, otherwise the first picture in the intro block or `hero`, otherwise `seo.og_default_image` (`20` §4.2, ["Page cover"](../spec/20-data-contract.md#page-cover)). `alt` is required. A photo - at least 1200 px wide, opaque; the file only in `media/`, not in `static/`. Under 1200 px - it is served as is, `heron check` warns. No cover - `og:image` is not output, a warning, not an error.

## 6. Migration

- an old address whose content has moved - `redirect_from` on the new page, in Cyrillic or `%D0%…`;
- two or three old pages about the same thing - one new page, all addresses in its `redirect_from`;
- addresses that no longer exist - in `gone` in `site.yaml`, not in a page.

The migration order - guide [05](../guide/05-seo.md#migrate-from-old-site).

Check: `heron check . --old-urls <file>` - a file with the old addresses (one address per line, or a Search Console export). An address that leads nowhere goes into the report with a hint: add it to the page's `redirect_from` or to `gone` (`21` §10, §11). An address is compared the way nginx sees it: the scheme and host are dropped, `%XX` and Cyrillic are equal, with and without a trailing slash is one address; case and the language prefix are distinguished (`/About/` and `/about/` are different addresses); query parameters count only for `gone` entries with a parameter.

## 7. Languages

A translation is a file with the same name in `content/<lang>/`. No translation - the page stays in the main language, with a warning in the report. The main language cannot be empty in production (`E021`).

## Checklist

- [ ] every page of the structure has a file; file names are the same in all languages
- [ ] `title`, `h1`, `description` are filled in and differ; group 2 is filled in
- [ ] not a single invented fact; anything unverified goes to the questions
- [ ] no empty placeholder sections
- [ ] links by keys; relations by theme fields
- [ ] images have `alt`
- [ ] old addresses are split between `redirect_from` and `gone`; `check --old-urls` has no lost addresses
- [ ] the cover is chosen by the `image`/`og_image` field and has an `alt`
- [ ] `check` has no errors; the "Not filled" summary goes to the report
