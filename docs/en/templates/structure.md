# <domain> on HERON - site structure

**Status:** draft · **Based on:** <where the data comes from: export, sitemap, report, interview>
**Engine:** HERON `>=0.1,<0.2` · **Languages:** <en, ru> · **Main:** <en>
**Rule:** facts come only from the source. What is missing is marked **GAP** and listed in section 8.

---

## 0. Decisions needed before production

| # | Question | Options | Recommendation |
|---|---|---|---|
| D1 | <what to decide> | A: … B: … | **A**, because … |

## 1. What exists now

In short: how many pages, which sections, in which language, which addresses, how much traffic, what brings requests, which analytics counters.

## 2. Content tree

The key is the path from `content/<lang>/` without `.md`, the same in all languages. Addresses of the second language are set with the `slug` field.

A filled-in example for `default_lang: en`, `languages: [en, ru]`:

```
content/en/ and content/ru/              type       en                        ru (slug in the ru file)
  index.md                               home       /                         /ru/
  404.md                                 404        -                         -
  about.md                               about      /about/                   /ru/o-nas/                 o-nas
  services/_index.md                     category   /services/                /ru/uslugi/                uslugi
    design.md                            service    /services/design/         /ru/uslugi/dizajn/         dizajn
```

## 3. Page types and sections

| Type | Pages | Why a separate type |
|---|---|---|
| `home` | home page | … |

For `theme.yaml`:

```yaml
types:
  home:
    uses: [intro, "why:list", "how:steps", "faq:faq"]
    jsonld: [WebSite]
links:
  - {field: related, type: service, back: related_from}
```

Sections of each type:

| Type | Anchor | Form (`kind`) | What goes there | Where the text comes from | Required |
|---|---|---|---|---|---|
| `service` | intro | 2 paragraphs | who we help; what the work ends with | … | yes |
| `service` | `{#includes}` | `list`, pairs | what is included | … | if the source has it |

## 4. `site.yaml`

```yaml
heron: ">=0.1,<0.2"
site:
  domain: <domain>
  theme: main
  default_lang: en
  languages: [en, ru]
  name: <name>
  name_ru: <name in Russian>
seo:
  title_suffix: " - <name>"
  title_suffix_ru: " - <name in Russian>"
nav:
  main: ["/", …]
analytics:
  ga4: <or GAP>
gone:
  - /wp-*
contact:
  phone: <or GAP>
```

## 5. Address migration

| Old address | What it was | Decision | Key | en | ru | Type |
|---|---|---|---|---|---|---|
| `/old-address/` | service | 301 | `services/design` | `/services/design/` | `/ru/uslugi/dizajn/` | `service` |
| `/category/news/page/2/` | pagination | 410 (`gone`) | - | - | - | - |

## 6. Relations

| Field | From → to | Reverse | Required |
|---|---|---|---|
| `related` | service → service | `related_from` | no |

## 7. What is not in pages

Where contacts, reviews, figures, company details live: `site.yaml` (`contact`, `organization`), `data/<file>.yaml`.

## 8. Questions for the client

1. <question> - options: …, recommendation: …

## 9. Engine tasks

Only what is not in `roles/capabilities.md`. The form is in `roles/architect.md`, "Engine task". If there are no tasks, say so.
