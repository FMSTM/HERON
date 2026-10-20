This is the demo site of the HERON white theme. Every page is a text file in the `content/` folder: open it in any editor, change the text and save.

Replace the texts with yours, delete the pages you do not need, add new ones as a copy of any file.

## How a page is made {#how}

1. **The file header.** Between the `---` lines is the description for search engines: `title`, `description`, `h1`. It is not shown on the page, search results show it.
2. **The intro.** The text before the first heading: one or two paragraphs under the main heading.
3. **Blocks.** Every `## Heading {#anchor}` is a block. The theme puts it in place by its anchor, and the way it is written decides what it is: a list, steps, a table, questions.

## What next {#next}

- **Page blocks.** Every kind of block the theme draws is on the page [«Blocks»](/blocks/).
- **The look.** Change the theme in the configurator or with a command — [«Themes»](/themes/).
- **Help.** The main commands and where to read the documentation — [«Documentation»](/docs/).

## Questions {#faq}

### Where do I change the site name, the domain and the contacts?

In the configurator: `heron setup .`. It writes everything to `site.yaml`, which you can also edit by hand.

### How do I look at the site?

Run `heron serve .` and open `localhost:8000` in the browser. The site rebuilds on every save.

### Light and dark?

The white theme follows the system setting, and the button in the header switches it by hand.
