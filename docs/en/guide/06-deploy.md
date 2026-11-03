# 06 · Build and deploy

How to build a site for production, pack it into an image and run several sites on different engine versions. For whoever deploys, a human or a builder agent.

## Two outputs: a folder or an image

| | The `dist/` folder | nginx image |
|---|---|---|
| With | `heron build` | `scripts/site.sh <site> image` |
| What is inside | HTML, images, maps, `.heron-nginx.conf` | nginx-unprivileged, static files, a config for this site |
| Where to | any static hosting, your own nginx | any host with docker, k8s |
| 301, 410, own 404 | include `.heron-nginx.conf` in your nginx | already enabled |

The output is chosen by the command, not when the site is created: the same folder builds both ways. → [`23` §5](../spec/23-distribution.md#two-outputs)

## Site environment

Dev and prod are a **build flag**, not a different engine image:

| | `--env dev` (default) | `--env prod` |
|---|---|---|
| indexing | closed: `noindex` and `Disallow: /` | open |
| counters from `analytics` | no | yes |
| build stamp (version, time, commit) | the theme may show it | not shown |

`--strict` turns warnings into errors and is mandatory for production. They can be overridden separately: `SITE_INDEXABLE=false`, `SITE_ANALYTICS=false` give a production-like preview closed to search engines.

**Domain by environment.** A dev build at its own address must link to itself, not to the production domain. For this, in `site.yaml`:

```yaml
site:
  domain: example.com          # production
  domains:
    dev: dev.example.com       # canonical, sitemap, hreflang, robots point to this address in the dev build
```

The environment name is the same as in `--env`: one lever controls both indexing and the domain.

## One site

```bash
H="docker run --rm -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:prod"
$H build my-site --env prod --strict
```

`my-site/dist/` is the finished site. A rebuild into the same folder removes what is no longer there (deleted and unpublished pages, old addresses) and does not touch foreign files; a failed build, or a strict build with warnings, changes nothing in `dist/`: the previous successful version stays there. `static/` cannot quietly replace a generated file (`E026`); if you need your own `robots.txt`, use `build.overrides: [robots.txt]`. Upload the folder to static hosting (then 301/410 are set up with the hosting tools from `dist/redirects.map` and `dist/gone.map`; the latter exists only if `gone` is set) or serve it with your own nginx, below.

### Your own nginx on a server

`dist/.heron-nginx.conf` is a ready `server {}` together with the 301/410 maps. It is included **in the `http` context**, like any site file. An example for Debian/Ubuntu with nginx from apt:

```bash
sudo cp -r my-site/dist /var/www/my-site
sudo cp my-site/dist/.heron-nginx.conf /etc/nginx/sites-enabled/my-site.conf
# in the file, fix root to /var/www/my-site and listen/server_name for your host
sudo nginx -t && sudo systemctl reload nginx
```

**301 and 410 are case-sensitive.** Every old address is a separate `location = "/old/" { return 301 "/new/"; }`, a prefix from `gone` is `location ^~`. This way `/About/` and `/about/` stay different addresses, as everywhere in the engine: string `map` tables compare without regard to case and turned `redirect_from: /Page/` into a redirect of `/page/` to itself. 301 and 410 fire only on an exact case match: a request `/about/` with the entry `/About/` gets 404, for Latin and for Cyrillic alike; if you need that variant too, add it to `redirect_from` (or `gone`) as a separate line. Exact locations have no hash tables, so there is no need to write `map_hash_bucket_size` either in the site file or in the host `nginx.conf`; the key `nginx.hash_sizes` in `site.yaml` is obsolete and does nothing. Regular-expression maps remain only for addresses with a parameter (`/?p=*`) and for broken percent addresses.

**Hidden files** (`/.git/…`, `/ru/.env`, `/media/.x`) answer 404 in the root, under every language, in `media/` and `assets/`; only `/.well-known/` is available.

If nginx is present on the machine where the build runs, the engine runs `nginx -t` on the built config itself and writes the result to the report; if it fails, it is a warning, and with `--strict` an error.

The config turns on HSTS for a year with subdomains (`Strict-Transport-Security`) and the `/healthz` address. If the domain is not on https yet or has subdomains without it, remove the `Strict-Transport-Security` line; details are in [`22`](../spec/22-deploy.md).

To look locally, use `heron serve my-site` (in the image: `docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD":/site -w /site ghcr.io/fmstm/heron:prod serve .`; in the container the preview listens on all interfaces by itself, so `--host 0.0.0.0` can be left out): the same 404 the visitor will see, a build into a temporary folder, the site folder stays clean. `heron serve` does not imitate 301, 410 and the closing of hidden files; `smoke` checks them on the image; `site.sh serve` starts a real nginx, where they work.

## An image from the site repository

A site usually lives in its own repository, and there is no HERON clone next to it. The image is built by a reusable HERON workflow, so you do not need to write your own Dockerfile:

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
      engine: prod      # engine tag: prod, beta or 0.1.0
```

The workflow builds the site with the engine from the image, packs `dist/` into nginx by the recipe of the same HERON version, starts the image, runs a smoke check and pushes it to `ghcr.io/<owner>/<repository>:<environment>`. The workflow inputs:

| Input | Default | What it does |
|---|---|---|
| `env` | `dev` | the build environment |
| `engine` | `prod` | the engine tag: `prod`, `beta`, `dev`, `X.Y.Z`, `@sha256:<digest>` is possible |
| `path` | `.` | the site folder inside the repository, without `..` |
| `image` | `ghcr.io/<owner>/<repository>` | the site image name |
| `tag` | the environment name | the image tag |
| `strict` | `auto` | `auto` - strict for `prod`; `true`/`false` |
| `nginx_image` | stock nginx by digest | `nginx -t` runs on it before the image is built |
| `export_docs` | `false` | raw documentation files into `static/` |
| `push` | `true` | `false` - build and check without pushing |

The output `image` is the full image name with the tag. The input `export_docs` (`true`/`false`, `false` by default) is needed only for the engine's own site: before the build, the same engine image puts the raw documentation files of this version into the site's `static/` - `agents/{ru,en}/**`, `schema/<major.minor>/*.json` and `AGENTS.md`; only the `static/` folder is mounted writable for this. An ordinary site does not need to enable it ([`22` §4](../spec/22-deploy.md)). Until beta becomes prod, call `@beta` with `engine: beta`.

## Several sites: `scripts/site.sh`

From a clone of the engine repository:

```bash
git clone https://github.com/FMSTM/HERON.git && cd HERON
HERON_NOTES=en ./scripts/site.sh mysite new ~/sites/my-site
```

`new` creates the site folder, in a terminal with the same questions as `heron new`, and sets up `env/.env.mysite.dev` and `.prod`. The folder may already exist and be under git. The site name in `site.sh` is Latin letters, digits and a hyphen: the image name `heron-site-<site>` is built from it, and docker does not accept Cyrillic. The site folder may be named anything. In a clone `new` builds the engine image from source, `ENGINE` does not affect it: the first run takes time. After that everything is one command:

```bash
./scripts/site.sh mysite check dev     # report without a build
./scripts/site.sh mysite build dev     # → out/mysite-dev
./scripts/site.sh mysite serve dev     # nginx image from out/ and a preview on localhost:$PORT; build first
./scripts/site.sh mysite stop          # stop the preview
./scripts/site.sh mysite build prod
./scripts/site.sh mysite image prod    # image IMAGE_NAME:IMAGE_TAG
./scripts/site.sh mysite smoke prod    # start the image, check the codes
./scripts/site.sh mysite push prod     # to REGISTRY
./scripts/site.sh mysite init          # build up the folder after editing site.yaml
```

The content folder is mounted **read-only**: everything the build produces lives in `out/`, and the content gets nothing dirty. The previous result in `out/` is not erased before a build: a failed build leaves the previous working site there, and a successful one removes the stale files itself. The script works both in bash 3.2 (the macOS default) and without a terminal.

Exit codes of `heron build`: 0 means built; 1 means an error, `dist/` is not touched; 2 means wrong flags or arguments; 3 means the site is written but the final plugin action failed (`on_build_finished`).

The site settings are `env/.env.<site>.<environment>`, they do not go into git. A sample with explanations: [`env/.env.example`](https://github.com/FMSTM/HERON/blob/prod/env/.env.example):

| Variable | What it sets |
|---|---|
| `SITE_PATH` | path to the site folder |
| `SITE_ENV` | `dev` or `prod`, what the site will be |
| `STRICT` | strict build |
| `ENGINE` | which engine to build with (below) |
| `IMAGE_NAME`, `IMAGE_TAG` | name of the site image |
| `REGISTRY`, `REGISTRY_CONFIG` | the registry for `push` and the docker config for it; empty means `push` is forbidden |
| `PORT` | preview port |
| `HERON_NOTES` | language of the help, messages and comments in files: `ru` or `en` |

Form secrets (SMTP, webhooks) do not go here: the build is static, and everything it sees may end up in the HTML.

## Smoke run

`site.sh <site> smoke <environment>` starts the built image and checks the answers (the check itself is done by `scripts/smoke-site.sh`, the same script is called by the site image workflow):

- the root and `robots.txt` give 200, a nonexistent address gives 404;
- every language from the build config gives 200 and its own 404;
- hidden and service files (`.heron-nginx.conf`, `.heron-manifest.json`) give 404 in the root, under the languages, in `media/` and `assets/`;
- **every** address from `redirects.map` gives 301 to where it is declared, and the target answers 200 itself, without a second redirect;
- **every** exact address from `gone.map` gives 410.

If it fails, the container is stopped and the nginx logs are printed. → [`23` §5, "Checks and smoke run"](../spec/23-distribution.md#checks-and-smoke)

## Engine versions

**The site pins the engine itself**, on the first line of `site.yaml`:

```yaml
heron: ">=0.1,<0.2"
```

An engine outside the range refuses to build (`E012`). Updating the engine for a site means changing this line, deliberately and one site at a time.

**Which engine `site.sh` builds with** is `ENGINE` in the env file:

| Value | When |
|---|---|
| empty | the exact version from `site.yaml` if it is exact there; otherwise the sources next to it; otherwise `:prod` |
| `ghcr.io/fmstm/heron:prod` | stable, the usual choice |
| `ghcr.io/fmstm/heron:0.1.0` | pin to a version |
| `source` | build from the sources next to it, only when you edit the engine itself |

**Engine image tags:**

| Tag | What it is |
|---|---|
| `:X.Y.Z` | an exact version, never changes |
| `:prod` | what the sites run on |
| `:beta` | trying out the next version on live sites |
| `:dev` | engine development; not meant for sites |

Which image you have is shown by `--version`: the branch, the commit and the build time, for example `heron, version 0.1.0 (beta, 55249f0, 2026-10-08 19:12 UTC)`. The version number is one for the whole development branch, and the commit shows whether the beta is fresh. From the sources it is `(source, <commit>)`.

There is intentionally no moving `:X.Y`: a site must be able to pin to what will not move under it tomorrow.

## Checklist before deploy

1. `site.yaml`: domain, languages, `heron:` with a range, counters.
2. `build --env prod --strict` passes without errors.
3. The "Not filled" summary is empty or knowingly accepted.
4. `smoke prod` is green: 200, 404, all 301 and 410.
5. After deploy, submit the sitemap in Search Console.

## If an agent builds the site

The boundary is simple: **the agent builds, the human publishes.** The agent runs `check`, `build --env prod --strict`, `serve` if needed, reads the report and fixes what belongs to its role; it hands the result in as the report `agents/work/report.md` and the list of questions `agents/work/questions.md`. `.heron/scripts/publish.sh`, `docker push`, `site.sh push`, `git push` and merge are not its commands: you read the report, look at the diff and publish yourself. Also not its commands: `Dockerfile`, compose, `.env`, tokens and code in `plugins/`. The full list of boundaries is in [`roles/builder.md`](../roles/builder.md) and the kit `README.md`.

---

Reference: [`22` · Deploy](../spec/22-deploy.md), [`23` · Distribution](../spec/23-distribution.md).
