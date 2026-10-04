# static — files at an exact address

Copied into the built site byte for byte, at the same path, with no processing
and no checks. That is its only purpose.

## Belongs here

- webmaster verification files;
- `.well-known/security.txt`;
- `ads.txt`, payment provider verification files;
- `site.webmanifest`, favicon.

## Does not belong here

- **Images, video, documents.** They live in `media/`, where they get an
  existence check, variants for every screen size and a clear error on a typo.
  Here they get none of that — they just sit.
- **Site chrome** — logo, icons, fonts. That is `theme/assets/`.

Dropping a file here is always faster than declaring it in the content. That
is exactly how this folder fills up. An empty `static/` is a normal site.
