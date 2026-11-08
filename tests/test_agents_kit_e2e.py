"""Сквозная проверка комплекта для агентов: как его получают человек и агент.

Один сценарий на пункт приёмки E12.S6.T1, целиком через командную строку:
new → agents/ → check --json → build --env prod --strict → образ сайта (nginx и
scripts/smoke-site.sh) → жизненный цикл init/setup → docs и schema.

Спецификация: docs/ru/spec/20-data-contract.md §1, §5, §9, §10;
21-engine.md §4, §10, §12, §14; 23-distribution.md §2, §4, §5, §12.

Часть «из образа» (п. 8) идёт тем образом, что назван в HERON_E2E_IMAGE, и
только там, где есть docker: внутри контейнера тестов сокета нет и быть не
должно. Без переменной эти проверки пропускаются, с переменной и без docker —
падают, а не пропускаются.
"""

from __future__ import annotations

import filecmp
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import heron
from heron import cli
from heron.cli import main
from tests.nginx_server import needs_nginx, serve
from tests.test_agent_docs import COMPANIES, VENDORS, vendor_left

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "smoke-site.sh"
POINTERS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")

# Полный комплект: 20 §1 «Состав agents/».
KIT_FILES = {
    "README.md",
    "architecture.md",
    "heron-kit.yaml",
    *(
        f"guide/{n}"
        for n in (
            "00-install.md",
            "01-concepts.md",
            "02-first-site.md",
            "03-content.md",
            "04-theme.md",
            "05-seo.md",
            "06-deploy.md",
            "07-theme-author.md",
        )
    ),
    *(f"roles/{n}.md" for n in ("architect", "content", "designer", "builder", "capabilities")),
    *(
        f"spec/{n}"
        for n in ("20-data-contract.md", "21-engine.md", "22-deploy.md", "23-distribution.md")
    ),
    *(
        f"templates/{n}"
        for n in ("structure.md", "site.yaml", "theme.yaml", "page.md", "report.md", "questions.md")
    ),
    *(
        f"schemas/{n}"
        for n in (
            "site.schema.json",
            "theme.schema.json",
            "frontmatter.schema.json",
            "setup.schema.json",
            "errors.json",
            "describe.schema.json",
        )
    ),
    "work/.gitkeep",
    "work/heron-readme.md",
}
SHORT_KIT = {f for f in KIT_FILES if not f.startswith(("guide/", "spec/"))}


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("HERON_NOTES", "HERON_IN_CONTAINER", "HERON_DEBUG", "HERON_CHANNEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "in_container", lambda: False)
    return tmp_path


def run(*args, ok: bool = True, **kwargs):
    result = CliRunner().invoke(main, [str(a) for a in args], **kwargs)
    if ok:
        assert result.exit_code == 0, (args, result.output)
    return result


def manifest(site: Path) -> dict:
    return yaml.safe_load((site / "agents/heron-kit.yaml").read_text(encoding="utf-8"))


def build_agents(site: Path):
    return yaml.safe_load((site / "site.yaml").read_text(encoding="utf-8"))["build"].get("agents")


def kit_files(site: Path) -> set[str]:
    agents = site / "agents"
    return {p.relative_to(agents).as_posix() for p in agents.rglob("*") if p.is_file()}


def snapshot(folder: Path, skip: tuple[str, ...] = ()) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and not p.relative_to(folder).as_posix().startswith(skip)
    }


def same_tree(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(same_tree(a / d, b / d) for d in cmp.common_dirs)


def without_kit(site: Path, target: Path) -> Path:
    """Тот же сайт без agents/ и корневых указателей (времена файлов сохраняются)."""
    shutil.copytree(site, target, ignore=lambda d, names: _kit_names(site, d, names))
    return target


def _kit_names(site: Path, folder: str, names: list[str]) -> list[str]:
    if Path(folder) != site:
        return []
    return [n for n in names if n == "agents" or n in POINTERS]


_LINK = re.compile(r"\]\(([^)\s]+)\)")
_FENCE = re.compile(r"^\s*(```|~~~)")


def relative_links(path: Path):
    """Относительные ссылки markdown вне блоков и спанов кода: (строка, цель)."""
    inside = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if _FENCE.match(line):
            inside = not inside
            continue
        if inside:
            continue
        for target in _LINK.findall(re.sub(r"`[^`]*`", "", line)):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                continue
            yield number, target.split("#", 1)[0]


def dead_links(site: Path) -> list[str]:
    dead = []
    for md in [site / "AGENTS.md", *sorted((site / "agents").rglob("*.md"))]:
        for number, target in relative_links(md):
            dest = (md.parent / target).resolve()
            inside = dest == site.resolve() or site.resolve() in dest.parents
            if not inside or not dest.exists():
                dead.append(f"{md.relative_to(site)}:{number} → {target}")
    return dead


def new_site(lang: str, name: str = "site", *extra) -> Path:
    run("new", name, "--notes", lang, "-y", *extra)
    return Path.cwd() / name


# --- 1. new --notes ru|en -y: дерево комплекта ------------------------------------


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_new_lays_out_a_complete_kit_with_live_links(here, lang):
    site = new_site(lang)
    assert kit_files(site) == KIT_FILES
    lines = (site / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    assert 60 <= len(lines) <= 100, len(lines)
    for name in ("CLAUDE.md", "GEMINI.md"):
        assert (site / name).read_bytes() == b"@AGENTS.md\n", name
    assert dead_links(site) == []

    data = manifest(site)
    assert data["heron_kit"] == 1 and data["lang"] == lang
    assert data["engine"] == heron.__version__
    assert data["contract"] == ".".join(heron.__version__.split(".")[:2])
    listed = {entry["path"]: entry["sha256"] for entry in data["files"]}
    # каждый файл комплекта, кроме work/ и самого манифеста, — в манифесте с верным хешем
    expected = {f for f in KIT_FILES if not f.startswith("work/")} - {"heron-kit.yaml"}
    expected |= {f"root/{name}" for name in POINTERS}
    assert set(listed) == expected
    for rel, digest in listed.items():
        path = site / rel[len("root/") :] if rel.startswith("root/") else site / "agents" / rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, rel


# --- 2. check --strict --json и prod-сборка: комплект невидим -------------------------


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_check_json_and_prod_build_do_not_see_the_kit(here, lang):
    site = new_site(lang)
    result = run("check", "site", "--strict", "--json")
    report = json.loads(result.output)
    assert report["ok"] is True and report["strict"] is True
    assert report["kit"] == {
        "present": True,
        "engine": heron.__version__,
        "lang": lang,
        "current": True,
    }

    run("build", "site", "--env", "prod", "--strict", "--out", "dist-kit")
    dist = here / "dist-kit"
    names = {p.relative_to(dist).as_posix() for p in dist.rglob("*")}
    assert names
    assert not any(n == "agents" or n.startswith("agents/") for n in names)
    assert not names & set(POINTERS) and not any(n.endswith("heron-kit.yaml") for n in names)

    without_kit(site, here / "plain")
    run("build", "plain", "--env", "prod", "--strict", "--out", "dist-plain")
    assert same_tree(dist, here / "dist-plain")

    # сайт, созданный с --no-agents, при тех же ответах собирается в тот же dist
    same = ("--name", "site", "--domain", "site.example")
    run("new", "off", "--notes", lang, *same, "--no-agents", "-y")
    assert not (here / "off" / "agents").exists() and build_agents(here / "off") is False
    run("build", "off", "--env", "prod", "--strict", "--out", "dist-off")
    assert same_tree(dist, here / "dist-off")


# --- 3. образ сайта: nginx отдаёт .md и .yaml текстом, комплекта в нём нет -----------


def _site_with_raw_files(here: Path) -> Path:
    site = new_site("ru")
    static = site / "static"
    (static / "notes.md").write_text("# Notes\n\nPlain markdown.\n", encoding="utf-8")
    (static / "data.yaml").write_text("key: value\n", encoding="utf-8")
    (static / "AGENTS.md").write_text("# raw pointer, published on purpose\n", encoding="utf-8")
    run("build", "site", "--env", "prod", "--strict", "--out", "dist")
    return here / "dist"


def _smoke(dist: Path, work: Path) -> subprocess.CompletedProcess:
    with serve(dist, work):
        conf = (work / "nginx.conf").read_text(encoding="utf-8")
        port = int(re.search(r"listen\s+127\.0\.0\.1:(\d+)", conf).group(1))
        return subprocess.run(
            ["bash", str(SMOKE), f"http://127.0.0.1:{port}", str(dist)],
            capture_output=True,
            text=True,
            timeout=120,
        )


@needs_nginx
def test_site_image_context_has_no_kit_and_smoke_checks_content_type(here):
    dist = _site_with_raw_files(here)
    # контекст Dockerfile.site — эта папка целиком: в ней нет комплекта сайта,
    # а static/AGENTS.md — обычный файл static/ (20 §1)
    assert not (dist / "agents").exists()
    assert not (dist / "CLAUDE.md").exists() and not (dist / "GEMINI.md").exists()
    assert (dist / "AGENTS.md").read_text(encoding="utf-8").startswith("# raw pointer")
    done = _smoke(dist, here / "nginx")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "/AGENTS.md → text/markdown" in done.stdout
    assert "/data.yaml → application/yaml" in done.stdout
    assert "Content-Type сырых файлов: проверено 2, не так: 0" in done.stdout


@needs_nginx
def test_smoke_fails_when_markdown_leaves_as_octet_stream(here):
    dist = _site_with_raw_files(here)
    conf = dist / ".heron-nginx.conf"
    text = conf.read_text(encoding="utf-8")
    broken = re.sub(r"types \{[^}]*\}", "", text, count=1)
    assert broken != text
    conf.write_text(broken, encoding="utf-8")
    done = _smoke(dist, here / "nginx")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "ждали 200 text/markdown" in done.stdout


@needs_nginx
def test_smoke_skips_content_type_when_there_are_no_raw_files(here):
    new_site("en")
    run("build", "site", "--env", "prod", "--strict", "--out", "dist")
    dist = here / "dist"
    assert not [p for p in dist.rglob("*.md") if not p.name.startswith(".")]
    done = _smoke(dist, here / "nginx")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Content-Type" not in done.stdout


# --- 4. init на старом сайте и init --agents по манифесту ------------------------------


def test_init_on_an_old_site_adds_the_kit_and_overwrites_nothing(here):
    site = new_site("ru", "site", "--no-agents")
    # сайт до комплекта: ключа build.agents ещё не было
    text = (site / "site.yaml").read_text(encoding="utf-8")
    (site / "site.yaml").write_text(
        re.sub(r"^  agents: false\n", "", text, flags=re.M), encoding="utf-8"
    )
    before = snapshot(site)
    result = run("init", "site", "-y")
    assert "agents/, AGENTS.md - ru" in result.output
    after = snapshot(site)
    assert {k: after[k] for k in before} == before  # ничего не перезаписано
    added = set(after) - set(before)
    assert added == {f"agents/{f}" for f in KIT_FILES} | set(POINTERS)
    assert dead_links(site) == []

    readme = site / "agents/README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nправка человека\n", encoding="utf-8")
    report = site / "agents/work/report.md"
    report.write_text("# отчёт агента\n", encoding="utf-8")
    result = run("init", "site", "--agents", "-y")
    assert "agents/README.md" in result.output  # правленный назван
    assert readme.read_text(encoding="utf-8").endswith("правка человека\n")
    run("init", "site", "--agents", "--force", "-y")
    assert "правка человека" not in readme.read_text(encoding="utf-8")
    assert report.read_text(encoding="utf-8") == "# отчёт агента\n"  # work/ не трогается


def test_init_agents_replaces_an_untouched_older_file(here):
    site = new_site("en")
    old = b"# older text of the role\n"
    target = site / "agents/roles/designer.md"
    fresh = target.read_bytes()
    target.write_bytes(old)
    kit = site / "agents/heron-kit.yaml"
    text = kit.read_text(encoding="utf-8")
    text = text.replace(hashlib.sha256(fresh).hexdigest(), hashlib.sha256(old).hexdigest())
    text = text.replace(f'engine: "{heron.__version__}"', 'engine: "0.0.1"')
    kit.write_text(text, encoding="utf-8")

    report = json.loads(run("check", "site", "--strict", "--json").output)
    assert report["ok"] is True  # устаревший комплект — сведение, не предупреждение
    assert report["kit"]["current"] is False and report["kit"]["engine"] == "0.0.1"
    run("init", "site", "--agents", "-y")
    assert target.read_bytes() == fresh
    assert manifest(site)["engine"] == heron.__version__


# --- 5. --no-agents держится через init и setup; build.agents: kit ---------------------


def test_disabled_kit_survives_init_and_setup_and_comes_back_on_request(here):
    site = new_site("ru", "site", "--no-agents")
    assert build_agents(site) is False
    run("init", "site", "-y")
    run("init", "site", "--force", "-y")
    assert not (site / "agents").exists() and not (site / "AGENTS.md").exists()

    answers = run("setup", "site", "--dump").output
    answers = answers.replace("title_suffix: ''", "title_suffix: ' | Test'")
    assert "' | Test'" in answers
    (here / "answers.yaml").write_text(answers, encoding="utf-8")
    run("setup", "site", "--answers", "answers.yaml")
    assert "' | Test'" in (site / "site.yaml").read_text(encoding="utf-8")
    assert build_agents(site) is False
    assert not (site / "agents").exists() and not (site / "AGENTS.md").exists()

    run("init", "site", "--agents", "-y")
    assert build_agents(site) is True
    assert kit_files(site) == KIT_FILES


def test_short_kit_from_build_agents_kit(here):
    site = new_site("ru", "site", "--no-agents")
    text = (site / "site.yaml").read_text(encoding="utf-8")
    text = text.replace("  agents: false", "  agents: kit")
    (site / "site.yaml").write_text(text, encoding="utf-8")
    run("init", "site", "-y")
    assert kit_files(site) == SHORT_KIT
    assert build_agents(site) == "kit"
    listed = {e["path"] for e in manifest(site)["files"]}
    assert not any(p.startswith(("guide/", "spec/")) for p in listed)


# --- 6. агент-нейтральность с белым списком --------------------------------------------

# Белый список 23 §12 и его проверка — общие с tests/test_agent_docs.py
# (NEUTRAL_WHITELIST, vendor_left): комплект сайта — те же файлы docs/<язык>/.


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_kit_texts_are_agent_neutral(here, lang):
    site = new_site(lang)
    bad = []
    kit = site / "agents"
    for path in [site / "AGENTS.md", *sorted(kit.rglob("*"))]:
        if not path.is_file():
            continue
        # белый список 23 §12 — по файлу комплекта; тело AGENTS.md сайта — текст
        # agents/README.md (20 §1), у него белый список README
        kit_path = path.relative_to(kit).as_posix() if path.is_relative_to(kit) else "README.md"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if VENDORS.search(line) and vendor_left(kit_path, line):
                bad.append(f"{path.relative_to(site)}:{number}: {line.strip()[:120]}")
    assert not bad, "\n".join(bad)
    # «Anthropic» и «OpenAI» — ни в одной строке комплекта, даже в перечне
    texts = [p.read_text(encoding="utf-8") for p in kit.rglob("*.md")]
    text = "\n".join([*texts, (site / "AGENTS.md").read_text(encoding="utf-8")])
    assert not COMPANIES.search(text)


def test_engine_code_names_no_agent_except_the_llms_hint():
    bad = []
    for path in sorted((ROOT / "heron").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".svg"}:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            rest = re.sub(r"CLAUDE\.md|GEMINI\.md|\bcursor:\s", "", line)
            if not VENDORS.search(rest):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel == "heron/setup/page.js" and "g_ai_about:" in line:
                continue  # подпись группы llms.txt в конфигураторе
            bad.append(f"{rel}:{number}: {line.strip()[:120]}")
    assert not bad, "\n".join(bad)


# --- 7. язык: флаг > HERON_NOTES > build.notes > en ------------------------------------


@pytest.mark.parametrize(
    ("flag", "env", "expected"),
    [(None, None, "ru"), (None, "en", "en"), ("ru", "en", "ru"), ("en", None, "en")],
)
def test_kit_language_priority_on_init(here, monkeypatch, flag, env, expected):
    site = new_site("ru", "site", "--no-agents")  # build.notes: ru
    if env:
        monkeypatch.setenv("HERON_NOTES", env)
    run("init", "site", "--agents", "-y", *(["--notes", flag] if flag else []))
    assert manifest(site)["lang"] == expected


def test_kit_language_defaults_to_en_without_anything(here):
    run("new", "site", "-y")
    assert manifest(here / "site")["lang"] == "en"


@pytest.mark.parametrize(
    ("flag", "env", "site_notes", "expected"),
    [
        ("ru", "en", "en", "ru"),
        (None, "ru", "en", "ru"),
        (None, None, "ru", "ru"),
        (None, None, None, "en"),
    ],
)
def test_docs_language_priority(here, monkeypatch, flag, env, site_notes, expected):
    if site_notes:
        new_site(site_notes)
        monkeypatch.chdir(here / "site")
    if env:
        monkeypatch.setenv("HERON_NOTES", env)
    result = run("docs", "kit", *(["--lang", flag] if flag else []))
    first = result.output.splitlines()[0]
    has_en = (ROOT / "docs" / "en" / "README.md").is_file()
    if expected == "ru":
        assert first == "# HERON для агентов", first
    elif has_en:
        assert first.startswith("# HERON for agents"), first
    else:
        assert first == "[ru: no English translation yet]", first


# --- 8. из образа ---------------------------------------------------------------------

IMAGE = os.environ.get("HERON_E2E_IMAGE")
if IMAGE and shutil.which("docker") is None:
    raise RuntimeError("HERON_E2E_IMAGE задан, а docker не найден")
needs_image = pytest.mark.skipif(not IMAGE, reason="образ не задан: HERON_E2E_IMAGE")


def image(mount: Path, *args: str) -> subprocess.CompletedProcess:
    """Образ так, как его запускают человек и агент: только папка, без сети и прав."""
    mount.chmod(0o777)
    return subprocess.run(
        [
            "docker", "run", "--rm", "--read-only", "--tmpfs", "/tmp", "--cap-drop=ALL",
            "--network", "none", "--security-opt", "no-new-privileges",
            "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{mount}:/site", "-w", "/site",
            IMAGE, *args,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )  # fmt: skip


@needs_image
def test_image_docs_and_schema(tmp_path):
    kit = image(tmp_path, "docs", "--lang", "en", "kit")
    assert kit.returncode == 0 and kit.stdout.strip(), kit.stderr
    contract = image(tmp_path, "docs", "--lang", "ru", "contract")
    assert contract.returncode == 0 and "контракт данных" in contract.stdout.splitlines()[0]
    for n in (1, 2):
        done = image(tmp_path, "schema", "--export", f"schema{n}")
        assert done.returncode == 0, done.stderr
    assert same_tree(tmp_path / "schema1", tmp_path / "schema2")
    assert {p.name for p in (tmp_path / "schema1").iterdir()} == {
        n.split("/")[1] for n in KIT_FILES if n.startswith("schemas/")
    }
    every = image(tmp_path, "docs", "--export", "all", "--all-langs")
    assert every.returncode == 0, every.stderr
    assert (tmp_path / "all/ru/README.md").is_file() and (tmp_path / "all/en/README.md").is_file()


@needs_image
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_image_new_check_build(tmp_path, lang):
    assert image(tmp_path, "new", "site", "--notes", lang, "-y").returncode == 0
    site = tmp_path / "site"
    assert kit_files(site) == KIT_FILES and dead_links(site) == []
    checked = image(tmp_path, "check", "site", "--strict", "--json")
    assert checked.returncode == 0, checked.stdout
    assert json.loads(checked.stdout)["kit"]["present"] is True
    built = image(tmp_path, "build", "site", "--env", "prod", "--strict", "--out", "dist")
    assert built.returncode == 0, built.stdout + built.stderr
    without_kit(site, tmp_path / "plain")
    again = image(tmp_path, "build", "plain", "--env", "prod", "--strict", "--out", "dist-plain")
    assert again.returncode == 0
    assert same_tree(tmp_path / "dist", tmp_path / "dist-plain")
