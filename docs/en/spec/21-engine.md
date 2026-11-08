# HERON - the engine

**Document 2 of 4.** Previous: `20-data-contract.md`. Next: `22-deploy.md` (site deployment), `23-distribution.md` (engine distribution).

---

## 1. What the engine does

It reads the site folder - `site.yaml`, `content/`, `data/`, `media/`, `static/` and the theme - and produces a ready static site in `dist/`.

One command, one pass, no state between runs. Build twice in a row and you get a byte-identical result.

The engine lives in the image `ghcr.io/fmstm/heron:<channel or version>` and in a pip package, not in the site folder. The first thing it does is compare its version with the `heron:` requirement in `site.yaml`; it refuses to build an incompatible site (`E012`).

The build runs **without network**. No stage goes outside: everything the site needs is in the site folder.

## 2. Stack

Python 3.12. Dependencies are minimal - each one must be justified, because a beginner developer will maintain this.

| Package | Why |
|---|---|
| `markdown-it-py` | markdown parsing; `{#id}` is parsed by the engine's own rule (`heron/core/parser/markdown.py`) |
| `PyYAML` | frontmatter and configs |
| `Jinja2` | templates |
| `Pillow` | image resizing and conversion |
| `pydantic` | validation of the frontmatter and `site.yaml` with clear messages |
| `click` | CLI |

Package manager - `uv`. Linter and formatter - `ruff`. Tests - `pytest`.

## 3. Code layout

Three levels: contracts, core, modules. The split is not cosmetic - the plugin boundary runs along it: a module and a plugin are written against the same hooks.

```
heron/
├── cli.py                all commands (§10)
├── docs.py               heron docs
├── messages.py           command-line texts in two languages
├── build_info.py         version, branch, commit
├── texts/                core messages by group
├── setup/                the heron setup configurator
├── themes/               theme installation and packing
├── edit/                 lossless page editing: fields, places in markdown, checks
├── contracts/
│   ├── loader.py         reading YAML, pydantic complaints
│   ├── schemas.py        JSON Schema and the error registry
│   ├── wiring.py         joining the theme and the site
│   ├── site.py           pydantic schema of site.yaml, including the version requirement
│   ├── theme.py          schema of theme.yaml and the field contract of a theme
│   ├── fields.py         service fields of a page
│   ├── frontmatter.py    schema of the frontmatter
│   └── version.py        check of the engine version against site.yaml
├── core/
│   ├── models.py         Site, Page, Section, Nav
│   ├── parser/
│   │   ├── frontmatter.py
│   │   ├── markdown.py   markdown-it environment, heading attributes
│   │   ├── sections.py   splitting by headings with anchors
│   │   └── blocks.py     parsing of structured sections: facts, faq, steps
│   ├── tree.py           walk of content/, building the page tree and URLs
│   ├── build.py          build pipeline
│   ├── check.py          template check, E033
│   ├── describe.py       heron describe: the theme contract outwards
│   ├── demo.py           the theme demo: is everything declared shown, E037
│   ├── dates.py          update date
│   ├── environment.py    build environment
│   ├── notes.py          heron-readme.md notes
│   ├── notfound.py       the 404 page
│   ├── output.py         owners and writing of the result
│   ├── paths.py          file boundaries
│   ├── progress.py       build progress
│   ├── urls.py           addresses and domain
│   ├── watch.py          preview with rebuilds
│   ├── data.py           loading data/ into the template namespace
│   ├── links.py          relation resolve: catalogs, languages, fields declared by the theme
│   ├── render/
│   │   ├── env.py        Jinja2 environment, mod.* macros
│   │   ├── pages.py      page rendering
│   │   ├── themeref.py   the theme reference: /_heron/theme/, docs theme-ref
│   │   └── signature.py  engine signature
│   ├── media.py          image processing
│   ├── resolver.py       lookup of the theme and plugins: local → packages
│   ├── hooks.py          registry of extension points and their calls
│   ├── report.py         check report, warning summary
│   └── errors.py         error types and codes
├── schemaorg/            markup check against the schema.org 29.3 vocabulary
│   ├── validate.py       node validator (a pure function), codes SCH001-SCH005
│   ├── policy.py         finding path -> file and key, strictness, exceptions, site_findings for the configurator
│   ├── images.py         SCH006: markup images and the build
│   ├── schemaorg-29.3.json  compressed vocabulary index
│   └── NOTICE.md         source, license, attribution
├── modules/              the same as plugins, only shipped in the core
│   ├── sitemap.py
│   ├── robots.py
│   ├── llms.py
│   ├── jsonld.py
│   ├── redirects.py
│   ├── nginx.py      nginx config
│   └── feed.py
└── scaffold/             sample files for new and init
```

The boundaries are strict: **the core knows nothing about the domain of any site.** A client name, a domain, a phone number, the slug of a specific page in the core code is an error. A pre-commit hook of the core repository checks this, not the developer's memory.

Everything specific lives in the site folder: `content/`, `data/`, `site.yaml` and the theme.

## 4. Build pipeline <a id="build-pipeline"></a>

Eight stages, strictly in order. Each one can stop the build.

**1. Loading configs.** The engine version is checked against the `heron:` key in `site.yaml`, then `site.yaml` itself and `theme.yaml` of the found theme are loaded. Pydantic validation. The version does not fit, the theme is not found or a page type has no template - stop.

**2. Tree walk.** A recursive pass over `content/<lang>/`. For each file the URL, the type (from the folder's `_index.md` or the default) and the language are determined. A flat list of pages is formed.

The address and the key are built separately:

- **key** - the folder path plus the file name without extension. It never
  looks at the slug: gluing them together would forbid languages different addresses, and
  would turn renaming an address into a broken link between translations
- **address** - the same chain of segments, but each one is replaced by the slug of its
  section if the section declared one, and by its own `slug` if the page itself
  declared one

Section slugs are collected by a separate pass over `_index.md` before the walk of
files: the engine meets a child page earlier than the index of its section,
and the child's address depends on how the parent named itself.

#### File boundaries

The build reads only the site sources, writes only to the build folder and the cache,
deletes only what it owns. A path is first normalized, then
resolved by the file system with all symbolic links, and only the
result is compared with the root (`heron/core/paths.py`). A string
check for `../` is not used: a symbolic link contains no dots.

| Operation | Where allowed | Violation |
|---|---|---|
| reading pages and data | inside `content/`, `data/` | a file link pointing outside - `E024` |
| reading resources | inside `media/` (`img/`) | `media/../x`, a link pointing outside - `E024` with the page where the path is declared |
| copying `static/`, theme `assets/` | inside its own folder; a link into the same folder is allowed | a link or a folder link pointing outside - `E024` |
| theme templates (`include`, `extends`) | inside the theme | a template link pointing outside - `E024` |
| writing the result | inside the build folder | a name with `..`, a folder link pointing outside - `E024` |
| deletion | files of the previous build's manifest - only by their real path inside `dist/`; cache entries - only inside the cache | a folder in `dist/` or a cache directory replaced by a link pointing outside is skipped; a cache entry that is a link pointing outside on read or write - `E024` |
| cache root | `.heron-cache/` and `.heron-cache/renditions/` are real folders next to the build; a link above them (the whole site folder as a link) is allowed | the root or `renditions/` is a link, broken ones included, - `E024` before any write and cleanup |
| a ready rendition | taken from the cache only if it is a regular file (type by the path itself, without following links) | a link or another non-file in place of a rendition is removed - the entry itself, not the target - and the rendition is encoded again; a folder in its place - `E024`, dist is not changed |
| the folders themselves | `content/`, `data/`, `media/`, `static/`, `plugins/` - inside the site; `assets/`, `i18n/`, `templates/`, `modules/` and string files `i18n/<lang>.yaml` - inside the theme | a folder or a string file is a link pointing outside - `E024` |
| plugins from `plugins:` | the name is `^[a-z0-9][a-z0-9_-]*\Z`, no repeats; the folder `plugins/<name>/` and its `__init__.py` are real, not links | a name outside the rule - `E011` (schema) or `E014` (the resolver called directly); `plugins/` itself, a plugin folder or `__init__.py` is a link pointing outside - `E024`; the check runs before any plugin code is executed, both on `build` and on `check`. Only the plugin entry point is checked (the folder `plugins/`, `plugins/<name>`, `__init__.py`): a plugin is arbitrary site code and may import anything that lies next to it; nested links inside the plugin package are not checked |
| writing to the site folder (`new`, `init`, `setup`, `theme get`) | `site.yaml`, `content/`, the theme, `.heron/`, `.gitignore`, the kit `agents/` and the root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, backups in `.heron-cache/setup/` - the final path is inside the site folder; a link to another place of the same site is allowed | the file or any folder on the path to it is a link pointing outside, broken ones included, - `E024`; the configurator checks all its targets before the first write, outside files are not changed |
| reserved root names: `agents/`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` (`20` §1) | the build and `check` do not read them, `serve` does not watch them; `check` reads only `agents/heron-kit.yaml` - softly, for an info line; `init --agents` writes inside them by the rule of the row above | a link in their place does not matter to the build (it does not go there); a broken or foreign manifest - one info line, not an error. The same names **not in the root** (`content/<lang>/agents.md`, `static/AGENTS.md`) are ordinary files of their folders |
| folder walk | a folder link into the same folder gives its own paths next to the original ones (`latest/` → `v2/`); a loop along the chain of ancestors is cut off | a source folder or file cannot be read (permissions, disk) - `E030`, not a silently incomplete build |

The folders do not overlap: the build folder (`--out`) cannot be the site root,
contain it, coincide with `content/`, `data/`, `media/`, `static/` or the
theme, or lie inside them; the cache overlaps neither with them nor with the build.
A violation - `E024` before the work starts. `dist/` inside the site folder is normal.

The update date is also determined here; its source is set by `build.updated_from`
(`manual` by default, `git`, `file`). The priority is the same for any
source: `updated` from the frontmatter always overrides the automatic date.

The `git` mode queries the history with **two** calls for the whole build, not two
per file: one history walk returns the dates for all paths at once, the second -
the list of uncommitted files. On a site of several hundred pages the difference
between this and `git log -1` per file is seconds versus minutes. The
committer time (`%cI`) with its time zone is taken: the moment the edit got into the
history, and therefore onto the site no earlier. The author time can be weeks
older (rebase, cherry-pick). After the dates are resolved, `dates.check` looks for dates
later than the build moment and updates earlier than the publication - warnings
of the "dates" kind, errors with `--strict` (`20` §4.2). Renames are not tracked:
for a site, renaming a file is a change of address, the page really
changed.

The history is unavailable - not a repository, no git in the image, the history is truncated
(`clone --depth 1`) - the build does not fail: the engine falls back to the file times
and says so with **one** warning per build. A warning with
a file path stays where it is about a specific file: the file is not in the history
or has uncommitted edits. Otherwise a build from a copy without `.git` would give
two hundred identical lines and clog the summary.

The date is reduced to a calendar date in UTC, without time: the result must not
depend on the time zone of the machine the build runs on.

**3. Parsing.** For each page: frontmatter → model, body → sections, structured sections → data. Errors are collected without interrupting the pass - so the developer sees all of them at once, not one per run.

**4. Relation resolve.** Child pages of catalogs, relation fields declared by the theme in `links`, language correspondences, menus, breadcrumbs, backlinks. A link to a page that does not exist - stop.

Internal links in the text are brought to the page language not by gluing on a prefix, but through the page: the written path is parsed first as a key, then as an address in the page language, then as an address of the default language (the full rule and an example - `20` §2). From the found page the version in the current page's language is taken, and its address is substituted. Pages of all languages are processed, the main one included: a key link to a section with a slug differs from the address there too. No translation - a warning, and the link leads to the version in the default language: the reader lands on an existing page, not on a 404.

Links written by hand in the text are checked separately: each one of the form
`/…/` must resolve to an existing page by the same rule.
It does not resolve - a warning with the file path, the line number and the
link itself. This is a warning, not an error: a broken link inside the text is no
reason not to deploy the rest of the site. But silence is not allowed either - a section address
is set by a slug, and renaming a section leaves links written as an address
pointing nowhere until the first click. Skipped are external
addresses, anchors, paths to `/media/`, `/static/`, `/assets/` and to files with
an extension.

**Large sections.** The engine has no pagination, and this is a decision, not a gap. A section with a hundred or more children is **one** catalog page: `page.children` gives the theme all children at once, sorted by `order`, then by `h1`. The engine does not create addresses like `/faq/page/2/`, so questions about their canonical, `prev`/`next` and inclusion in the sitemap do not arise: the sitemap gets the section and each child, one entry each.

How to show a long list conveniently is the theme's concern: group the children by a field (`groupby` in Jinja), output a table of contents with anchors, collapse the groups into `<details>`. All links must still be in the HTML (`20` §10): loading the list with a script hides pages from search engines. A hundred links on a catalog page is a normal size; if a section grows to thousands, it is split into subsections by folders - each with its own `_index.md`, its own address and its own sitemap entry.

Tested on a section of 120 pages (`tests/test_large_section.py`).

**5. Image plan.** For each master - the names and sizes of all renditions the theme may ask for (aspect ratios × widths × formats, the fallback format - one width `fallback_width`). Nothing is encoded: templates need only the names and `width`/`height`, and the master's geometry gives them. Originals are not touched.

**After rendering and the generators - renditions.** The engine looks for links to `media/` in all the built text: pages, sitemaps, markup, plugin files, theme styles and static files. Only the intersection of these links with the plan is encoded and put into the build. A master goes in whole only if something links to it (`media_url(src)`, og:image) or it is declared "raw": an image from the page text, `og_image`, `twitter_image`, `video_poster`, `seo.og_default_image`. Files the engine does not cut (video, PDF, svg, `as_is`) are copied as before.

Renditions live **in the cache**, addressed by the content of the master, and get into the build as a hard link (details - "Rendition cache" below). Links to `media/` in markdown are from the site root: `media/x.svg`, `./media/x.svg` and `/media/x.svg` in an image and in a link are output as `/media/x.svg` at any page depth.

Encoding is spread across cores, the task is a master, not a single rendition: splitting finer means decoding the source seven hundred times instead of ninety-five. The number of processes is `build.workers`, zero means the number of cores. Progress ticks in the order of the source list, not in the order of readiness: otherwise the log stops being readable, and people look at it precisely during a long build.

Measured on a site with 95 masters and 2062 renditions, four cores: cold build 157 s, repeated - 4 s, of which images 0.3 s.

**6. Rendering.** Each page goes through the theme's `templates/<type>.html` (or the template named in `types.<type>.template`). The 404 page of the main language is additionally put into the root as `404.html` (`20` §2, "The 404 page").

**7. Generating the service files.** sitemap, robots, llms.txt, redirects, feed. JSON-LD is embedded at step 6.

**8. Writing the result.** Stages 6-7, `static/`, `theme/assets/`, renditions and plugin files only *declare* output files; one step writes them - and only after the build is recognized as successful (no errors, and in strict mode no warnings either; the report, the markup and `nginx -t` are checked before writing).

#### Writing the result

- **Owners.** Each build path has one owner: a page, a generator (sitemap, robots, llms, sitemaps, nginx config, feed), `static/`, a theme resource, media, a plugin. Two owners of one path - `E026` with both names; a file and a folder with the same name (`about` and `about/index.html`) - also `E026`. The only allowed replacement is a generated file replaced by a file from `static/` listed in `build.overrides` (`20` §5).
- **A failure does not touch the previous version.** An error, or a warning in strict mode - nothing is written to `dist/`.
- **Applying.** The new version is prepared in the temporary `dist/.heron-staging/` (the same file system) and put in place by renaming. Only outdated files owned by the previous build are deleted - their list is in `dist/.heron-manifest.json` (nginx does not serve it: hidden files are 404). Foreign files in `dist/` are not touched; a foreign file in place of a needed path - `E026`. Before the first rename the manifest is atomically rewritten with the list "previous ∪ new" (a journal): if applying breaks off in the middle (the disk ran out), `dist/` may be left with a mix of versions, but all files that appeared are already listed as owned - the next successful build will remove its own extra files and will not touch foreign ones. At the end the manifest is the exact list of the new build.
- **A foreign file.** A regular file on a needed path that is not in the manifest - `E026` before any change of `dist/` (the same bytes are not a conflict). A folder built by a previous engine version without a manifest (it contains `.heron-nginx.conf`) is considered owned - once, until the first manifest.
- **The final result is checked.** `nginx -t` runs on the content of `.heron-nginx.conf` that will go into the build - including content replaced by a static file via `build.overrides`.
- **Service names.** `.heron-manifest.json` and `.heron-staging/` in the build root are written only by the engine: a file with such a path from `static/` or a plugin - `E026`.
- **One build at a time.** Applying runs under a lock on the file `.<build folder>.heron-lock` next to the build folder: two builds into one folder at the same time are applied in turn, not intermixed.
- **What did not change is not rewritten.** A file with the same bytes keeps its previous time (ETag and browser caches survive), a rendition keeps the same hard link to the cache. An inode shared with the cache or with the previous version is never edited in place: the directory entry is replaced, not the data.
- **What is incremental and what is not.** The expensive part - image encoding - is taken from the cache and not repeated (§8, "Rendition cache"). HTML is rendered in full on every build: page dependencies (menus, catalogs, relations, translations, sitemaps) are not tracked, and this is not incremental rendering. In return a repeated build matches a cold one byte for byte with the same inputs and `SOURCE_DATE_EPOCH`, and only changed files are written to `dist/`.
- **Build time.** The build stamp (`env.stamp`) takes the time from `SOURCE_DATE_EPOCH` if it is set - this makes builds reproducible.

After that - a summary: how many pages per language and type, how many warnings, the list of content debts.

Warnings are grouped by kind: `images`, `relations`, `links`, `menu`,
`translations`, `languages`, `other`, and also `no translation`, `dates`, `content`, `seo` and `redirects` (12 kinds in all; the order of the groups is set by `ORDER` in `heron/core/report.py`, kinds outside it are printed after "no translation" in alphabetical order). At the top is what breaks the page for a visitor,
at the bottom what only an editor will notice. Each group has six examples, the full
list is written to `<next to dist>/.heron-cache/warnings.txt`. Without grouping
a hundred similar remarks about translations hid a dozen important ones about images
that are not on disk.

The build progress is visible in the terminal: the stage, the time since it started, a counter and a bar
inside long stages - image renditions, rendering, writing files. In a non-terminal
(CI, docker without `-t`, redirection to a file) there is nothing to redraw, so
a stage is announced as soon as it starts, long stages are marked once every two
seconds, the total is written at the end. Each line is flushed from the buffer at once:
otherwise the whole log reaches the human in one batch at the end and the build cannot be told
from a hung one.

## 5. Section parser

The heart of the system, so in detail.

The file body is parsed by `markdown-it-py` with its own heading-attributes rule. A section is a heading with an anchor `{#id}` plus all content up to the next heading with an anchor **of the same or a higher level** or to the end of the file. The level is set by the first heading with an anchor in the file; an anchor deeper than that level stays inside the current section.

Rules:

- headings without an anchor do not start a section and belong to the current one
- the text before the first section is available as `intro`
- the identifier: `[a-z0-9-]+`. Anything else is an error
- a duplicate identifier in a file is an error
- a section keeps: `id`, `title` (the heading text), `level`, `html` (the rendered content without the heading), `raw` (the source markdown)
- and the parsed parts: `lead` (paragraphs before the main node), `body` (the node itself), `note` with `note_title` (paragraphs after), `callout` (a quote) and `links`
- the intro block is given in three fields: `lead` - the first paragraph, `promise` - the second, `intro` - the whole text. A third paragraph and further - a warning: the template has no place for them

The theme decides itself whether to show the section heading: `mod.prose('what')` outputs both the heading and the text, while `mod.facts('quick-facts')` ignores the heading because it draws a frame with facts.

### Section forms

After parsing, each section gets the field `kind` - one of thirteen forms: `prose`, `list`, `alert-list`, `checklist`, `two-lists`, `steps`, `table`, `facts`, `faq`, `timeline`, `callout`, `gallery`, `tabs` - and `data` with the parsed data of that form. The table of forms, their signs, the recognition order and the data shape - `20` §4.4, the only place where they are described. The list of forms in code - `heron.contracts.theme.KINDS`, the auto-detection order - `heron.core.parser.blocks.AUTO_ORDER`.

Parsing fails softly: the class is set but the content does not fit - the section is given as prose and a warning is written. Failing the build because of a missing pipe in a table is not acceptable.

The section model:

```python
class Section:
    id: str                # anchor from {#anchor}
    title: str             # heading text
    level: int
    line: int | None       # heading line
    classes: list[str]     # classes from the anchor: alert, timeline, …
    raw: str               # source markdown without the heading
    html: str              # rendered content without the heading
    kind: str              # form: prose, list, … - see 20 §4.4
    data: Any              # parsed data of the form; in a module template - items
    lead: str              # paragraphs before the main node
    promise: str           # second paragraph of the intro block
    note: str              # paragraphs after
    note_title: str        # bold opening of the note
    callout: str           # the quote, wherever it stands
    links: list[dict]      # section links {title, href}
    body: Any              # property: data, and for prose - html
```

## 6. Page model <a id="page-model"></a>

Frontmatter fields live in `page.meta` - one attribute per row of the table in `20` §4.2, plus theme fields the core does not interpret (`page.meta.<field>`, and all of them at once - `page.meta.extra`). The page itself adds what the engine found out during the walk and the resolve:

```python
class Page:
    lang: str                      # language code
    source: str                    # file path from content/: ru/services/x.md
    key: str                       # key: services/x; for the home page - an empty string, in templates and nav - "/"
    meta: PageMeta                 # frontmatter, see 20 §4.2
    url: str                       # address with the language prefix and slugs: /ru/rukovodstva/x/
    type: str                      # page type, the selection rule - 20 §4.2
    sections: dict[str, Section]   # sections by anchor
    intro: Section | None          # text before the first section
    auto_updated: date | datetime | None  # date from git or the file, if updated is not set by hand
    links: list[tuple[int, str]]   # text links as written: line and address

    # filled in at the resolve stage
    parent: Page | None
    children: list[Page]
    translations: dict[str, Page]  # versions in other languages, by key
    breadcrumbs: list[Page]
    related: dict[str, list[Page]] # relations declared by the theme, and reverse ones

    # computed
    title: str                     # meta.title
    h1: str                        # meta.h1
    updated: date | None           # meta.updated, otherwise auto_updated
    generated: bool                # the page was created by the engine
    date                           # publication date
    date_at                        # the same with time
    updated_at                     # update date with time and time zone
    nav_title: str                 # meta.nav_title, otherwise the file name
    video: Video | None            # parsed meta.video*
    cover: dict | None             # cover: src, url, width, height, alt; none - None (20 §4.2)
    slug: str                      # last segment of url
    name: str                      # file name without extension
    is_index: bool                 # _index.md or the home page

    def section(self, id): ...     # section by anchor
    def has(self, id): ...         # whether such a section exists
```

**The cover.** `page.cover` is computed in the order `og_image`, `image`, the first image of `intro` or `hero`, `seo.og_default_image` of the language (`20` §4.2). The source is determined from the source text, before rendering, so the cover of a neighboring page (`page_of('services').cover`) does not depend on the rendering order. An external URL is taken as is; a path that is not in the build plan gives `None`.

`Site.page(key, lang)` finds a page by key in a language; in a template the same is `page_of(key)`.

## 7. Rendering <a id="rendering"></a>

Jinja2, `autoescape` on, `StrictUndefined` - accessing a variable that does not exist fails the build instead of outputting nothing. This catches typos in the theme at build time.

A theme is untrusted code: it is installed from a catalog, by a link or as an archive. So templates are built in the immutable Jinja sandbox (`ImmutableSandboxedEnvironment`): Python service attributes (`__globals__`, `__class__` and the like) are closed, lists and dictionaries are not changed from a template (`.append`, `.update`). Beyond the sandbox, the methods of pydantic `BaseModel` itself are closed on `site` and `theme` (`parse_file`, `model_construct` and so on - the fields and the schemas' own methods are available), as are any path attributes and the `env` methods that build the environment anew. Accessing something closed - `E033` with the template name. `heron check` finds data changes even before the build, by parsing the templates (§12); how to accumulate data without `.append` and `.update` - recipes in [`guide/04`, "Accumulating data in a template without `append`"](../guide/04-theme.md#accumulate-data-without-append). Filters and functions of site plugins (`plugins/`) are the site's own code, the sandbox does not cover them.

A template has access to: `page`, `site` (the whole `site.yaml`), `data` (the content of `data/`), `nav`, `t` (the theme's interface strings), `mod` (module macros), `lang` and `languages`, `hreflang`, `page_of(key, lang=None)` (a page by key, by default in the current language, the home page - `'/'`), `picture`, `media_url`, `absolute` (the last two are also available as filters), `jsonld()`, `pages` (the site object with all pages), `theme` (`theme.yaml` as a model), `env` (the build environment: `name`, `indexable`, `analytics`, `version`, `revision`, `built_at`, `stamp`).

### Module macros

`mod.<module>(<section id>)`. The logic is the same for all:

1. there is no section with this id → return an empty string, render nothing
2. the section exists → render `theme/modules/<module>.html`, passing it the section data

Modules without an argument (`mod.call()`, `mod.author()`, `mod.breadcrumbs()`) take their data from `site` and `page`, not from sections.

An empty string instead of a block is a matter of principle: a heading without content is worse than a missing block.

### Interface strings

Texts that belong to the theme rather than the content ("Book now" / "Записаться", "Read more" / "Читать далее") live in `theme/i18n/<lang>.yaml` and are available as `t.book_now`. Otherwise they end up hardcoded in the templates and the theme stops being portable between languages.

### Theme contract: block fields and hints <a id="theme-contract"></a>

In `theme.yaml` a theme describes not only which pages it draws but also what they are made of: the sections of every type, the fields of every block, the category views and the hints to them. This description is one for everybody: `heron check`, `heron describe` (§10), the questionnaire, the studio, the theme reference page and an agent read it. There is no separate "editor API".

An example - a piece of the starter theme:

```yaml
languages: [ru, en]                # the hint languages of the theme

types:
  page:
    uses: [intro, "*"]             # sections in order; "*" - any blocks
    hint_ru: Обычная страница - текст и блоки любой формы
    hint_en: An ordinary page - text and blocks of any form
    children_type: page            # the type of the pages inside a category of this type
    views:                         # how a category shows its pages
      key: view                    # the front matter key of _index.md that picks the view
      default: cards
      options:
        cards: {hint_ru: Карточки сеткой, hint_en: Cards in a grid}
        list: {hint_ru: Список строками, hint_en: A list of rows}
    sections:
      intro:
        required: true
        hint_ru: Вводный абзац - о чём страница
        hint_en: The intro paragraph - what the page is about

modules:
  faq:
    kinds: [faq]                   # the section forms the module draws
    schemaorg: FAQPage
    hint_ru: Вопросы и ответы - вопрос заголовком, ответ под ним
    hint_en: Questions and answers - the question as a heading, the answer under it
    fields:
      - name: items
        type: list
        required: true
        md: groups                 # where the value lies in markdown
        hint_ru: Пары вопрос - ответ
        hint_en: Question - answer pairs
        fields:
          - {name: q, type: text, required: true, md: heading, max_length: 120, schemaorg: Question.name, hint_ru: Вопрос, hint_en: The question}
          - {name: a, type: markdown, required: true, md: content, schemaorg: Answer.text, hint_ru: Ответ, hint_en: The answer}
```

**Keys.**

- `languages` - the hint languages of the theme. Not set - the languages of the suffixes that occur in the hints.
- `modules` - a list of names, as before, or a description of every module: `scope` (`section` - it draws a section, `page` - it takes data from the page and the site, like `mod.breadcrumbs()`), `kinds` (section forms from `20` §4.4; not set - the form with the name of the module), `schemaorg` (the markup type of the block), `fields` (the fields of the block), hints.
- `types.<type>.sections.<anchor>` - a section from `uses`: `required` (whether it is required), `fields` (own fields of a section that has no form - this is how `intro` is described), hints. The anchor `"*"` is the hint to "any blocks". The order of sections is the order of `uses`; a section that is not in `uses` is `E008`.
- `types.<type>.children_type` - the type of the pages inside a category of this type, from `types` of the same theme.
- `types.<type>.views` - category views: `key` (the front matter key of the category page, `view` by default), `default` (the view without the key), `options` (the views of the theme with hints). The theme invents the list of views - the engine only checks that `default` is in `options`.

**A block field.**

| Key | What it is |
|---|---|
| `name` | the field name: lowercase Latin letters, digits, `_`, starting with a letter |
| `type` | `text`, `markdown`, `list`, `image`, `link`, `number`, `date`, `enum`, `ref`, `flag` (yes or no) |
| `required` | whether it is required |
| `md` | where the value lies in markdown: a place from the vocabulary below |
| `min_length`, `max_length` | the length of the text |
| `min_items`, `max_items` | the number of list items |
| `ratio`, `min_width` | the proportion (`16:9`) and width of a picture, only for `image` |
| `values` | the allowed values, only for `enum` (and required for it) |
| `ref` | for `ref` - the type of the pages the field points to |
| `schemaorg` | the markup property the value goes into: `Question.name` |
| `item` or `fields` | for a list - the type of every item or the fields of every item, one of the two |

**Places in markdown (`md`).** The vocabulary is common to all themes: every place is a form the section parser already understands (§5, `20` §4.4). By it the questionnaire finds the value in the file and writes it back to the same place.

| Place | What is in the file |
|---|---|
| `body` | the whole content of the section |
| `first-paragraph`, `second-paragraph` | the first and the second paragraphs of the intro |
| `lead` | paragraphs before the main node: a list, a table, `###` groups, "key \| value" lines |
| `quote` | a quote `> …` |
| `items`, `numbered` | items of a `- …` list and of a numbered `1. …` one |
| `bold`, `tag`, `text`, `more` | the bold start `**Term.**`, the tag `[TAG]`, the text after the start, the indented rest of an item |
| `groups`, `heading`, `heading-id`, `content` | `### Heading` groups, the text of the heading, its anchor `{#id}`, everything under it |
| `pairs`, `key`, `value` | `key \| value` lines and their parts |
| `table-head`, `table-rows`, `cells` | the table header, the rows, the cells of a row |
| `image`, `alt` | the path of a picture `![caption](path)` and the caption |

**Hints.** `hint` is one line for hovering, `help` - what it is, what it affects on the site and in search, a good example, common mistakes; a module also has `example` - a markdown sample. Per language - with a suffix, as in `site.yaml`: `hint_ru`, `help_en`, `example_uk`; the key without a suffix is for languages that have no own text. Hints exist on a type, a section, a module, a field, a view and the `views` block.

**Service fields** are described by the engine (`heron/contracts/fields.py`, the texts are in the message dictionary, ru and en), the theme does not repeat them. These are the SEO block (`title`, `h1`, `description`), the address (`slug`, the category - the folder of the page, `type`, `children_type`), the menu (`nav.main` in `site.yaml`, `nav_title`, `order`), the cover (`image`, `image_alt`), social networks (`og_image`, `og_title`, `og_description`), publishing (`noindex`, `published`, `date`, `updated`, `redirect_from`) and for every block - the heading `## …` and the anchor `{#…}`. The order and the groups are the same for `describe`, the questionnaire and the studio.

**Check.** A theme without `fields` builds as before - sections stay free markdown. `heron check` warns once: "no field description: the questionnaire and the studio will show only the SEO block". A theme that has `fields` must give a `hint` to every type, section in `sections`, module in the description, field and view - in every one of its languages; if something is missing, `heron check` gives `E008` with the list of paths (`modules.faq.fields.items.fields.q (en)`). A missing hint does not stop the build. An invalid description - an unknown `md` place or type, a list without `item` and `fields`, an `enum` without `values`, a `default` outside `options`, `children_type` or `ref` to a type that does not exist, a repeated field name - is `E008` when `theme.yaml` is read, like any error of the passport.

The starter theme is fully described in ru and en (`heron/scaffold/text/theme-contract.yaml` - the part of its `theme.yaml` common to both notes languages); a test matches the markdown samples of each of its modules against the section parser.

### The theme demo and reference <a id="theme-demo"></a>

**The demo is required.** The demo of a theme is the content of the site it is packed from: a sample of presentation for a niche that the author of the theme thinks through once. It must show everything the contract declares: every type in `types` - at least one page from a file (the 404 the engine builds itself does not count); every module in `modules` drew non-empty HTML at least once (`mod.<name>()` of a section or a page module); every view in `views` - on a page with child pages whose view key (`views.key`) equals the view, and for the default view the key is absent or equals the view. A view counts by the pair "key - name": for types with one set of views it is enough to show the view on a page of any of them. "Shown" is decided by a real render: the pages are drawn with the templates of the theme, `Modules` records every call that returned something non-empty (`core/demo.py`). It is checked by `heron theme pack` (before the archive is written) and `heron check --theme`; a plain `heron check` does not require a demo. Gaps - `E037` with a list ("type 404: no demo page at all", "block gallery (gallery): not shown…", "section view list…"); template errors on demo pages come with their own codes. For a theme without `fields` an incomplete demo is a warning (kind "other") with the same list, `pack` prints it and writes the archive. `pack` without `site.yaml` in the folder - `E037`: without it the languages and pages of the demo cannot be read.

**The theme reference** is built from the contract (the same object as `heron describe --json`) and the demo, nobody writes it by hand (`core/render/themeref.py`). It has: page types (hints, template, sections in the order of `uses`, section fields, `children_type`, `jsonld`, demo pages of the type); every module - hint, help, fields with their place in markdown and an example for every form it draws: a live example (the theme module draws a demo section in the environment of its page) and next to it the source markdown of the section (the heading with the anchor and classes, and the content), with the file and the address of the page; a module without an example - a mark and the sample `example` from `theme.yaml`; section views with the key and the line that turns them on, and the live view of a section page; schema.org markup (`types.*.jsonld`, `schemaorg` of modules and fields); styles - the CSS files of `assets/` and the `:root` variables; interface strings `i18n/<lang>.yaml`. Examples are taken from the language of the reference, if it has no pages - from the default language.

Where to see it: `heron docs theme-ref [path] [--lang ru|en]` - as text (the examples are the source markdown and the file); the service page of a draft build - `/_heron/theme/` in the default language and `/_heron/theme/<lang>/` in the other site languages, with live examples in the styles of the theme (its CSS is linked). The page is written by any build except `--env prod` and by `heron serve`; it is not in the sitemap, `llms.txt` or the menu, it has `<meta name="robots" content="noindex, nofollow">`. The frame of the page is in the language of the reference if the engine knows it (ru, en), otherwise in the message language. A template that fails on an example does not break the build: the error text stands in place of the example.

### The page editing model <a id="edit-model"></a>

The console questionnaire, the studio in the browser and an agent with `--answers` edit pages through one core - `heron/edit/`. It has no database of its own: the page file is the source of truth. The model keeps its whole text and knows which characters hold each value.

- **Reading.** `load(file or text, contract)`; the contract is the `heron describe` object (`core/describe.py`, `contract`). The SEO block is read twice: `yaml.safe_load` gives the values, `yaml.compose` gives their places in the text. The body is cut into sections by the same rule as the build (§5), the form of a section comes from the same parser, and the fields of a block find their values by `md` from the dictionary of places ("Theme contract" above).
- **List of fields.** `fields(page)` - the service fields of the engine by groups (`contracts/fields.py`), on a category and the home page the view from the `views` of the type, then the schema.org markup of the type (`schema.<Type>`), then the sections in the order of `uses`: heading, anchor and the fields of the block. A field has its value, the default value (what comes from `site.yaml` and the theme when nothing is entered), `hint`, `help`, limits and a group. The console, the studio and an agent see the same list.
- **Editing.** `set(page, path, value)` replaces only the characters of this field and returns a new page. Paths: `title`, `schema.Service.serviceType`, `sections.faq.heading`, `sections.faq.items.0.q`; a number past the end of a list adds an item, an empty value removes the field. When the SEO block has no such key, the commented template line `# og_title:   # hint` is uncommented together with its hint, otherwise the key is added before `---`; a reset puts the line back into the template. New lines use the line ending of the file itself. Whole sections - `add_section` (in the order of `uses`, with the anchor class for forms recognized only by class) and `remove_section`.
- **Lossless.** Without edits `dump(load(file))` gives the same bytes: comments, hand-written markup, the order of keys and sections, `\r\n`, the BOM and a missing final newline stay. When a whole list is replaced, the items that did not change stay as they were written. `tests/test_edit_lossless.py` checks this on every demo and sample page of the engine and on the fixture pages of the tests, and for every field - that an edit changes only its place.
- **Read-only.** What cannot be written without losses is shown but not edited, and the field has a reason: a heading underlined by the next line; an `md` place that is not in the dictionary; a block in another form than the theme expects; an SEO block that does not read as YAML; a body with a parse error (`E016`, `E003`). The category (the folder of the file) and the menu item (`nav.main` in `site.yaml`) live outside the file: page and category commands move the category, a menu edit is collected by the page in `site_changes()`.
- **Checks.** `validate(page, site_root)` - the same rules as `heron check`: the `PageMeta` model and its remarks (the length of `title` and `description`, `title` = `h1`, `image` without `image_alt`), plus the theme contract: required fields and sections, length, the number of items, allowed values, the picture (whether the file exists, the width from `min_width` or `images.cover_width`, the `ratio` proportions) and the markup of the page (the type is in the schema.org vocabulary, the property belongs to the type).
- **Languages.** The page key is the path from the language folder without `.md`, as in the build. `files(root, site, key)` - the files of the page in every language of `site.yaml`, the default one first, and whether each exists; `folder_type` - the page type by its folder (`children_type` of the category).

### The cover and `robots_meta` in the template <a id="cover-robots"></a>

Besides what is listed, the template gets:

- `page.cover` - the page cover (section 6);
- `cover_url(page, min_width=1200)` - the absolute address of a JPEG/PNG cover not narrower than `min_width` (1200 by default regardless of `images.cover_width`; for a larger one pass `min_width` explicitly); if there is no such variant - the address of the master; no cover - an empty string. It is also available as a filter: `{{ page|cover_url }}`;
- `robots_meta` - a string for `<meta name="robots">`: `max-image-preview:large, max-snippet:-1, max-video-preview:-1` for an indexable page of a prod build, otherwise `noindex, nofollow`. A page with `noindex: true` and any non-prod build get the closed variant.

```jinja
{% set cover = cover_url(page) %}
{% if cover %}<meta property="og:image" content="{{ cover }}">
<meta name="twitter:image" content="{{ cover }}">{% endif %}
<meta name="robots" content="{{ robots_meta }}">
```

The names `cover_url` and `robots_meta` are reserved: the engine counts these names as its own when checking theme templates.

## 8. Images

For each image the content links to:

- width variants: 400, 800, 1200, 1600 - but not larger than the source
- formats: AVIF and WebP at all widths; the source format is the fallback for `<img src>` (for a WebP master the fallback file is WebP too; the extension comes from the master), in one width `images.fallback_width` (800), not larger than the frame width. Other widths of the source format are cut only if they are requested via `media_url(src, ratio, width)`
- only what the built site links to is cut: an aspect ratio no template asked for does not get into the build
- `srcset` and `sizes` are set by the module
- `width` and `height` are mandatory in the markup - otherwise the layout jumps and CLS grows
- `loading="lazy"` on everything except the image of the first screen
- renditions are stored in the cache and get into the build as a hard link

The page cover (`20` §4.2) is cut specially: the master always goes into the build whole, and a JPEG/PNG `max(images.fallback_width, images.cover_width)` wide, but not wider than the frame, is added to the fallback files (`images.cover_width` is 1200 by default). A master narrower than `cover_width` is served whole, and `heron check` warns.

An image that something links to but that is not on disk: in strict mode (`--strict` or `build.fail_on_warning`) - error `E007` and the build stops; in a normal build - the warning "no file <path>" (kind "images"), and the build goes on. `heron check` is stricter than a normal build: it counts a missing image as error `E007` even without `--strict`. A broken image in production costs more than a failed build, so enable `--strict` for CI.

Only `.jpg`, `.jpeg`, `.png` and `.webp` are cut (`KEEP` in `heron/core/media.py`). `.avif`, `.gif`, `.svg` and any other file are copied as is, without variants.

### Rendition cache

Encoding is the most expensive part of the build: 95 masters with three aspect ratios, four widths and three formats give more than two thousand files and minutes of CPU work. Editing one line of CSS must not cost that.

**Where it lives.** Next to the build folder, not inside it (`<parent of --out>/.heron-cache/`):

```
.heron-cache/
├── renditions/v5-<encoder settings>/
│   └── <master sha256>/
│       ├── shape.json             width, height, whether there is transparency
│       ├── crop-16x9-800.webp     rendition: method, aspect ratio, width, format
│       └── .used                  when a build last needed the entry
└── warnings.txt                   full list of warnings of the last build
```

**EXIF rotation.** A master is read the way a browser shows it: the Orientation tag (2-8) is applied before the size is determined, before cropping and encoding, and the tag does not go into the rendition. The cache format version is `v5`: `v4` entries of rotated photos were cut without rotation, the build does not take them, the cleanup removes them.

**Identity is the content and the parameters.** The entry folder is the sha256 of the master's bytes, the file name is the transformation parameters; the encoder settings (quality, speed) are in the name of the version folder. The file name in the build (`media/photo-16x9-800.webp`) comes from the site, the bytes - from the entry by hash. So "a file with this name already exists" means nothing: a changed master is a different entry, two sites with the same `media/photo.jpg` and different content do not mix, and with the same content they share the entry fairly.

**A shared cache and concurrent builds.** Several sites built into one folder (`--out out/a`, `--out out/b`) share `out/.heron-cache`. Files are written to a temporary file next to the target and put in place with `os.replace`: two builds cutting the same thing write the same bytes and never see an unfinished file.

**How it gets into the build.** As a hard link (§4, "Writing the result"); if that fails - as a copy. A shared inode is never edited in place: both the build and the cache change only directory entries.

**What counts as a change.** A master - by content. The set of renditions - by the theme spec (`widths`, `ratios`, `formats`, `crop`, `fallback_width`): a new width is encoded, already encoded widths and aspect ratios are reused. A master already seen is not decoded for the plan: the size and transparency are in `shape.json`.

**Cleanup.** The cache is shared, so "this build does not need it" is no reason to delete. A build holds a shared lock on the cache from the image plan to writing the result; the cleanup needs an exclusive one, and while someone is building, it is postponed until the next build. A build marks the entries it needs (`.used`); once a day, under the exclusive lock, entries no build has used for 30 days and entries of past formats are deleted. A rendition already placed in a build is not affected by deleting the entry. The cache of the previous format (`media.json`, `media/` by site paths - it was what mixed sites) is deleted on the first build.

**The cache can be deleted at any moment.** It affects only speed: the first build after deletion will be cold. That is exactly why it is in `.gitignore` and why production and CI are not required to have it.

**Identical rendition names.** `media/photo.jpg` and `media/photo.png` give the same names (`photo-16x9-800.webp`) - `E027`: rename one of the masters. The rendition addresses of existing sites do not change because of this rule.

### How many processes

Encoding is independent and CPU-bound, so it is spread across cores. The task is a master, not a single rendition: splitting finer means decoding the source seven hundred times instead of ninety-five.

`build.workers` in `site.yaml`, zero - the number of the machine's cores. It is set by hand where cores are shared with other tasks: in CI the site build is not alone on the machine, and taking all cores means slowing down the neighbors.

Progress ticks in the order of the source list, not in the order of readiness. Otherwise the log stops being readable, and people look at it precisely during a long build.

The number of processes is chosen in order: the flag `--workers N` of `heron build` and `heron serve` (0-64), the variable `HERON_WORKERS`, `build.workers`. A variable value outside 0-64 - `E011` with a hint; a flag out of range is rejected by `click` itself.

**A pool failure does not fail the build.** In environments with limited inter-process communication (the macOS sandbox, a container without semaphores, some CI) the pool is not created or dies. Then the engine warns once (`pool_fallback`) and encodes the rest sequentially; renditions already in the cache (`_reusable`) are not encoded again, the result is byte for byte the same as with `workers=1`. A pool failure is `BrokenProcessPool` and a refusal when creating the pool or on `submit`: any `OSError` (any `errno`: `EACCES`, `ENOSPC`, `EROFS`, `ENOENT`, `EIO`... - typical `/dev/shm` failures in a container) and `NotImplementedError` about missing semaphores. This is safe: if the cause is a real disk error, the sequential cutting meets it again and raises it as is. From `result()` only `BrokenProcessPool` is caught. The `pool_fallback` warning carries the error text with `errno`. Worker errors - `HeronError`, `PIL.*`, `ValueError`, and also a disk `OSError` - are passed through as is, the fallback does not engage for them.

### Encoder speed

webp and avif have explicit speed controls set - not the library defaults. A default can change with a dependency update and make the build five times slower without a single line changed in our code.

An avif measurement on a set of 95 masters, 800px, quality 82:

| speed | time per variant | size | vs. the chosen one |
|---|---|---|---|
| 0 | 5.33 s | 43.0K | −5.7% |
| 4 | 0.69 s | 44.4K | −2.6% |
| **6** | **0.13 s** | **45.6K** | - |
| 8 | 0.05 s | 47.3K | +3.6% |
| 10 | 0.02 s | 57.1K | +25.0% |

The final encoder parameters (not configurable from `site.yaml` and `theme.yaml`): `quality` 82 for webp, avif and jpeg; webp `method=4`; avif `speed=6`; PNG - without `quality`.

Six was chosen: four costs five times more time for two and a half percent of size, ten saves time at the cost of a quarter of the weight. For webp `method=4` was chosen the same way: the slowest mode gave 7 seconds per variant instead of 0.1 for a gain of about two percent.

## 9. Generators

### sitemap <a id="sitemap"></a>

The composition depends on the number of languages in `site.languages`:

- **one language** - `sitemap.xml` is the list of addresses itself (`<urlset>`). An index over a single file adds nothing except an extra request;
- **two or more** - `sitemap.xml` becomes an index, next to it lies `sitemap-<lang>.xml` for each language from `languages` that has indexable pages. A language that is not in the list is not in the sitemap either.

Pages with `published: true` and `noindex: false` are included, except the 404 page. `lastmod` comes from `updated`, as a full date with a time zone (`20` §4.2). An entry that has versions in at least two languages gets `xhtml:link` to all versions plus `x-default` if there is a version in the default language. The same set is output in `<head>` (the template variable `hreflang`), but with differences: in the sitemap `xhtml:link` is written only for a set of more than two links, while `hreflang` in the template is present on every page of a multilingual site, even without translations (a self-reference); on a single-language site it is an empty list. The full rules - `20` §3.

**Images.** A page entry carries `<image:image><image:loc>` (the `xmlns:image` namespace is declared only if there are images): the cover first, then the images from the page text (intro and sections, without code blocks; only links to `.jpg`, `.jpeg`, `.png`, `.webp` are taken, by the master's address; front matter images and `data/` images other than the cover do not go in), no more than 20 in all (the constant `SITEMAP_IMAGES`, not a setting), without repeats, only absolute addresses of the environment domain (the cover address is the same as `cover_url` gives). There are no images in the sitemap of builds that are not indexed: on dev the pages are closed with `noindex, nofollow`, and the addresses point to the dev domain.

There are no service entry types in the sitemap by definition: the system has no entities without a URL. Service entries of the kind CMS plugins leave in sitemaps are architecturally impossible here.

### robots.txt <a id="robots-txt"></a>

In an indexable build: `User-agent: *` and `Allow: /`, then `seo.robots_extra`, an empty line and the mandatory `Sitemap:` line with an absolute address. In a closed build (`env.indexable=false`) it is always `User-agent: *` and `Disallow: /`, without `Sitemap` and without `robots_extra`. It is generated rather than kept as a file: put there by hand, in half a year it starts to lie.

### llms.txt <a id="llms-txt"></a>

In the llmstxt.org format: the site title, a short description, sections with a list of pages and one-line descriptions from `description`. It is built from the same tree as the menu and by the same policy as the sitemap: a page with `noindex` (or outside the sitemap) gets neither into the common list nor into the list of children of its catalog.

With `seo.llms_txt: true` there is additionally `llms-full.txt` - the whole text of the site in one file.

**A single-language site** gets no language files: `/llms.txt` contains the full list of pages right away (with the `seo.llms_note` block of that language), `/llms-full.txt` - the full texts, and they link to each other. A table of contents of one link would make the model take an extra step for the same content.

**On a multilingual site a file is built for each language**, not only for the main one:

- `/llms.txt` - the root one: the site name, the description and the list of language versions. It has no list of pages, it is a table of contents;
- `/llms-<lang>.txt` - the full list of pages of its language. The header links to the other versions and to the root file, so that a model that landed directly on the Russian one knows the others exist;
- `/llms-full-<lang>.txt` - the same with the full text, with `seo.llms_txt: true`.

**Navigation is closed: the set has no dead ends.** From any file you can reach any other:

| File | Where its header leads |
|---|---|
| `/llms.txt` | to the short and the full version of each language |
| `/llms-<lang>.txt` | to the root one, to the short versions of other languages, to its own full one |
| `/llms-full-<lang>.txt` | to the root one, to the full versions of other languages, to its own short one |

The link between the short and the full version of one language is not about languages, so it exists on a single-language site too, where the "other languages" block does not exist at all. Full files are switched off (`seo.llms_txt: false`) - there are no links to them anywhere.

Line captions are in the language of the file itself, for the root one - in the site's default language; the exception is two captions hardcoded in Russian for any language: the "Language versions" heading in the root `/llms.txt` and the "All language versions:" line in the header of `/llms-<lang>.txt` and `/llms-full-<lang>.txt` (only `TO_FULL`, `TO_SHORT`, `PAGES`, `FULL_TITLE` are translated). A language that is not in the set of captions gets the English one: it is understood by both a model and a human, and an invented translation by nobody. Ready captions exist for `uk`, `ru`, `en`, `de`, `pl`; in the list of language versions a language outside the set is labelled with its own code (`fr`).

Languages are not mixed in one file on purpose: a model answers in the language of the text it read, and close languages - Ukrainian and Russian - are what it confuses most often. Separate files let it choose the right one, cross links let it find the others.

The llmstxt.org format does not describe language versions, so the convention is our own: a model reads the file, and a clear line of human text is enough for it.

A language that has nothing but a stub does not get into the list: a link to an empty file is worse than no link - the model will follow it and come back with nothing.

**Information about the site.** `seo.llms_note` gives a piece of markdown per language, inserted verbatim:

- in `/llms-<lang>.txt` - after the short description, before the list of pages;
- in `/llms-full-<lang>.txt` - after the title, before the page texts;
- in `/llms.txt` - the text in the site's default language.

The order is exactly this: first "what this site is", then "how to deal with it", then the content. The reader needs the answer before the table of contents - the answer is what they came for.

The block is not searched for in the finished text and is not "inserted" anywhere after the fact: the file is built as a list of lines, and the place of the block is set at build time. A search over the finished file would stumble over page texts, where both headings and quotes resembling the header occur.

The content of the block is facts about the site, not instructions to the reading model. A consumer is entitled to treat text from someone else's site as data, not instructions; trying to steer someone else's agent through it is useless and looks like prompt injection.

### JSON-LD <a id="json-ld"></a>

It is embedded in the `<head>` of each page, the type depends on the page type:

The markup types are declared by the **theme**, with the key `types.<type>.jsonld` in `theme.yaml`: a service site, a shop and a reference site have different mappings, and the core does not have to know them. A page can declare a type too: every key of the front matter `schema` block (except `entity`) with a map value that is not in `types.<type>.jsonld` is added to the graph as a new node.

The core builds what it really knows itself:

| What | Where it comes from |
|---|---|
| `@type` declared by the theme | `theme.yaml` |
| `name`, `description`, `url`, `inLanguage` | the page: for the `WebSite` node `name` is `site.name` in the page language, or `site.domain` if empty; for other types - the page `h1` (not `title`). `inLanguage`, `datePublished`, `dateModified` are output only if the schema.org 29.3 vocabulary allows them for the type; a type outside the vocabulary is not filtered |
| `datePublished` | the `date` field, midnight UTC: `2026-03-14T00:00:00+00:00` |
| `dateModified` | `updated` or `build.updated_from`; from git - the commit time with its time zone |
| organization fields and other details | the `schema` block in `site.yaml` |
| refinements for a specific page | the `schema` block in the frontmatter |
| `BreadcrumbList` | the built breadcrumbs, always, except the home page |
| `primaryImageOfPage` | the page cover: an `ImageObject` with `url`, `width`, `height` and `caption` from the cover `alt` (empty `width`/`height` are dropped); added to the types from the fixed list `WEBPAGE_TYPES` (`WebPage`, `AboutPage`, `CheckoutPage`, `CollectionPage`, `MediaGallery`, `ImageGallery`, `VideoGallery`, `ContactPage`, `FAQPage`, `ItemPage`, `MedicalWebPage`, `ProfilePage`, `QAPage`, `RealEstateListing`, `SearchResultsPage`) if the site did not set its own. It appears only on nodes from the theme's `types.<type>.jsonld` and the `schema` block; the starter theme does not declare `WebPage`, and a `FAQPage` node assembled from a section does not get the image |
| `alternateName` | `site.alternate_names` of the page language, in any `WebSite` node on any page where the theme or the page declared it |
| `FAQPage` | a section parsed as `faq` |

The merge has several levels: the core fields, then `schema.<type>` from `site.yaml`, then `schema.<type>` from the page front matter (nested maps are merged, the rest is replaced), then the `{{ }}` substitutions. Organization data lives in `site.yaml` and is not duplicated in the content.

The `jsonld()` function returns ready JSON: one node - an object with `@context`, several - `@graph`, no graph - an empty string. The characters `<`, `>`, `&`, U+2028 and U+2029 are escaped (`\u003c`), so a field value cannot close `<script>`.

**Check against the vocabulary.** After the graph is built, every page hands its nodes to the `heron/schemaorg` package: types, properties, enumerations and value types are checked against the schema.org 29.3 vocabulary (`schemaorg-29.3.json`, codes `SCH001`-`SCH005`), markup images against the build (`SCH006`). The finding path is translated into a source file and a key: the site-wide node - `site.yaml`, `schema.entity.<path>`; a type from the theme - `theme.yaml`, `types.<type>.jsonld.<i>`; a page block - the content file; breadcrumbs and FAQ - `engine`. The finding key is `<CODE>:<file>:<path>`; identical keys from pages and languages merge into one finding with a page counter. On `prod` a finding is an error, otherwise a warning; a `schema_exceptions` entry in `site.yaml` or `--allow-schema` moves it to the "Markup exceptions" section of the report. A page with `noindex` is checked the same way. The existing `E020` checks stay as they were.

**Attribution.** The vocabulary is the Schema.org vocabulary, release 29.3, https://schema.org, licensed under Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0). The engine built the index from the release without term descriptions; the source, the commit and the sha256 sum are recorded in `heron/schemaorg/NOTICE.md`, the file ships in the package and the image.

### redirects <a id="redirects"></a>

Collects all `redirect_from` from all pages into `dist/redirects.map` in the nginx format:

```
/old/address/  /new/address/;
```

Old addresses are normalized first: percent-encoding is decoded, the text is brought to NFC, the case is kept, a trailing slash is added to everything except files (`20` §2, "Old addresses"). An example with Cyrillic: `/%D0%BA%D1%80%D0%B5%D0%B4%D0%B8%D1%82` and `/кредит/` give one map line `/кредит/  /credits/;`, and 301 works for both forms, with and without the slash. An address that is not text after decoding (a slug cut in the middle of a letter) stays in percent form and is matched against `$request_uri`.

Build-time checks use the normalized form: an old URL does not coincide with any existing one, one old URL does not lead to two places, there are no chains (`E009`).

Next to it - the 410 list from the `gone` key in `site.yaml` (`20` §5): exact addresses, prefixes `/wp/*` and addresses with a parameter `/?p=*`. An overlap with a page or with `redirect_from` - `E022`. A copy of the list - `dist/gone.map`.

The engine writes both maps into the nginx config it builds together with the site (`dist/.heron-nginx.conf`): an exact address - `location = "/old/"` (and the variant without a slash), a prefix - `location ^~ "/wp/"`, an entry with a parameter - a regex map `map "$uri?$args"`, a broken percent address - a regex map over `$request_uri` (the case of `%xx` does not matter, the case of letters does). String maps are not used: nginx compares them case-insensitively, while the engine's addresses are case-sensitive. **301 and 410 work only on an exact case match** with the entry in `redirect_from` or `gone`: an address in a different case (`/about/` for the entry `/About/`, Latin and Cyrillic alike, an exact address and a prefix) gets 404. This is the intended behavior, `tests/test_nginx_redirect_case.py` pins it; if you need a second case variant, write it as a separate entry. The response goes out without touching files. 301 and 410 addresses are matched against each other, against pages and against service addresses in the form without a trailing slash - the server answers both (`/a.html` and `/a.html/` are one address; a match - `E009` or `E022`). Control characters in an old address (`%0A`, `%00`) - also `E009`/`E022`. A `gone` prefix that coincides with a service one (`/media/`, `/assets/`, `/.well-known/`, a language `/<lang>/`), and 301/410 on the service 404 pages - `E022`.

### feed

`dist/feed.xml` in the Atom format - only if `seo.feed` is set in `site.yaml`: the type of pages that go into the feed. Published and indexable pages of that type in the default language are taken, no more than `seo.feed_limit` (20). The order is by publication date (`date`), for pages without it - by update date, newest first. An entry has `<published>` if `date` is set, and `<updated>` - a full date with a time zone, as in the markup. The feed title is the `h1` of the home page in the default language, otherwise `site.name`, otherwise the domain; an entry: `title` = `h1`, `link` and `id` - the absolute address, `summary` = `description`, `updated` = `updated` or `date` (otherwise `1970-01-01`); the feed `updated` is the latest of the entries; with equal dates the order is by address (descending).

### The nginx config <a id="nginx-conf"></a>

The generator `heron/modules/nginx.py` writes `dist/.heron-nginx.conf`: `listen 8080`, `root /usr/share/nginx/html`, `/healthz`; security headers (`nosniff`, `Referrer-Policy`, CSP, HSTS); `Cache-Control: no-cache` for pages and `public, max-age=86400` for `/media/` and `/assets/`; gzip; a ban on hidden files except `/.well-known/`; `location ^~ /<lang>/` with its own 404 for non-default languages; comments in the `build.notes` language.

## 10. CLI

These commands are the whole surface of the engine for a human. There is no need to go inside it.

```
heron new [path] [--notes ru|en] [--name …] [--domain …] [--lang en,ru] [--no-agents] [-y] [-v]
                                             create a site from scratch; the default path is "."
heron init [path] [--force] [--notes ru|en] [--name …] [--domain …] [--lang …] [--agents | --no-agents] [-y] [-v]
                                             complete the folder to match what site.yaml says
heron check [path] [--strict] [--drafts] [--json] [--env NAME] [--allow-schema KEY] [--old-urls file] [--theme]  report without a build; --json - codes, files, lines for an agent;
                                             --old-urls - check old URLs (one per line or a Search Console export); --theme - the theme demo too (§7)
heron serve [path] [--port 8000] [--host X] [--workers N] [--no-drafts]  local preview with rebuilds
heron build [path] [--out folder] [--env prod] [--strict] [--drafts] [--allow-schema KEY] [--workers N]   build
heron page <type> <slug> [path] [--lang ru] [--folder section]          page stub
heron describe [name] [path] [--json] [--lang ru]  theme contract, service fields, hints
heron docs [topic | template <file> | theme-ref [path]] [--lang ru|en] [--all-langs] [--search text] [--export folder]
                                             documentation of this version in the chosen language
heron setup [path] [--answers file|-] [--dump] [--port 8000] [--host X]  configurator
heron theme get <starter|name|https-link|archive> [path]   install a theme with its demo pages
heron theme list | heron theme pack [path] [--out file]   catalog; your own theme with content into an archive
heron schema [--site | --theme | --frontmatter | --setup | --errors | --describe] [--lang ru|en] [--export folder]
                                             JSON Schema of the contracts and the error registry
heron recipe                                 Dockerfile of the nginx image for the built dist/
```

Global options before the command: `-V/--version` (a string from `HERON_CHANNEL`, `HERON_REVISION`, `HERON_BUILT`), `-h/--help`, `--debug` (the whole traceback), `--notes ru|en`.

| Command | Option | Type | Default | Meaning |
|---|---|---|---|---|
| `new`, `init` | `--lang` | comma-separated list | `en` | site languages, the first is the default |
| `new`, `init` | `--domain` | string | `<name>.example` | the site domain |
| `new`, `init` | `--name` | string | the repository or folder name | the name |
| `new`, `init` | `-y` | flag | off | do not ask questions |
| `init` | `--force` | flag | off | overwrite what exists |
| `check`, `build` | `--strict` | flag | off | warnings become errors |
| `check`, `build` | `--drafts` | flag | off | show `published: false` |
| `serve` | `--drafts/--no-drafts` | flag | **on** | show `published: false` |
| `check`, `build` | `--env` | name | `SITE_ENV`, then dev | the build environment |
| `check`, `build` | `--allow-schema` | key, repeatable | - | a one-off exception for `SCH001`-`SCH006` |
| `check` | `--json` | flag | off | the report as one JSON object |
| `check` | `--old-urls` | file | - | check old URLs |
| `check` | `--theme` | flag | off | check the theme demo too: every type, block and view is shown (§7) |
| `build` | `--out` | folder | `<path>/dist` | where to build |
| `serve` | `--host` | address | `127.0.0.1`, in the image `0.0.0.0` | where to listen |
| `serve` | `--port` | number | `8000` | the port |
| `build`, `serve` | `--workers` | number | `HERON_WORKERS`, then `build.workers` | cutting processes |
| `docs` | `--lang` | `ru` or `en` | see below | documentation language |
| `docs` | `--all-langs` | flag | off | only with `--export`: both languages into the folders `ru/` and `en/` (without `--export` - `UsageError`, code 2) |
| `schema` | `--lang` | `ru` or `en` | the notes language | the language of descriptions and error titles in the schemas |
| `theme pack` | `--out` | file | `<path>/dist/theme.tar.gz` | the theme archive |
| `describe` | `--json` | flag | off | the description as one JSON object (`heron schema --describe`) |
| `describe` | `--lang` | language code | the notes language | the language of the theme hints |

**Exit codes.**

| Code | When |
|---|---|
| `0` | success (for `check --json` - no errors, with `--strict` no warnings either) |
| `1` | there are errors (for `check --json` too) |
| `2` | wrong invocation: invalid `--lang`/`--domain` for `new` and `init` without `site.yaml`, invalid `setup --answers` answers, an invalid `--allow-schema` key, `theme get` over `http://`, click `UsageError`, `heron` without a command |
| `3` | for `build`: the site is written but `on_build_finished` failed (§15) |

**Environment variables.** `SITE_ENV` - the environment for `check --env` and `build --env` (the flag, then `SITE_ENV`, then dev); `HERON_NOTES` - the notes language for all commands, including `init`, `setup`, `docs`, `schema`: help, messages, the error frame, the `check` and `build` report, the comments and notes in the site files, the language of `docs` and `schema` when they have no `--lang` of their own; `HERON_IN_CONTAINER=1` - the image mode (also enabled by the presence of the file `/.dockerenv`); `HERON_DEBUG=1` - same as `--debug`; `HERON_WORKERS` - cutting processes; `SOURCE_DATE_EPOCH` - the build time for `env.stamp` (§4); `HERON_THEMES_URL` - the theme catalog; `HERON_CHANNEL`, `HERON_REVISION`, `HERON_BUILT` - the `heron --version` string is built from them.

- `requires` in `theme.yaml` is a list of paths to the blocks and fields of `site.yaml` that the theme needs (`20` §2); if a path is missing, `heron check` reports it before the build;
- `-v`, `--verbose` (on `new` and `init`) prints the whole file plan instead of a short summary; `-y`, `--yes` accepts the defaults without questions or confirmation;
- `--drafts` includes `published: false` (for `serve` it is on by default, `--no-drafts` turns it off, `check` and `build` have no paired flag); `--strict` turns warnings into errors - the mode for CI;
- `--allow-schema KEY` (for `build` and `check`) - a one-off exception for a `SCH001`-`SCH006` finding, a key of the form `<CODE>:<file>:<path>`; the flag is repeatable and applies only to this run, `site.yaml` does not change. The key is checked by the same rule as `schema_exceptions[].key`; an invalid one is an error. `check --env NAME` sets the environment for the `SCH` strictness as in `build`: the flag, then `SITE_ENV`, then dev.
- `--env prod` - the production build: indexing and analytics counters. Without it - dev: `robots.txt` with `Disallow: /`, `noindex`, no counters. An empty site and an empty main language are allowed only in dev (`E017`, `E021`);
- `heron new` creates a site in a new folder or in the current one (`.`). The folder may be under git: `.git`, `.gitignore`, `.gitattributes`, `.gitmodules`, `.github`, `.gitlab`, `.DS_Store`, `.editorconfig`, `README`, `LICENSE` do not get in the way and are not overwritten. Any other file - a refusal with a list of what is in the way and the advice `heron init`;
- **in a terminal `new` asks questions**: the language of the notes, the name, the domain, the site languages, the main language (the last one only if there is more than one language). Each question has a default value, a wrong answer is asked again, at the end - a summary and a confirmation; a refusal creates nothing. **Without a terminal** (an agent, CI, `docker run` without `-it`) there are no questions: the values come from the flags `--name`, `--domain`, `--lang` (comma-separated, the first one is the main one) or the defaults, and a line says so. `-y` switches off the questions in a terminal too. The answers go into `site.yaml`, and for each language `content/<lang>/index.md` and `404.md` with a full SEO block are created right away: the starter site builds with `--env prod --strict` without a single warning. From then on `site.yaml` is the single source of truth, `heron init` completes the folders to match what it says;
- `--notes ru|en` - the language of the notes: comments in all skeleton files (`site.yaml`, `theme.yaml`, the SEO block of pages), the notes `heron-readme.md` and the messages on screen: the steps and the result of `new`, `init`, `page`, `check`, `build`, errors. The `check` and `build` report follows the same language (its sections: "Pages - N" / "Страниц - N", types, translations, links, orphans and others), and so does the frame of the error and warning summary ("Warnings - N" / "Предупреждений - N", the warning kinds, "… and N more" / "… и ещё N", "what to do" / "что сделать"), as well as the layout error `E024` of `init` and `new` (the heading and the frame captions). The details and hints of errors and warnings follow the language of the messages; the text of a library itself (Pydantic, PyYAML, Jinja2 errors and the like) stays as it is; `E033` from `check` (§12) has its text and recipe in both languages. The order: the flag → the environment variable `HERON_NOTES` → `build.notes` from `site.yaml` → `en`. `new` writes the choice to `build.notes`, so `init` and `page` without the flag keep the language the site was set up in. The languages of the site itself do not depend on it. All commands accept `--notes` (and so does `heron` itself before the command); the `--help` text and the service lines of flag parsing (`Usage`/"Использование", `Error`/"Ошибка") are in the same language, and the comments of the `heron recipe` recipe - in the notes language of the current folder. The help language is chosen before the arguments are parsed: `--notes`, `HERON_NOTES`, `build.notes` from `site.yaml` of the current folder, otherwise `en`; the `heron --version` line is one for both languages - scripts parse it. If `site.yaml` cannot be parsed, after the flag and `HERON_NOTES` the language is searched for in its text as the line `notes: ru|en` (a commented one does not count), otherwise `en`: the `E011` error frame and "what to do" are in the site language;
- `heron init` looks at what the folder has, adds what is missing, overwrites nothing without `--force` and prints what it found and what it added. **No `site.yaml` - the site is only being set up**: in a terminal the same questions as for `new`, with the same flags; the folders already present in `content/` are offered as the default languages. There is a `site.yaml` - no questions, it is the source of truth;
- `new` in a folder that already has `site.yaml` does not list "files in the way", but says that a site is already here - in the language of that site (`build.notes`) - and offers `init`, `check`, `build` or how to start over;
- **the default name** is the repository name from `origin` in `.git/config`, otherwise the folder name. In a container the folder is always `/site`, so without a repository `my-site` is offered there;
- `new` and `init` print a summary by meaning (config, content per language, theme, folders, notes, what was left untouched) and a "What next" block with ready commands for this folder; the full list of files - `-v`. In a container (`HERON_IN_CONTAINER=1` or `/.dockerenv`) every `heron …` hint in the messages - here and in errors, `check`, `build`, `page`, `setup` - is printed on its own line as a full `docker run … ghcr.io/fmstm/heron:<tag> …` command for the image of its channel (`HERON_CHANNEL`: `prod`, `beta`, `dev`; a release `vX.Y.Z` - tag `X.Y.Z`; no channel - `prod`): `-it` for `new`, `init`, `setup`, `serve`, plus `-p 127.0.0.1:8000:8000` for `setup` and `serve`. The `--help` text stays short;
- **paths are relative to the current folder.** In the image (`HERON_IN_CONTAINER=1` or the file `/.dockerenv`) only the mounted folder `/site` is visible; a path from the human's computer that does not exist inside gives an explanation about mounting and the advice to pass `.` or the name of a nested folder;
- **a traceback never gets out.** An engine error is printed by the form: code and title, where, details, what to do. No write permission - advice about `--user $(id -u):$(id -g)`. An unexpected error - its kind, text and the advice to repeat with `--debug` (or `HERON_DEBUG=1`), which gives the full traceback;
- `heron page` creates a file with a full SEO block and all sections of the type from `theme.yaml`;
- `heron new` puts in the white starter theme (light and dark, a language and mode switcher) and its demo pages in each language: the home page, `blocks.md` (all thirteen forms), `themes.md`, `docs.md`, the section `structure/` (`_index.md` with `view: list` and two pages inside), 404, the menu `["/", blocks, themes, docs, structure]`, images `media/demo/`. The demo shows every type, block and section view of the white theme (§7, "The theme demo and reference"). The texts are in Ukrainian, Russian and English, other languages get the English ones. There is no "without demo" flag: the demo pages are part of the theme. `heron init` adds them for a new language only if `blocks.md` is still in the main language;
- **the agent kit** (`20` §1): `new` and `init` put `agents/` and the root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` in the notes language, unless `build.agents` is `false`. `init` without flags (and the `setup` configurator, which calls the same `init`) only adds `agents/` files: puts the missing ones, does not overwrite existing ones, `--force` has no effect on the kit without the flag; the root pointers (`AGENTS.md`: name, languages, domain, about the project) are updated by the hash from the manifest - an untouched one is replaced, one edited by the human stays. The language here is the `lang` of the manifest, not `build.notes`: missing files and pointers are written in the language of the snapshot, the manifest header does not change. If `build.notes` is different, the summary prints the info line "the kit stays in <lang>, build.notes is <lang>: to switch the kit language - heron init --agents" - on every `init`, as long as the languages differ. No manifest, a broken one or a `lang` in it that is not ru/en - `build.notes` is taken. `init --agents` updates the kit by the manifest in the `build.notes` language: files whose sha256 match `agents/heron-kit.yaml` are replaced by the new version, edited ones are skipped and listed ("edited by you, left as is: `agents/roles/content.md`"), new ones are added, extra ones are not deleted; with `--force` the edited ones are replaced too. If the kit language changes along the way, the manifest `lang` becomes the new one, and the summary prints "kit language changed: <old> → <new> (build.notes)"; a repeated `init --agents` is silent. `--no-agents` for both commands puts nothing from the kit, does not touch the manifest and `AGENTS.md`, and writes `build.agents: false`; `init --agents` on such a site turns the kit back on (`build.agents: true`). The source of the files is the package documentation (`heron/_docs/docs/<lang>/`), the schemas are generated by the same function as `heron schema --export`. The `new`/`init` summary names the kit in one line ("agent instructions: agents/, AGENTS.md - ru"), `-v` lists the files. All writes go through the path check (`E024`), the write is deterministic (the same call gives the same bytes, except `created` without `SOURCE_DATE_EPOCH`);
- `heron docs` - the documentation of exactly this engine version, from the package: without arguments - the table of contents, with a topic - the whole file in markdown, `template <file>` - a sample, `--search` - lines with context, `--export <folder>` - everything as a folder with the same paths as in the repository (`--all-langs` - both languages into `ru/` and `en/`). **Language:** `--lang ru|en`, otherwise `--notes`/`HERON_NOTES`/`build.notes` from `site.yaml` of the current folder (in the image - of the mounted `/site`), otherwise `en`. Topics are read from `docs/<lang>/`; if there is no file in that language, the file in the other language is printed, and the first line of the output is a mark in the language of the requested topic: for `--lang en` - `[ru: no English translation yet]`, for `--lang ru` - `[en: перевода на ru пока нет]`; an outdated translation (`docs/translation.yaml`, `23` §10) is marked the same way: `[en: the translation lags behind ru]`. The table of contents (`heron docs` without arguments) marks in a topic's line that it will open in the other language: `(opens in ru)` for `en`, `(откроется на en)` for `ru`. Topics: `agents` - the repository pointer (`AGENTS.md`, bilingual), `kit` - the kit README, `readme` - the repository README (by the language of the request: `README.md` for `en`, `README.ru.md` for `ru`; if there is no file in the needed language, the other one is given with a notice, as with the other topics), the roles `architect`, `content`, `designer`, `builder`, `capabilities`, the guides `concepts`, `first-site`, `pages`, `theme`, `seo`, `deploy`, the reference `contract`, `engine`, `deploy-spec`, `distribution`, `architecture`, `skills` - the skills from `skills/`, `schemas` - which schemas exist and how to get them; `template <file>` - a sample; `theme-ref [path]` - the theme reference of the site at the path (by default ".") from its contract and demo (§7, "The theme demo and reference"). `--export` writes out `docs/<lang>/**`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` of the site template and `schemas/` - exactly what a new site gets in `agents/` - and advises starting with `README.md`. Only text goes into the package and the image (both languages and the skills - about 1 MB, compressed - about 300 KB), the brand images do not; a test makes sure every documentation file is available as a topic in its language;
- `heron schema` - JSON Schema (draft 2020-12) of the contracts of this version: `--site` (the default) - `site.yaml`, `--theme` - `theme.yaml`, `--frontmatter` - the page frontmatter (the fields from `20` §4.2; relation fields declared by the theme and custom `page.meta` fields are allowed as additional ones; rules the schema does not express - the trailing newline, field dependencies - are written in `description` in the words of the contract), `--setup` - the configurator answers, `--describe` - the output of `heron describe --json`, `--errors` - the error code registry: `{"$id": …, "$schema": …, "x-heron-version": …, "errors": {"E002": {"title": …, "hint": …}}}`, including `SCH001`-`SCH006` (the same dictionary the engine prints; matches §11). `--export <folder>` writes all six files (the kind flag is ignored here; two kind flags at once are an invocation error): `site.schema.json`, `theme.schema.json`, `frontmatter.schema.json`, `setup.schema.json`, `errors.json`, `describe.schema.json`. The output is deterministic: keys are sorted, indent 2, non-ASCII without escaping, a newline at the end; two runs are byte-equal. `$id` - `https://sitebuilder.heron.software/schema/<major.minor>/<name>.schema.json`, for the registry - `.../errors.json`; the field `x-heron-version` - the exact engine version. Editor hints: export the schemas with `heron schema --export schemas/` and point your editor's YAML settings at the file you need;
- `heron check --json` - the same report for an agent and CI, as one JSON object in stdout, no human output. Exit code `0` - no errors (with `--strict` - no warnings either), `1` - there are some. Fields: `ok` (bool), `version` (the `heron --version` string without the `heron, version` prefix), `strict`, `pages` (the number of pages, an integer; `null` if parsing was not reached), `schema` (the markup section of the report, `section.as_json()`, or `null`), `errors` - a list of `{code, path, line, message, hint}`, `warnings` - a list of `{kind, path, line, message}` (`kind` is the internal name of the kind, in Russian, not translated; `message` and `hint` are in the language of the messages, as in the regular output), `kit` - `{present, engine, lang, current}` about the kit `agents/` (`current` - whether the manifest's `engine` matches the engine; the manifest is unreadable - `present: true`, the rest `null`). With `--old-urls` the lost old URLs get into `warnings` (kind "redirects", path `old-urls`), and the object gets an `old_urls` section - `{summary, lost}`: `summary` is the summary line, `lost` is a list of `{path, line, message}`, texts in the language of the messages; without `--old-urls` there is no such section. New fields are added, existing ones are not renamed and do not disappear within a minor version.

Packaging into an image is not among the engine commands: the nginx image with the site is built by the **host** - `scripts/site.sh <site> image <environment>` from the engine repository (`23-distribution.md` §5).

### heron page

`heron page <type> <slug> [--lang L] [--folder F] [path]` puts a stub into `content/<lang>/<folder>/<slug>.md`.

- `--lang` must be in `site.languages`, otherwise `E005` (the hint is the list of languages). Without it `site.default_lang` is taken.
- `--folder` - a path inside `content/<lang>/`. A leading `./` and `/` (one) and a trailing `/` are stripped: `/guides` is the same as `guides`. A path with `..`, starting with `//` or with a part starting with a dot (`.git`) gives `E024`, no file is created.
- If `content/<lang>` or an intermediate folder is a symbolic link pointing outside the site, the command fails with `E024` and writes nothing.
- The type must be described in `theme.yaml`, otherwise `E008` with a list of types. The slug is Latin letters, digits and hyphens, otherwise `E005`; the type and the slug are checked before the file is written.
- An existing file is not overwritten (`E004`).

### heron describe <a id="heron-describe"></a>

`heron describe [name] [path] [--json] [--lang L]` shows the contract of the site theme (§7, "Theme contract") together with the service fields of the engine and the defaults from `site.yaml`. The theme is found the same way as by the build.

- Without a name - everything in short: the service fields by group, the types and their sections in order, the blocks and their fields with `hint`. With the name of a type or a module - only it (for a type - also the modules its page needs), with full `help` and a markdown sample. An unknown name is `E008` with the list of types and modules.
- `--lang` - the language of the hints: `ru`, `en` or another language of the theme (a code like `pt-br`, otherwise an invocation error, code 2). Without it - the notes language. No text in this language - the text without a suffix, then the English one. Service fields are in ru and en.
- `--json` - one object for an agent and programs, its form is `heron schema --describe` (`describe.schema.json`). Every key is always there; what is missing is `null` or an empty list.

Top-level keys of `--json`:

| Key | What is in it |
|---|---|
| `$schema`, `heron`, `lang` | the schema address, the engine version, the hint language |
| `selected` | `{kind: type\|module, name}` or `null` without a name |
| `site` | values from `site.yaml` in the language `lang`: `name`, `languages`, `default_lang`, `title_suffix`, `og_default_image`, `menu` (`nav.main`), `updated_from` |
| `theme` | `name`, `title`, `version`, `heron`, `languages` (the hint languages), `described` (whether the theme described fields) |
| `groups` | the groups of service fields in order: `name`, `title` |
| `service` | service fields: `page` and `section` - `name`, `type`, `group`, `where` (`frontmatter`, `path`, `site.yaml`, `heading`), `key`, `default`, `default_from`, `hint`, `help` and limits |
| `md_places` | the vocabulary of places in markdown: `name`, `hint` |
| `types` | types: `name`, `template`, `jsonld`, `children_type`, `views`, `sections` (in the order of `uses`: `id`, `any`, `kind`, `module`, `required`, `fields`), hints |
| `modules` | modules: `name`, `scope`, `kinds` (`kind`, `class` - the class in the anchor, `auto` - recognized without a class), `schemaorg`, `fields`, `example`, hints |

A field in `fields` has all keys of a block field (§7) and hints; nested items have their own `fields`. The questionnaire and the studio use the same object: the field list of a page is `service.page`, then the sections of its type.

### heron setup <a id="heron-setup"></a>

A configurator instead of a hand-written `site.yaml`. Without flags it brings up a local page (address and port as for `heron serve`: in the image it listens on `0.0.0.0`, the port is published only on the machine's loopback `-p 127.0.0.1:8000:8000`). The access boundary is a key the engine prints in the terminal in the page address after `#` (`http://localhost:8000/#key`): it is not built into the page itself, and without it `/api/*` (reading answers, uploading a theme, writing) answers 403. A client that reached the port but did not see the terminal gets only an empty page. The `Host` header must additionally be local - this is a defense against DNS spoofing, not the access boundary. `--answers file` applies the same answers without a browser - for an agent and CI, `-` reads stdin; `--dump` prints the recorded answers in YAML: fix them and feed them back. The answer schema - `heron schema --setup`.

The configurator opens only in a site folder: no `site.yaml` - a refusal with the advice to go to the site folder or to create one (`heron new`). A changed field is marked "was: X" with an "undo" button - the comparison is with what is currently written in `site.yaml`.

Configurator groups:

1. **site and domains** - `site.name`, the working domain, the service domain → `site.domains.dev`. The working domain is the one production is built with: `site.domains.prod` if it is set, otherwise `site.domain`; change it and both change, the other environments of `site.domains` are not touched;
2. **languages** - a reference list of languages, the selected ones as tabs, the main one chosen from the selected;
3. **who the site is about** - "Who you are": a person or an organization and the kind of organization (`heron/setup/vocab.yaml`), then the field of work and the specialization by the classifier `heron/setup/classifier.yaml` (a specialization may have an exact schema.org type: dentistry → `Dentist`; a company with it - `["Corporation", "Dentist"]`; for a person - `hasOccupation`; the kind "A doctor who sees patients in a clinic or hospital" gives the type `IndividualPhysician` with the fields: specialty (`medicalSpecialty`), the practice place `practicesAt` (a type from a list, a name, an address: street, city, region, postal code, country), `hospitalAffiliation`, `isAcceptingNewPatients`; a specialty from the classifier goes into `medicalSpecialty` as a list of addresses `https://schema.org/<name>`, only for an organization and only if the schema.org vocabulary allows the property for its type); fields in each site language (name, title, position, "what you do"), the address as a block (country from a reference list with the phone code, city, region, postal code, street, building), a contacts builder `type · purpose · value`. The field of work and the specialization go as captions into `organization.field_of_work` and `organization.specialization` (with language suffixes), into the markup - `knowsAbout`;
4. **search** - the title suffix as a separator and text (`seo.title_suffix`: the configurator and `--answers` always put spaces around the separator, text without a separator gets " - "), `seo.og_default_image`, `seo.allow_prices`;
5. **AI assistants** - `seo.llms_note` as tabs by site language;
6. **analytics** - `analytics.ga4` (format `G-...`), `gtm` (format `GTM-...`), `metrika` (digits only) (into the build only with `--env prod`);
7. **publication** - `publish:`: "Not sure yet", GitHub (repository, branch, version, environment, `auto` - automatic build and publication of the image), Docker Hub, static files (to a server or GitHub Pages - with a branch); when building an image - a dev/prod table: domain, indexing, image address; the helpers `publish.helpers` - a build script, a publish script, `.gitignore`, each switched on separately. With "Not sure yet" only switched-off helpers and the engine, if it is not `prod`, remain in `publish:` - reopening the configurator does not bring them back;
8. **keys and modules** - in development, no fields;
9. **theme** - the current one, from the catalog (the white one - `starter`), by a link, as your own archive.

**The `publish` keys in the answers** (`heron schema --setup`):

- `way` - `github`, `dockerhub`, `static` or `none` (`none` by default);
- `auto` - `true`;
- `env` - `dev` or `prod` (`dev` by default);
- `engine` - `prod`;
- `branch` - `main`;
- `repo`, `dockerhub_user`, `image`, `server`, `path` - an empty string;
- `static_target` - `server` or `pages` (`server` by default);
- `helpers` - `build`, `publish`, `gitignore`, all `true` by default.

How the answers go into `site.yaml`:

- each fact goes to one place: the name and the description - `organization`, the address - `contact`, the communication channels - `contact.channels` (`{type, purpose, value}`), the first phone and the first email - also `contact.phone`/`contact.email` (the theme footer and the markup substitutions use them); language values - with the suffix `_<lang>` (`city_de`). The markup node `schema.entity` is written with substitutions (`"{{ contact.phone }}"`), not copies: the phone changes in one place;
- a skipped question removes the key - there is never an empty value in the markup; the price level gets into the markup only with `seo.allow_prices: true`;
- keys the configurator does not manage (`gone`, `forms`, `nginx`, custom blocks) stay as they were. The node `schema.entity` is merged three ways: the base is what the configurator would have written for the previous config; the answer did not change - the key stays as in the file (fields by hand - `geo`, `openingHours`, `medicalSpecialty`, `founder`…, an exact `@type`, a custom `@id`), it changed - the new one is taken, the answer was removed - the key is removed; the previous `site.yaml` goes to `.heron-cache/setup/site.yaml.<time>`; two copies in the same second get `-2`, `-3`: the file is created exclusively, an existing copy is not overwritten. The configurator keeps the comments in `site.yaml` (above a key, at the end of a line, the file tail and its own block);
- the result is checked by the same schema as the build; it did not pass - nothing is written;
- after the write the structure follows the config: a new language gets a folder, a home page and a 404 (`heron init`).

Files next to `site.yaml` (each with a `heron setup` mark; a file without the mark is not overwritten, its own file that became unnecessary after a change of method is removed):

| Method | Files |
|---|---|
| helper | `.heron/scripts/build.sh` - the final build with the HERON image by the same policy as `scripts/site.sh` and `site-image.yml`: no network, the image root read-only, no capabilities, not as root; the site folder read-only, writable - only `dist/`, `.heron-cache/` and `.dist.heron-lock` |
| helper | `.heron/scripts/publish.sh` - publication by the chosen method (`git push`, an image to Docker Hub, `rsync`); `.gitignore` |
| GitHub | with `auto` - `.github/workflows/image.yml` (calls `site-image.yml` of the same HERON branch; GitHub sets the path) |
| Docker Hub | the publish script: build, `heron recipe` → nginx image, `docker push` (login - `docker login` on the computer) |
| static files | the publish script (`rsync` to a server) or `.github/workflows/pages.yml` (GitHub Pages; the build - the same run policy) |

There is still no build logic in the site folder: the scripts and the workflow are short calls of the HERON image; a Dockerfile and `.env` are not put into the site folder. The scripts lie in the hidden folder `.heron/` (inside - `scripts/`, with room for other service files): the engine does not read it, it does not get into `dist/`. Former `scripts/*.sh` with the configurator mark are removed on the next save.

**Keys and modules** are still in development: the configurator has no fields for them, keys are never written to `site.yaml` and git. Docker Hub takes the login from `docker login`, the GitHub workflow - a short-lived build token.

Contacts go into the markup like this: `telephone`/`email` - by substituting the main ones, `contactPoint` - per channel with a purpose (`contactType`: main → customer service, support → technical support, sales, marketing, booking → reservations, press), `sameAs` - public profiles (`t.me/…`, `wa.me/…`, social networks). The configurator rewrites the set of `contactPoint` and `sameAs` on every save.

The engine for building the site is `publish.engine`: a channel (`prod`, `beta`, `dev`), an exact version `X.Y.Z` or any of them with a digest - `prod@sha256:<digest>`. With a digest `site-image.yml` takes the recipe from the channel branch, and the engine image - exactly this one.

Publication values go into shell commands and into YAML, so they are checked when the answers are read: the branch `publish.branch` - letters, digits and `. _ - + /` by the git rules (no `..`, `//`, leading `-`, `.lock` ending); the server - `user@host` without a leading `-`; the folder on the server - an absolute path of letters, digits and `. _ - + ~ @` without `..` (the shell on the server parses it too). In the scripts the values are additionally quoted, in the workflow the branch is written as a string. `site-image.yml` gets its input values as environment variables and checks them before the first build step.

**Markup in the configurator.** Before writing `site.yaml` the configurator checks the site nodes (`site_findings`: the site-wide node and the `schema.<Type>` blocks for each language, without pages and the theme). The page shows three lists: active findings, excepted ones (reason and deadline) and expired exceptions. In the page state this is `schema.findings` with the keys `active`, `excepted`, `expired`; excepted and expired ones are `{key, code, path, field, reason, until}`, active ones and the refusal of the `check` mode (answer 409) are `{key, code, title, detail, hint, field, path, value, drop_label}`; `field` is the configurator field the finding is tied to, or `null`. An unknown `schema.mode` is a refusal "mode X: check, drop or except"; `except` without `reason` is a refusal before the check; if there are no findings, the mode affects nothing. The `schema.mode` mode in the answers: `check` (the default) - findings are not written, the answer is rejected with a list; `drop` - remove the keys listed in `schema.drop` (all of them if the list is not set) from `site.yaml`, the list of what was removed goes into the result; `except` - append to `schema_exceptions` an entry `key` + `reason` for each finding, `reason` is required; if an exception with this key already exists (an expired one too), its reason is replaced and its deadline `until` is removed - the exception becomes permanent. After `drop` the check is repeated, the remainder is a refusal.

### heron theme <a id="heron-theme"></a>

A theme archive: `heron-theme.yaml` (name, compatible HERON versions), `theme/`, `demo/` - the theme's demo pages: `content/<lang>/`, `media/`, `data/`. Sources: `starter` - the built-in starter theme (no network), a name - the catalog `HERON_THEMES_URL` (by default `catalog.json` of the repository `FMSTM/heron-themes`: name → https address and sha256), an https link (`#sha256=<hash>` at the end is verified), a `.zip` or `.tar.gz` file.

Unpacking is distrustful: absolute paths, `..`, links and devices, the path parts `plugins`, `.git`, `__pycache__` and the extensions `.py`, `.pyc`, `.sh`, `.exe`, `.bat`, `.cmd`, `.ps1`, `.so`, `.dll` - refusal `E032`. Timeouts: archive download 20 s, theme catalog 3 s. Forbidding code files does not by itself make a theme harmless: the templates of an installed theme are built in the sandbox (§7); the limit is 200 MB per archive, 50 MB per file, 5000 files. A broken or truncated archive (zip or tar.gz), damaged compressed data included, is also `E032` ("the archive is damaged or truncated"), not `BadZipFile`/`EOFError`; the configurator answers such an archive with `400 {"ok": false, "error": …}`. The theme is checked against the `theme.yaml` schema before installation; the previous one moves to `.heron-cache/setup/theme.<time>` (in the same second - `theme.<time>-2`). The archive path of `theme get` is relative to the current folder, and if there is no file there - to the site folder. This is a trusted path from the terminal: an absolute one is allowed too. In the configurator (`--answers`, the server) the source `file` without an upload (`upload`) accepts only a path inside the site, from its root (`themes/t.tar.gz`); an absolute path, `..` or a link pointing outside - `E024`, the theme and the backups are not touched, the file content is not read. An archive for `--answers` is put into the site folder or installed as a theme with `heron theme get`. The theme's demo pages are put into each site language and only where there is no file: a site page is never overwritten. No pages in a site language - the pages of the main language are taken, otherwise the first ones. `theme get` lists every file of the theme and the demo it placed and the number of files kept as they are because the site already had them. `heron theme pack` builds an archive from the site's theme and its content - only if the content shows everything the theme contract declares (§7, "The theme demo and reference"; otherwise `E037`, no archive is written).

## 11. Errors and warnings

The split is strict: an error stops the build, a warning goes into the report.

The detail and hint of an error and the text of a warning are in the language of the messages (§10, `--notes`), including in `check --json`; the text of a library stays as it is. The kind of a warning in `warnings.txt` is always in Russian, the message text is in the language of the messages.

**Stop the build:**

| Code | Condition |
|---|---|
| `E001` | broken YAML in the frontmatter |
| `E002` | no `title`, `h1` or `description`, or a frontmatter field of the wrong type (a date that is not a date, an `order` that is not a number) |
| `E003` | a duplicate section identifier in a file |
| `E004` | two files give one URL |
| `E005` | an invalid file or folder name in `content/`; for `heron page` - an invalid slug or a language outside `site.languages`. An invalid `slug` in the frontmatter is `E002` |
| `E006` | a relation field refers to a page that does not exist |
| `E007` | the image is not on disk |
| `E008` | a page type has no template in the theme, the strings file `theme/i18n/<language>.yaml` is unusable, a theme with `fields` lacks a hint in one of its languages (`heron check`), an unknown name in `heron describe` |
| `E009` | `redirect_from` coincides with an existing URL |
| `E010` | access to a variable that does not exist in a template, or an exception while a template runs |
| `E011` | `site.yaml` does not pass validation; also an invalid value of `HERON_WORKERS` (outside 0-64 or not a number) |
| `E012` | the engine version does not satisfy the `heron:` requirement in `site.yaml` |
| `E013` | the theme is found neither locally nor among the installed packages |
| `E014` | a plugin from `plugins:` is not installed, failed on loading or in a hook, or has an invalid name |
| `E015` | raw HTML in markdown with `build.allow_raw_html: false` |
| `E016` | an invalid section identifier |
| `E017` | a production build without a single page |
| `E018` | the site resource folder is doubled: `media` and the old `img`, or `media` and `static/media` |
| `E019` | a local video has no poster |
| `E020` | the schema.org markup cannot be built: not JSON, no type declared by the theme, the address or coordinates are declared but empty in the site-wide node, there are money fields with `seo.allow_prices: false` |
| `E021` | a production build in which the default language is empty: the site root would answer 404 |
| `E022` | a `gone` entry closes the address of an existing page or overlaps with `redirect_from` |
| `E023` | `fields` in `theme.yaml` names fields the engine does not know: custom frontmatter fields are not written there, or a newer engine is needed |
| `E024` | a path goes outside the allowed folders: `..` in a file path, a symbolic link pointing outside from `content/`, `data/`, `media/`, `static/` or the theme, a result name outside the build folder; the build, cache and source folders overlap; `.heron-cache` or its `renditions/` is a link (§4, "File boundaries") |
| `E025` | a heading attribute outside the allowed set (`#id`, `.class`, `lang`, `dir`, `title`, `data-*`): `onclick=`, `style=` and the like (`20` §4) |
| `E026` | two sources give one build file (a page, a generator, `static/`, the theme, media, a plugin), a file and a folder with the same name, a foreign file in the build folder in place of a needed path; replacing a generated file with a static one - only via `build.overrides` (§4, "Writing the result") |
| `E027` | two masters give identical rendition names: `photo.jpg` and `photo.png` in one folder (§8, "Rendition cache") |
| `E028` | a production build in which a language has no home page (`content/<lang>/index.md`): `/` or `/<lang>/` would answer 404. In dev and in `check` - a warning |
| `E029` | two files of one language give one page key (`a.md` with its own `slug` and the section `a/_index.md`): the key links translations and links |
| `E030` | a source folder or file cannot be read - no permissions, a disk failure: the build is stopped instead of passing without some of the pages (§4, "File boundaries") |
| `E031` | `heron serve` cannot take the address and port: the port is taken by another program or the address does not belong to the machine |
| `E032` | the theme cannot be installed: the archive breaks the rules (paths, links, code, size) or is broken/truncated, the catalog is unavailable, the sha256 does not match, `theme.yaml` did not pass the check |
| `E033` | a theme template accesses something the sandbox closes: Python service attributes, changing site data, `BaseModel` methods, paths (§7). `check` finds data changes without a build too (§12) |
| `E034` | a build file the engine must check before writing is empty, unreadable or not UTF-8: a replacement of `.heron-nginx.conf` from `static/` via `build.overrides`. An error even without `--strict`, `dist/` is not changed |
| `E035` | `.heron-cache` or the lock file `.<dist>.heron-lock` cannot be created next to the build folder: the folder above `--out` is not writable. `dist/` is not touched; the engine names the path and the system's reason, not a generic "no permission" |
| `E036` | an image master exists on disk but cannot be read as an image: a Git LFS pointer, an empty, truncated or oversized file. It is an error in both strict and dev builds (unlike `E007`, where the file is simply absent). The engine names the `src`, the owner page and the kind of failure |
| `E037` | the theme demo does not show everything its contract declares: a type has no demo page, a module never drew anything, a section view is not shown (`heron theme pack`, `heron check --theme`; for a theme without `fields` - a warning); `theme pack` in a folder without `site.yaml` (§7, "The theme demo and reference") |

**schema.org markup** (a separate code series; on `prod` - an error, otherwise a warning; exception - `schema_exceptions` in `site.yaml` or `--allow-schema`):

| Code | Condition |
|---|---|
| `SCH001` | the schema.org type is not in the vocabulary. `prod` - an error, otherwise a warning; exception - `schema_exceptions` or `--allow-schema` |
| `SCH002` | the property does not belong to this type. `prod` - an error, otherwise a warning; exception - `schema_exceptions` or `--allow-schema` |
| `SCH003` | the value is not from the enumeration. `prod` - an error, otherwise a warning; exception - `schema_exceptions` or `--allow-schema` |
| `SCH004` | the value type does not fit the property. `prod` - an error, otherwise a warning; exception - `schema_exceptions` or `--allow-schema` |
| `SCH005` | a deprecated type or property. `prod` - an error, otherwise a warning; exception - `schema_exceptions` or `--allow-schema` |
| `SCH006` | the image from the markup is not in the build. `prod` - an error, otherwise a warning; exception - `schema_exceptions` or `--allow-schema` |

An error message must contain the file path, the line number, what is wrong and what to do. `Error in template` without an address is not a message.

**Warnings:**

The format of an error line: `<CODE> <path>[:<line>]: <message>`, with a hint the line `  what to do: <hint>` follows; without a path - `<unknown file>`. This is how content and build errors are printed. An error that aborted the whole command (config, theme, `heron page`, `heron theme get`) is printed in a frame: code and title, `where`, `details`, `what to do`.

Code warnings: `title` longer than 60 characters · `description` longer than 155 · "an image is set but `image_alt` is not" (only if `image` is set; kind "other") · "`title` and `h1` are the same" · "the navigation `nav.main` is empty" (kind "seo", path `site.yaml`) · "the same `title` on N pages (<language>)" (among indexable pages of one language) · "navigation links are not in the HTML of the home page (<language>): the menu is built by a script".

Other warnings by message key (texts - `heron/texts/`):

| Area | Key | When |
|---|---|---|
| images | `media_heavy` | the master weighs too much |
| images | `media_legacy_folder`, `media_two_folders` | an old asset folder, or two folders at once |
| images | `media_no_file` | the image file is missing |
| images | `render_no_rendition`, `render_no_rendition_files` | no cut variant or no files for it |
| relations | `links_field_empty`, `links_too_few` | a relation field is empty or has fewer links than the theme expects |
| relations | `links_self` | a page links to itself, the link is skipped |
| links | `links_fallback`, `links_unresolved` | no page in the needed language (the link leads to another) or the address leads nowhere |
| menu | `links_menu_missing`, `links_menu_untranslated` | no page in the language or it is not translated |
| translations | `links_no_default` | the page exists in a language but not in the default language |
| translations | `render_i18n_key_type`, `render_i18n_missing`, `render_string_missing` | wrong key type, no strings for the language, or no translation strings |
| languages | `tree_empty_lang`, `tree_no_lang_tree` | a language has no pages or no content tree |
| content | `links_notfound_from_theme`, `links_notfound_no_template` | problems with the 404 page |
| dates | `links_dates_backwards`, `links_dates_future` | update earlier than publication; a date later than the build |
| dates | `links_dates_dirty`, `links_dates_no_history`, `links_dates_not_in_history`, `links_dates_same_time`, `links_dates_unreadable` | the date comes from the file time or is missing |
| other | `output_override_unused`, `tree_home_key` | an unused `build.overrides`; the home page key |
| redirects | `redirects_gone_twice`, `redirects_nginx_rejected`, `redirects_page_gone` | `gone` set twice; `nginx -t` rejected the config; the obsolete `gone` field on a page |

"A section in a file that the theme does not use" and "a missing optional section" are not warnings but sections of the `Report` (`unused_sections`, `missing_sections`); they do not get into the "Warnings - N" counter or into `warnings.txt`. The full list is written to `<next to dist>/.heron-cache/warnings.txt` as lines `<kind>\t<path>[:<line>]\t<message>` (the kind in Russian, the message text in the language of the messages; a file write error is silently skipped).

A missing optional section is collected into the debt summary:

```
The theme expects a section, but the file has none:
  contra       - 6 pages: content/ru/design.md, content/ru/audit-basic.md, …
```

The line lists the source paths `page.source`, up to 5, then " …"; without a list the line is not printed.

**The cover and old URLs** (`heron check` warnings, not errors):

- `cover is smaller than <images.cover_width> px: <path>` (kind "images", the actual number is substituted, 1200 by default) - the cover master is narrower than `images.cover_width`; what to do: put a master not narrower than `images.cover_width`, otherwise the crawler gets a small picture;
- `old URL <url> leads nowhere; probably set a 301 to <target>: redirect_from: [<url>] in the front matter of <file>` (kind "redirects", path `old-urls`) - only with `--old-urls`; what to do: add the address to `redirect_from` of the named page or to `gone`.

This is exactly the list for the client that otherwise gets lost. It is printed after every build, not remembered once a quarter.

## 12. The `heron check` report <a id="check-report"></a>

Without a build, it reads the content and the theme and prints:

- pages by languages and types, what is translated and what is not
- section fill rate per type
- sections in files that the theme does not use - catches a typo in an anchor
- theme modules that no type uses
- internal links: broken ones, and pages nobody links to
- orphans: pages that no link leads to
- the lengths of `title` and `description`
- sections that are not in the list above and that `Report.render` prints: "The section format is not the one the theme expects (this is not an error)" with a line `<file>: <section> - expected <format>, got <format>`; "In the menu but without a short name - the file name will be shown"; "`nginx -t` on the built config: passed"; "The manual `updated` date on M of N pages overrides `updated_from`: <mode>".
- with `--old-urls <file>`: every old URL must lead to a page, to `redirect_from` or to `gone`; for each one without a path - a warning with the presumed target and a summary line "old URLs: N, without a path: M". Empty lines and lines with `#` are skipped, in a CSV the first column that looks like a URL is taken. An address is compared the way nginx sees it: the scheme and host are dropped, `%XX` and Cyrillic are equal, with and without a trailing slash is one address; case and the language prefix are distinguished; query parameters count only for `gone` entries with a parameter; repeats are counted once; the warning prints only the path; the texts of warnings and the summary are in the language of the messages (§10, `--notes`)
- **schema.org markup**: during the build and in `check` - report lines: "schema.org markup (vocabulary 29.3): nodes N, findings M (E errors, W warnings)", for each finding a line `CODE file:path - reason (pages: K)` and "exception key: ..."; then "Markup exceptions: N" with the reason and the deadline (or "one-off (--allow-schema)"); "Unused exception: <key> - catches nothing, remove it from schema_exceptions"; "Exception expired: <key> - the deadline <date> has passed, the finding is in force again"; and the information "Properties from the pending section: ...". `--json` carries the same data. In the language of the messages (§10, `--notes`).
- files in `media/` that no page expects, and content that settled in `static/`
- folders without the note `heron-readme.md` - information, not an error
- the agent kit (`20` §1) - one info line, not a warning: "`agents/`: agent instructions, engine 0.1.0, ru; not part of the build", on a version mismatch - "kit from 0.1.0, engine 0.2.0 - update: `heron init --agents`", with `build.agents: false` - "agent kit disabled", without the folder and without the key - "no agent kit - `heron init`"
- **fields that not every list element has**: the engine has a strict mode for undefined values, and accessing a missing key fails the build. A template is written for the first element and fails on the sixth. This is not a content error - half of the documents really have no place of issue; it is a warning to the template author to write `d.get("place")`
- **data changes in theme templates** - error `E033` before the build. The module `heron/core/check.py` does not execute templates but parses them with Jinja itself (`Environment.parse` of the same environment as the build) and looks for calls of methods the sandbox closes (§7): `.append`, `.extend`, `.insert`, `.update`, `.pop`, `.remove`, `.add`, `.setdefault`, `.clear`, `.sort`, `.reverse` and the rest of the same list, including the workarounds `x|attr('append')(…)` and `x['append'](…)`. The message names the template by its path from the site root, the line number, the call itself and a recipe by the meaning of the method (list concatenation, `namespace()`, `dict(d, key=value)`, the filters `rejectattr`, `unique`, `sort`), and at the end - `heron docs theme`; the text language is the language of the messages (§10, `--notes`), in `--json` these are the fields `code`, `path`, `line`, `message`, `hint`. Parsed are the theme's `*.html`, `*.htm`, `*.j2`, `*.jinja`, `*.jinja2`, except `assets/` and `i18n/`, and the files templates include by name (`extends`, `include`, `import`, `from`). Not code for Jinja and not checked: text outside tags (JS in `<script>`, `.js` files), `{% raw %}`, comments; `{% set ns.x = … %}` is an assignment, not a call. A template with broken syntax is skipped - the build names it. **`check` is stricter than the build here:** it also flags a template the theme does not render (the build does not touch such a template and passes), and a call of a mutating method on a value whose type is not statically known; plugin global values are checked by their real type. `check` does not consider these containers and therefore does not flag them: `self` (template blocks, `self.<block>()`), aliases `{% import … as h %}` (a template module) and the engine context objects `mod`, `t`, `env`, `page_of`, `picture`, `media_url`, `jsonld`, `cover_url`, `robots_meta` - for example, `mod.update()` renders the module `modules/update.html`. A name redefined in the template itself (`set`, `for`, a macro parameter) is no longer an engine object. Names from `{% from … import x %}` do not count as known objects: it may be a dictionary, so `{{ cfg.update({}) }}` gives `E033` both in `check` and in the build. How to rewrite such places - [`guide/04`, "Accumulating data in a template without `append`"](../guide/04-theme.md#accumulate-data-without-append)

A site's CI adds the command itself: the shared `site-image.yml` does not run it, it builds the image through `heron build`; locally - `scripts/site.sh <site> check`.

**What `check` does not find.** It does not render templates and writes nothing, so it does not see `E010`, `E026`, `E027`; the production readiness checks `E017`, `E021`, `E028` are run only by `build`. A green `check` does not guarantee a successful build.

## 13. Performance

A site of 40 pages in three languages is 120 pages. Everything except images - parsing, relations, rendering, generators, writing - fits into a couple of seconds. There is one expensive part: encoding the renditions.

Measured: 95 masters, 2062 renditions, four cores.

| Build | Time |
|---|---|
| cold, no cache | 157 s |
| repeated, cache intact, `dist` wiped | 4 s, of which images 0.3 s |

Hence two rules. First: the rendition cache must survive deleting `dist`, otherwise it does not exist at all. Second: only cores save a cold build - production and CI have no cache by definition.

Where `heron serve` listens: without `--host` - `127.0.0.1` on the human's machine and `0.0.0.0` in the HERON image (`HERON_IN_CONTAINER=1` is set there). Inside a container `127.0.0.1` is the container itself, and the forwarded port `docker run -p 127.0.0.1:8000:8000` does not reach such a server. The prefix `127.0.0.1:` publishes the port only to the human's machine: without it docker opens it on all interfaces of the computer. `--host 0.0.0.0` outside a container opens the drafts to the whole network - the engine warns about this. The port is taken - `E031` with a hint to take another one.

There is no incremental page rendering: `heron serve` rebuilds everything when a file changes, and without images that is a couple of seconds. A change is detected by a snapshot "path → (time, size)" over `content/`, `data/`, `media/`, `img/`, `static/`, `theme/`, `plugins/` and the site root files in one walk: additions, deletions, renames and edits with the same time are all visible. The agent kit is not part of the snapshot: `agents/` is not walked, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` in the root are skipped - editing instructions does not change the site.

## 14. Tests

Mandatory, the work is not accepted without them:

- section parser: anchors, nested headings, duplicates, text before the first section
- structured sections: facts, faq, steps, timeline on valid and broken data
- building URLs from paths, including `_index.md` and language prefixes
- relation resolve, including a link to nowhere
- **every URL from the redirect map returns 301 to an address that exists and answers 200.** This is the only thing that protects the index during a migration. It is checked on a real nginx, including non-ASCII addresses in both forms, without a slash and with a truncated slug (`tests/test_redirects_unicode.py`, `tests/test_gone.py`)
- each built page contains exactly one `<h1>`
- all internal links in the built HTML lead to existing files
- `hreflang` is symmetric: if A links to B, then B links to A
- the sitemap contains no pages with `noindex` and contains all the others
- two builds in a row give a byte-identical result
- **the agent kit does not affect the build:** `dist/` of a site with `agents/` and the root pointers is byte-equal to `dist/` of the same site without them; not a single kit file in `dist/`; `serve` does not react to edits in `agents/`
- `new --notes ru|en` puts the kit in its language, the site's `AGENTS.md` is 60-100 lines, `CLAUDE.md` and `GEMINI.md` are exactly `@AGENTS.md`; all relative links in `agents/**` and `AGENTS.md` lead to existing files; `init --agents` does not touch an edited file and replaces an untouched one; `build.agents: false` holds
- `heron schema --export` gives the same bytes twice; the samples `templates/{site.yaml,theme.yaml,page.md}` pass their schemas; `errors.json` contains every code from §11
- **documentation parity** (`23` §10): every `docs/ru/**` has a `docs/en/**` with the same path and vice versa (except `docs/en/GLOSSARY.md`); the same number of lines, of headings of each level, of list items, of tables and rows in them, of code blocks and lines in each; the same sequence of explicit heading anchors (`<a id="…"></a>`, `23` §10); the same set of relative links and their targets; in the `.yaml` samples and in the frontmatter of `page.md` - the same keys and values of non-string fields. Only literal tokens are compared byte for byte - commands, flags, keys, error codes, paths, file names; text, comments and captions inside code blocks are translated; on `beta` and `prod` - the translation does not lag behind the source according to `docs/translation.yaml`
- the documentation and the kit contain no name of a specific agent or of an AI model developer company outside the list "which agent reads which file" (an allowlist in the test); the engine site is only `sitebuilder.heron.software`

Separately, beyond unit tests: Lighthouse is not part of the engine delivery, the site itself sets up the run and the thresholds (`22-deploy.md` §4); the guideline is LCP under 2 seconds, CLS under 0.05.


---

## 15. Extension points

Modules from `heron/modules/` and external plugins are written against one set of hooks. The only difference is the delivery: a module lies in the core, a plugin is installed as a package and declared in `site.yaml`.

A plugin is a function `register(hooks)`, called on loading, anew on every build and check (module state is not kept between builds). A hook subscription is `hooks.on(<hook name>, function)`, a custom section type is `hooks.on("block:<name>", function)`. Example: in `plugins/<name>/__init__.py` - `def register(hooks): hooks.on("on_generate", f)`, in `site.yaml` - `plugins: [<name>]`.

| Hook | When it is called | Arguments → result | `check` |
|---|---|---|---|
| `on_config` | after `site.yaml` and `theme.yaml` are loaded | `(config, theme)` - editing or checking the config | yes |
| `block:<name>` | when parsing a section with the class `{#id .<name>}` | `(section)` → section data; `section.kind = <name>`. Built-in types are not replaced this way | yes |
| `on_page_parsed` | after each page is parsed, before relations | `(page)` - editing the page model | yes |
| `on_tree_built` | after the walk of `content/`, `data/` and the dates, before relations | `(site)` - custom relations and groupings | yes |
| `hooks.filter(name, f)` / `hooks.add_global(name, v)` | when the Jinja2 environment is built | custom filters and theme variables; built-in names are not overridden | - |
| `on_page_rendered` | after each page is rendered | `(page, html)` → new HTML or `None`. Handlers run as a chain: each gets the result of the previous one | - |
| `on_generate` | after the generators, before the owner check | `(site, config)` → `{path: text}` - custom build files; a match with someone else's path - `E026` | - |
| `on_build_finished` | **after** the result is written, only for a successful build | `(site, config, dist)` - export, notifications. An exception does not make the build failed: the site is written (`result.failed` is false), the error is in `result.finish_errors`, `heron build` prints "The site is written and intact, but a plugin finishing step (on_build_finished) failed" and exits with **code 3**. The other `on_build_finished` handlers are still called | - |

`on_build_finished` used to be called before writing and could return files. **Compatibility:** files from there are no longer written - the build passes and prints the explanation "build files are declared in `on_generate`"; the plugin needs to move the generation to `on_generate` and accept the third argument `dist`. A failed build (an error or a warning in strict mode) may not reach `on_page_rendered`, `on_generate` and `on_build_finished` - they are not guaranteed to be called.

We add nothing more at the start: an API invented for the future is always invented wrong.

**Hooks act only at the build stage.** A plugin that "accepts a form" does not exist - at the moment of the POST the engine has already done its work and exited. Everything that lives at runtime will be accepted by a separate service, `heron-relay`; it is not implemented yet (see `23-distribution.md`).

Plugin sources and the resolution order - `core/resolver.py`: the site's local folder `plugins/` → an installed package (an entry point of the group `heron.plugins`). Local wins.
