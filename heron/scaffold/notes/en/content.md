# content — page text

One page, one markdown file. The file path sets the page address, the type is
inherited from the folder: on a site with `default_lang: en`,
`content/en/services/design.md` becomes `/services/design/` and takes the
type declared in the section's `_index.md`. Its translation is
`content/ru/services/design.md`: `/ru/services/design/`, or its own address
if the file sets `slug`.

## Belongs here

- pages in markdown, under language folders: `content/<lang>/…`;
- `_index.md` of a section — its heading, intro and the type of its children;
- page frontmatter: title, description, relations, declared files.

## Does not belong here

- **Image and video files.** They live in `media/`; the page only declares
  them: `image: media/photo/portrait.jpg`.
- **Shared reference data** — schedules, prices, details needed by many pages
  at once. That lives in `data/`.
- **Interface strings** — "Book a visit", "Read more". That is the theme:
  `theme/i18n/<lang>.yaml`.
