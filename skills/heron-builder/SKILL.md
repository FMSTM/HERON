---
name: heron-builder
description: Build, check and publish a HERON site - heron check, serve, build with --env prod --strict, the publishing scripts and workflow written by heron setup - and report what is left. Use when asked to build, preview, pack or publish a HERON site, or to assemble a site from a ready structure.
---

# HERON builder

Read first: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs --lang en kit` (role «Builder»), `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs first-site`, `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs deploy`, error codes in `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta docs engine` §11.
Inside a HERON site the same documentation sits in `agents/` (start with `AGENTS.md`); your deliverables go to `agents/work/`.
Every command is written in full, ready to copy; run it from the site folder. No `-it`: an agent has no terminal. `-p 127.0.0.1:8000:8000` only for `serve`: it publishes the port.

**You may write:** anything the other roles may, when you lead them; plus `heron setup` answers for publishing.
**You do not touch:** the engine. Add no Dockerfile, compose, `.env` or tokens to the site: Docker Hub uses `docker login`, GitHub builds with its own short-lived token.

Steps:

1. `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta check .` — the report without a build; fix errors, sort warnings into content debt or fixes. Pages marked `translation: pending` are listed and stay out of production: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta page list . --json`.
2. `docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta serve .` — preview on localhost:8000 with a rebuild on every save; the theme reference is at `/_heron/theme/`.
3. `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta build . --env prod --strict` — the final build into `dist/`.
4. A theme handed over on its own: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta check . --theme` (no `E008`, `E041`, `E037`), then `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta theme pack . --out theme.tar.gz`.
5. Publishing: `docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:beta setup . --dump > answers.yaml`, set `publish.way` (github, dockerhub, static), apply with `--answers answers.yaml`. The agent only prepares settings and the build; the human runs publishing (`.heron/scripts/publish.sh`, or `git push` for the git way).
6. Browser cache: the build gives theme files and media hashed copies (`site.0123456789.css`), served for a year; plain names and their times are `cache.versioned`, `cache.assets`, `cache.media` in the answers (`nginx.cache` in `site.yaml`, defaults `1y`, `1d`, `1d`). Remove any own `?v=` stamping step of the site. The server's outer nginx only does TLS, mirrors and http to https and adds no headers or cache of its own - the sample is in `docs deploy`, "The outer nginx in front of the site image".

Report: what was done, content debt, questions, warnings left on purpose and why.
