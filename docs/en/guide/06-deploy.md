# 06 · Build and deploy

This section covers how to build a site for publishing, put it on hosting or your own server, pack it into a Docker image and run several sites on different engine versions. It is for whoever deploys the site - a person or an AI agent in the builder role.

> **Installed the engine without Docker?** Then in every command replace everything up to and including `ghcr.io/fmstm/heron:prod` with the word `heron`. More - [in the installation section](00-install.md#without-docker).

As in [02 · First site](02-first-site.md), commands are run from the folder that holds the site folder `my-site`.

## Two kinds of result: a folder or an image

You can get the built site in two forms:

| | The `dist/` folder | An nginx image |
|---|---|---|
| How to build | `heron build` | `scripts/site.sh <site> image` |
| What is inside | HTML, images, sitemaps, `.heron-nginx.conf` | nginx-unprivileged, static files, a config for this site |
| Where to deploy | any static hosting, your own nginx | any server with Docker, k8s |
| 301, 410, own 404 | include `.heron-nginx.conf` in your nginx | already included |

The kind is chosen by the build command, not when the site is created: the same site folder builds both ways. More - [`23` §5](../spec/23-distribution.md#two-outputs).

## Draft and production builds

A draft (dev) and a production (prod) build differ by a **flag of the build command**, not by a different engine image:

| | `--env dev` (the default) | `--env prod` |
|---|---|---|
| search engines | the site is closed: `noindex` and `Disallow: /` | the site is open |
| counters from `analytics` | not added | added |
| build label (version, time, commit) | the theme may show it | not shown |

The `--strict` flag turns warnings into errors - it is mandatory for a production build. Each property can be overridden separately with the environment variables `SITE_INDEXABLE` and `SITE_ANALYTICS`. Pass them into the container with the `-e` flag: a variable set only in your terminal does not reach the engine. This gives a preview that looks like a production build but is closed to search engines:

```bash
docker run --rm -e SITE_INDEXABLE=false -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site --env prod
```

**A separate domain for the draft build.** A draft build deployed to its own address must link to that address, not to the production domain. For this, in `site.yaml`:

```yaml
site:
  domain: example.com          # production
  domains:
    dev: dev.example.com       # canonical, sitemap, hreflang, robots point here in the draft build
```

The environment name in `domains` is the same as in the `--env` flag: one switch controls both indexing and the domain.

## One site

The production build of one site:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site --env prod --strict
```

The finished site appears in `my-site/dist/`. What to know about this folder:

- **A rebuild into the same folder** removes what is no longer on the site (deleted and unpublished pages, old addresses) and does not touch foreign files.
- **A failed build** or a strict build with warnings changes nothing in `dist/` - the previous successful version stays there.
- **`static/` cannot quietly replace a generated file** - that is error `E026`. If you need your own `robots.txt`, allow the replacement explicitly: `build.overrides: [robots.txt]`.

Exit codes of `heron build`:

- 0 - built;
- 1 - error, `dist/` untouched;
- 2 - wrong flags or arguments;
- 3 - the site is written, but the final plugin action (`on_build_finished`) failed.

Then the folder can be uploaded to any static hosting. In that case 301 redirects and 410 responses are set up with the hosting tools from the files `dist/redirects.map` and `dist/gone.map` (the second appears only if `gone` is set in `site.yaml`). Or serve the folder with your own nginx - see below.

### Your own nginx on a server

`dist/.heron-nginx.conf` holds a ready `server {}` block together with the 301 and 410 rules. It is included **in the `http` context** of nginx, like the config of any site. An example for Debian/Ubuntu with nginx installed via apt:

```bash
sudo mkdir -p /var/www/my-site && sudo cp -r my-site/dist/. /var/www/my-site/
sudo cp my-site/dist/.heron-nginx.conf /etc/nginx/sites-enabled/my-site.conf
# in the file, fix root to /var/www/my-site and listen/server_name for your host
sudo nginx -t && sudo systemctl reload nginx
```

The first two lines copy the site and its config, the third is a reminder to fix the paths and host name in the copied config, the last one checks the config and reloads nginx.

**301 and 410 are case-sensitive.** Every old address is a separate rule `location = "/old/" { return 301 "/new/"; }`, a prefix from `gone` is a `location ^~` rule. So `/About/` and `/about/` stay different addresses, as everywhere in the engine.

The consequence: 301 and 410 fire only on an exact case match. A request for `/about/` with the entry `/About/` gets 404 - for Latin and Cyrillic alike. If you need that variant of the address too, add it to `redirect_from` (or `gone`) as a separate line.

There is no need to set `map_hash_bucket_size` or the `nginx.hash_sizes` key in `site.yaml` any more: the key is obsolete and does nothing.

**Hidden files** (`/.git/…`, `/ru/.env`, `/media/.x`) answer 404 in the root, under every language, in `media/` and `assets/`. Only the `/.well-known/` folder is available.

The config turns on HSTS for a year including subdomains (the `Strict-Transport-Security` header) and the service address `/healthz` for checking that the server is alive. If the domain does not work over https yet or has subdomains without https, remove all `add_header Strict-Transport-Security` lines - the config has several, one per `location` block. Details - in [`22`](../spec/22-deploy.md).

If nginx is installed on the machine where the build runs, the engine runs `nginx -t` on the built config itself and writes the result to the report. If it fails, it is a warning, and with `--strict` an error.

### Look at it locally

```bash
docker run --rm -it -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod serve my-site
```

This is the same preview as in step 2 of the first site. In the container it listens on all interfaces by itself, so there is no need to write the `--host 0.0.0.0` flag. The preview shows the same 404 page a visitor will see, builds the site into a temporary folder and keeps the site folder clean.

What the preview does not imitate: 301, 410 and the closing of hidden files. The `smoke` run - an automatic check of the finished image (more below) - checks them, and `site.sh serve` starts a real nginx where all of this works.

## An image from the site repository

Usually a site lives in its own repository on GitHub, with no engine clone next to it. The site's Docker image is built by a ready reusable HERON workflow - you do not need to write your own Dockerfile. Add a file to the site repository:

```yaml
# .github/workflows/image.yml in the site repository
name: image
on:
  push:
    branches: [main]

jobs:
  image:
    uses: FMSTM/HERON/.github/workflows/site-image.yml@prod
    permissions:
      contents: read
      packages: write
    with:
      env: dev          # dev or prod
      engine: prod      # engine tag: prod, beta or X.Y.Z
```

On every push to `main` the workflow builds the site with the engine from the image, packs `dist/` into nginx using the recipe of the same HERON version, starts the image, runs the smoke check and pushes the image to `ghcr.io/<owner>/<repository>:<environment>`.

What you can set in `with:`:

| Input | Default | What it does |
|---|---|---|
| `env` | `dev` | build environment |
| `engine` | `prod` | engine tag: `prod`, `beta`, `dev`, `X.Y.Z`, `@sha256:<digest>` allowed |
| `path` | `.` | site folder inside the repository, no `..` |
| `image` | `ghcr.io/<owner>/<repository>` | site image name |
| `tag` | environment name | image tag |
| `strict` | `auto` | `auto` - strict for `prod`; `true`/`false` |
| `nginx_image` | the official nginx image pinned by digest | `nginx -t` runs on it before the image build |
| `export_docs` | `false` | raw documentation files into `static/` |
| `push` | `true` | `false` - build and check without pushing |

If `engine` names an exact version, the image recipe and the smoke check are taken from the tag `vX.Y.Z`. The tag `v0.1.0` was released before `scripts/smoke-site.sh` existed, so the workflow does not work with it: use `prod` or `beta` or a newer version.

The workflow returns the `image` output - the full name of the built image with its tag.

The `export_docs` input is needed only by the site of the engine itself. Before the build, the same engine image puts the raw documentation files of this version into the site's `static/` - `agents/{ru,en}/**`, `schema/<major.minor>/*.json` and `AGENTS.md`; only the `static/` folder is mounted for writing. An ordinary site does not need to turn it on ([`22` §4](../spec/22-deploy.md)).

Until beta is released to prod, for beta call the workflow as `@beta` together with `engine: beta`.

## Several sites: `scripts/site.sh`

If you run several sites, it is more convenient to work from a clone of the engine repository: it has the `scripts/site.sh` script, which does everything with one command.

```bash
git clone https://github.com/FMSTM/HERON.git && cd HERON
mkdir -p ~/sites
HERON_NOTES=en ./scripts/site.sh mysite new ~/sites/my-site
```

The first line downloads the engine and goes into its folder, the second creates the folder for sites if it does not exist yet. The third creates a site named `mysite` in the folder `~/sites/my-site`:

- in a terminal `new` asks the same questions as `heron new`, and creates the settings files `env/.env.mysite.dev` and `env/.env.mysite.prod`;
- the site folder may already exist and be under git;
- the site name in `site.sh` is Latin letters, digits and hyphens: the image name `heron-site-<site>` is built from it, and Docker does not accept Cyrillic. The site folder itself can be named anything;
- in the clone, `new` builds the engine image from the sources, and `ENGINE` does not affect this, so the first run takes a while.

From then on, each action is one command:

```bash
./scripts/site.sh mysite check dev     # report without building
./scripts/site.sh mysite build dev     # → out/mysite-dev
./scripts/site.sh mysite serve dev     # nginx image from out/ and preview on localhost:$PORT; build first
./scripts/site.sh mysite stop dev      # stop the preview
./scripts/site.sh mysite build prod
./scripts/site.sh mysite image prod    # image IMAGE_NAME:IMAGE_TAG
./scripts/site.sh mysite smoke prod    # start the image, check the codes
./scripts/site.sh mysite push prod     # to REGISTRY
./scripts/site.sh mysite init          # complete the folder after editing site.yaml
```

The site folder is mounted **read-only**: everything the build produces lives in `out/`, and the content stays clean. The previous result in `out/` is not wiped before a build: a failed build leaves the previous working site there, and a successful build removes outdated files by itself. The script works both in bash 3.2 (the macOS default) and without a terminal.

The settings of each site live in `env/.env.<site>.<environment>` and do not get into git. A sample with explanations - [`env/.env.example`](https://github.com/FMSTM/HERON/blob/prod/env/.env.example):

| Variable | What it sets |
|---|---|
| `SITE_PATH` | path to the site folder |
| `SITE_ENV` | `dev` or `prod` - what the site will be |
| `STRICT` | strict build |
| `ENGINE` | which engine builds it (below) |
| `IMAGE_NAME`, `IMAGE_TAG` | site image name |
| `REGISTRY`, `REGISTRY_CONFIG` | the registry for `push` and the docker config for it; empty - `push` is forbidden |
| `PORT` | preview port |
| `HERON_NOTES` | language of help, messages and comments in files: `ru` or `en` |

Form secrets (SMTP, webhooks) do not go here: the build is static, and everything it sees may end up in the HTML.

## Smoke run

The command `site.sh <site> smoke <environment>` starts the built image and checks that the site responds as it should. The check itself is done by `scripts/smoke-site.sh` - the site image workflow calls the same script. What is checked:

- the root and `robots.txt` answer 200, a nonexistent address - 404;
- every language from the build config answers 200 and serves its own 404;
- hidden and service files (`.heron-nginx.conf`, `.heron-manifest.json`) answer 404 in the root, under languages, in `media/` and `assets/`;
- **every** address from `redirects.map` answers 301 to where it was declared, and the target itself answers 200, without a second redirect;
- **every** exact address from `gone.map` answers 410.

If the check fails, the container is stopped and the nginx logs are printed. More - [`23` §5, "Checks and the smoke run"](../spec/23-distribution.md#checks-and-smoke).

## Engine versions

**The site itself pins which engine suits it** - with the first key of `site.yaml`, `heron:`:

```yaml
heron: ">=0.1,<0.2"
```

An engine outside this range refuses to build the site (error `E012`). Updating the engine for a site means changing this key: deliberately and one site at a time.

**Which engine `site.sh` builds with** is set by the `ENGINE` variable in the site's env file:

| Value | When |
|---|---|
| empty | the exact version from `site.yaml`, if it is exact there; otherwise the sources next to it; otherwise `:prod` |
| `ghcr.io/fmstm/heron:prod` | stable - the usual choice |
| `ghcr.io/fmstm/heron:0.1.0` | pin to a version |
| `source` | build from the sources next to it - only when you are editing the engine itself |

**Engine image tags:**

| Tag | What it is |
|---|---|
| `:X.Y.Z` | an exact version, never changes |
| `:prod` | what the sites run on |
| `:beta` | the next version being tried on live sites |
| `:dev` | engine development; not meant for sites |
| `:latest` | the latest release without a suffix (`vX.Y.Z`, but not `-rc`); an exact version is better for sites |
| `:sha-<commit>` | the build of a specific commit, for example `sha-55249f0` |

Which image you have is shown by `--version`: branch, commit and build time, for example `heron, version 0.1.0 (beta, 55249f0, 2026-10-08 19:12 UTC)`. The version number is the same for the whole development branch, and the commit tells you whether the beta is fresh. An engine built from the sources prints `(source, <commit>)`.

There is no moving `:X.Y` tag on purpose: a site must be able to pin itself to something that will not change under its feet tomorrow.

## Checklist before deploying

1. `site.yaml` sets the domain, languages, `heron:` with a version range and the counters.
2. `build --env prod --strict` passes without errors.
3. The "Not filled in" summary in the report is empty or you accepted it deliberately.
4. `smoke prod` is green: 200, 404, all 301 and 410.
5. After deploying, the sitemap is submitted to Search Console.

## If an agent builds the site

The boundary is simple: **the agent builds, a person publishes.**

The agent runs `check`, `build --env prod --strict`, `serve` if needed, reads the report and fixes what belongs to its role. It hands in the result as the report `agents/work/report.md` and the list of questions `agents/work/questions.md`.

Publishing is not its job: you run `.heron/scripts/publish.sh`, `docker push`, `site.sh push`, `git push` and merge after reading the report and looking at the diff. Likewise not its business: `Dockerfile`, compose, `.env`, tokens and code in `plugins/`. The full list of boundaries is in [`roles/builder.md`](../roles/builder.md) and the kit's [`README.md`](../README.md).

---

Reference: [`22` · Deployment](../spec/22-deploy.md), [`23` · Distribution](../spec/23-distribution.md).
