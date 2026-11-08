# Role: Builder

Build a site by the content structure, check it and deploy it. If the theme and the pages are not ready yet, the builder does the work of the designer ([`designer.md`](designer.md)) and of content ([`content.md`](content.md)) alone, by their checklists. Common rules - [`README.md`](../README.md).

**Input:** a document with the site structure (in the form of [`templates/structure.md`](../templates/structure.md)), sometimes texts and images.
**Output:** a site folder that builds with `build --env prod --strict` without errors; an image if needed; a report.

Commands are written as `heron <command>` - this is how they work when the engine is installed as a package (`pipx install git+https://github.com/FMSTM/HERON.git@<channel>`). With Docker it is the same as a full command without `-it`, since an agent has no terminal:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check my-site
```

The path to the site is **relative to the current folder**: the container sees only that folder. `.` if you are in the site folder.

Documentation of this engine version - `heron docs` (table of contents), `heron docs <topic>`, `heron docs --search <text>`.

## 1. Create the folder

An agent has no terminal, so `new` asks no questions - everything goes through flags:

```bash
heron new my-site --notes en --name "Site name" --domain example.com --lang en,ru -y
```

- `--lang` - languages separated by commas, the first one is the main one; `--domain` without a scheme. If you do not know the domain, do not pass it: the placeholder `<name>.example` stays, and that is a line in the report;
- `--notes ru|en` - the language of help, messages and comments in all files; `en` by default, remembered in `build.notes`;
- a folder under git (`.git`, `.gitignore`, `README`) is fine: `heron new . …`;
- the result is `site.yaml`, a theme, in each language a home page, a 404 and the demo pages `blocks.md`, `themes.md`, `docs.md`, the images `media/cover.png` and `media/demo/`, notes in the folders. The starter site builds with `--env prod --strict` without warnings. The demo pages are not in the site structure: their fate is a line in the report and a question to the human.

If a folder with content already exists - not `new` but `heron init my-site`: it adds what is missing and overwrites nothing.

## 2. Fill in `site.yaml`

The sample with all keys is [`templates/site.yaml`](../templates/site.yaml). The minimum:

```yaml
heron: ">=0.2,<0.3"
site:
  domain: example.com
  theme: main
  default_lang: en                 # from the root: /about/
  languages: [en, ru]              # Russian goes under /ru/
  name: Daybreak
  name_ru: Рассвет                 # if it differs
seo:
  title_suffix: " - Daybreak"
  title_suffix_ru: " - Рассвет"
nav:
  main: ["/", about, services, contacts]   # page keys
```

Then complete the folders for the languages:

```bash
heron init my-site           # content/<lang>/index.md and 404.md, theme/i18n/<lang>.yaml
```

What not to do: do not write an "approximate" domain, phone or analytics counters - empty is better than invented. Do not put a Dockerfile, compose or `.env` into the folder.

## 3. Theme

`types` and `links` in `theme/theme.yaml` come from the structure; a template for each type, a module for each form. How - [`designer.md`](designer.md).

## 4. Content

A file for each page of the structure; file name = key, the same in all languages. A new page - `heron page <type> <name> my-site`. How to write the SEO block and the sections - [`content.md`](content.md).

## 5. The check loop

```bash
heron check my-site                      # report without a build
heron build my-site                      # dev build into my-site/dist
heron build my-site --env prod --strict  # like production: warnings are errors
```

Read the whole report. Errors (`E0xx`) stop the build - fix them. Warnings are grouped: `images`, `relations`, `links`, `menu`, `translations`, `languages`, `content`, `dates`, `redirects`, `other`, `no translation`; the full list is `.heron-cache/warnings.txt` next to the build. The "Not filled" summary is the content debts; they go to the report.

Common errors:

| Code | What it means | What to do |
|---|---|---|
| `E002` | no `title`/`h1`/`description`, or a field of the wrong type | add it; dates are `YYYY-MM-DD` |
| `E004` | two files give the same address | different `slug` |
| `E005` | the file name or `slug` is not Latin letters, digits and hyphens | rename |
| `E006` | a relation to a page that does not exist | the file name without the extension, not an address |
| `E007` | a file from `media/` is not on disk | the path from the site root |
| `E008` | a type has no template or the theme does not know the type | an entry in the theme's `types` and `theme/templates/<type>.html` |
| `E009` | `redirect_from` matches the page address or leads to two places | remove the duplicate |
| `E011` | `site.yaml` failed validation, or the theme requires an empty key | read the message |
| `E012` | the engine is outside the `heron:` range in `site.yaml` | another image tag or range |
| `E020` | markup: no declared type, an empty address in the site-wide node, prices | `schema` in `site.yaml`; prices - `seo.allow_prices` |
| `E021` | production, and the main language is empty | fill it in or change `default_lang` |
| `E022` | `gone` closes a page or overlaps with `redirect_from` | choose one |

The full list - `21` §11 ([`spec/21-engine.md`](../spec/21-engine.md)).

## 6. What to check in the built site

- the main pages of each language open; `<head>` has `<title>` with the suffix, `canonical`, hreflang (on a multilingual site);
- `dist/sitemap.xml` lists all indexable pages (on a multilingual site through `sitemap-<lang>.xml`); 404 and `noindex` are not there;
- `dist/404.html` and `dist/<lang>/404/index.html` are in place;
- `dist/llms.txt` - a description and a list (or a table of contents of languages);
- `dist/redirects.map` and `dist/gone.map` (the second only when `gone` is not empty) - what was expected from the migration table;
- the markup (`<script type="application/ld+json">`) has the needed types; the report counts pages by type.

## 7. Deploy

The `dist/` folder goes to any static hosting, with `.heron-nginx.conf` for your own nginx. The image and the check of server responses come from a clone of the engine repository. The settings `env/.env.<site>.<environment>` are needed: `./scripts/site.sh <site> new <path>` creates them, for an existing folder - `cp env/.env.example env/.env.<site>.prod`.

```bash
./scripts/site.sh <site> build prod
./scripts/site.sh <site> image prod
./scripts/site.sh <site> smoke prod      # 200, 404, every 301 and every 410
./scripts/site.sh <site> push prod
```

A site in its own repository without a HERON clone uses the reusable workflow `FMSTM/HERON/.github/workflows/site-image.yml`: it builds, packages, checks and pushes the image; no Dockerfile of your own is needed.

In detail - the guide [06 · Build and deploy](../guide/06-deploy.md).

## 8. Report

`agents/work/report.md` in the form of [`templates/report.md`](../templates/report.md): what was done; which pages were created; which sections are not filled (the debt summary); which facts are not confirmed (questions - `agents/work/questions.md`); which warnings were left and why; mismatches between the documentation and the engine behavior, if any; check commands and their exit codes.

**Publication boundary.** Deploy (section 7) is done by the human's commands: you do not run `.heron/scripts/publish.sh`, `docker push`, `site.sh push`, `git push` or merge. Your result is a branch with the changes, green `check --strict --json` and `build --env prod --strict`, the report and the questions. You do not write code in `plugins/` without an explicit task from the human: a plugin runs during the build.

## Checklist

- [ ] `site.yaml`: `heron:`, domain, languages, name, menu; no invented facts
- [ ] every type of the structure has a template; every page has a file
- [ ] `build --env prod --strict` without errors
- [ ] the 301/410 maps match the migration table; `smoke prod` is green
- [ ] the report: debts, questions, warnings left in place
