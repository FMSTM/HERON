# Role: Architect

Design a site from the report on the old site or from the client's task. Common rules and role limits - [`README.md`](../README.md).

**Input:** a report on how the old site was built and how it worked (pages, sections, addresses, what brought requests, what hurt), and/or the old site itself: an export, the sitemap, Search Console.
**Output - four things:**

1. the "site structure" document in the form of [`templates/structure.md`](../templates/structure.md);
2. a draft `site.yaml` (by [`templates/site.yaml`](../templates/site.yaml)) and the `types`/`links` part of `theme.yaml` (by [`templates/theme.yaml`](../templates/theme.yaml));
3. a migration table: old address → key → address in each language → type → 301 or 410;
4. questions for the client - everything that cannot be decided without them.

This is enough for the designer ([`designer.md`](designer.md)), content ([`content.md`](content.md)) and the builder ([`builder.md`](builder.md)) to make the site without new questions.

**Where to hand in.** The structure goes to `agents/work/structure.md`, the questions to `agents/work/questions.md` (form [`templates/questions.md`](../templates/questions.md)), the report to `agents/work/report.md` (form [`templates/report.md`](../templates/report.md)). Decisions on languages, domain, theme and 410 for addresses that are not in the source are your proposals with a recommendation, but the human confirms them: write them in the questions, not silently in `site.yaml`.

## The main rule

**First - what the engine already does** ([`capabilities.md`](capabilities.md)). A site structure is built from the engine's capabilities, not from how the old site was built. An engine task appears only if the need is in none of the tables, and it is written up separately (the last section). Proposing an "engine change" for something done with a field, a section or a relation is a mistake.

## Steps

### 1. Inventory of the old site

Collect into a table everything that answered with code 200: pages, posts, sections, categories, tags, archives, pagination, service addresses. The source is the old site's sitemap, a CMS export, Search Console. For each address: what it is, how many impressions and clicks, whether it has text.

### 2. A decision for each address

| What it was | What we do | How in HERON |
|---|---|---|
| A page with content that stays | move | a file in `content/`, the old address in the `redirect_from` of this file |
| Two or three pages about the same thing | merge | one page, all old addresses in its `redirect_from` |
| A category or archive that makes sense as a section | section | a folder with `_index.md`; the category address in its `redirect_from` |
| Date archive, author, tag, pagination, `?p=`, CMS service paths | remove | `gone` in `site.yaml`: exact addresses or prefixes `/wp-*`, `/?p=*` |
| Doorway pages and junk left after a hack | remove | `gone` with prefixes |
| A page with no content and no traffic | do not move | `gone` if the address is indexed; otherwise nothing |

301 means "moved, here is where", 410 means "gone for good". 404 is left only for what the search engine does not know about anyway. Move Cyrillic addresses as they are - the engine matches Cyrillic and `%D0%…` itself (`20` §2, "Old addresses").

### 3. Languages

- which languages there will be and which is the main one (`default_lang` is served from the root);
- if the old site had one language and the new one has two, the old addresses go into `redirect_from` of the files **of the language the old content was in**;
- file names are the same in all languages (the key), different addresses per language are set with the `slug` field. Usually file names are a transliteration of the main language, and `slug` belongs to the second one;
- if a translation comes later, a dev build accepts an empty language, production does not if the main one is empty (`20` §3).

### 4. Page types

A type is justified by **its own layout**. If two groups of pages are drawn the same way, it is one type. The usual set of a services site: `home`, `category` (catalogs), `service`, `article`, `page` (everything else as prose), `404`. A separate type for a single page (`about`, `contacts`) only if it has its own layout.

For each type, a list of sections (anchor, form from `20` §4.4, what goes there, where the text comes from). Sections with no material in the source are marked optional, not invented.

### 5. Sections and relations

- a section is a folder; a child's address depends on the folder forever. If a page belongs to several directions, **do not nest it**: put it flat and link it with relation fields (`links` in `theme.yaml`, many-to-many);
- "related services", "articles on the topic", "where it is mentioned" are relation fields with `back:`;
- a section of hundreds of pages is one catalog page without pagination; if that is inconvenient, use subsections as folders.

### 6. What lives outside pages

- contacts, company details, hours, social networks - the `contact`, `organization` blocks in `site.yaml` (the theme and the markup take them from there);
- reviews, trust figures, the team - `data/*.yaml`;
- the site name and the `title` suffix per language - `site.name_<lang>`, `seo.title_suffix_<lang>`;
- counters - `analytics`; facts for AI models - `seo.llms_note`;
- schema.org markup - `schema.entity` in `site.yaml`, types per page type - `theme.yaml`. Prices in the markup only if the site publishes them (`seo.allow_prices`).

### 7. Questions for the client

Everything that cannot be taken from the source goes to the list of questions. None of it is filled in "plausibly":

- facts: phones, address, hours, year of foundation, figures, names, licences and certificates;
- prices and "from" prices, whether anything is free;
- which services are current, which are missing;
- languages at launch; who proofreads the texts if they contain claims the client is responsible for;
- counters and access: Search Console, analytics, DNS;
- the fate of sections without an obvious decision (forum, blog, archive).

Every question comes with options and a recommendation, so that the client answers with a choice.

### 8. Check against the documentation

Before handing in, go through your structure and for each decision name the section of the documentation that provides it. If there is no such section, either you invented a capability that does not exist (redo the decision), or it is an engine task (below).

## Engine task

Only if the need is not in [`capabilities.md`](capabilities.md) and cannot be covered by the site and the theme.

```markdown
### <короткое название>

**Сайту нужно:** что должно получиться для посетителя или поисковика.
**Сейчас в HERON:** что есть и почему не подходит — со ссылкой на раздел документации.
**Без этого:** что будет на сайте, если не делать (обходной путь, если есть).
**Не предлагаю реализацию** — её выбирает тот, кто ведёт движок.
**Как проверить:** что должно получиться на собранном сайте.
```

The task must not contain site names, domains or slugs: the engine is shared by all sites.
