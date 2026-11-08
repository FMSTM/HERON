A section gathers pages on one topic: services, articles, instructions. A section has its own page with text, a description for search and a list of the pages inside.

## How to make a section {#how}

1. **Create a folder.** The name of the folder becomes the address of the section: the folder `structure/` in a language folder is the address `structure/`.
2. **Put `_index.md` into it.** This is the page of the section itself: the SEO block, the intro and blocks, like on any page.
3. **Pick the look.** The line `view: list` in the front matter of `_index.md` shows the pages as rows, without it - as cards.
4. **Add pages.** Every `.md` file in the folder is a page of the section. `order` sets their order.

## How many levels {#depth}

A section can sit inside a section: `services/roofing/`. The breadcrumbs above the heading of a page show where a person is and lead one level up.
