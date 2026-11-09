# 07 · Your own theme: contract, hints, demo

This section is for the author of a theme: a designer, a front-end developer or an AI agent who makes a theme not for one site but for many. Here is how to describe in `theme.yaml` what the pages of the theme consist of, how to write hints for a person with no experience, how to make the demo, check the theme and pack it. How the templates, modules and styles themselves work is in [04 · Theme and design](04-theme.md). The theme is already made on version 0.2 - go straight to [Moving a theme from 0.2 to 0.3](#migrate-0-3).

> **The commands in this section are written for Docker** and run from the folder of the site you make the theme on (`cd ~/sites/my-theme`), so the path to the site in them is a dot. Installed the engine without Docker - replace everything up to and including the image name (`ghcr.io/fmstm/heron:…`) with the word `heron` ([more](00-install.md#without-docker)).

## What a theme tells about itself <a id="what-a-theme-says"></a>

Templates and styles tell the engine how a page looks. But whoever runs a site on your theme does not read templates. To manage on their own, they need the theme to tell three more things about itself:

- **the contract** - which page types it can show, which blocks it expects on each of them and which fields every block consists of. It is written in `theme.yaml`;
- **the hints** - what to write in every field, how it affects the site and search, a good example and common mistakes. Also in `theme.yaml`, in every language of the theme;
- **the demo** - pages that show everything the theme can do. It is the content of the site the theme is packed from.

From these three parts the engine builds everything else itself: the questions of the `page add` and `category add` commands, the forms of the studio in the browser, the theme reference, the description for an agent (`describe --json`) and the `check`. There is nothing to write separately for any of them: change `theme.yaml` - and it changes everywhere.

## Where to start <a id="start"></a>

A theme is made inside an ordinary site: the `theme/` folder is the theme itself, and the pages in `content/` become its demo. So the first step is a site:

```bash
mkdir -p ~/sites && cd ~/sites
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod new my-theme
cd my-theme
```

Choose the site languages the demo pages will be in, for example `en, ru`. A new site already has the starter theme - white, fully described, with a demo. Then there are two ways:

- **from a copy of the starter** - the simplest, and it fits almost always. Change the styles (the variables at the top of `assets/site.css`), the templates and modules, add your own page types. The contract and the demo are already there - you only need to keep them up to date along with the theme;
- **from scratch** - empty `theme/` and put your own files. The minimum that builds: `theme.yaml`, `base.html`, a template for every type in `templates/` (`home.html`, `page.html`, `404.html`) and the modules the templates call.

Either way, keep the preview running - it rebuilds the site after every save - and open <http://localhost:8000>:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod serve .
```

## The passport: `theme.yaml` <a id="passport"></a>

At the top of `theme.yaml` there are details of the theme itself:

```yaml
name: workshop                 # the theme name in Latin letters: it lives under it in an archive and the catalog
title: Workshop                # the name for people
version: "1.0"                 # the version of your theme
heron: ">=0.3"                 # which engine versions the theme works with; a wrong one - E012
languages: [ru, en]            # which languages the hints of the theme are written in
requires: [contact.phone]      # what the theme takes from site.yaml; not filled in - E011
images:
  ratios: ["1:1", "16:9"]      # the proportions templates may ask for
```

Below come two big parts: `types` (page types) and `modules` (blocks). More on them next. The other keys of the passport (`links`, `forms`, `images` in full) are described in [04 · Theme and design](04-theme.md) and in [`20` §6](../spec/20-data-contract.md#theme-yaml).

## Page types <a id="types"></a>

A page type is a kind of page with its own template and its own set of blocks: the home page, a service, an article, contacts. Every type is drawn by the file `templates/<type>.html`. An example of the type "service" in full:

```yaml
types:
  service:
    uses: [intro, "includes:list", "how:steps", "faq:faq"]
    jsonld: [Service]
    hint_ru: Услуга - что входит, как проходит работа, вопросы
    hint_en: A service - what is included, how the work goes, questions
    help_ru: Одна страница - одна услуга; в поиске она отвечает на запрос «услуга + город»
    help_en: One page - one service; in search it answers the query "service + city"
    sections:
      intro:
        required: true
        hint_ru: Вводный абзац - кому нужна услуга и что человек получит
        hint_en: The intro paragraph - who needs the service and what they get
        fields:
          - {name: text, type: markdown, required: true, md: body, hint_ru: Один-два абзаца о пользе, hint_en: One or two paragraphs about the benefit}
      includes:
        required: true
        hint_ru: Что входит в услугу - список с жирным зачином
        hint_en: What the service includes - a list with a bold start
      how: {hint_ru: Как проходит работа - нумерованные шаги, hint_en: How the work goes - numbered steps}
      faq: {hint_ru: "Вопросы о цене, сроках и гарантии", hint_en: "Questions about price, time and warranty"}
```

What is what here:

- **`uses`** - the sections of a page of this type in order. It is the agreement with the content: `page add` puts stubs of exactly these sections into a new page and asks for them in this order. After the colon - the form the theme expects from the section: `"how:steps"` - numbered steps. `"*"` - "any blocks": a person may add a section of any form. All forms - [`20` §4.4](../spec/20-data-contract.md#section-forms);
- **`jsonld`** - the schema.org markup of pages of this type: `Service`, `Article`, `FAQPage`. A person fills in its fields in the "Markup" group;
- **`sections.<anchor>`** - the description of a section from `uses`: `required` (whether it is mandatory), the hints and, when the section has no form of its own, its fields (`fields`). This is how `intro` is described - the intro block before the first `##` heading. A section that is not in `uses` is an `E041` error. The entry `"*"` in `sections` is the hint to "any blocks";
- **`template`** - when the type is drawn not by the file `templates/<type>.html` but by another one.

### Categories: `children_type` and `views` <a id="views"></a>

A category (section) is a folder with its own page `_index.md`: "Services", "Articles". When a page of your type can be a category, tell the engine two things:

```yaml
types:
  page:
    uses: [intro, "*"]
    hint_ru: Обычная страница
    hint_en: An ordinary page
    children_type: service       # the type of the pages inside a category of this type
    views:                       # how a category shows its pages
      key: view                  # the line view: list in the front matter of _index.md
      default: cards             # the view when the line is absent
      hint_ru: Как категория показывает свои страницы
      hint_en: How a category shows its pages
      options:
        cards: {hint_ru: Карточки сеткой - для разделов на 3-12 страниц, hint_en: Cards in a grid - for sections of 3-12 pages}
        list: {hint_ru: Список строками - для длинных разделов, hint_en: A list of rows - for long sections}
```

- **`children_type`** - the type of the pages inside such a category. `category add` writes it into the `_index.md` of a new category, and `page add --category services` picks this type for a new page by itself;
- **`views`** - the looks a category shows its pages in. You make up the list - exactly the views your templates draw: cards, a list, a table, tiles. The engine only checks that `default` is among the `options`. A person picks the view with a question of `category add`, the `--view` flag or in the studio, and the line `view: list` goes into the file.

The template reads the view itself. In the starter theme the `children` module does this:

```jinja
<ul class="{{ 'rows' if page.meta.get('view') == 'list' else 'cards' }}">
```

### Modules: blocks and their fields <a id="modules"></a>

A module is the file `modules/<name>.html` that draws one block. In `theme.yaml` modules can simply be listed, as in 0.2: `modules: [prose, list, faq]`. But then the engine does not know what the block consists of, and there is nothing to hint to a person. So a module is described:

```yaml
modules:
  faq:
    scope: section               # section - draws a section, page - takes data from the page
    kinds: [faq]                 # which section forms the module draws
    schemaorg: FAQPage           # the markup the block gives
    hint_ru: Вопросы и ответы - вопрос заголовком, ответ под ним
    hint_en: Questions and answers - the question as a heading, the answer under it
    help_ru: Вопрос - заголовок третьего уровня, ответ - текст под ним; в поиске блок размечается как FAQPage
    help_en: A question is a third-level heading, the answer is the text under it; in search it is marked up as FAQPage
    fields:
      - name: items
        type: list
        required: true
        md: groups               # ### groups in markdown
        hint_ru: Пары вопрос - ответ
        hint_en: Question - answer pairs
        fields:
          - {name: q, type: text, required: true, md: heading, max_length: 120, schemaorg: Question.name, hint_ru: Вопрос, hint_en: The question}
          - {name: a, type: markdown, required: true, md: content, schemaorg: Answer.text, hint_ru: Ответ, hint_en: The answer}
  breadcrumbs:
    scope: page
    schemaorg: BreadcrumbList
    fields: []                   # nothing to fill in: the crumbs are built by themselves
    hint_ru: Хлебные крошки - путь от главной до страницы
    hint_en: Breadcrumbs - the path from the home page to the page
```

- **`scope`** - `section` (the default): the module draws a section and is called as `mod.faq('faq')`; `page`: the module takes data from the page and the site (`mod.breadcrumbs()`, `mod.children()`), it has no fields - write `fields: []`;
- **`kinds`** - the section forms the module draws: one module may draw several similar forms, as `list` in the starter theme draws both `list` and `alert-list`. Not set - the form named after the module;
- **`schemaorg`** - the markup type the block gives;
- **`fields`** - the fields of the block, below;
- **`example_<lang>`** - a markdown sample of the block. `describe <name>` and the theme reference show it when the block is not on the demo pages.

### Fields <a id="fields"></a>

A field describes one value a person writes into a block. The main rule: **a field describes real markdown**, not a data model you made up. The `md` key tells where the value lies in the file: `heading` - the text of a `###` heading, `content` - everything under it, `items` - the `- …` items of a list, `bold` - the bold start of an item, `body` - all the content of a section, `first-paragraph` - the first paragraph of the intro block. By this place the console and the studio find the value in the file and write it back - to the same place, without touching anything else. The whole dictionary of places - [`21` "The theme contract"](../spec/21-engine.md#theme-contract).

| Key | What it is |
|---|---|
| `name` | the field name: lowercase Latin letters, digits and `_`, starting with a letter |
| `type` | `text` - a line, `markdown` - text with markup, `list` - a list, `image` - a picture from `media/`, `link` - a link, `number` - a number, `date` - a date YYYY-MM-DD, `enum` - a choice from a list, `ref` - another page of the site, `flag` - yes or no |
| `required` | whether it is mandatory: an empty field is an error, nothing is written - the console asks again, the studio does not save, `--answers` stops with `E039`. The intro block does not vanish silently if its required text is erased |
| `md` | where the value lies in markdown - a place from the dictionary |
| `min_length`, `max_length` | the length of the text in characters |
| `min_items`, `max_items` | how many items a list has |
| `ratio`, `min_width` | for a picture: the proportion (`"16:9"`) and the smallest width in pixels |
| `values` | for `enum`: the allowed values, mandatory |
| `ref` | for `ref`: which page type the field points to |
| `schemaorg` | the markup property the value goes to: `Question.name` |
| `item` or `fields` | for a list: the type of every item or the fields of every item - one of the two |

For example, the gallery of the starter theme is a list of pictures, each with a file and a caption:

```yaml
    fields:
      - name: items
        type: list
        required: true
        min_items: 1
        md: items
        hint_ru: Картинки галереи
        hint_en: The pictures of the gallery
        fields:
          - {name: image, type: image, required: true, md: image, min_width: 800, schemaorg: ImageObject.contentUrl, hint_ru: Файл картинки в media/, hint_en: The picture file in media/}
          - {name: alt, type: text, required: true, md: alt, max_length: 125, schemaorg: ImageObject.caption, hint_ru: Подпись - что на картинке, hint_en: The caption - what is in the picture}
```

The limits are checked at once, right at the field. An error - an empty required field or item, a value not from `values`, a picture not from `media/` or without a file: the console asks again, the studio does not save, `check` names the file. A warning - length and number of items out of bounds, a picture narrower than `min_width` or of another proportion: the answer is written, the warning stays in the report.

**Service fields are not yours to write.** `title`, `h1`, `description`, the address (`slug`), the category, the menu, the cover, the picture for social networks, `noindex`, the "translation not ready" mark, the heading and the anchor of every block are described by the engine itself - the same for all themes, with hints in ru and en.

### Own fields of a page <a id="own-fields"></a>

Sometimes a template needs a value that is in no block: the status of a case, the figures of the result, an eyebrow above the `h1`. Such a value is written right into the SEO block of the page, and the theme describes it on the type - with the key `fields`. The description is the same as for a block field, only without `md`: the value lives in the front matter under the field name. An example - the type "case" with a list of figures and a status:

```yaml
types:
  case:
    uses: [intro, "*"]
    hint_ru: Кейс - задача, что сделали, результат
    hint_en: A case - the task, what was done, the result
    fields:
      - name: status
        type: enum
        values: [done, in-progress]
        required: true
        hint_ru: Статус работы - готово или ещё идёт
        hint_en: The status of the work - done or still going
      - name: metrics
        type: list
        item: text
        max_items: 4
        hint_ru: Цифры результата - по одной на пункт, например «+40% заявок»
        hint_en: The figures of the result - one per item, such as "+40% requests"
```

In the page file these are two lines of the SEO block, and the template reads them via `page.meta.get(…)`:

```yaml
status: done
metrics: ["+40% requests", "3 weeks"]
```

```jinja
{% for item in page.meta.get('metrics') or [] %}<li>{{ item }}</li>{% endfor %}
```

What the engine does with them:

- `page add` and the studio show them as the group "Theme fields" with your hints: an `enum` as a choice from `values`, a list one item per line. A new page gets a required field filled at once (the first of `values`, the example or the marker `TODO`), an optional one - as a stub `# metrics:` with the hint;
- `check` and the build: a required one empty, a value not from `values` or of the wrong type - error `E042`; length and number of items out of bounds - a warning;
- translations: the fields with text (`text`, `markdown`, `list`, `link`) are translated in other languages like the headings; the rest (`enum`, `number`, `flag`, `date`, `ref`, `image`) are one for all languages - an edit in the main language writes the same value into every file of the page. Need an own value in every language (a picture with text, an own figure for a market) - add `translatable: true` to the field: a language with its own value shows it, without one - the value of the main language, like the cover `image`; a new language copy does not copy the field. On a text field the flag changes nothing - `check` warns;
- `describe`, the theme reference and an agent (`describe --json`) show them at the type.

The name of an own field does not coincide with an engine field (`title`, `slug`, `order`, `image`, `translation`, `view` and the others from `describe`) - otherwise `E041`. And do not confuse it with the **top-level** key `fields` of `theme.yaml`: that one is a list of names of engine fields your templates read (`fields: [date, updated]`); own fields are not described there (`E023`).

## Hints: for a person with no experience <a id="hints"></a>

Whoever runs a site on your theme often sees HERON, markdown and the word "snippet" for the first time. The hints are the only thing between them and an empty field. They are seen in four places: in the console at every question of `page add`, in the studio when hovering over a field and by the `?` button, in the theme reference and in the output of `describe` - an AI agent reads it too.

- **`hint`** - one line seen at once: what the field is. "The question", "The first paragraph - the main benefit in one or two sentences".
- **`help`** - detailed help by `?`: what it is, what it affects on the site and in search, a good example, common mistakes. Several lines - handy as a `|-` block.
- **`example`** - for a module: a markdown sample one can copy.

Hints are written in every language of the theme with the language suffix: `hint_ru`, `hint_en`, `help_uk`. A key without a suffix (`hint`) is for the languages that have no text of their own. The languages of the theme are the `languages` list. `hint` is mandatory for every type, section from `sections`, module from the description, field and view: when even one is missing, `check` stops with `E041` and lists the paths, for example `types.service.sections.how (en)`.

How to write them well:

- write in the words of the one who runs the site, not the one who made the theme: "What the service includes", not "items of the list block";
- `help` has four parts: what it is; what a visitor sees and what a search engine understands; an example of good filling; common mistakes;
- name the limits plainly: "up to 60 characters", "a picture at least 1200 px wide", "three to five items";
- a good sample is `theme.yaml` of the starter theme: `help` of every one of its blocks is written exactly like that.

## The whole description: `describe` <a id="describe"></a>

To see what you got, use the `describe` command. Without a name it briefly shows the whole description together with the service fields of the engine and the default values from `site.yaml`. With the name of a type or a block - that one alone with detailed help and a markdown sample. With `--json` - the same as one object for an agent and programs:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod describe
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod describe service
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod describe --json --lang en
```

`--lang` picks the language of the hints. The form of the `--json` output - [`21` §10](../spec/21-engine.md#heron-describe).

## The theme demo <a id="demo"></a>

The demo is not a decoration but a sample of presentation: which pages a site of this kind needs, which blocks they have and in what order. You think this structure through once, and whoever installs the theme gets it ready and replaces the texts with their own. That is why every theme must have a demo, and it shows everything `theme.yaml` declares:

- **every page type** - at least one page of this type from a file: the home page (`index.md`), an ordinary page, 404 (`404.md`) and every type of yours;
- **every block** - the module drew something at least once on some page, the page modules (`breadcrumbs`, `children`) included;
- **every category view** - a category page with pages inside that has `view: <view>`; the default view - on a category without this line.

**Where the demo lives.** It is the ordinary content of the site you make the theme on: `content/<lang>/…`, pictures in `media/`, reference data in `data/`. When packing, all of it goes into the archive next to the theme, and `theme get` puts the demo pages into the site the theme is installed to - only where there is no page yet. For a language the demo has no pages in, the site gets the pages of the main language.

**How the demo is checked.** The engine really builds the pages with the theme templates and records which module drew what. What is missing it names as a list - the `E037` error:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check . --theme
```

```
E037 theme/theme.yaml: the demo of theme workshop does not show everything theme.yaml declares (1 gap):
    type service: no demo page at all
```

The ordinary `check .` does not require the demo: on their own site a person may delete the demo pages they do not need. For a theme without a description of fields an incomplete demo is only a warning.

**How to write a good demo.** Write plausible texts of your niche, not "Lorem ipsum": from them a person understands what to write where. Let a page explain itself - like "Blocks" of the starter theme: next to a block, one phrase on what it is for. The demo is in every language the hints are written in.

## The theme reference <a id="theme-ref"></a>

The theme reference is built from `theme.yaml` and the demo by itself, nobody writes it by hand: page types with their sections, every block with its hint and fields, next to it a live example from the demo and its source markdown, category views with the line that turns them on, the schema.org markup, style variables and interface strings. Change the contract or the demo - and the reference changes too.

- in the preview and a draft build - the page `/_heron/theme/` (in the other site languages - `/_heron/theme/<lang>/`), with live examples in the theme styles. It does not get into the production build, the sitemap or search;
- in the studio - the "Theme reference" tab;
- in the terminal - as text, the examples there are the source markdown and the file it lies in:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod docs theme-ref .
```

Read the reference with the eyes of a newcomer: is it clear from the hints what to write in every field? If not - add to `help`.

## Strict CSP <a id="csp"></a>

A HERON site is served with the browser security rule `script-src 'self'`. A theme has to live by it - the rules and how to rework an old theme are in [04 · Theme and design](04-theme.md#strict-csp). In short: no scripts right in the HTML and no `onclick=` handlers - only files from `assets/`; fonts, pictures and scripts come from your own site, not from other servers.

## How to include theme files: `asset()` <a id="asset"></a>

Styles, scripts, fonts and pictures of the theme go through `asset('site.css')`, not `/assets/site.css`: the address gets the content hash in the name, after a theme update the browser does not keep yesterday's file, and a typo in the name is build error `E045`. Links inside `.css` (`url(…)`, `@import`) the engine rewrites itself. Inside `.js` it does not: pass an address for a script from the template in a `data-*` attribute with the value `{{ asset('…') }}`. Details and examples - [04 · Theme and design](04-theme.md#asset).

## Checking <a id="check"></a>

After every step:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check . --theme
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build . --env prod --strict
```

- `check --theme` - the theme description is complete (`E041` - something is missing or wrong), every type has a template (`E008`), the demo shows everything (`E037`), templates do not change data (`E033`), there are no inline scripts and no hand-written `/assets/` addresses (warnings, [`asset()`](#asset));
- `build --env prod --strict` - every page is drawn without errors and warnings.

## Packing and publishing <a id="pack"></a>

A finished theme is packed into an archive together with the demo:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme pack . --out theme.tar.gz
```

Before writing, `theme pack` makes the same demo check as `check --theme`: the demo is incomplete - `E037`, and there is no archive. The archive holds `heron-theme.yaml` (the theme name and the engine versions it is compatible with), the `theme/` folder and the `demo/` folder - the pages from `content/`, the pictures from `media/`, the reference data from `data/`. There can be no code in the archive: `.py`, `.sh`, `.exe` files, `plugins` and `.git` folders, links to other files - `theme get` will not install such an archive (`E032`).

How to hand the theme over:

- **as a file** - send `theme.tar.gz`, it is installed with the command `theme get ./theme.tar.gz .`;
- **as a link** - put the archive online over https: `theme get https://example.com/theme.tar.gz .`. Add `#sha256=<archive hash>` to the end of the link - the engine checks that it downloaded exactly your file;
- **into the catalog** - for the theme to be installed by name (`theme get workshop .`), it is added to the theme catalog - the `catalog.json` file of the [FMSTM/heron-themes](https://github.com/FMSTM/heron-themes) repository: the name, the title, the description, the https address of the archive and its sha256. Propose the entry there with an ordinary change request (pull request).

The hash of the archive is printed by the command `sha256sum theme.tar.gz` (on macOS - `shasum -a 256 theme.tar.gz`). Installing a theme from a file and from a link - the commands in full (they run in the folder of the site the theme is installed to):

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme get ./theme.tar.gz .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme get "https://example.com/theme.tar.gz#sha256=<hash>" .
```

## A worked example: the type "service" <a id="example"></a>

Let us add the type `service` with fields, hints and a demo to a copy of the starter theme - from the start to the archive.

1. **The contract.** Add the type `service` from the example in [Page types](#types) to `types` of the file `theme/theme.yaml`. The `list`, `steps` and `faq` blocks are already described in the starter theme, their fields need no rewriting.
2. **The template.** Copy `theme/templates/page.html` to `theme/templates/service.html` and put the blocks in their places: `{{ mod.list('includes') }}`, `{{ mod.steps('how') }}`, `{{ mod.faq('faq') }}`.
3. **Checking the description.** `describe service` shows the type with your hints, and `check .` names a hint missing in some language.
4. **The demo: a category and a page.** Create the services section and one service in it - in every site language at once:

```bash
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod category add services . --children-type service
docker run --rm -it -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod page add roofing . --category services
```

5. **The demo texts.** The engine asks about the fields of the type - with your hints. The sections of the new page already stand in the form the theme expects (`includes` - a list, `how` - steps, `faq` - questions), with the sample from `example_<lang>` of the modules, and the section headings are the marker `TODO heading`. So you can press Enter at every question: `check .` passes, and the production build reminds you with error `E040` that the page is not finished. Lists are asked one item per line, items with fields - after `+`, field by field. Write a plausible service: an intro paragraph, three to five items "what is included", the steps, two or three questions. Translate into the other languages - otherwise the page gets the `translation: pending` mark. Add the `services` item to the menu (`nav.main` in `site.yaml`).
6. **Checking the demo.** `check . --theme` no longer says "type service: no demo page at all". Open `localhost:8000/_heron/theme/` - the `service` type is in the reference.
7. **Packing.** `theme pack . --out theme.tar.gz` - the archive is ready.

The commands of steps 3, 6 and 7 in full:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod describe service
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check . --theme
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme pack . --out theme.tar.gz
```

## Moving a theme from 0.2 to 0.3 <a id="migrate-0-3"></a>

This section can be read apart from the rest. It is for someone who has already made a theme on engine 0.2 and moves it to 0.3. A 0.2 theme still builds on engine 0.3, but `check` warns "no description of fields", `page add` and the studio show a person only the SEO block, without the fields of the blocks and the hints, and the theme reference is almost empty. For the theme to work at full strength, go through the list.

1. **Update the engine and check its version** - the first two commands at the end of the section. The version must be `0.3` or newer. If `--version` shows `0.2` both for the `:prod` and the `:beta` image (write `beta` instead of `prod` in the command), release 0.3 is not published yet - wait for it. Move the theme together with switching to engine 0.3, not in advance: engine 0.2 does not know the contract keys (`hint_*`, `help_*`, `sections`, `views`, `children_type`, `fields` of modules and types) and refuses to build such a theme ("the contract has no such field"), so a theme with the 0.3 description does not build on engine 0.2.
2. **Raise the engine version in `theme.yaml`:** `heron: ">=0.3"`. If it said `">=0.2,<0.3"`, engine 0.3 does not build the theme (`E012`). Raise the `version` of your theme too.
3. **Name the hint languages:** `languages: [ru, en]` - the ones you will write the hints in.
4. **Describe every type.** Every type in `types` has `hint_<lang>` in every language and `help_<lang>`; every section from `uses` that a person fills in has an entry in `sections` with `required` and a hint; `intro` and other sections without a form have `fields` ([Page types](#types)). If templates read own keys from the page (`page.meta.get('status')`, `page.meta.eyebrow`), describe them in `fields` of the type - then `page add` and the studio ask them with hints, and `check` checks them ([Own fields of a page](#own-fields)).
5. **Describe every module.** Turn the list `modules: [prose, list, …]` into a description: a module has `scope`, `kinds`, `schemaorg` (when the block gives markup), the hints, `example_<lang>` and `fields` with the `md` place for every field ([Modules](#modules), [Fields](#fields)). The page modules (`breadcrumbs`, `children`) have `scope: page` and `fields: []`. Do not mix them up: the top-level `fields` key of `theme.yaml` is about engine fields, not blocks; your own fields do not go there (`E023`).
6. **Categories.** When a type can be a category - `children_type` and `views` with the views your templates draw; the template reads the view from `page.meta.get('view')` ([Categories](#views)).
7. **The demo.** In `content/` of the theme site - at least one page of every type (`404.md` as a file included), every block at least once and every category view on a category with pages inside ([The theme demo](#demo)). A module no page draws - remove it from `modules` or show it in the demo. Pages are easy to create with the `category add` and `page add` commands - they put files in every site language at once.
8. **Old commands in texts.** If the demo or the docs of the theme advise `page <type> <key>` or `--folder`, replace them with `page add <key> --type <type> --category <path>`: the old form is removed in 0.3 (`E038`).
9. **Strict CSP.** No inline `<script>` with code and no `onclick=`, `onload=` handlers in templates - code goes to `assets/*.js`, data goes in `data-*` attributes; fonts, pictures and scripts come from `assets/`, not from other servers ([Strict CSP](04-theme.md#strict-csp)); theme files in templates go through `asset('…')` instead of `/assets/…` ([How to include theme files](#asset)).
10. **Check and pack.** `check . --theme` - not a single `E008`, `E041` or `E037`; `describe` - the whole description is in place; `localhost:8000/_heron/theme/` in the preview - the reference reads as instructions for a newcomer; `build . --env prod --strict` - no errors; `theme pack . --out theme.tar.gz` - the archive is ready.

The commands of the list in full, in order:

```bash
docker pull ghcr.io/fmstm/heron:prod
docker run --rm ghcr.io/fmstm/heron:prod --version
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod check . --theme
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod describe
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod serve .
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build . --env prod --strict
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod theme pack . --out theme.tar.gz
```

A sample of a fully described theme is the starter: its `theme.yaml` lies in `theme/` of any new site (`new`), and all keys of the contract are in [`21` "The theme contract"](../spec/21-engine.md#theme-contract).

---

Next: [04 · Theme and design](04-theme.md) · [03 · Pages and content](03-content.md)
