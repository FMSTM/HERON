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
- **Demo pages.** A sample of presentation for the topic of the theme: which pages are needed and which blocks they have. They go only where there is no page yet: your files are never overwritten. Replace the texts with your own, and delete the pages you do not need in all language folders and remove them from the menu.
- **The theme reference.** Everything the theme can do: every block with its hint, a live example and its markdown next to it, section views. In the preview - the page `/_heron/theme/`, in the studio - the «Theme reference» tab, in the terminal - `heron docs theme-ref .`.
- **Hints at the fields.** `heron page add` and the studio ask for the fields of a page with the hints of the theme, `?` opens detailed help.
- **The previous theme.** It is not deleted: it moves to `.heron-cache/setup/`.

## Your own theme {#own}

The white theme is a base for your own: change the colours at the top of `theme/assets/site.css`, place the blocks in `theme/templates/`. A theme describes itself in `theme.yaml`: page types, the fields of every block, section views and hints for whoever runs the site. Its demo must show every type, block and view - the check is `heron check . --theme`. To pack the theme with its demo for another site: `heron theme pack . --out theme.tar.gz`. How to write all this and how to move a theme from version 0.2 - the guide «Your own theme»: `heron docs theme-author`.
