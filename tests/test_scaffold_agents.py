"""Комплект для агентов в папке сайта: состав, манифест, указатели, обновление (20 §1)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
import yaml

import heron
from heron import docs
from heron.contracts.schemas import FILES as SCHEMA_FILES
from heron.contracts.schemas import all_schemas
from heron.core.errors import HeronError
from heron.scaffold import agents

DECLARED = {
    "name": "Demo",
    "domain": "demo.example",
    "languages": ["en", "ru"],
    "default_lang": "en",
}
HAS_EN = (docs.root() / "docs" / "en" / "README.md").is_file()


def put(root: Path, lang: str = "ru", **kwargs) -> agents.KitPlan:
    root.mkdir(parents=True, exist_ok=True)
    return agents.place(
        root, lang, agents.fields(root, DECLARED, lang), mode=kwargs.pop("mode", "create"), **kwargs
    )


def kit_tree(root: Path) -> set[str]:
    base = root / "agents"
    return {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}


def load_manifest(root: Path) -> dict:
    return yaml.safe_load((root / "agents" / "heron-kit.yaml").read_text(encoding="utf-8"))


def md_links(text: str) -> list[str]:
    """Относительные ссылки markdown вне кода: внешние и от корня сайта пропускаются."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    out = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        target = target.split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:", "/")):
            continue
        out.append(target)
    return out


# --- состав -------------------------------------------------------------------


def test_create_ru_lays_out_the_whole_kit(tmp_path):
    root = tmp_path / "site"
    plan = put(root, "ru")
    files = kit_tree(root)
    assert "README.md" in files and "architecture.md" in files
    count = {
        folder: len([f for f in files if f.startswith(f"{folder}/")])
        for folder in ("roles", "templates", "guide", "spec", "schemas")
    }
    assert count == {"roles": 5, "templates": 6, "guide": 6, "spec": 4, "schemas": 5}
    assert {f"schemas/{name}" for name in SCHEMA_FILES} <= files
    assert {"work/.gitkeep", "work/heron-readme.md", "heron-kit.yaml"} <= files
    for name in agents.ROOT_FILES:
        assert (root / name).is_file()
    # ровно дерево docs/ru + схемы + work + манифест
    assert files == set(docs.tree("ru")) | {
        *(f"schemas/{n}" for n in SCHEMA_FILES),
        "work/.gitkeep",
        "work/heron-readme.md",
        "heron-kit.yaml",
    }
    assert set(plan.created) == {f"agents/{f}" for f in files} | set(agents.ROOT_FILES)
    assert plan.files == len(plan.created)
    assert not plan.skipped and not plan.updated and not plan.edited


def test_docs_are_copied_byte_for_byte_and_schemas_match(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    for rel, have in docs.tree("ru").items():
        assert (root / "agents" / rel).read_bytes() == (
            docs.root() / "docs" / have / rel
        ).read_bytes(), rel
    for name, text in all_schemas().items():
        assert (root / "agents" / "schemas" / name).read_text(encoding="utf-8") == text
    assert (root / "agents/work/.gitkeep").read_bytes() == b""
    note = (root / "agents/work/heron-readme.md").read_text(encoding="utf-8")
    assert "structure.md" in note and "questions.md" in note and "report.md" in note


def test_manifest_lists_every_file_with_its_sha256(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    data = load_manifest(root)
    major, minor, *_ = heron.__version__.split(".")
    assert data["heron_kit"] == 1
    assert data["engine"] == heron.__version__
    assert data["contract"] == f"{major}.{minor}"
    assert data["lang"] == "ru"
    assert data["channel"] == "prod"
    assert data["docs_url"] == "https://github.com/FMSTM/HERON/blob/prod/docs/ru/"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", data["created"])
    listed = {entry["path"]: entry["sha256"] for entry in data["files"]}
    paths = [entry["path"] for entry in data["files"]]
    assert paths == sorted(paths)
    expected = {f for f in kit_tree(root) if not f.startswith("work/")} - {"heron-kit.yaml"}
    expected |= {f"root/{name}" for name in agents.ROOT_FILES}
    assert set(listed) == expected
    for rel, digest in listed.items():
        path = root / agents._site_rel(rel)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, rel
    text = (root / "agents/heron-kit.yaml").read_text(encoding="utf-8")
    assert "\r" not in text and "{" not in text  # блочный YAML, LF


def test_agents_md_and_pointers(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert 60 <= len(text.splitlines()) <= 100
    assert text.startswith("# Demo — для агентов\n")
    assert "en, ru" in text and "demo.example" in text and heron.__version__ in text
    assert "docker run --rm ghcr.io/fmstm/heron:prod docs --lang ru" in text
    assert "<о проекте: заполняет архитектор>" in text
    # тело — README комплекта со ссылками, направленными в agents/
    readme = (root / "agents/README.md").read_text(encoding="utf-8")
    assert readme.splitlines()[0] in text
    assert "](agents/roles/architect.md)" in text and "](roles/architect.md)" not in text
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (root / "GEMINI.md").read_text(encoding="utf-8") == "@AGENTS.md\n"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_relative_link_resolves(tmp_path, lang):
    root = tmp_path / "site"
    put(root, lang)
    checked = 0
    for path in [root / "AGENTS.md", *(root / "agents").rglob("*.md")]:
        for link in md_links(path.read_text(encoding="utf-8")):
            assert (path.parent / link).exists(), f"{path.relative_to(root)} → {link}"
            checked += 1
    assert checked > 20


def test_level_kit_leaves_out_guides_and_specs(tmp_path):
    root = tmp_path / "site"
    plan = put(root, "ru", level="kit")
    files = kit_tree(root)
    assert not any(f.startswith(("guide/", "spec/")) for f in files)
    assert {"README.md", "roles/architect.md", "templates/page.md"} <= files
    assert not any(e["path"].startswith(("guide/", "spec/")) for e in load_manifest(root)["files"])
    assert plan.level == "kit"
    with pytest.raises(ValueError):
        agents.kit_files("ru", "yes")


def test_english_kit_uses_translation_or_marks_fallback(tmp_path):
    root = tmp_path / "site"
    plan = put(root, "en")
    data = load_manifest(root)
    assert data["lang"] == "en"
    assert data["docs_url"].endswith("/docs/en/")
    readme = (root / "agents/README.md").read_bytes()
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# Demo — for agents\n")
    assert "<about the project: the architect fills this in>" in text
    assert 60 <= len(text.splitlines()) <= 100
    marked = {e["path"]: e.get("lang") for e in data["files"]}
    if HAS_EN:
        assert readme == (docs.root() / "docs/en/README.md").read_bytes()
    else:
        assert readme == (docs.root() / "docs/ru/README.md").read_bytes()
        assert marked["README.md"] == "ru"
        assert "agents/README.md" in plan.fallback
        assert "[ru: перевода на en пока нет]" in text
    for rel, have in docs.tree("en").items():
        assert marked[rel] == (None if have == "en" else "ru"), rel


def test_about_comes_from_organization(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "site.yaml").write_text(
        "site:\n  name: Studio\n  domain: studio.example\n  languages: [ru, en]\n"
        "  default_lang: ru\n  theme: main\n"
        "organization:\n  about: Plain about\n  about_ru: Студия  интерьеров\n    в Праге\n",
        encoding="utf-8",
    )
    ru = agents.fields(root, None, "ru")
    assert ru["about"] == "Студия интерьеров в Праге"
    assert (ru["name"], ru["domain"], ru["languages"], ru["default_lang"]) == (
        "Studio",
        "studio.example",
        "ru, en",
        "ru",
    )
    assert agents.fields(root, None, "en")["about"] == "Plain about"
    agents.place(root, "ru", ru)
    assert "**О проекте:** Студия интерьеров в Праге" in (root / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    # параметры вызова сильнее site.yaml; сырой site.yaml — не ошибка
    (root / "site.yaml").write_text("site: [broken\n", encoding="utf-8")
    soft = agents.fields(root, {"name": "Given"}, "en")
    assert soft["name"] == "Given" and soft["about"].startswith("<about")


def test_channel_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HERON_CHANNEL", "beta")
    root = tmp_path / "site"
    put(root, "ru")
    data = load_manifest(root)
    assert data["channel"] == "beta"
    assert data["docs_url"] == "https://github.com/FMSTM/HERON/blob/beta/docs/ru/"
    assert "ghcr.io/fmstm/heron:beta docs --lang ru" in (root / "AGENTS.md").read_text(
        encoding="utf-8"
    )


def test_deterministic_with_source_date_epoch(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1761386400")
    first, second = tmp_path / "a", tmp_path / "b"
    put(first, "ru")
    put(second, "ru")
    files = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(second) for p in second.rglob("*") if p.is_file())
    for rel in files:
        assert (first / rel).read_bytes() == (second / rel).read_bytes(), rel
    assert load_manifest(first)["created"] == "2025-10-25T10:00:00Z"


# --- create поверх существующего ------------------------------------------------


def test_create_does_not_overwrite_without_force(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "AGENTS.md").write_text("# my own\n", encoding="utf-8")
    plan = put(root, "ru")
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# my own\n"
    assert "AGENTS.md" in plan.skipped and "AGENTS.md" not in plan.created
    # повторный create кладёт только недостающее и ничего не перезаписывает
    (root / "agents/roles/content.md").write_text("mine\n", encoding="utf-8")
    (root / "agents/roles/builder.md").unlink()
    again = put(root, "ru")
    assert again.created == ["agents/roles/builder.md"]
    assert (root / "agents/roles/content.md").read_text(encoding="utf-8") == "mine\n"
    forced = put(root, "ru", force=True)
    assert "agents/roles/content.md" in forced.updated
    assert "AGENTS.md" in forced.updated
    assert (root / "AGENTS.md").read_text(encoding="utf-8").startswith("# Demo")


# --- обновление по манифесту ------------------------------------------------------


def _age(root: Path, rel: str, old: bytes) -> None:
    """Сделать файл «прежней версии комплекта»: на диске и в манифесте — `old`."""
    (root / agents._site_rel(rel)).write_bytes(old)
    manifest = root / "agents/heron-kit.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for entry in data["files"]:
        if entry["path"] == rel:
            entry["sha256"] = hashlib.sha256(old).hexdigest()
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_update_replaces_untouched_keeps_edited_and_orphans(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    fresh = (root / "agents/roles/designer.md").read_bytes()
    _age(root, "roles/designer.md", b"# old version of the role\n")
    _age(root, "root/AGENTS.md", b"# old pointer\n")
    (root / "agents/roles/content.md").write_text("# edited by a person\n", encoding="utf-8")
    (root / "agents/work/report.md").write_text("my report\n", encoding="utf-8")
    (root / "agents/work/heron-readme.md").write_text("my note\n", encoding="utf-8")
    # файл прежнего комплекта, которого в новом нет
    (root / "agents/guide/00-old.md").write_text("old guide\n", encoding="utf-8")
    manifest = root / "agents/heron-kit.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["files"].append({"path": "guide/00-old.md", "sha256": "0" * 64})
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (root / "agents/roles/builder.md").unlink()

    plan = put(root, "ru", mode="update")
    assert (root / "agents/roles/designer.md").read_bytes() == fresh
    assert (root / "AGENTS.md").read_text(encoding="utf-8").startswith("# Demo")
    assert {"agents/roles/designer.md", "AGENTS.md"} <= set(plan.updated)
    assert (root / "agents/roles/content.md").read_text(encoding="utf-8") == (
        "# edited by a person\n"
    )
    assert plan.edited == ["agents/roles/content.md"]
    assert any("agents/roles/content.md" in line for line in plan.found)
    assert plan.created == ["agents/roles/builder.md"]
    assert (root / "agents/guide/00-old.md").read_text(encoding="utf-8") == "old guide\n"
    assert plan.orphans == ["agents/guide/00-old.md"]
    assert any("agents/guide/00-old.md" in line for line in plan.found)
    assert (root / "agents/work/report.md").read_text(encoding="utf-8") == "my report\n"
    assert (root / "agents/work/heron-readme.md").read_text(encoding="utf-8") == "my note\n"
    # манифест переписан последним: новая версия, лишнего в нём нет
    listed = {e["path"]: e["sha256"] for e in load_manifest(root)["files"]}
    assert "guide/00-old.md" not in listed
    assert listed["roles/designer.md"] == hashlib.sha256(fresh).hexdigest()
    # правленый файл остаётся правленым и при следующем обновлении
    assert put(root, "ru", mode="update").edited == ["agents/roles/content.md"]


def test_update_with_force_replaces_edited(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    fresh = (root / "agents/roles/content.md").read_bytes()
    (root / "agents/roles/content.md").write_text("# edited\n", encoding="utf-8")
    (root / "agents/work/report.md").write_text("my report\n", encoding="utf-8")
    plan = put(root, "ru", mode="update", force=True)
    assert (root / "agents/roles/content.md").read_bytes() == fresh
    assert "agents/roles/content.md" in plan.updated and not plan.edited
    assert (root / "agents/work/report.md").read_text(encoding="utf-8") == "my report\n"


def test_update_without_manifest_treats_differing_files_as_edited(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    (root / "agents/heron-kit.yaml").write_text("- not: a manifest\n", encoding="utf-8")
    (root / "agents/roles/content.md").write_text("# someone's\n", encoding="utf-8")
    plan = put(root, "ru", mode="update")
    assert plan.edited == ["agents/roles/content.md"]
    assert (root / "agents/roles/content.md").read_text(encoding="utf-8") == "# someone's\n"
    assert load_manifest(root)["heron_kit"] == 1


def test_symlink_outside_is_e024_and_nothing_written_outside(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "site"
    root.mkdir()
    (root / "agents").symlink_to(outside)
    with pytest.raises(HeronError) as caught:
        put(root, "ru")
    assert caught.value.code == "E024"
    assert list(outside.iterdir()) == []


def test_bad_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        agents.place(tmp_path, "ru", {}, mode="replace")  # type: ignore[arg-type]
