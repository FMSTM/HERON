A good structure means a person finds the answer to their question in a couple of clicks, and a search engine understands what every page is about. A theme thinks such a structure through once, and its demo is a sample of how to present a niche: which pages are needed, which blocks they carry and in what order.

This page is a section: the folder `structure/` with its own page `_index.md`. The engine itself shows the pages of the folder below - as rows, because the front matter of this page has `view: list`.

## How to read the demo of a theme {#read}

- **Page types.** Every type of the theme has its own demo page: the home page, an ordinary page, a section, the 404 page.
- **Blocks.** Every block of the theme is shown on at least one demo page. Open the file next to the page in the browser and compare.
- **Section views.** The home page shows its pages as cards, this section as rows. The key `view` picks the look.

> The theme reference - every block with its hints, a live example and the source markdown side by side: `heron docs theme-ref .`, and in a draft build and in `heron serve` - the page `/_heron/theme/`.
