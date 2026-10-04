# media — everything the content shows

Images, video, documents. A file is declared in the content — in page
frontmatter or as a link in the text — and is captioned there too.

Images are resized and converted by the engine itself: the repository holds a
single master, the variants are produced during the build. Everything else is
copied as is. Only declared files ship: whatever nothing points at stays here
and shows up in the report.

## Belongs here

- image masters — one file per subject, any aspect ratio;
- video together with its poster: without a poster the browser downloads the
  clip just to show the first frame;
- documents for the visitor: leaflets, price lists, forms in PDF.

## Does not belong here

- **Site chrome** — logo, interface icons, fonts. That is part of the theme:
  `theme/assets/`. Simple test: the logo does not stop being the logo when
  you delete every page.
- **Files that must sit at an exact address** — webmaster verification and
  the like. Those go to `static/`.
