# 00 · Installation

There are two ways to run HERON:

- **with Docker** - you install nothing but Docker. This suits almost everyone;
- **without Docker** - the engine is installed as an ordinary Python program.

If you are not sure which to pick, take Docker.

## With Docker

1. Install Docker:
   - **macOS and Windows** - [Docker Desktop](https://www.docker.com/products/docker-desktop/). After installing, start it: commands do not work while Docker Desktop is not running. On Windows, run every command from this documentation in a WSL (Ubuntu) terminal: install it with `wsl --install` in PowerShell and turn it on in Docker Desktop: Settings → Resources → WSL integration;
   - **Linux** - Docker Engine, following the [instructions for your distribution](https://docs.docker.com/engine/install/).

2. Check that everything works:

   ```bash
   docker run --rm ghcr.io/fmstm/heron:prod --version
   ```

   The first time, Docker downloads the engine - this takes a minute or two. Then it prints the version, for example:

   ```
   heron, version 0.1.0 (prod, 8c8f730, …)
   ```

That's it, the engine is ready. Go on to [the first site](02-first-site.md): every command there is written in full, so you can copy it into the terminal as is.

### Docker sees only the current folder <a id="docker-current-folder"></a>

The command `docker run … -v "$PWD:/site"` shows the engine **only the folder you are in right now in the terminal**, and everything inside it. So:

- run commands from the folder where the site is, or from the folder above it;
- write the path to the site from the current folder: `my-site` or, if you are already inside the site folder, `.` (a dot means "the current folder");
- a path like `~/sites/my-site` or `/Users/…` will not work: the engine does not see such a folder and will say so.

### Update the engine

```bash
docker pull ghcr.io/fmstm/heron:prod
```

## Without Docker

1. Check that you have Python 3.12 or newer and git:

   ```bash
   python3 --version
   git --version
   ```

   If Python is older than 3.12 or missing, install it from [python.org](https://www.python.org/downloads/) (on macOS, if you have [Homebrew](https://brew.sh), you can use `brew install python`). If git is missing - [git-scm.com](https://git-scm.com/downloads) (on macOS - `xcode-select --install`).

2. Install pipx - it installs Python programs so that they do not get in each other's way:

   ```bash
   brew install pipx                  # macOS, with Homebrew
   sudo apt install pipx              # Debian, Ubuntu, WSL
   pipx ensurepath                    # then, on any system
   ```

   After `pipx ensurepath`, close the terminal and open a new one.

3. Install HERON:

   ```bash
   pipx install git+https://github.com/FMSTM/HERON.git@prod
   ```

   The engine is installed straight from the GitHub repository: it is not in the PyPI package index yet. `@prod` at the end is the stable version. If pipx says the Python version does not fit, name it explicitly: `pipx install --python python3.12 git+https://github.com/FMSTM/HERON.git@prod`.

4. Check:

   ```bash
   heron --version
   ```

### How to read the commands in this documentation <a id="without-docker"></a>

All commands in the documentation are written for Docker. Without Docker, everything up to and including `ghcr.io/fmstm/heron:prod` is replaced with the single word `heron`:

```bash
# in the documentation
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site

# for you
heron build my-site
```

The "current folder only" limit does not apply here: the path to the site can be anything, for example `heron build ~/sites/my-site`.

### Update the engine

```bash
pipx install --force git+https://github.com/FMSTM/HERON.git@prod
```

## Versions: prod and beta

The engine has two versions:

- **prod** - the stable one. Live sites run on it, and every command in the documentation uses it;
- **beta** - the next version under review; new things appear here first. To try it, replace `prod` with `beta`: `ghcr.io/fmstm/heron:beta` in Docker or `@beta` in the pipx command.

The command from the "Check" step shows which version you have.

## If you build sites regularly

This section is optional. It is for those who are tired of copying the long `docker run …` command.

Add a `heron` function to your terminal settings file - then instead of the full command you can write it short, as without Docker: `heron new my-site`, `heron build my-site`.

The settings file: on macOS - `~/.zshrc` (to open: `open -e ~/.zshrc`; if the file does not exist, run `touch ~/.zshrc` first), on Linux and in WSL - `~/.bashrc` (for example, `nano ~/.bashrc`). Paste at the end of the file:

```bash
# HERON: the site engine in Docker
heron() {
  local -a opts
  opts=(--rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)")
  [ -t 0 ] && [ -t 1 ] && opts+=(-it)
  case " $* " in
    *" serve "*|*" setup "*) opts+=(-p 127.0.0.1:8000:8000) ;;
  esac
  docker run "${opts[@]}" ghcr.io/fmstm/heron:prod "$@"
}
```

Save the file, open a new terminal and check: `heron --version`. The function adds the right flags by itself: `-it` when a person runs the command in a terminal (then `new` can ask questions, and the configurator and the preview can be stopped with Ctrl+C), `-p` for the configurator and the preview. The "current folder only" limit stays: it is how Docker works.

## For scripts, CI and AI agents

Scripts and CI do not read terminal settings, so the function from the section above does not work there. Write the command in full and without `-it` - scripts have no terminal, and with this flag Docker will not start:

```bash
docker run --rm -v "$PWD:/site" -w /site --user "$(id -u):$(id -g)" ghcr.io/fmstm/heron:prod build my-site --env prod --strict
```

If the engine is installed with pipx, plain `heron` works in scripts.

---

Next: [01 · Concepts](01-concepts.md) · [02 · The first site](02-first-site.md)
