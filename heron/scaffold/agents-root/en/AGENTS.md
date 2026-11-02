# {name} - for agents

This is a site on the HERON engine. Everything an agent needs to work on it is in `agents/`; there is no need to read the engine code.

- **About the project:** {about}
- **Site languages:** {languages}, main - {default_lang}; domain - {domain}.
- **Kit language:** {notes} (`build.notes`); work results go to `agents/work/`.
- **Engine:** HERON {version}, channel {channel}; kit version and hashes - `agents/heron-kit.yaml`.
- **Documentation of this version:** {docs_url} and `docker run --rm ghcr.io/fmstm/heron:{channel} docs --lang {notes} <topic>`.
- **Done check:** `heron check --strict --json` exits with code 0.

Read [agents/README.md](agents/README.md) first - its text follows; its links lead into `agents/`.

---
