# media - everything the content shows

Images, video, documents. A file is declared in the content - in page
frontmatter or as a link in the text - and is captioned there too.

Images are resized and converted by the engine itself: the repository holds a
single master, the variants are produced during the build. Everything else is
copied as is. Only declared files ship: whatever nothing points at stays here
and shows up in the report.

## Belongs here

- image masters - one file per subject, any aspect ratio;
- video together with its poster: without a poster the browser downloads the
  clip just to show the first frame;
- documents for the visitor: leaflets, price lists, forms in PDF;
- the photo for a page cover and the social sharing image - also here, not in `static/`.

## Cover and social image

- Use a master at least 1200 px wide. If the master is narrower, the engine
  serves it whole and `check` warns.
- The cover master always ships whole.
- Make the cover opaque. The engine does not add a backing under transparent
  areas.
- Cover not found - the page gets no `primaryImageOfPage` and no `og:image`.
  `check` warns, the build does not fail.
- If the site sets `primaryImageOfPage` or `entity.image` itself, its value
  wins.
- On `dev` pages are closed (`noindex, nofollow`), there are no images in the
  sitemap, and addresses point to the dev domain.

## Does not belong here

- **Site chrome** - logo, interface icons, fonts. That is part of the theme:
  `theme/assets/`. Simple test: the logo does not stop being the logo when
  you delete every page.
- **Files that must sit at an exact address** - webmaster verification and
  the like. Those go to `static/`.
