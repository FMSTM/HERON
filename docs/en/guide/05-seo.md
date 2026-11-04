# 05 · SEO

This section is for whoever is responsible for how people find the site in search: a person or an AI agent in the "Content and SEO" role. We look at what the engine does for search engines by itself, what you need to fill in, and how to move from an old site without losing your positions in search results.

> **Without Docker?** In the commands below replace everything up to and including `ghcr.io/fmstm/heron:prod` with the word `heron` - more [in the installation section](00-install.md#without-docker). Commands are run from the folder that holds the site folder `my-site`.

## What the engine does by itself

You do not write anything in this table by hand, and none of it is kept as a separate file. The engine assembles it anew on every build - from the pages and `site.yaml`. So it never goes stale: change a page title, and on the next build the `<title>`, the sitemap and the markup all change too.

| What | Where it comes from | In detail |
|---|---|---|
| `<title>`, meta description, canonical | `title` + `seo.title_suffix`, `description`, the page address | [`20` §4.2](../spec/20-data-contract.md#frontmatter) |
| Open Graph and Twitter - the link card in social networks and messengers | fields of groups 3-4 of the SEO block, otherwise `title`/`description`/`seo.og_default_image` | [`20` §4.2](../spec/20-data-contract.md#frontmatter) |
| `sitemap.xml` - the sitemap for search engines | all published indexable pages, `lastmod` from `updated` | [`21` §9](../spec/21-engine.md#sitemap) |
| hreflang in `<head>` and in the map - the link between translations of one page | translations are found by file name, `x-default` is the default language | [`20` §3](../spec/20-data-contract.md#languages) |
| `robots.txt` | `seo.robots_extra` + the `Sitemap:` line; on a draft build (dev) only `Disallow: /` | [`21` §9](../spec/21-engine.md#robots-txt) |
| JSON-LD - schema.org markup | type from the theme, data from the page and the `schema` block in `site.yaml`, breadcrumbs, FAQ | [`21` §9](../spec/21-engine.md#json-ld) |
| `llms.txt`, `llms-full.txt` - a description of the site for AI models | page tree, `description`, `seo.llms_note` | [`21` §9](../spec/21-engine.md#llms-txt) |
| 301 and 410 - redirects and "this address is gone" | `redirect_from` of pages and `gone` in `site.yaml`, straight into the nginx config | [`21` §9](../spec/21-engine.md#redirects) |
| image in search results | the page cover - one image for all places: `og:image`, `twitter:image`, `primaryImageOfPage` in JSON-LD and the first image of the entry in `sitemap.xml`. `primaryImageOfPage` appears only if the theme declared `WebPage` or a derived type (`types.<type>.jsonld`) for the page type; the starter theme does not | [`20` §6, "Page cover"](../spec/20-data-contract.md#page-cover) |
| large previews | `<meta name="robots" content="max-image-preview:large, max-snippet:-1, max-video-preview:-1">` on every indexable page of a production build | [`21` §7](../spec/21-engine.md#cover-robots) |
| image sitemap | `<image:image>` in the page entry: the cover first, then the images from the text, no more than 20 | [`21` §9](../spec/21-engine.md#sitemap) |
| site name | `WebSite` with `name` and `alternateName` on the home page, from `site.name` and `site.alternate_names`. Only if the page type declares `WebSite` in `jsonld` in `theme.yaml` (usually the `home` type). The starter theme declares no `jsonld`: there are no such nodes on it, while `og:image` and the image map work | [`21` §9](../spec/21-engine.md#json-ld) |
| closed draft build | without `--env prod`: `noindex` on everything, `Disallow: /`, no counters | [`23`, "Engine version and site environment"](../spec/23-distribution.md#engine-version-vs-site-environment) |

## What you fill in <a id="you-fill"></a>

### On every page

At the top of every page file is the SEO block. Its group 1 is required:

- `title` - the title for search results, up to 60 characters. The ending with the site name is added by the engine;
- `h1` - the heading on the page itself, for someone who has already opened it. Not a copy of `title`: if they are the same, the engine warns;
- `description` - the description under the title in search results, up to 155 characters: what a person gets on this page;
- group 2 "key queries" - the engine does not read it, it is your working note. The rule: one intent (what a person wants to find) - one page. If two files have the same main query, they are worth merging into one page.

Fill in the other groups as needed: your own image for social networks (group 3), refining the markup (5), an image in the catalog and its `alt` (6), the publication date and `noindex` (7), old addresses (8).

### Once for the whole site

These are settings in `site.yaml`. Most of them are easier to fill in with the configurator (`setup`, see [02 · First site](02-first-site.md)), but this is how they look in the file:

```yaml
site:
  domain: example.com
  name: Workshop
  name_ru: Мастерская        # value for the Russian pages
seo:
  title_suffix: " - Workshop"
  title_suffix_ru: " - Мастерская"
  og_default_image: media/og/default.jpg
  llms_txt: true
  llms_note:                 # facts about the site for AI models, by language
    en: |
      Phone for bookings: …
    ru: |
      Телефон для записи: …
contact: { phone: "…", city: "…" }
organization: { name: "…" }
schema:
  entity:                    # site-wide node: who stands behind the site
    "@type": Organization
    name: "{{ organization.name }}"
    telephone: "{{ contact.phone }}"
analytics:
  ga4: G-XXXXXXX
```

`{{ … }}` in the `schema` block are substitutions from the same `site.yaml`. The phone and the address are written in one place, so they are always the same on the pages and in the markup. → [`20` §5, "Schema block"](../spec/20-data-contract.md#schema-block)

### The page cover

The cover is the image people see in the link card in a messenger and, with luck, in Google search results. Which photo becomes the cover is up to you; the engine does the rest.

- **Where it comes from.** The first one found: the page's `og_image`, then `image`, then the first image in the intro block or in `hero` (the first-screen block), then the site's `seo.og_default_image`. The image caption is `og_image_alt`, otherwise `image_alt`.
- **Size.** At least 1200 px wide. A smaller image is served as is, and `heron check` warns: "cover smaller than 1200 px".
- **Composition.** The face or the main subject - in the central third of the frame. Social networks and search results crop previews differently, and the edges go first.
- **No transparency.** The engine adds no background: a transparent PNG ends up on a black or white background at the search engine.
- **No cover at all** - the page has no `og:image` and no `primaryImageOfPage` (if the theme declared it), and `heron check` warns. This does not stop the build, but the preview in a messenger will be empty.
- **Your value wins.** If you set `primaryImageOfPage` or `entity.image` in the `schema` block yourself, the engine does not replace them with the computed cover.

### What people call the site

`site.alternate_names` are other names people search the site by: the old name, a transliteration, an abbreviation. For a separate language - `alternate_names_ru` and so on. They get into the markup only if the theme declared `WebSite` for the page type:

```yaml
types:
  home:
    jsonld: [WebSite]
```

Otherwise these values affect nothing, and the engine does not warn about it.

```yaml
site:
  name: Workshop
  alternate_names: [Workshop Studio, Atelier]
  alternate_names_ru: [Workshop RU]
```

An empty list means the key is absent in the markup. Write here only how people really call and search for the site, not keyword queries.

### Prices in the markup

Forbidden by default (error `E020`): if the site's pages show no prices, they must not appear in JSON-LD either. To allow them - `seo.allow_prices: true`.

### Update date

`lastmod` in the sitemap and `dateModified` in the markup are taken from `updated` in the page's SEO block. If it is absent - from the source `build.updated_from`:

- `git` - the date of the last commit of the file;
- `file` - the time the file was changed;
- `manual` - only what is written by hand.

An `updated` written by hand is stronger than the source. If you put it on all pages while moving a site, the git dates stop working - the report after the build shows how many pages ended up this way. Dates go to the search engine as full ISO 8601 with a time zone: from git it is the commit time (`2026-10-17T11:30:12+02:00`), a day written by hand is midnight UTC (`2026-10-14T00:00:00+00:00`). On the page itself the caption stays a plain date. A date from the future and an update earlier than the publication are warnings, and with `--strict` - errors.

## The image and extra links in Google <a id="google-images-sitelinks"></a>

To be honest about the limits: the engine prepares everything that depends on the site, but what to show in search results is Google's decision.

- **The image in search results.** The markup and the image sitemap give the search engine the right to show an image, not an obligation. After a deploy it usually takes 2-3 weeks for the image to appear, and on some pages it never appears.
- **What to check after a deploy:**
  1. Rich Results Test (a separate Google tool for checking rich results): paste the page address and make sure the markup reads without errors and `primaryImageOfPage` is in place.
  2. In Search Console: "URL Inspection" -> "Request indexing" - for the home page and a few main pages after a deploy.
  3. In Search Console: the "Images" report (in search performance, search type "Image"): in a few weeks impressions should appear there.
- **Extra links (sitelinks) are not switched on by markup.** There is no special markup for them, and the engine does not invent one - Google builds them by itself. What affects them: clear navigation in HTML (a menu of ordinary links), breadcrumbs, a unique `title` on every page, no duplicate pages and brand demand - how many people search for the site by name. The first is in your hands, the last comes with time.
- **Large previews** (`max-image-preview:large`) are switched on in `<head>` by the engine. They can be switched off only by closing the page to search: `noindex: true`.
- **Dev build.** Without `--env prod` pages are closed with `noindex, nofollow`, there are no images in `sitemap.xml`, and addresses lead to the dev domain. Checking how Google shows it makes no sense.

## Checking the schema.org markup <a id="schema-check"></a>

The engine contains the schema.org vocabulary version 29.3, and every node of your markup is checked against it. This catches what a search engine would silently ignore later: a type missing from the vocabulary, a property that does not fit the type, a value not from the enumeration, a value of the wrong type, something deprecated, an image from the markup that did not get into the build. These are codes `SCH001`-`SCH006`, the full list - [`21` §11](../spec/21-engine.md).

**Production and draft builds.** With `--env prod` a finding is an error, and the build stops. In other environments it is a warning: the site is built, and the report gets a line with the finding. To see in advance what will stop the production build, without building the site:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check my-site --env prod
```

**How to read a finding.** The report has a line like `CODE file:path - reason (pages: K)`:

- the code - what is wrong;
- the file and path - where to fix it;
- the number of pages - how many pages it affects. The same finding from different pages and languages comes as one line.

Under the line is the "exception key": a ready line you can copy (more on it below). With `--env prod` the same finding comes as an error in a short form: `CODE file: reason`, without the path and the number of pages; the exception key is printed there too.

**Fix first.** An exception is needed only when it cannot be fixed right now. Most often the fix is replacing a property or a type, as in the doctor example below.

**How to record an exception.** It is an entry in `site.yaml`; the reason is required, the deadline is optional:

```yaml
schema_exceptions:
  - key: "SCH002:site.yaml:schema.entity.worksFor"   # key copied from the report
    reason: "moving to practicesAt after the theme change"
    until: 2026-12-31                                  # optional
```

- without `reason` the build stops with `E011`; the same key twice is also `E011`;
- after the `until` date the exception stops working: the finding returns, and the report says "Exception expired";
- an exception that caught nothing is called redundant by the report - remove it;
- to skip a finding once without editing the file: `check my-site --allow-schema "<key>"`, the same works for `build`;
- an exception written through the configurator is permanent: if such a key already existed (including an expired one), the reason is replaced and the `until` deadline is removed. Need a deadline - set it by hand.

**The configurator checks too.** Before writing `site.yaml`, `setup` checks the site-wide node and the `schema` blocks and shows three lists: active findings, excepted ones and expired ones. A finding can be removed from the file or recorded as an exception - then the configurator asks for a reason.

### Example: a doctor, before and after

All data is fictional. Earlier the doctor was described as `Physician` and tied to a clinic through `worksFor`:

```yaml
schema:
  entity:
    "@id": "#owner"
    "@type": Physician
    name: "Ivan Obraztsov"
    worksFor:
      "@type": MedicalClinic
      name: "Sample Clinic"
    medicalSpecialty: "primary care"
```

Since release 24.0 a specific doctor in the vocabulary is `IndividualPhysician`. This is an organizational type, so `worksFor` is not valid for it (`SCH002`). The place of work is set with the `practicesAt` property with a type from the vocabulary list, and the specialty only with a `MedicalSpecialty` value, an address like `https://schema.org/<name>`:

```yaml
schema:
  entity:
    "@id": "#owner"
    "@type": IndividualPhysician
    name: "Ivan Obraztsov"
    practicesAt:
      "@type": MedicalClinic
      name: "Sample Clinic"
    medicalSpecialty: https://schema.org/PrimaryCare
```

The `practicesAt` property is still in the pending section of the vocabulary: it is valid, and the report only mentions it for information. If the specialty is written as an arbitrary string, that is `SCH003`: the value is not from the enumeration. → [`20` §5, "Schema block"](../spec/20-data-contract.md#schema-block)

## Languages

- A translation is a file with the same name in another language's folder. hreflang and the language switch appear by themselves.
- A translation can have its own address (`slug`): translations are linked by file name, not by address.
- One language - no hreflang, no per-language sitemaps, no `llms-<lang>.txt`: nothing extra is generated.
- No translation - a warning in the report, the language is inactive in the switch, and links to such a page from other languages lead to the version in the default language.
- The main language is empty - the production build stops (`E021`).

## Moving from an old site <a id="migrate-from-old-site"></a>

The goal of the move: no address the search engine already knows may return 404. Every old address either redirects (301) to a new page or honestly answers "this address is gone" (410).

1. **Export the old addresses.** Where to get the list:
   - Search Console -> "Pages" -> export (CSV; the engine takes the first column that looks like an address);
   - the old sitemap (`sitemap.xml`) - write the addresses out one per line;
   - a WordPress export or server logs.

   Save the list to the file `old-urls.txt` next to the site folder: one address per line, lines with `#` and empty ones are skipped. Then check:

   ```bash
   docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check my-site --old-urls old-urls.txt
   ```

   Every address must lead to a page, be in `redirect_from` or in `gone`. The rest go into warnings - with a hint where to redirect them most likely:

   ```
   old address /uslugi-dlya-primera/ leads nowhere; probably set a 301 to /ru/uslugi/: redirect_from: [/uslugi-dlya-primera/] in the frontmatter of ru/uslugi.md
   old addresses: 120, without a path: 7
   ```

   To close a warning, add the address to `redirect_from` of the suggested page (or another one, if the engine guessed wrong) or to `gone`, and run the check again. The work is done when the summary says "without a path: 0".

   **An address without a language prefix.** Old addresses usually have no `/ru/`, while in the new site a non-main language has a prefix. For the server `/x/` and `/ru/x/` are different addresses, so a redirect from `/ru/x/` does not serve the old `/x/`. Example: the old page `/uslugi-dlya-primera/` (a made-up address), the new one lives at `/ru/uslugi/`. Write the old address exactly as it was, without the prefix:

   ```yaml
   redirect_from:
     - /uslugi-dlya-primera/
   ```

   **Case.** `/About/` and `/about/` are different addresses for the server: write them as in the export. Addresses are compared the way nginx sees them: `https://` and the domain are dropped, encoded non-Latin letters (`%D0%BE…`) and plain ones count as one address, and so do addresses with and without a trailing slash; query parameters are taken into account only by `gone` entries with a parameter; repeats in the file count once.

   Where to redirect, the engine guesses by the last part of the address that looks like a slug or a page title. If nothing is found, it suggests the home page of that language - and then you decide: a suitable page or `gone`.
2. **The address has moved** - put it into the SEO block of the new page:

   ```yaml
   redirect_from:
     - /old-page/
     - /%D1%81%D1%82%D0%B0%D1%80%D0%B0%D1%8F/
   ```

   Cyrillic and percent-encoding are brought to one form: an address written in Cyrillic and its percent-encoded form (as in the second line) are one address, and the 301 works for either of them, with a slash and without.
3. **The address is gone** - put it into `gone` in `site.yaml`. The server answers 410, and the search engine drops the address from results faster than after a 404:

   ```yaml
   gone:
     - /sample-page/        # exactly this address
     - /wp/*                # everything under /wp/
     - /?p=*                # the home page with the parameter p
   ```

4. **Build the site.** The engine checks that the old address does not match a live page, does not lead to two places and does not form a chain of redirects (`E009`), and that 410 does not overlap with pages and redirects (`E022`).
5. **Check on the image.** If you have a clone of the engine repository, `scripts/site.sh <site> smoke prod` starts nginx with the site and checks the answers 200, 404, every 301 and every 410 - more in [06 · Build and deploy](06-deploy.md).

In detail: [`20` §2, "Old addresses"](../spec/20-data-contract.md#old-addresses-cyrillic), [`22` §6](../spec/22-deploy.md#migrate-existing-site).

## Before deploy

The last step is the production build in strict mode:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site --env prod --strict
```

`--strict` turns warnings into errors: a broken link, an image without `alt` or an unfilled required relation will not reach the live site. The build report counts pages by markup type - so you can see that JSON-LD is on all of them.

---

Next: [06 · Build and deploy](06-deploy.md)
