The theme decides how the site looks. The page texts do not depend on it: change the theme and the pages stay, only the look changes.

## How to change the theme {#change}

1. **In the configurator.** `heron setup .`, the «Theme» group: pick a theme from the catalog, paste a link to an archive or upload your own.
2. **With a command.** By name from the catalog, by link or as an archive:

   ```bash
   heron theme list && heron theme get NAME .
   ```

3. **Check it.** `heron serve .` shows the site in the new theme at `localhost:8000`.

## What comes with a theme {#what}

- **The look.** Templates, styles and fonts, into the `theme/` folder.
- **Demo pages.** Example pages of the theme: a site structure for its topic. They go only where there is no page yet: your files are never overwritten.
- **The previous theme.** It is not deleted: it moves to `.heron-cache/setup/`.

## Your own theme {#own}

The white theme is a base for your own: change the colours at the top of `theme/assets/site.css`, place the blocks in `theme/templates/`. To pack the theme with its demo pages for another site: `heron theme pack . --out theme.tar.gz`.
