# data - shared reference data

Lists, tables and details needed by many pages at once. Everything here
reaches templates as `data.<file name>`; nested folders give nested names.

## Belongs here

- opening hours, branches, extra addresses; the site's main contacts and legal
  details live in `site.yaml`, written by `heron setup`;
- repeated blocks: booking terms, disclaimers;
- any data edited separately from prose and not owned by a single page.

## Does not belong here

- **Text of one particular page.** If a visitor reads it on one page, it is
  `content/`.
- **Interface strings** - those live in `theme/i18n/`.
- **Files.** Only yaml here; an image is declared by path and stored in
  `media/`.
