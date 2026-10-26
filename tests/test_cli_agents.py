"""Командная строка и комплект для агентов: new/init, docs --lang, schema, check --json.

Спецификация: docs/ru/spec/21-engine.md, раздел 10; 20 §1 «Комплект для агентов»; 21 §12.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import heron
from heron import cli, docs
from heron.cli import main
from heron.contracts.schemas import FILES as SCHEMA_FILES
from heron.contracts.schemas import all_schemas
from heron.core import build as pipeline
from heron.core.report import KitStatus, Report, kit_status

HAS_EN = (docs.root() / "docs" / "en" / "README.md").is_file()
# Имена инструментов — только в перечне «кто какой файл читает» документации, не в справке.
AGENT_NAMES = re.compile(
    r"\b(Claude|Codex|Cursor|Copilot|Windsurf|Amp|Jules|Devin|Zed|opencode|Gemini|Aider|"
    r"Anthropic|OpenAI)\b"
)


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("HERON_NOTES", "HERON_IN_CONTAINER", "HERON_DEBUG", "HERON_CHANNEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "in_container", lambda: False)
    return tmp_path


def run(*args, **kwargs):
    return CliRunner().invoke(main, list(args), **kwargs)


def config(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))


def manifest(root: Path) -> dict:
    return yaml.safe_load((root / "agents/heron-kit.yaml").read_text(encoding="utf-8"))


# --- new ----------------------------------------------------------------------


def test_new_ru_lays_out_the_kit(here):
    result = run("new", "site", "--notes", "ru", "-y")
    assert result.exit_code == 0, result.output
    root = here / "site"
    assert manifest(root)["lang"] == "ru"
    assert (root / "agents/roles/architect.md").read_bytes() == (
        docs.root() / "docs/ru/roles/architect.md"
    ).read_bytes()
    lines = (root / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    assert 60 <= len(lines) <= 100
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (root / "GEMINI.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert config(root)["build"]["agents"] is True
    # одна строка сводки, а не тридцать путей agents/…
    assert "инструкции для агентов: agents/, AGENTS.md — ru, файлов" in result.output
    assert "agents/roles" not in result.output


def test_new_verbose_lists_kit_files(here):
    result = run("new", "site", "--notes", "ru", "-y", "-v")
    assert result.exit_code == 0, result.output
    assert "+ agents/roles/architect.md" in result.output
    assert "+ AGENTS.md" in result.output


def test_new_en_uses_english_or_marks_fallback(here):
    result = run("new", "site", "--notes", "en", "-y")
    assert result.exit_code == 0, result.output
    root = here / "site"
    data = manifest(root)
    assert data["lang"] == "en"
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# site — for agents")
    assert "agent instructions: agents/, AGENTS.md — en" in result.output
    if HAS_EN:
        assert (root / "agents/README.md").read_bytes() == (
            docs.root() / "docs/en/README.md"
        ).read_bytes()
    else:
        assert "[ru: перевода на en пока нет]" in text
        assert "no en translation yet, placed in ru" in result.output
        assert {e.get("lang") for e in data["files"] if e["path"] == "README.md"} == {"ru"}


@pytest.mark.parametrize(
    ("flag", "env", "expected"),
    [(None, None, "en"), (None, "ru", "ru"), ("en", "ru", "en"), ("ru", None, "ru")],
)
def test_kit_language_flag_then_env_then_default(here, monkeypatch, flag, env, expected):
    if env:
        monkeypatch.setenv("HERON_NOTES", env)
    args = ["new", "site", "-y"] + (["--notes", flag] if flag else [])
    assert run(*args).exit_code == 0
    assert manifest(here / "site")["lang"] == expected


def test_kit_language_from_build_notes_on_init(here):
    assert run("new", "site", "--notes", "ru", "-y", "--no-agents").exit_code == 0
    result = run("init", "site", "--agents")
    assert result.exit_code == 0, result.output
    assert manifest(here / "site")["lang"] == "ru"  # build.notes сайта


def test_new_no_agents(here):
    result = run("new", "site", "-y", "--no-agents")
    assert result.exit_code == 0, result.output
    root = here / "site"
    assert not (root / "agents").exists()
    assert not any((root / name).exists() for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"))
    assert config(root)["build"]["agents"] is False
    assert "build.agents: false" in result.output and "heron init --agents" in result.output


def test_new_in_repository_with_agents_md(here):
    root = here / "repo"
    root.mkdir()
    (root / "AGENTS.md").write_text("# repo\n", encoding="utf-8")
    result = run("new", "repo", "-y")
    assert result.exit_code == 0, result.output
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# repo\n"
    assert (root / "agents/README.md").is_file()


# --- init ---------------------------------------------------------------------


def test_init_keeps_kit_disabled_and_agents_turns_it_on(here):
    assert run("new", "site", "-y", "--no-agents").exit_code == 0
    root = here / "site"
    result = run("init", "site")
    assert result.exit_code == 0, result.output
    assert not (root / "agents").exists() and config(root)["build"]["agents"] is False
    assert "build.agents: false" in result.output

    result = run("init", "site", "--agents")
    assert result.exit_code == 0, result.output
    assert (root / "agents/heron-kit.yaml").is_file() and (root / "AGENTS.md").is_file()
    assert config(root)["build"]["agents"] is True


def test_init_no_agents_writes_false_and_keeps_files(here):
    assert run("new", "site", "-y").exit_code == 0
    root = here / "site"
    readme = (root / "agents/README.md").read_bytes()
    result = run("init", "site", "--no-agents")
    assert result.exit_code == 0, result.output
    assert config(root)["build"]["agents"] is False
    assert (root / "agents/README.md").read_bytes() == readme


def test_init_agents_skips_edited_and_force_replaces(here):
    assert run("new", "site", "--notes", "ru", "-y").exit_code == 0
    root = here / "site"
    fresh = (root / "AGENTS.md").read_bytes()
    (root / "AGENTS.md").write_text("# edited by a person\n", encoding="utf-8")
    (root / "content/en/404.md").unlink()

    result = run("init", "site", "--agents")
    assert result.exit_code == 0, result.output
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# edited by a person\n"
    assert "правлен вами, не тронут: AGENTS.md" in result.output
    assert "инструкции для агентов обновлены (ru)" in result.output
    assert not (root / "content/en/404.md").exists()  # --agents трогает только комплект

    result = run("init", "site", "--agents", "--force")
    assert result.exit_code == 0, result.output
    assert (root / "AGENTS.md").read_bytes() == fresh
    assert "правлен вами" not in result.output


def test_init_agents_replaces_untouched_older_file(here):
    assert run("new", "site", "-y").exit_code == 0
    root = here / "site"
    rel = "roles/designer.md"
    fresh = (root / "agents" / rel).read_bytes()
    old = b"# older engine\n"
    (root / "agents" / rel).write_bytes(old)
    path = root / "agents/heron-kit.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for entry in data["files"]:
        if entry["path"] == rel:
            entry["sha256"] = hashlib.sha256(old).hexdigest()
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run("init", "site", "--agents")
    assert result.exit_code == 0, result.output
    assert (root / "agents" / rel).read_bytes() == fresh
    assert "edited by you" not in result.output
    # заменён ровно один файл: манифест в счёт не идёт
    assert "agent instructions updated (en): 1 replaced, 0 added" in result.output


def test_init_plain_adds_only_missing_kit_files(here):
    assert run("new", "site", "-y").exit_code == 0
    root = here / "site"
    (root / "agents/roles/content.md").write_text("mine\n", encoding="utf-8")
    (root / "agents/roles/builder.md").unlink()
    result = run("init", "site")
    assert result.exit_code == 0, result.output
    assert (root / "agents/roles/builder.md").is_file()
    assert (root / "agents/roles/content.md").read_text(encoding="utf-8") == "mine\n"


def test_init_agents_and_no_agents_together_is_usage_error(here):
    assert run("new", "site", "-y").exit_code == 0
    result = run("init", "site", "--agents", "--no-agents")
    assert result.exit_code == 2
    assert "--agents" in result.output and "--no-agents" in result.output


# --- docs ---------------------------------------------------------------------


def test_docs_lang_en_kit(here):
    result = run("docs", "--lang", "en", "kit")
    assert result.exit_code == 0, result.output
    if HAS_EN:
        assert result.output == (docs.root() / "docs/en/README.md").read_text(encoding="utf-8")
    else:
        first, _, rest = result.output.partition("\n\n")
        assert first == "[ru: перевода на en пока нет]"
        assert rest == (docs.root() / "docs/ru/README.md").read_text(encoding="utf-8")


def test_docs_lang_ru_contents_and_language_from_site_yaml(here):
    ru = run("docs", "--lang", "ru")
    assert ru.exit_code == 0 and "Роли агентов:" in ru.output
    en = run("docs")
    assert en.exit_code == 0 and "Agent roles:" in en.output  # по умолчанию en
    assert run("new", ".", "--notes", "ru", "-y", "--no-agents").exit_code == 0
    from_site = run("docs")
    assert "Роли агентов:" in from_site.output  # build.notes текущей папки
    assert "Agent roles:" in run("docs", "--lang", "en").output  # флаг сильнее


def test_docs_unknown_topic_and_template_on_language(here):
    result = run("docs", "--lang", "en", "nonsense")
    assert result.exit_code == 1 and "heron docs" in result.output
    result = run("docs", "--lang", "en", "template", "nope.md")
    assert result.exit_code == 1 and "page.md" in result.output


def test_docs_export_all_langs(here):
    result = run("docs", "--export", "d", "--all-langs")
    assert result.exit_code == 0, result.output
    for lang in ("ru", "en"):
        assert (here / "d" / lang / "README.md").is_file()
    assert not (here / "d" / "AGENTS.md").exists()


def test_docs_export_one_language_is_the_kit(here):
    result = run("docs", "--lang", "ru", "--export", "d")
    assert result.exit_code == 0, result.output
    assert (here / "d/README.md").is_file() and (here / "d/AGENTS.md").is_file()
    assert sorted(p.name for p in (here / "d/schemas").iterdir()) == sorted(SCHEMA_FILES)
    assert f"Начать с {Path('d') / 'README.md'}" in result.output


def test_docs_all_langs_without_export_is_usage_error(here):
    result = run("docs", "--all-langs")
    assert result.exit_code == 2
    assert "--export" in result.output


# --- schema -------------------------------------------------------------------


def test_schema_export_writes_five_files_deterministically(here):
    first = run("schema", "--export", "a")
    second = run("schema", "--export", "b")
    assert first.exit_code == 0 and second.exit_code == 0, first.output
    assert sorted(p.name for p in (here / "a").iterdir()) == sorted(SCHEMA_FILES)
    for name in SCHEMA_FILES:
        assert (here / "a" / name).read_bytes() == (here / "b" / name).read_bytes()
        assert (here / "a" / name).read_text(encoding="utf-8") == all_schemas()[name]
    assert str(Path("a") / "site.schema.json") in first.output


@pytest.mark.parametrize(
    ("flag", "name"),
    [
        (None, "site.schema.json"),
        ("--site", "site.schema.json"),
        ("--theme", "theme.schema.json"),
        ("--frontmatter", "frontmatter.schema.json"),
        ("--setup", "setup.schema.json"),
        ("--errors", "errors.json"),
    ],
)
def test_schema_prints_one_document(here, flag, name):
    result = run("schema", *([flag] if flag else []))
    assert result.exit_code == 0, result.output
    assert result.output == all_schemas()[name]
    major, minor, *_ = heron.__version__.split(".")
    assert json.loads(result.output)["$id"] == (
        f"https://sitebuilder.heron.software/schema/{major}.{minor}/{name}"
    )


def test_schema_two_kinds_is_usage_error(here):
    result = run("schema", "--site", "--theme")
    assert result.exit_code == 2


def test_schema_export_does_not_follow_a_symlink(here):
    outside = here / "outside.json"
    outside.write_text("keep\n", encoding="utf-8")
    (here / "out").mkdir()
    (here / "out" / "errors.json").symlink_to(outside)
    result = run("schema", "--export", "out")
    assert result.exit_code == 1
    assert "E024" in result.output
    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert not (here / "out" / "site.schema.json").exists()  # проверка — до первой записи


# --- check --------------------------------------------------------------------


def test_check_json_has_kit(here):
    assert run("new", "site", "--notes", "ru", "-y").exit_code == 0
    result = run("check", "site", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["kit"] == {
        "present": True,
        "engine": heron.__version__,
        "lang": "ru",
        "current": True,
    }
    assert data["ok"] is True


def test_check_json_kit_when_config_is_broken(here):
    assert run("new", "site", "-y").exit_code == 0
    (here / "site/site.yaml").write_text("heron: '>=0.1'\nsite: [broken\n", encoding="utf-8")
    result = run("check", "site", "--json")
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["kit"]["present"] is True and data["kit"]["lang"] == "en"
    assert data["errors"]


def test_check_text_kit_lines(here):
    assert run("new", "site", "--notes", "ru", "-y").exit_code == 0
    result = run("check", "site")
    assert result.exit_code == 0, result.output
    found = f"`agents/`: инструкции для агентов, движок {heron.__version__}, ru; в сборку не входит"
    assert found in result.output
    assert run("init", "site", "--no-agents").exit_code == 0
    assert "комплект отключён" in run("check", "site").output


def test_kit_lines_come_from_messages(tmp_path):
    def line(kit: KitStatus, lang: str) -> str:
        return Report(kit=kit, notes_lang=lang).kit_line()

    assert line(KitStatus(), "ru") == "комплекта нет — `heron init`"
    assert line(KitStatus(), "en") == "no agent kit — `heron init`"
    assert line(KitStatus(disabled=True), "ru") == "комплект отключён"
    assert line(KitStatus(present=True), "ru") == (
        "`agents/`: инструкции для агентов, манифест не прочитан; в сборку не входит"
    )
    old = KitStatus(present=True, engine="0.0.1", lang="ru", current=False)
    assert line(old, "ru") == (
        f"комплект от 0.0.1, движок {heron.__version__} — обновить: `heron init --agents`"
    )
    assert line(old, "en") == (
        f"kit from 0.0.1, engine {heron.__version__} — update: `heron init --agents`"
    )
    from heron.core import report

    assert not hasattr(report, "_KIT_TEXT")


@pytest.mark.parametrize("engine", ["١.٠", "0.١.0", "１.0"])
def test_kit_engine_version_is_ascii_only(tmp_path, engine):
    from tests.sites import config as site_config

    kit = tmp_path / "agents"
    kit.mkdir()
    (kit / "heron-kit.yaml").write_text(f'engine: "{engine}"\nlang: ru\n', encoding="utf-8")
    status = kit_status(tmp_path, site_config())
    assert status.present is True and status.engine is None and status.current is None


# --- сборка и справка ---------------------------------------------------------------


def test_build_strict_of_created_site_has_no_kit_in_dist(here):
    assert run("new", "site", "--notes", "ru", "-y").exit_code == 0
    result = pipeline.run(here / "site", strict=True)
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = here / "site" / "dist"
    names = {p.relative_to(dist).as_posix() for p in dist.rglob("*")}
    assert names and not any(n == "agents" or n.startswith("agents/") for n in names)
    assert not names & {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}


@pytest.mark.parametrize(
    "args", [["--help"], ["docs", "--help"], ["new", "--help"], ["init", "--help"]]
)
def test_help_names_no_specific_agent(here, args):
    result = run(*args)
    assert result.exit_code == 0
    assert not AGENT_NAMES.search(result.output), AGENT_NAMES.search(result.output)
    # и имён их файлов-указателей: справка говорит «агент», не называя инструмент
    assert "CLAUDE.md" not in result.output and "GEMINI.md" not in result.output


def test_docs_help_mentions_spec_and_options(here):
    text = run("docs", "--help").output
    assert "--lang" in text and "--all-langs" in text and "21 §10" in text
    assert "--export" in run("schema", "--help").output


# --- безопасность записи (E12.S2.T9) ----------------------------------------------


def test_cli_docs_export_through_a_link_is_e024(here):
    outside = here / "outside.md"
    outside.write_text("keep\n", encoding="utf-8")
    (here / "d").mkdir()
    (here / "d" / "README.md").symlink_to(outside)
    result = run("docs", "--lang", "ru", "--export", "d")
    assert result.exit_code == 1
    assert "E024" in result.output
    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_cli_new_with_agents_link_outside_fails_before_writing(here):
    (here / "outside").mkdir()
    (here / "s").mkdir()
    (here / "s" / "agents").symlink_to(here / "outside", target_is_directory=True)
    result = run("new", "s", "-y")
    assert result.exit_code == 1 and "E024" in result.output
    assert not (here / "s" / "site.yaml").exists()
    assert list((here / "outside").iterdir()) == []
