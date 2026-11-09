# HERON - site deployment

**Status:** in force for engine 0.1; section 2 describes running without a site image, section 8 describes what is not implemented. The revision history is in the CHANGELOG and git.
**Document 3 of 4.** Previous: `20-data-contract.md`, `21-engine.md`. Next: `23-distribution.md`.

The deploy paths that work: the site image via `scripts/site.sh <site> image|smoke|push <environment>` in the engine repository (`23-distribution.md` §5) and the reusable workflow `site-image.yml` in the site repository (section 4). Then the image runs like any nginx container. A ready `dist/` folder works too: any nginx serves it with the config `dist/.heron-nginx.conf`.

---

## 1. What we deploy

One site is one folder and one repository. It holds the content, data, images, theme and config. **There is no engine code in it**: the engine comes as the image `ghcr.io/<owner>/heron:<version>`.

Two consequences follow, and they shape the whole deploy:

- updating the engine is a change of the image at build time, not a merge of someone else's code into the site repository;
- rolling the engine back is returning to the previous image.

`site.yaml` declares a requirement for the engine; the engine checks itself against it and stops with `E012`. Which image builds the site is chosen by whoever runs the build: the `engine` input of `site-image.yml`, `ENGINE` of `scripts/site.sh`. Without `ENGINE` the script takes the exact version from `site.yaml` if it is written as X.Y.Z, otherwise the sources next to the script, otherwise `ghcr.io/fmstm/heron:prod`. A range does not count as a version. Updating and rolling back is changing this value.

## 2. Containers

Two, both light. A third one (`relay`) appears only on sites with forms.

**Builder** - the engine image. It runs once, builds the site into `dist/` and exits. Between builds it does not run and uses no resources. You do not build it on the target machine: it is pulled from the registry.

**Web** - nginx serving `dist/`. The only process that runs all the time. The image is `nginxinc/nginx-unprivileged`: the master process does not run as root and listens on 8080; a proxy faces the outside.

There is no database. There is no application. Serving static files is the only thing the site does in production.

A variant without the site image. This file lives on the server separately from the site repository: a Dockerfile, compose and `.env` inside the site folder are forbidden (`20` §1). The path to the site is set in `volumes`.

```yaml
services:
  build:
    image: ghcr.io/OWNER/heron:0.1.0
    profiles: ["build"]              # does not start together with web
    user: "${UID}:${GID}"
    network_mode: "none"             # the build needs no network
    read_only: true
    tmpfs: ["/tmp"]
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges:true"]
    volumes:
      - /srv/site:/site             # path to the site on the server
    command: ["build", "--strict"]

  web:
    # the same digest as in Dockerfile.site
    image: nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:782bb89768cc87b7f95c18b95baa1af250e5d451f26794f59363540161147c01
    restart: unless-stopped
    volumes:
      - /srv/site/dist:/usr/share/nginx/html:ro
      # the engine builds the config: languages, 404, the 301 and 410 maps are already inside
      - /srv/site/dist/.heron-nginx.conf:/etc/nginx/conf.d/default.conf:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8080/healthz"]
      interval: 30s
      timeout: 3s
      retries: 3
```

Run the build: `UID=$(id -u) GID=$(id -g) docker compose --profile build run --rm build`.

`dist/` is mounted into nginx read-only. The builder writes there, the web container only reads.

`.env` is not mounted into the builder: the build has no secrets and runs without a network. The security model is covered in `23-distribution.md`, section 9.

## 3. What is on the server

The server gets either the site image (`23-distribution.md` §5) or a ready `dist/` folder. The delivery has no install and deploy scripts, no `deploy.conf` and no `.env`: a static site has no secrets, and what appears with relay is described in section 8. Atomic swap of the build directory is an idea for the future, see section 8.

## 4. CI

The reusable workflow `site-image.yml` performs: the build (`--strict` for `prod`), `nginx -t` on a stock nginx, the image build, a smoke check of response codes including `redirects.map` and `gone.map` (every old URL answers 301 or 410), and the push to the registry. `heron check --strict`, Lighthouse and the deploy to the server are added by the site itself as separate jobs: the engine ships no ready steps for them.

The smoke check of the redirect map is not a formality. It is the only thing that protects the index when migrating from an old system.

The tests of the engine itself run in the CI of the **engine repository**, not the site: the site consumes a ready image and does not have to know how it was built.

**What does not get into the site image.** The image context is the built `dist/`, so the site sources are physically absent from it: no `.git`, no image masters, no agent kit (`agents/`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` - `20` §1). There is no need to check this separately in the site CI: it is a property of the build, pinned by the engine tests.

**The step before the build.** The reusable workflow `site-image.yml` takes an optional input `export_docs` (`true`/`false`, default `false`) - an allowlist, not an arbitrary command: with `true`, **with the same engine image**, in the repository working copy before the build, while the folder is not yet mounted read-only, it runs `heron docs --export static/agents --all-langs`, `heron schema --export static/schema/<major.minor> --lang en` and `heron schema --export static/schema/<major.minor>/ru --lang ru` (the version comes from `heron --version` of the same image) and `heron docs agents > static/AGENTS.md`. This is how the engine site publishes the raw documentation files (`23` §12). The run policy is the same: no network, no capabilities, not as root, the container root read-only. Only the site's `static/` folder is mounted for writing (inside the container it is `/out`), not the site folder and not the whole working copy: with `path: "."` that would be the checkout root together with `.git` and `.heron/` (the recipe and the smoke check the image build then follows). A symbolic link in place of `static/` or `static/AGENTS.md` is a step error: the mount and the output redirection would follow it outside the site folder. Nothing is added to the image except what later gets into `dist/` through the normal build.

`site-image.yml` already fetches the whole repository history (`fetch-depth: 0`); the advice about history below is needed only for the site's own workflow.

Inputs of the `site-image.yml` workflow (one output - `image`, the full image name with the tag):

| Input | Default | What it does |
|---|---|---|
| `env` | `dev` | build environment |
| `engine` | `prod` | engine tag `prod`, `beta`, `dev`, `X.Y.Z`; `@sha256:<digest>` is allowed |
| `path` | `.` | site folder inside the repository, without `..` |
| `image` | `ghcr.io/<owner>/<repository>` | site image name |
| `tag` | the environment name | image tag |
| `strict` | `auto` | `auto` - strict for `prod`; `true` / `false` |
| `nginx_image` | stock `nginx:1.30.6-alpine` by digest | `nginx -t` runs on it before the image build |
| `export_docs` | `false` | raw documentation files into `static/` |
| `push` | `true` | whether to push the image to the registry |

**Rendition cache in CI.** Without it every build is cold: on a site with a hundred images that is minutes of CPU time for any text edit. This is a recipe for the site's own workflow only. `site-image.yml` does not save a rendition cache: every build of it is cold. In a build with `--out` the cache lives next to the output folder, in `.heron-cache/`, and goes into the runner cache as an ordinary folder:

```yaml
- uses: actions/cache@v4
  with:
    path: .heron-cache
    key: heron-media-${{ hashFiles('media/**', 'theme/theme.yaml') }}
    restore-keys: heron-media-
```

The key includes the theme for a reason: `widths`, `ratios` and `formats` are part of the hash of every entry, and an edit of `theme.yaml` invalidates the whole cache.

The cache affects only speed. Lost, stale, not restored - the build is simply cold, and the result is the same byte for byte. So cache misses need no fixing, and `build.workers` in CI should be pinned by hand: the cores there are shared with other jobs.

**If the site turned on `build.updated_from: git`, the history has to reach the build.** GitHub Actions clones the repository shallow - only the last commit - and then the history formally exists but has no dates: the engine falls back to file times, and after the clone all files are dated with the clone time. The whole site claims it was updated today, at every build. One line fixes it:

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0
```

The same applies to a build from an archive or from a copy of the folder without `.git`: dates fall back to file times. If dates matter, the history must sit next to the content at build time.

### Engine CI: caches, jobs and cache reset

The engine repository workflow `ci.yml` has four jobs. `quality` (lint and tests), `browser` (Chromium checks) and `image-build` (image build and check, push only) run **in parallel**. `publish` (image publishing, push only) waits for all of them: `needs: [quality, browser, image-build]`. `publish` does not rebuild the image: it receives the image verified in `image-build` as the `heron-candidate` artifact (`docker save`/`docker load`, retention 1 day), so exactly the image that passed the smoke check is published. The runner is pinned explicitly, `ubuntu-26.04`.

**Concurrency.** Group `${{ github.workflow }}-${{ github.ref }}`: one active run per branch or pull request. A stale run is cancelled by a new one only for pull requests and the `dev` branch. On `beta`, `prod` and tags cancellation is off: the image is published there.

| What is cached | Where | Key |
|---|---|---|
| Python dependencies (uv) | `quality`, `browser`: `astral-sh/setup-uv`, `enable-cache` | hash of `uv.lock` (`cache-dependency-glob`) |
| nginx `.deb` packages | `quality`: `~/.apt-archives` | `apt-nginx-<OS>-<arch>-ubuntu-26.04` |
| Playwright Chromium | `browser`: `~/.cache/ms-playwright` | `playwright-<OS>-<Playwright version>` |
| Docker layers (buildx, gha backend) | `image-build` (writes and reads) | `scope=heron-engine` |
| Site image Docker layers | `site-image.yml` | `scope=heron-site` |

A Chromium cache hit skips the browser download, but system libraries are still installed (`playwright install-deps`). A Docker layer cache miss affects the build time of `image-build`, and the image that passed the check is published in any case. A cold build may differ in content: it reinstalls the unpinned git package (the git install step in `Dockerfile`).

**How to reset a cache.**

- Change the version in the key. For Chromium this is the step that sets the Playwright version for the cache key (version `1.63.0` in `ci.yml`, the same number must be changed in the `playwright` commands); for nginx `.deb` files, the `ubuntu-26.04` label in the key; for uv, changing `uv.lock` is enough. The old cache is no longer found and is evicted over time.
- Delete selectively: `gh cache list`, then `gh cache delete <id or key>`; everything at once - `gh cache delete --all`.
- By hand in the UI: the repository, the Actions tab, the Caches section on the left, the delete button next to the entry.

Docker layers live in the same GitHub Actions cache storage (the `scope=heron-engine` and `scope=heron-site` index entries; the blocks themselves are stored under hash keys, so filtering `gh cache list` by scope does not find everything): they show up in `gh cache list` and are deleted the same ways. The `heron-site` cache belongs to the site repository, not the engine one. The storage limit is 10 GB per repository; above it GitHub evicts the oldest entries.

## 5. nginx

The minimum the config must have:

- static files: HTML with `Cache-Control: no-cache`; copies of `assets/` files with the content hash in the name (`site.0123456789.css`) and `media/` resources with a version mark in a parameter (`/media/photo.jpg?v=0123456789`, exactly 10 hex chars) - `public, max-age=31536000, immutable`; theme files under their plain names and resources without the mark or with another one - `public, max-age=86400`. Resources lie in the build once: a hashed copy would double the image (Docker `COPY` does not keep hard links), and a static server simply does not read the mark - the site works on any hosting. A caveat: some CDNs and proxies cache without the query string, there a resource replaced in place does not arrive at once; a resource is rarely replaced in place, and theme files, whose staleness broke layouts, carry the version in the name (`21` §4). The times are the `nginx.cache` keys in `site.yaml` (`20` §5). Pages always get `no-cache`, and this is not configurable: the new names of theme files arrive together with the page, and caching the page would delay the whole update
- gzip compression for text, styles, scripts, svg, maps and markup; the config does not enable brotli
- 301 from `redirect_from` and 410 from `gone` are served without touching files. The maps are already written into the config the engine builds together with the site (`dist/.heron-nginx.conf`); `redirects.map` and, if `gone` is set, `gone.map` in `dist/` are human-readable copies
- one canonical URL form by `urls.trailing_slash` (`20` §2): `always` - `try_files $uri $uri/ =404`, an address without the slash gets a 301 to the address with it; `never` - `try_files $uri $uri/index.html =404` (the page `/x` from `x/index.html`, without a 301 to `/x/`), the form with the slash gets a 301 to the form without it keeping the query string, the language home is `location = /<lang>`. `/media/`, `/assets/`, `/.well-known/` and real files (`/robots.txt`, `/sitemap.xml`, hashed copies) are served the same way in both modes; a folder without a page (`/assets/`, `/media/demo/`) is not a page, there is no 301 to it
- `/healthz` for the healthcheck
- headers: `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`, HSTS
- **no execution of anything**: the site is static, PHP and any handler are absent as a class
- dot files are closed

The CSP is strict: `script-src 'self'`; there is one exception - the domains of the counters enabled in `analytics` of `site.yaml`. For `heron-relay` the config has no exception yet: the service is not implemented.

**Two nginx servers.** All of the above is done by the inner nginx - the one in the site image: security headers, CSP, cache, 301 and 410 from `site.yaml`, hidden files. The outer nginx of the server only accepts TLS and passes the request to the container (`proxy_pass`); 301 from mirrors (www, old domains) to the main domain and 301 from http to https are its job too, the inner config knows nothing about domains. The outer nginx adds no `Cache-Control`, CSP or other headers of its own and does not cache responses: the headers would be doubled, and an old version of a page would outlive the deployment. A ready block - [`guide/06`, "The outer nginx in front of the site image"](../guide/06-deploy.md#outer-nginx).

## 6. Migration from an existing site <a id="migrate-existing-site"></a>

The order in which the site does not lose ground. The specific redirect rules are the site's business; here is only the sequence.

**Preparation.** The new site is built and started on a service subdomain. Everything is checked: pages, languages, markup, speed.

**Redirect map.** The full list of old addresses is taken from the live sitemap. For each one `redirect_from` is written in the matching md file; what no longer exists - archives, service paths, doorway pages - goes into `gone` in `site.yaml`, as exact addresses or prefixes (`20` §5). The smoke check of the image passes on the service domain.

The difference between 301 and 410 is fundamental: 301 tells the search engine "the address moved, here is the new one", 410 says "this is gone, drop it from the index". The service entities of the old system are the second case, and there is no point pretending they are temporarily unavailable.

**Switchover.** The proxy is pointed at the new container. The old stack stays up but unreachable from outside, in case of a rollback.

**After.** The sitemap is resubmitted in Search Console. For a week we watch the crawl error report. If it is quiet, the old stack is shut down and its directories are archived.

## 7. Backup

Back up only what a build cannot restore.

**Needed:** the site repository with the content and images - it is the source of truth; the secrets of services, once they appear.

**Not needed:** `dist/` together with the nginx config - it is rebuilt in seconds. `.heron-cache/` - even more so. The engine image - it is in the registry and pinned by version.

The whole site is restored from git: clone and build. This is the main practical advantage over systems where a restore means deploying a database.

## 8. What comes later

Laid into the structure, not implemented now:

**`heron-relay`** - the third container on sites with forms: receives POST, validates against the schema from `site.yaml`, antispam, sends to mail, a CRM webhook and Telegram. No database; SQLite only as a retry spool. Secrets come from the mounted `.env`, only into this container - nginx knows nothing about them.

**Own analytics** - receiving events instead of an external counter. A separate relay endpoint, a separate storage decision.

**Atomic deploy** - build into a neighbouring directory and swap `dist` with one rename, returning the previous one on an error. The delivery has no scripts for this.

**Admin panel** - a web editor of md files that starts a rebuild. The rule without which it must not be made: **the admin panel edits files and commits them to git, it does not write to a database.** Otherwise HERON turns into the very system the sites are leaving.

None of them requires rewriting what is being done now, provided the boundaries from `21-engine.md` and `23-distribution.md` are kept.
