# HERON - site deployment

**Date:** 2026-09-08 · **Revised:** 2026-09-14 · **Status:** for development
**Document 3 of 4.** Previous: `20-data-contract.md`, `21-engine.md`. Next: `23-distribution.md`.

**Revision 2026-09-14:** the document follows the "engine separate from the site" concept and is cleared of the specifics of any particular site - they moved to the documents of the sites themselves.

> **Status as of 2026-10-04.** The deploy path that works today is the site image: `scripts/site.sh <site> image|smoke|push <environment>` in the engine repository (`23-distribution.md` §5); then the image runs like any nginx container. The "build on the server" scheme of sections 2-3 (`compose` with the builder, `install.sh`, `deploy.sh`, `deploy.conf`) is the target: these scripts do not exist in the engine repository yet. Sections 4-6 (site CI, nginx requirements, migration) apply to both paths.

---

## 1. What we deploy

One site is one folder and one repository. It holds the content, data, images, theme and config. **There is no engine code in it**: the engine comes as the image `ghcr.io/<owner>/heron:<version>`, and the version is declared in `site.yaml`.

Two consequences follow, and they shape the whole deploy:

- updating the engine is a change of one line in `site.yaml` and a rebuild, not a merge of someone else's code into the site repository;
- rolling the engine back is reverting that line.

## 2. Containers

Two, both light. A third one (`relay`) appears only on sites with forms.

**Builder** - the engine image. It runs once, builds the site into `dist/` and exits. Between builds it does not run and uses no resources. You do not build it on the target machine: it is pulled from the registry.

**Web** - nginx serving `dist/`. The only process that runs all the time. The image is `nginxinc/nginx-unprivileged`: the master process does not run as root and listens on 8080; a proxy faces the outside.

There is no database. There is no application. Serving static files is the only thing the site does in production.

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
      - .:/site
    command: ["build", "--strict"]

  web:
    image: nginxinc/nginx-unprivileged:1.30.6-alpine
    restart: unless-stopped
    volumes:
      - ./dist:/usr/share/nginx/html:ro
      # the engine builds the config: languages, 404, the 301 and 410 maps are already inside
      - ./dist/.heron-nginx.conf:/etc/nginx/conf.d/default.conf:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 3s
      retries: 3
```

`dist/` is mounted into nginx read-only. The builder writes there, the web container only reads.

`.env` is not mounted into the builder: the build has no secrets and runs without a network. The security model is covered in `23-distribution.md`, section 9.

## 3. Two scripts

Both live in the project directory on the server and run from there. Style: `set -e`, clear steps, a clear failure.

### `install.sh` - once, at the first installation

1. Checks that `docker` and `docker compose` are present, and their versions
2. Creates `dist/`, `cache/`, `logs/` with the right permissions
3. Copies `.env.example` to `.env` if it does not exist and **stops**, asking you to fill it in. It does not run with empty secrets (relevant for sites with relay; on a static site the file stays empty)
4. Checks that `deploy.conf` is filled in
5. Pulls the engine image of the required version from the registry
6. First build of the site
7. Starts nginx
8. Prints what comes next: check the site, set up the proxy, issue a certificate

### `deploy.sh` - at every update

1. Reads `deploy.conf` and `.env`
2. `git pull` of the required branch
3. Compares the engine version from `site.yaml` with the locally available image; on a mismatch pulls the required tag
4. **Builds the site into the temporary directory `dist.new/`**, without touching the live one
5. Runs `heron check --strict`. Errors mean a stop, `dist/` stays as it was
6. Atomic swap: `dist` → `dist.old`, `dist.new` → `dist`, nginx reload
7. On a failure at any step - `dist.old` is restored with a clear message
8. Removes `dist.old` after a successful check

The key point: **the build goes to the side, the swap is atomic.** A broken commit does not leave the site half updated. A rollback is restoring the previous directory, not a rebuild.

### Two configuration files

`deploy.conf` - environment parameters, kept in git:

```
REPO_BRANCH=main
SITE_DIR=/opt/site
DOMAIN=example.com
KEEP_RELEASES=3
```

`.env` - secrets, absent from git, permissions 600. On a static site it is empty: secrets appear with relay. The handling rules are in section 8 of `20-data-contract.md`.

The separation is fundamental: `deploy.conf` can be shown to anyone, `.env` to no one.

## 4. CI

On an event in the site repository:

1. `heron check --strict` - fails on errors and on warnings
2. `heron build` into a temporary directory
3. Redirect map check: every old URL returns 301 to an address that answers 200
4. Lighthouse on the built site, the site sets the thresholds
5. Only if everything is green - `deploy.sh`

The tests of the engine itself run in the CI of the **engine repository**, not the site: the site consumes a ready image and does not have to know how it was built.

**What does not get into the site image.** The image context is the built `dist/`, so the site sources are physically absent from it: no `.git`, no image masters, no agent kit (`agents/`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` - `20` §1). There is no need to check this separately in the site CI: it is a property of the build, pinned by the engine tests.

**The step before the build.** The reusable workflow `site-image.yml` takes an optional input `export_docs` (`true`/`false`, default `false`) - an allowlist, not an arbitrary command: with `true`, **with the same engine image**, in the repository working copy before the build, while the folder is not yet mounted read-only, it runs `heron docs --export static/agents --all-langs`, `heron schema --export static/schema/<major.minor> --lang en` and `heron schema --export static/schema/<major.minor>/ru --lang ru` (the version comes from `heron --version` of the same image) and `heron docs agents > static/AGENTS.md`. This is how the engine site publishes the raw documentation files (`23` §12). The run policy is the same: no network, no capabilities, not as root, the container root read-only. Only the site's `static/` folder is mounted for writing (inside the container it is `/out`), not the site folder and not the whole working copy: with `path: "."` that would be the checkout root together with `.git` and `.heron/` (the recipe and the smoke check the image build then follows). A symbolic link in place of `static/` or `static/AGENTS.md` is a step error: the mount and the output redirection would follow it outside the site folder. Nothing is added to the image except what later gets into `dist/` through the normal build.

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

**Rendition cache in CI.** Without it every build is cold: on a site with a hundred images that is minutes of CPU time for any text edit. The cache lives in `.heron-cache/` next to the build folder and goes into the runner cache as an ordinary folder:

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

Item 3 is not a formality. It is the only thing that protects the index when migrating from an old system.

## 5. nginx

The minimum the config must have:

- static files with a long cache for `assets/` and `media/`, a short one for HTML
- gzip and brotli
- 301 from `redirect_from` and 410 from `gone` are served without touching files. The maps are already written into the config the engine builds together with the site (`dist/.heron-nginx.conf`); `redirects.map` and `gone.map` in `dist/` are human-readable copies
- `try_files` with a trailing slash, one canonical URL form
- `/healthz` for the healthcheck
- headers: `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`, HSTS
- **no execution of anything**: the site is static, PHP and any handler are absent as a class
- dot files are closed

A strict CSP makes sense: the own scripts are a few kilobytes, there are no external ones. `script-src 'self'` with no exceptions. Sites with a form add `connect-src` to the relay address, and nothing else.

## 6. Migration from an existing site <a id="migrate-existing-site"></a>

The order in which the site does not lose ground. The specific redirect rules are the site's business; here is only the sequence.

**Preparation.** The new site is built and started on a service subdomain. Everything is checked: pages, languages, markup, speed.

**Redirect map.** The full list of old addresses is taken from the live sitemap. For each one `redirect_from` is written in the matching md file; what no longer exists - archives, service paths, doorway pages - goes into `gone` in `site.yaml`, as exact addresses or prefixes (`20` §5). The test from item 3 passes on the service domain.

The difference between 301 and 410 is fundamental: 301 tells the search engine "the address moved, here is the new one", 410 says "this is gone, drop it from the index". The service entities of the old system are the second case, and there is no point pretending they are temporarily unavailable.

**Switchover.** The proxy is pointed at the new container. The old stack stays up but unreachable from outside, in case of a rollback.

**After.** The sitemap is resubmitted in Search Console. For a week we watch the crawl error report. If it is quiet, the old stack is shut down and its directories are archived.

## 7. Backup

Back up only what a build cannot restore.

**Needed:** the repository with the content and images - it is the source of truth. `.env`. The nginx config.

**Not needed:** `dist/` - it is rebuilt in seconds. `cache/` - even more so. The engine image - it is in the registry and pinned by version.

The whole site is restored from git with one command. This is the main practical advantage over systems where a restore means deploying a database.

## 8. What comes later

Laid into the structure, not implemented now:

**`heron-relay`** - the third container on sites with forms: receives POST, validates against the schema from `site.yaml`, antispam, sends to mail, a CRM webhook and Telegram. No database; SQLite only as a retry spool. Secrets come from the mounted `.env`, only into this container - nginx knows nothing about them.

**Own analytics** - receiving events instead of an external counter. A separate relay endpoint, a separate storage decision.

**Admin panel** - a web editor of md files that starts a rebuild. The rule without which it must not be made: **the admin panel edits files and commits them to git, it does not write to a database.** Otherwise HERON turns into the very system the sites are leaving.

None of the three requires rewriting what is being done now, provided the boundaries from `21-engine.md` and `23-distribution.md` are kept.
