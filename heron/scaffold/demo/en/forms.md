Every block below is a section of this one markdown file. HERON sees its form by how it is written, and the theme draws each form with its own module.

Open `content/en/forms.md` next to this page: the file and the page side by side are the whole manual.

## Plain text {#text}

A section without a list, a table or a quote is prose. **Bold**, *italic*, [links](/) and `code` work as usual.

## A list {#list}

- **Term first.** A bold start with a full stop makes a pair: the theme gets the term and the text apart.
- **Any length.** A list item can hold a sentence or a short paragraph.
- A plain item without a bold start is fine too.

## Warning signs {#warning .alert}

- The class `.alert` in the heading turns a list into a warning.
- Use it for what must not be missed.

## Steps {#steps}

1. **Create the site.** One command, and the folder is ready:

   ```bash
   heron new my-site -y
   ```

2. **[MOST OFTEN] Fill the questionnaire.** The tag in square brackets, in capitals, marks a step.
3. **Build.** The final build opens the site to search engines.

## Two lists {#compare}

### Fits

- A site that is text and pictures
- Pages you edit in any editor

### Does not fit

- A shop with a cart
- A forum

## Checklist {#checklist}

### Before you start

- Docker
- A text editor

### To publish

- A domain
- Git

### Later

- Analytics
- A second language

## Table {#table}

| What | Where | How often |
|---|---|---|
| Texts | `content/` | Any time |
| Photos | `media/` | When needed |
| Look | `theme/` | Rarely |

## Facts {#facts}

Short facts are lines with a bar, without a table header:

Format | markdown files
Output | a static site
Languages | as many as you need

## Timeline {#timeline .timeline}

Day 1 | Create the site and fill the questionnaire
Week 1 | Write the pages
Week 2 | Publish

## Questions {#faq}

### Is this a real page?

Yes. Every block on it is drawn by the starter theme from this file.

### Can I delete it?

Delete `forms.md` in every language folder and remove `forms` from `nav.main` in `site.yaml`.

## A quote {#quote}

> A quote becomes a callout: a short note the theme sets apart.

## Gallery {#gallery .gallery}

- ![A light square](media/demo/light.svg)
- ![A dark square](media/demo/dark.svg)

## Tabs {#tabs .tabs}

### Git {#git}

Send the changes to git, and GitHub builds the image of the site.

```bash
git push
```

### Files {#files}

Copy the `dist/` folder to any hosting.

### Image {#image}

Run the image of the site on any server with Docker.
