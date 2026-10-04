# theme — how the site looks

Templates, styles, script, interface strings and the site's own chrome. A
theme is portable between sites: it knows how to render a section with a given
anchor, but not what that section says.

## Belongs here

- `templates/` — one template per page type;
- `partials/`, `base.html` — shared markup;
- `assets/` — styles, script, logo, icons, fonts;
- `i18n/<lang>.yaml` — interface strings: buttons, labels, block headings;
- `theme.yaml` — which sections the theme expects from each page type.

## Does not belong here

- **Not a single content photograph.** A portrait, a room, a scanned
  certificate — that is content, it lives in `media/`.
- **Not a single line of text the visitor reads as the page itself.**
  Headings, paragraphs and lists come from `content/`. The theme holds
  interface wording only.
- **Data** — prices, addresses, opening hours. That lives in `data/`.
