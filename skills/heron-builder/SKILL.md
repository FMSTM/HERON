---
name: heron-builder
description: Build, check and publish a HERON site - heron check, serve, build with --env prod --strict, the publishing scripts and workflow written by heron setup - and report what is left. Use when asked to build, preview, pack or publish a HERON site, or to assemble a site from a ready structure.
---

# HERON builder

Read first: `$H docs agents` (role «Builder»), `$H docs first-site`, `$H docs deploy`, error codes in `$H docs engine` §11.
`H="docker run --rm -i -p 8000:8000 -v $PWD:/site -w /site --user $(id -u):$(id -g) ghcr.io/fmstm/heron:beta"`

**You may write:** anything the other roles may, when you lead them; plus `heron setup` answers for publishing.
**You do not touch:** the engine. Add no Dockerfile, compose or `.env` to the site; tokens live outside the folder (`~/.config/heron/sites/<domain>.env`, `scripts/keys.sh`).

Steps:

1. `$H check .` — the report without a build; fix errors, sort warnings into content debt or fixes.
2. `$H serve .` — preview on localhost:8000 with a rebuild on every save.
3. `$H build . --env prod --strict` — the final build into `dist/`.
4. Publishing: `$H setup . --dump`, set `publish` (git, dockerhub, static), apply with `--answers`; then `scripts/publish.sh`, or `git push` for the git way.

Report: what was done, content debt, questions, warnings left on purpose and why.
