The main HERON commands and where to read more. The documentation lives in the engine repository and in the image itself, the same version your site is built with.

## How to run the commands {#run}

Every command below starts with `heron` - this is how they look when the engine is installed without Docker. With Docker, write the full command instead of `heron` (`-it` for the commands that ask questions, `-p` for the preview, the configurator and the studio), for example:

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod serve .
```

## The main commands {#commands}

1. **Create a site.** Asks a few questions and creates the site folder:

   ```bash
   heron new my-site
   ```

2. **Set it up.** The configurator in the browser - open the address the engine prints, with the key after `#`: name, domains, who the site is about, publishing, theme. Run it from the site folder:

   ```bash
   cd my-site && heron setup .
   ```

3. **Look.** The site at `localhost:8000` rebuilds on every save:

   ```bash
   heron serve .
   ```

4. **Add a page and a section.** A page and a section are created in every site language at once. The engine asks for the fields with the hints of the theme: Enter keeps the value in brackets, `?` - detailed help. The same command a second time opens the page for editing:

   ```bash
   heron page add about . && heron category add services .
   ```

5. **Edit with a mouse.** The studio in the browser: the page tree, the fields with hints, translations, the theme reference. Open the address in full, with the key after `#`:

   ```bash
   heron studio .
   ```

6. **Check.** What to fill in and what to fix, without a build:

   ```bash
   heron check .
   ```

7. **Build for checking.** The dev version: closed to search engines, no counters:

   ```bash
   heron build . --env dev
   ```

8. **Build the working version.** The prod version: open to search engines, warnings count as errors. The result is the `dist/` folder:

   ```bash
   heron build . --env prod --strict
   ```

Instructions for an AI agent sit in the site root: the `AGENTS.md` file and the `agents/` folder.

## Where to read {#where}

- **In the repository.** [The guides in order](https://github.com/FMSTM/HERON/tree/prod/docs/en/guide): concepts, first site, pages, theme, search, publishing, your own theme.
- **For AI agents.** [AGENTS.md](https://github.com/FMSTM/HERON/blob/prod/AGENTS.md): roles, rules and the map of the documentation.
- **In the terminal.** Offline, the same version as the engine:

  ```bash
  heron docs
  ```
