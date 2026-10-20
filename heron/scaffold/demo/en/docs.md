The main HERON commands and where to read more. The documentation lives in the engine repository and in the image itself, the same version your site is built with.

## How to run the commands {#run}

Every command below starts with `heron`, a short name for running the HERON image in Docker. How to set it up is in «Get started» of the documentation. Without the short name, write the full command instead of `heron`, for example:

```bash
docker run --rm -it -p 8000:8000 -v "$PWD":/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod serve .
```

## The main commands {#commands}

1. **Create a site.** Asks a few questions and creates the site folder:

   ```bash
   heron new my-site
   ```

2. **Set it up.** A questionnaire in the browser at `localhost:8000`: name, domains, who the site is about, publishing, theme. Run it from the site folder:

   ```bash
   cd my-site && heron setup .
   ```

3. **Look.** The site at `localhost:8000` rebuilds on every save:

   ```bash
   heron serve .
   ```

4. **Check.** What to fill in and what to fix, without a build:

   ```bash
   heron check .
   ```

5. **Build for checking.** The dev version: closed to search engines, no counters:

   ```bash
   heron build . --env dev
   ```

6. **Build the working version.** The prod version: open to search engines, warnings count as errors. The result is the `dist/` folder:

   ```bash
   heron build . --env prod --strict
   ```

## Where to read {#where}

- **In the repository.** [The guides in order](https://github.com/FMSTM/HERON/tree/beta/docs/guide): concepts, first site, pages, theme, search, publishing.
- **For AI agents.** [AGENTS.md](https://github.com/FMSTM/HERON/blob/beta/AGENTS.md): roles, rules and the map of the documentation.
- **In the terminal.** Offline, the same version as the engine:

  ```bash
  heron docs
  ```
