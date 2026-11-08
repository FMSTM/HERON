# theme - how the site looks

Templates, styles, script, interface strings and the site's own chrome. A
theme is portable between sites: it knows how to render a section with a given
anchor, but not what that section says.

## Belongs here

- `templates/` - one template per page type;
- `partials/`, `base.html` - shared markup;
- `modules/` - one module per section form;
- `assets/` - styles, script, logo, icons, fonts;
- `i18n/<lang>.yaml` - interface strings: buttons, labels, block headings;
- `theme.yaml` - the passport and the contract: page types and their sections,
  the fields of every block, section views and hints in every language of the
  theme. The questions of `page add`, the studio and the theme reference
  (`/_heron/theme/` in the preview) work by it. The check is
  `check . --theme`: the description is complete, the demo shows every type,
  block and view. How to write it - the guide "Your own theme" (`docs theme-author`).

Code only as files in `assets/`: the browser does not run inline `<script>` and
`onclick=` handlers (strict CSP).

## Does not belong here

- **Not a single content photograph.** A portrait, a room, a scanned
  certificate - that is content, it lives in `media/`.
- **Not a single line of text the visitor reads as the page itself.**
  Headings, paragraphs and lists come from `content/`. The theme holds
  interface wording only.
- **Data** - prices, addresses, opening hours. That lives in `data/`.
