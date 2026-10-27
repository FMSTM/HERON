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


GITHUB_LINK = re.compile(r"\]\((https://github\.com/FMSTM/HERON/blob/[^)\s]+)\)")


def _github_links(text: str) -> list[str]:
    return GITHUB_LINK.findall(text)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_level_kit_has_no_dead_links_to_guides_and_specs(tmp_path, lang):
    """Сокращённый комплект: ссылки на guide/ и spec/ — абсолютные, на ветку канала (23 §12)."""
    root = tmp_path / "site"
    put(root, lang, level="kit")
    checked = 0
    absolute: list[str] = []
    for path in [root / "AGENTS.md", *(root / "agents").rglob("*.md")]:
        text = path.read_text(encoding="utf-8")
        for link in md_links(text):
            assert (path.parent / link).exists(), f"{path.relative_to(root)} → {link}"
            checked += 1
        absolute += _github_links(text)
    assert checked > 20
    # ссылки, что в полном комплекте шли в guide/ и spec/, — все стали абсолютными
    full = tmp_path / "full"
    put(full, lang)
    dead = 0
    for path in [full / "AGENTS.md", *(full / "agents").rglob("*.md")]:
        if path.relative_to(full).as_posix().startswith(("agents/guide/", "agents/spec/")):
            continue
        for link in md_links(path.read_text(encoding="utf-8")):
            where = (path.parent / link).resolve()
            if where.is_relative_to((full / "agents").resolve()):
                inner = where.relative_to((full / "agents").resolve()).as_posix()
                dead += inner.startswith(("guide/", "spec/"))
    moved = [url for url in absolute if "/docs/" in url and ("/guide/" in url or "/spec/" in url)]
    assert dead >= 10 and len(moved) == dead
    prefix = "https://github.com/FMSTM/HERON/blob/prod/docs/"
    for url in moved:
        assert url.startswith(prefix), url
        rel = url.removeprefix(prefix).split("#", 1)[0]
        assert (docs.root() / "docs" / rel).is_file(), url  # файл есть в репозитории движка
    # якорь сохраняется, язык — того файла, что лёг бы в полный комплект
    have = docs.tree(lang)["guide/05-seo.md"]
    content = (root / "agents/roles/content.md").read_text(encoding="utf-8")
    assert f"]({prefix}{have}/guide/05-seo.md#" in content
    assert "](../guide/" not in content and "](../README.md)" in content


def test_level_kit_links_follow_the_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("HERON_CHANNEL", "beta")
    root = tmp_path / "site"
    put(root, "ru", level="kit")
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "](https://github.com/FMSTM/HERON/blob/beta/docs/ru/guide/01-concepts.md)" in text
    assert "](https://github.com/FMSTM/HERON/blob/beta/docs/ru/spec/21-engine.md)" in text
    assert "](agents/guide/" not in text and "](agents/spec/" not in text


def test_level_kit_manifest_is_of_the_delivered_files(tmp_path):
    """Манифест — по выложенным байтам: повторное обновление не видит правок."""
    root = tmp_path / "site"
    put(root, "ru", level="kit")
    readme = (root / "agents/README.md").read_bytes()
    assert readme != (docs.root() / "docs/ru/README.md").read_bytes()  # ссылки переписаны
    listed = {e["path"]: e["sha256"] for e in load_manifest(root)["files"]}
    for rel, digest in listed.items():
        path = root / agents._site_rel(rel)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, rel
    again = put(root, "ru", mode="update", level="kit")
    assert not again.edited and not again.forced and not again.created
    assert [rel for rel in again.updated if rel != "agents/heron-kit.yaml"] == []
    # файл без ссылок в guide/ и spec/ — байт в байт
    assert (root / "agents/templates/page.md").read_bytes() == (
        docs.root() / "docs" / docs.tree("ru")["templates/page.md"] / "templates/page.md"
    ).read_bytes()
    # переход kit → true и обратно: нетронутые файлы заменяются, правок нет
    full = put(root, "ru", mode="update")
    assert not full.edited and "agents/README.md" in full.updated
    assert (root / "agents/README.md").read_bytes() == (
        docs.root() / "docs/ru/README.md"
    ).read_bytes()
    back = put(root, "ru", mode="update", level="kit")
    assert not back.edited and "agents/README.md" in back.updated
    assert (root / "agents/README.md").read_bytes() == readme
    assert "agents/guide/01-concepts.md" in back.orphans  # лишние не удаляются


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
        assert "[ru: no English translation yet]" in text
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


def _for_channel(data: bytes, name: str) -> bytes:
    """Ожидаемая подстановка: ветка prod и образ prod в готовой команде → канал `name`."""
    text = data.decode("utf-8").replace(
        "https://github.com/FMSTM/HERON/blob/prod/", f"https://github.com/FMSTM/HERON/blob/{name}/"
    )
    return re.sub(
        r"ghcr\.io/fmstm/heron:prod(?=[\"'\s])", f"ghcr.io/fmstm/heron:{name}", text
    ).encode("utf-8")


def test_kit_body_follows_the_channel(tmp_path, monkeypatch):
    """Канал beta: README комплекта и тело AGENTS.md ведут на ветку и образ beta (23 §12)."""
    monkeypatch.setenv("HERON_CHANNEL", "beta")
    root = tmp_path / "site"
    put(root, "ru")
    readme = (root / "agents/README.md").read_text(encoding="utf-8")
    body = (root / "AGENTS.md").read_text(encoding="utf-8")
    for text in (readme, body):
        assert "blob/prod" not in text and 'ghcr.io/fmstm/heron:prod"' not in text
        assert "https://github.com/FMSTM/HERON/blob/beta/AGENTS.md" in text
        assert 'H="docker run --rm -v $PWD:/site -w /site --user $(id -u):$(id -g) ' in text
        assert 'ghcr.io/fmstm/heron:beta"' in text
    builder = (root / "agents/roles/builder.md").read_text(encoding="utf-8")
    assert 'ghcr.io/fmstm/heron:beta"' in builder and 'heron:prod"' not in builder
    deploy = (root / "agents/guide/06-deploy.md").read_text(encoding="utf-8")
    assert "https://github.com/FMSTM/HERON/blob/beta/env/.env.example" in deploy
    assert "| `ghcr.io/fmstm/heron:prod` |" in deploy  # таблица тегов — описание, не адрес
    # кроме адресов канала — байт в байт с docs/ru
    changed = 0
    for rel, have in docs.tree("ru").items():
        source = (docs.root() / "docs" / have / rel).read_bytes()
        placed = (root / "agents" / rel).read_bytes()
        assert placed == _for_channel(source, "beta"), rel
        changed += placed != source
    assert changed >= 3
    # манифест — по выложенному: повторное обновление без правок
    listed = {e["path"]: e["sha256"] for e in load_manifest(root)["files"]}
    for rel, digest in listed.items():
        assert hashlib.sha256((root / agents._site_rel(rel)).read_bytes()).hexdigest() == digest
    again = put(root, "ru", mode="update")
    assert not again.edited and [r for r in again.updated if r != "agents/heron-kit.yaml"] == []


def test_channel_change_replaces_untouched_files_without_edits(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_CHANNEL", raising=False)
    root = tmp_path / "site"
    put(root, "ru")
    assert b'heron:prod"' in (root / "agents/README.md").read_bytes()
    monkeypatch.setenv("HERON_CHANNEL", "beta")
    plan = put(root, "ru", mode="update")
    assert not plan.edited and not plan.forced
    assert {"agents/README.md", "agents/roles/builder.md", "AGENTS.md"} <= set(plan.updated)
    assert b'heron:beta"' in (root / "agents/README.md").read_bytes()
    assert load_manifest(root)["channel"] == "beta"


def test_docs_export_follows_the_channel_like_the_kit(tmp_path, monkeypatch):
    monkeypatch.setenv("HERON_CHANNEL", "beta")
    site, out, every = tmp_path / "site", tmp_path / "out", tmp_path / "all"
    put(site, "ru")
    docs.export(out, "ru")
    for rel in docs.tree("ru"):
        assert (out / rel).read_bytes() == (site / "agents" / rel).read_bytes(), rel
    assert "blob/beta/AGENTS.md" in (out / "AGENTS.md").read_text(encoding="utf-8")
    docs.export(every, all_langs=True)
    assert (every / "ru/README.md").read_bytes() == (site / "agents/README.md").read_bytes()
    monkeypatch.setenv("HERON_CHANNEL", "prod")
    docs.export(tmp_path / "prod", "ru")
    assert (tmp_path / "prod/README.md").read_bytes() == (
        docs.root() / "docs/ru/README.md"
    ).read_bytes()


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


# --- create()/adopt(): build.agents (S2.T5) ---------------------------------------


def _agents_value(root: Path):
    return yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))["build"]["agents"]


def test_create_places_the_kit_by_default(tmp_path):
    from heron.scaffold import create

    root = tmp_path / "site"
    plan = create(root, name="Demo", languages=["en", "ru"], notes="ru")
    assert (root / "agents/heron-kit.yaml").is_file()
    assert (root / "AGENTS.md").read_text(encoding="utf-8").startswith("# Demo — для агентов")
    assert "**Языки сайта:** en, ru, основной — en; домен — demo.example." in (
        root / "AGENTS.md"
    ).read_text(encoding="utf-8")
    assert _agents_value(root) is True
    assert plan.kit is not None and plan.kit.mode == "create"
    assert "agents/README.md" in plan.created and "AGENTS.md" in plan.created
    assert load_manifest(root)["lang"] == "ru"


def test_create_with_level_kit_and_false(tmp_path):
    from heron.scaffold import create

    short = tmp_path / "short"
    create(short, name="Demo", agents="kit")
    assert _agents_value(short) == "kit"
    assert not (short / "agents/guide").exists() and (short / "agents/roles").is_dir()

    off = tmp_path / "off"
    plan = create(off, name="Demo", agents="false")
    assert _agents_value(off) is False
    assert not (off / "agents").exists()
    assert not any((off / name).exists() for name in agents.ROOT_FILES)
    assert plan.kit is None
    with pytest.raises(ValueError):
        create(tmp_path / "bad", name="Demo", agents="yes")


def test_adopt_keeps_the_kit_off(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "site"
    create(root, name="Demo", agents="false")
    (root / "content/en/index.md").unlink()
    plan = adopt(root)
    assert "content/en/index.md" in plan.created  # остальное скелет достроил
    assert not (root / "agents").exists() and not (root / "AGENTS.md").exists()
    assert plan.kit is None and _agents_value(root) is False


def test_adopt_agents_flag_true_turns_it_back_on(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "site"
    create(root, name="Demo", agents="false")
    before = (root / "site.yaml").read_text(encoding="utf-8")
    plan = adopt(root, agents_flag="true")
    after = (root / "site.yaml").read_text(encoding="utf-8")
    assert _agents_value(root) is True
    # правка точечная: изменилась ровно строка agents
    diff = [(a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b]
    assert diff == [("  agents: false", "  agents: true")]
    assert (root / "agents/heron-kit.yaml").is_file() and (root / "AGENTS.md").is_file()
    assert plan.kit is not None and "agents/README.md" in plan.created


def test_adopt_agents_flag_false_writes_and_leaves_the_kit(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "site"
    create(root, name="Demo")
    readme = (root / "agents/README.md").read_bytes()
    plan = adopt(root, agents_flag="false")
    assert _agents_value(root) is False
    assert (root / "agents/README.md").read_bytes() == readme  # ничего не удалено
    assert plan.kit is None


def test_adopt_agents_only_updates_kit_and_nothing_else(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "site"
    create(root, name="Demo", notes="ru")
    (root / "content/en/404.md").unlink()
    (root / "theme/base.html").write_text("mine\n", encoding="utf-8")
    _age(root, "roles/designer.md", b"# old\n")
    (root / "agents/roles/content.md").write_text("# edited\n", encoding="utf-8")
    plan = adopt(root, agents_only=True, agents_flag="true")
    assert not (root / "content/en/404.md").exists()
    assert (root / "theme/base.html").read_text(encoding="utf-8") == "mine\n"
    assert plan.kit.mode == "update"
    assert plan.kit.edited == ["agents/roles/content.md"]
    assert "agents/roles/designer.md" in plan.kit.updated
    assert all(p.startswith("agents/") or p in agents.ROOT_FILES for p in plan.created)
    assert any("agents/roles/content.md" in line for line in plan.found)


def test_adopt_without_flags_adds_only_missing_kit_files(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "site"
    create(root, name="Demo")
    (root / "agents/roles/content.md").write_text("# edited\n", encoding="utf-8")
    _age(root, "roles/designer.md", b"# old\n")
    (root / "agents/roles/builder.md").unlink()
    plan = adopt(root)
    assert (root / "agents/roles/builder.md").is_file()
    assert (root / "agents/roles/designer.md").read_bytes() == b"# old\n"
    assert (root / "agents/roles/content.md").read_text(encoding="utf-8") == "# edited\n"
    assert plan.kit.mode == "create" and "agents/roles/builder.md" in plan.created


def test_adopt_kit_level_from_site_yaml(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "site"
    create(root, name="Demo", agents="kit")
    plan = adopt(root)
    assert plan.kit.level == "kit" and not (root / "agents/spec").exists()


def test_setup_on_disabled_site_does_not_bring_the_kit_back(tmp_path):
    from heron.scaffold import create
    from heron.setup import apply
    from heron.setup.answers import Answers

    root = tmp_path / "site"
    create(root, name="Demo", agents="false")
    answers = Answers.model_validate(
        {"site": {"name": "Demo", "domain": "demo.example", "languages": ["en", "ru"]}}
    )
    result = apply(root, answers)
    assert "content/ru/index.md" in result.created
    assert not (root / "agents").exists() and not (root / "AGENTS.md").exists()
    assert _agents_value(root) is False


def test_new_in_folder_with_agents_md_keeps_it(tmp_path):
    from heron.scaffold import SERVICE, create, foreign_files

    root = tmp_path / "repo"
    root.mkdir()
    (root / "AGENTS.md").write_text("# the repository's own\n", encoding="utf-8")
    (root / "agents").mkdir()
    assert {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "agents"} <= set(SERVICE)
    assert foreign_files(root) == []
    plan = create(root, name="Demo")
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# the repository's own\n"
    assert "AGENTS.md" in plan.skipped
    assert (root / "agents/README.md").is_file()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("kit", "kit"), ("true", True), ("false", False)],
)
def test_site_config_accepts_agents_values(value, expected):
    from heron.contracts.site import SiteConfig

    data = {"heron": ">=0.1", "site": {"domain": "a.example", "theme": "main"}}
    data["build"] = {"agents": value}
    assert SiteConfig.model_validate(data).build.agents == expected
    assert SiteConfig.model_validate({**data, "build": {}}).build.agents is True


@pytest.mark.parametrize("value", ["yes", "no", 1, "full", None])
def test_site_config_rejects_other_agents_values(tmp_path, value):
    from heron.contracts.site import load_site

    path = tmp_path / "site.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "heron": ">=0.1",
                "site": {"domain": "a.example", "theme": "main"},
                "build": {"agents": value},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HeronError) as caught:
        load_site(path)
    assert caught.value.code == "E011"
    assert "true, kit или false" in caught.value.message


@pytest.mark.parametrize(
    ("text", "expected_line"),
    [
        ("heron: '>=0.1'\nbuild:\n  notes: ru\n  workers: 2\n", "  agents: false"),
        ("heron: '>=0.1'\nbuild:\n  agents: true  # keep me\n", "  agents: false  # keep me"),
        ("heron: '>=0.1'\nsite:\n  theme: main\n", "  agents: false"),
        ("heron: '>=0.1'\nbuild: {notes: ru}\n", "build: {agents: false, notes: ru}"),
    ],
)
def test_set_build_agents_edits_one_line(tmp_path, text, expected_line):
    from heron.scaffold import set_build_agents

    (tmp_path / "site.yaml").write_text(text, encoding="utf-8")
    assert set_build_agents(tmp_path, "false") is True
    after = (tmp_path / "site.yaml").read_text(encoding="utf-8")
    assert expected_line in after.splitlines()
    assert yaml.safe_load(after)["build"]["agents"] is False
    # прочее не тронуто
    for line in text.splitlines():
        if "agents" not in line and "build: {" not in line:
            assert line in after.splitlines()
    assert set_build_agents(tmp_path / "nowhere", "true") is False


def test_site_created_with_kit_builds_the_same_dist(tmp_path, monkeypatch):
    import filecmp

    from heron.core import build as pipeline
    from heron.scaffold import create

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1761386400")
    with_kit, plain = tmp_path / "a" / "site", tmp_path / "b" / "site"
    create(with_kit, name="Demo", languages=["en", "ru"], notes="ru", demo=True)
    create(plain, name="Demo", languages=["en", "ru"], notes="ru", demo=True, place_kit=False)
    assert (with_kit / "agents").is_dir() and not (plain / "agents").exists()
    a = pipeline.run(with_kit, strict=True)
    b = pipeline.run(plain, strict=True)
    assert not a.failed and not b.failed, [str(e) for e in a.collector.errors]

    def tree(root: Path) -> dict[str, bytes]:
        return {
            p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()
        }

    left, right = tree(with_kit / "dist"), tree(plain / "dist")
    assert left.keys() == right.keys()
    assert [k for k in left if left[k] != right[k]] == []
    assert not any(k.startswith("agents") or k in agents.ROOT_FILES for k in left)
    assert filecmp.cmp(with_kit / "site.yaml", plain / "site.yaml", shallow=False)


# --- безопасность записи (E12.S2.T9) ----------------------------------------------


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


@pytest.mark.parametrize(
    "rel", ["agents/roles/content.md", "agents/work", "agents/heron-kit.yaml", "agents/roles"]
)
def test_link_outside_inside_the_kit_is_e024_before_any_write(tmp_path, rel):
    from heron.scaffold import adopt, create

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.md").write_text("keep\n", encoding="utf-8")
    root = tmp_path / "site"
    create(root, name="Demo")
    adopt(root, agents_flag="false")
    target = root / rel
    if target.is_dir():
        import shutil

        shutil.rmtree(target)
        target.symlink_to(outside, target_is_directory=True)
    else:
        target.unlink()
        target.symlink_to(outside / "keep.md")
    before = _snapshot(root)
    (root / "AGENTS.md").write_bytes(b"# old pointer\n")
    before["AGENTS.md"] = b"# old pointer\n"
    with pytest.raises(HeronError) as caught:
        adopt(root, agents_flag="true", force=True)
    assert caught.value.code == "E024"
    assert _snapshot(root) == before  # build.agents: false на месте, AGENTS.md не тронут
    assert _agents_value(root) is False
    assert _snapshot(outside) == {"keep.md": b"keep\n"}


def test_new_in_folder_with_agents_link_outside_writes_nothing(tmp_path):
    from heron.scaffold import create

    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "repo"
    root.mkdir()
    (root / "agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(HeronError) as caught:
        create(root, name="Demo")
    assert caught.value.code == "E024"
    assert sorted(p.name for p in root.iterdir()) == ["agents"]  # скелет не записан
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "bad",
    [
        "../../outside/evil.md",
        "root/../../outside/r.md",
        "/tmp/abs.md",
        "roles/../../../outside/x.md",
        "root/README.md",
    ],
)
def test_manifest_with_escaping_paths_is_treated_as_damaged(tmp_path, bad):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "site"
    put(root, "ru")
    (root / "agents/roles/content.md").write_text("# edited\n", encoding="utf-8")
    manifest = root / "agents/heron-kit.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["files"].append({"path": bad, "sha256": "0" * 64})
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert agents.read_manifest(root).damaged is True
    assert agents.read_manifest(root).files == {}

    plan = put(root, "ru", mode="update")
    assert plan.edited == ["agents/roles/content.md"]  # без манифеста правленое не затирается
    assert not plan.orphans
    assert any("heron-kit.yaml" in line for line in plan.found)
    assert list(outside.iterdir()) == []
    fresh = agents.read_manifest(root)
    assert fresh.damaged is False and bad not in fresh.files  # переписан начисто


def test_manifest_link_inside_or_folder_is_damaged_not_read(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    manifest = root / "agents/heron-kit.yaml"
    manifest.unlink()
    manifest.mkdir()
    assert agents.read_manifest(root).damaged is True
    with pytest.raises(HeronError) as caught:
        put(root, "ru", mode="update")
    assert caught.value.code == "E024"  # писать манифест на место папки нельзя


def test_link_inside_the_site_is_not_written_through(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    designer = (root / "agents/roles/designer.md").read_bytes()
    content = root / "agents/roles/content.md"
    content.unlink()
    content.symlink_to(root / "agents/roles/designer.md")
    plan = put(root, "ru", mode="update", force=True)
    assert content.is_symlink()
    assert (root / "agents/roles/designer.md").read_bytes() == designer
    assert "agents/roles/content.md" in plan.edited


def test_write_files_checks_every_target_first(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep\n", encoding="utf-8")
    target = tmp_path / "out"
    target.mkdir()
    (target / "b.txt").symlink_to(outside)
    with pytest.raises(HeronError) as caught:
        agents.write_files(target, [("a.txt", b"a"), ("b.txt", b"b")])
    assert caught.value.code == "E024"
    assert not (target / "a.txt").exists()
    assert outside.read_text(encoding="utf-8") == "keep\n"
    # сама папка назначения может быть ссылкой — её назвал человек
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    assert agents.write_files(tmp_path / "alias", [("x/y.txt", b"y")]) == ["x/y.txt"]
    assert (real / "x/y.txt").read_bytes() == b"y"


@pytest.mark.parametrize("rel", ["README.md", "roles", "schemas/errors.json"])
def test_docs_export_does_not_write_through_links(tmp_path, rel):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "README.md").write_text("keep\n", encoding="utf-8")
    target = tmp_path / "out"
    (target / rel).parent.mkdir(parents=True, exist_ok=True)
    if rel == "roles":
        (target / rel).symlink_to(outside, target_is_directory=True)
    else:
        (target / rel).symlink_to(outside / "README.md")
    with pytest.raises(HeronError) as caught:
        docs.export(target, "ru")
    assert caught.value.code == "E024"
    assert _snapshot(outside) == {"README.md": b"keep\n"}
    assert not (target / "architecture.md").exists()  # ни одного файла до проверки


def test_docs_export_all_langs_does_not_write_through_links(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "out"
    target.mkdir()
    (target / "en").symlink_to(outside, target_is_directory=True)
    with pytest.raises(HeronError):
        docs.export(target, all_langs=True)
    assert list(outside.iterdir()) == []
    assert not (target / "ru").exists()


def test_setup_checks_kit_targets_before_the_first_write(tmp_path):
    from heron.scaffold import create
    from heron.setup import apply
    from heron.setup.answers import Answers

    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "site"
    create(root, name="Demo", place_kit=False)
    (root / "agents").symlink_to(outside, target_is_directory=True)
    before = _snapshot(root)
    answers = Answers.model_validate(
        {"site": {"name": "Studio", "domain": "studio.example", "languages": ["en", "ru"]}}
    )
    with pytest.raises(HeronError) as caught:
        apply(root, answers)
    assert caught.value.code == "E024"
    assert _snapshot(root) == before  # site.yaml прежний, резервной копии и темы нет
    assert not (root / ".heron-cache").exists()
    assert list(outside.iterdir()) == []


# --- поведение adopt/init (E12.S2.T10) --------------------------------------------

STUDIO = {
    "site": {"name": "Studio", "domain": "studio.example.com", "languages": ["en", "ru"]},
    "about": {
        "type": "LocalBusiness",
        "fields": {"name": "Studio", "about": {"en": "We make things.", "ru": "Мы делаем вещи."}},
    },
}


def test_setup_refreshes_agents_md_from_the_answers(tmp_path):
    from heron.scaffold import create
    from heron.setup import apply
    from heron.setup.answers import Answers

    root = tmp_path / "s"
    create(root, name="s", notes="ru")
    assert "<о проекте: заполняет архитектор>" in (root / "AGENTS.md").read_text(encoding="utf-8")
    apply(root, Answers.model_validate(STUDIO))
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# Studio — для агентов\n")
    assert "**Языки сайта:** en, ru, основной — en; домен — studio.example.com." in text
    expected = agents.fields(root, None, "ru")["about"]
    assert "заполняет архитектор" not in expected
    assert f"**О проекте:** {expected}" in text
    # манифест знает новый AGENTS.md: следующий init --agents считает его нетронутым
    listed = {e["path"]: e["sha256"] for e in load_manifest(root)["files"]}
    assert listed["root/AGENTS.md"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_setup_keeps_an_edited_agents_md(tmp_path):
    from heron.scaffold import create
    from heron.setup import apply
    from heron.setup.answers import Answers

    root = tmp_path / "s"
    create(root, name="s", notes="ru")
    (root / "AGENTS.md").write_text("# our own\n", encoding="utf-8")
    apply(root, Answers.model_validate(STUDIO))
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# our own\n"


def test_plain_adopt_refreshes_only_pointers_and_keeps_manifest_header(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s", notes="ru")
    _age(root, "roles/designer.md", b"# old\n")
    path = root / "agents/heron-kit.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["engine"] = "0.0.9"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    text = (root / "site.yaml").read_text(encoding="utf-8").replace("s.example", "real.example")
    (root / "site.yaml").write_text(text, encoding="utf-8")
    plan = adopt(root)
    assert "домен — real.example" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert plan.kit.updated == ["AGENTS.md", "agents/heron-kit.yaml"]
    assert (root / "agents/roles/designer.md").read_bytes() == b"# old\n"
    after = load_manifest(root)
    assert after["engine"] == "0.0.9"  # комплект не обновлён — версия в манифесте прежняя
    listed = {e["path"]: e["sha256"] for e in after["files"]}
    assert listed["roles/designer.md"] == hashlib.sha256(b"# old\n").hexdigest()
    # init --agents потом обновит нетронутый старый файл
    plan = adopt(root, agents_only=True, agents_flag="true")
    assert "agents/roles/designer.md" in plan.kit.updated


def test_plain_adopt_with_force_does_not_touch_edited_kit_files(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s")
    (root / "agents/roles/content.md").write_text("# edited\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# edited pointer\n", encoding="utf-8")
    (root / "theme/base.html").write_text("mine\n", encoding="utf-8")
    plan = adopt(root, force=True)
    assert (root / "theme/base.html").read_text(encoding="utf-8") != "mine\n"  # --force скелета
    assert (root / "agents/roles/content.md").read_text(encoding="utf-8") == "# edited\n"
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# edited pointer\n"
    assert plan.kit.edited == ["AGENTS.md"] and not plan.kit.forced
    assert "agents/roles/content.md" not in plan.created


def test_force_on_kit_names_overwritten_edited_files(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s")
    (root / "agents/roles/content.md").write_text("# edited\n", encoding="utf-8")
    plan = adopt(root, agents_only=True, agents_flag="true", force=True)
    assert plan.kit.forced == ["agents/roles/content.md"]
    assert "agents/roles/content.md" in plan.kit.updated


def test_agents_flag_true_keeps_level_kit(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s", agents="kit")
    before = (root / "site.yaml").read_bytes()
    plan = adopt(root, agents_only=True, agents_flag="true")
    assert plan.kit.level == "kit"
    assert not (root / "agents/guide").exists() and not (root / "agents/spec").exists()
    assert (root / "site.yaml").read_bytes() == before  # kit не переписан в true
    # явное kit → true по API (не CLI) — пишется
    adopt(root, agents_only=True, agents_flag="kit")
    assert _agents_value(root) == "kit"


@pytest.mark.parametrize(
    ("line", "shown"),
    [
        ('  agents: "yes"', '"yes"'),
        ("  agents:", "null"),
        ("  agents: 1", "1"),
        ("  agents: full", '"full"'),
    ],
)
def test_unclear_agents_value_is_e011_in_init_and_check(tmp_path, line, shown):
    from heron.contracts.site import load_site
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s", place_kit=False)
    text = (root / "site.yaml").read_text(encoding="utf-8").replace("  agents: true", line)
    (root / "site.yaml").write_text(text, encoding="utf-8")
    before = _snapshot(root)
    with pytest.raises(HeronError) as caught:
        adopt(root)
    assert caught.value.code == "E011"
    assert f"build.agents: {shown}" in caught.value.message
    assert "true, kit" in caught.value.hint
    assert _snapshot(root) == before and not (root / "agents").exists()
    with pytest.raises(HeronError) as checked:
        load_site(root / "site.yaml")
    assert checked.value.code == "E011"
    # явный флаг чинит значение
    adopt(root, agents_flag="false")
    assert _agents_value(root) is False


def test_unquoted_yes_is_true_everywhere(tmp_path):
    from heron.contracts.site import load_site
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s", place_kit=False)
    text = (root / "site.yaml").read_text(encoding="utf-8")
    text = text.replace("  agents: true", "  agents: yes")
    (root / "site.yaml").write_text(text, encoding="utf-8")
    assert load_site(root / "site.yaml").build.agents is True
    adopt(root)
    assert (root / "agents/heron-kit.yaml").is_file()


def test_pointer_link_to_agents_md_is_kept(tmp_path):
    root = tmp_path / "s"
    put(root, "ru")
    (root / "CLAUDE.md").unlink()
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    plan = put(root, "ru", mode="update", force=True)
    assert (root / "CLAUDE.md").is_symlink()
    assert "CLAUDE.md" not in plan.edited and "CLAUDE.md" not in plan.updated


def test_docs_export_pointers_match_the_kit(tmp_path, monkeypatch):
    monkeypatch.setenv("HERON_CHANNEL", "   ")
    target = tmp_path / "out"
    docs.export(target, "en")
    text = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "ghcr.io/fmstm/heron:prod docs --lang en" in text  # пустой канал — prod
    assert "](agents/" not in text and "[agents/README.md](README.md)" in text
    if not (docs.root() / "docs/en/README.md").is_file():
        assert "[ru: no English translation yet]" in text
    for name in ("_Blank", "_DEFAULT_HEAD", "_pointer_head", "AGENTS_ROOT"):
        assert not hasattr(docs, name), name
    assert not hasattr(agents, "_TEXT")


# --- язык комплекта при init без флагов (E13.S1.T11) ------------------------------


def _set_notes(root: Path, lang: str) -> None:
    path = root / "site.yaml"
    text = path.read_text(encoding="utf-8")
    changed = re.sub(r"(?m)^(\s+notes:)\s*\w+", rf"\1 {lang}", text, count=1)
    assert changed != text
    path.write_text(changed, encoding="utf-8")


def test_kept_lang_is_the_manifest_language(tmp_path):
    root = tmp_path / "s"
    put(root, "ru")
    assert agents.kept_lang(agents.read_manifest(root), "en") == "ru"
    assert agents.kept_lang(agents.Manifest(), "en") == "en"  # манифеста нет
    damaged = agents.Manifest(header={"lang": "ru"}, present=True, damaged=True)
    assert agents.kept_lang(damaged, "en") == "en"
    odd = agents.Manifest(header={"lang": "de"}, present=True)
    assert agents.kept_lang(odd, "en") == "en"


@pytest.mark.parametrize(("old", "new"), [("ru", "en"), ("en", "ru")])
def test_plain_adopt_keeps_kit_language_and_header_together(tmp_path, old, new):
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s", notes=old)
    (root / "AGENTS.md").unlink()
    (root / "agents/roles/builder.md").unlink()
    text = (root / "site.yaml").read_text(encoding="utf-8").replace("s.example", "real.example")
    (root / "site.yaml").write_text(text, encoding="utf-8")
    _set_notes(root, new)

    plan = adopt(root)
    assert plan.notes == new  # сообщения — на build.notes
    assert plan.kit.lang == old and plan.kit.notes_lang == new and plan.kit.lang_from == ""
    assert load_manifest(root)["lang"] == old
    # недостающее положено на языке снимка, а не build.notes
    expected = agents.root_files(old, agents.fields(root, None, old))["AGENTS.md"]
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == expected
    assert "real.example" in expected
    have = docs.tree(old)["roles/builder.md"]
    assert (root / "agents/roles/builder.md").read_bytes() == (
        docs.root() / "docs" / have / "roles/builder.md"
    ).read_bytes()

    switched = adopt(root, agents_only=True, agents_flag="true")
    assert switched.kit.lang == new and switched.kit.lang_from == old
    assert not switched.kit.notes_lang
    assert load_manifest(root)["lang"] == new
    again = adopt(root)
    assert again.kit.lang == new and not again.kit.notes_lang and not again.kit.lang_from


def test_plain_adopt_without_manifest_uses_build_notes(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s", notes="ru")
    (root / "agents/heron-kit.yaml").unlink()
    _set_notes(root, "en")
    plan = adopt(root)
    assert plan.kit.lang == "en" and not plan.kit.notes_lang
    assert load_manifest(root)["lang"] == "en"


def test_setup_keeps_kit_language_of_the_snapshot(tmp_path):
    from heron.scaffold import adopt, create

    root = tmp_path / "s"
    create(root, name="s", notes="ru")
    before = (root / "agents/heron-kit.yaml").read_bytes()
    plan = adopt(root, notes="en")  # анкета зовёт adopt с языком своих пояснений
    assert plan.kit.lang == "ru" and plan.kit.notes_lang == "en"
    assert (root / "agents/heron-kit.yaml").read_bytes() == before


# --- E13.S1.T17: висячая ссылка или файл на месте папки выгрузки — E024 ------------


def _export(kind: str, target: Path, *flags: str, env: dict[str, str] | None = None):
    from click.testing import CliRunner

    from heron.cli import main

    return CliRunner().invoke(main, [kind, "--export", str(target), *flags], env=env)


def _occupy(tmp_path: Path, how: str) -> Path:
    """Цель выгрузки, занятая не папкой: висячая ссылка, ссылка на файл, файл."""
    target = tmp_path / "out"
    if how == "dangling":
        target.symlink_to(tmp_path / "nowhere", target_is_directory=True)
    elif how == "link-to-file":
        (tmp_path / "file.txt").write_text("keep\n", encoding="utf-8")
        target.symlink_to(tmp_path / "file.txt")
    else:
        target.write_text("keep\n", encoding="utf-8")
    return target


@pytest.mark.parametrize("kind", ["docs", "schema"])
def test_export_into_dangling_link_is_e024_not_a_crash(tmp_path, kind):
    target = _occupy(tmp_path, "dangling")
    before = _snapshot(tmp_path)
    result = _export(kind, target, "--notes", "ru")
    assert result.exit_code == 1
    assert "E024" in result.output
    assert "unexpected error" not in result.output and "engine bug" not in result.output
    assert "FileExistsError" not in result.output
    assert "out: на месте папки символическая ссылка, которая никуда не ведёт" in result.output
    assert "уберите ссылку или файл" in result.output
    assert "a symbolic link that leads nowhere" not in result.output  # один язык (T19)
    assert not (tmp_path / "nowhere").exists()  # по висячей ссылке ничего не создано
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("kind", ["docs", "schema"])
@pytest.mark.parametrize("how", ["link-to-file", "file"])
def test_export_into_file_is_e024(tmp_path, kind, how):
    """Командная строка такую цель отклоняет сама (click, код 2); писатель — E024."""
    from heron.cli import _write_schemas

    target = _occupy(tmp_path, how)
    before = _snapshot(tmp_path)
    with pytest.raises(HeronError) as caught:
        if kind == "docs":
            docs.export(target, "ru")
        else:
            _write_schemas(target, "ru")
    assert caught.value.code == "E024"
    assert "файл или ссылка не на папку" in caught.value.message
    assert "a file or a link to something other" not in caught.value.message  # один язык (T19)
    assert _snapshot(tmp_path) == before


def test_dangling_link_outside_container_path_is_e024(tmp_path):
    """Как в CI: static/agents ведёт на путь, которого в контейнере нет."""
    target = tmp_path / "static" / "agents"
    target.parent.mkdir()
    target.symlink_to(tmp_path / "missing" / "deep" / "agents", target_is_directory=True)
    with pytest.raises(HeronError) as caught:
        docs.export(target, "ru")
    assert caught.value.code == "E024"
    assert caught.value.path == str(target)
    assert "agents: на месте папки символическая ссылка" in caught.value.message
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("how", ["dangling", "file"])
def test_missing_parent_of_the_target_is_checked_too(tmp_path, how):
    """out/sub ещё нет, а out — висячая ссылка или файл: mkdir parents упал бы на out."""
    out = _occupy(tmp_path, how)
    with pytest.raises(HeronError) as caught:
        agents.write_files(out / "sub", [("a.txt", b"a")])
    assert caught.value.code == "E024"
    assert caught.value.path == str(out)


@pytest.mark.parametrize("how", ["dangling", "file"])
def test_non_folder_inside_the_target_is_e024_before_any_write(tmp_path, how):
    target = tmp_path / "out"
    target.mkdir()
    if how == "dangling":
        (target / "roles").symlink_to(target / "nowhere", target_is_directory=True)
    else:
        (target / "roles").write_text("keep\n", encoding="utf-8")
    with pytest.raises(HeronError) as caught:
        docs.export(target, "ru")
    assert caught.value.code == "E024"
    assert caught.value.message.startswith("roles: на месте папки")
    assert not (target / "README.md").exists()  # ни одного файла до проверки
    assert not (target / "nowhere").exists()


@pytest.mark.parametrize("kind", ["docs", "schema"])
def test_export_through_link_to_existing_folder_works(tmp_path, kind):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    result = _export(kind, alias)
    assert result.exit_code == 0, result.output
    name = "README.md" if kind == "docs" else "errors.json"
    assert (real / name).is_file()


# --- E13.S1.T19: подробность E024 из write_files - на одном языке ---------------------


def _error_text(error: HeronError) -> str:
    return f"{error.message}\n{error.hint}"


def _has_cyrillic(text: str) -> bool:
    return any("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in text)


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("how", ["dangling", "file"])
def test_write_files_folder_error_is_in_one_language(tmp_path, lang, how):
    out = _occupy(tmp_path, how)
    with pytest.raises(HeronError) as caught:
        agents.write_files(out, [("a.txt", b"a")], lang)
    text = _error_text(caught.value)
    assert caught.value.code == "E024"
    assert _has_cyrillic(text) is (lang == "ru")
    assert "·" not in caught.value.message
    key = "write_dangling" if how == "dangling" else "write_not_folder"
    from heron.messages import say

    assert say(lang, key) in caught.value.message
    assert say(lang, "write_folder_hint") == caught.value.hint


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_write_files_file_error_is_in_one_language(tmp_path, lang):
    target = tmp_path / "out"
    target.mkdir()
    (target / "a.txt").mkdir()  # на месте файла папка
    with pytest.raises(HeronError) as caught:
        agents.write_files(target, [("a.txt", b"a")], lang)
    assert caught.value.code == "E024"
    assert caught.value.message.startswith("a.txt: ")
    assert _has_cyrillic(_error_text(caught.value)) is (lang == "ru")


def test_write_files_without_language_speaks_english(tmp_path):
    out = _occupy(tmp_path, "file")
    with pytest.raises(HeronError) as caught:
        agents.write_files(out, [("a.txt", b"a")])
    assert not _has_cyrillic(_error_text(caught.value))


def _detail_only_in(output: str, lang: str) -> bool:
    """Подробность E024 (висячая ссылка) в выводе - ровно на языке `lang`.

    Название ошибки в рамке тоже локализовано, поэтому проверяется сама фраза писателя.
    """
    from heron.messages import say

    other = "en" if lang == "ru" else "ru"
    return say(lang, "write_dangling") in output and say(other, "write_dangling") not in output


@pytest.mark.parametrize("kind", ["docs", "schema"])
@pytest.mark.parametrize("lang", ["ru", "en"])
def test_export_error_follows_notes_flag(tmp_path, kind, lang):
    target = _occupy(tmp_path, "dangling")
    result = _export(kind, target, "--notes", lang)
    assert result.exit_code == 1 and "E024" in result.output
    assert _detail_only_in(result.output, lang), result.output
    assert "·" not in result.output


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_export_error_follows_heron_notes(tmp_path, lang):
    target = _occupy(tmp_path, "dangling")
    result = _export("schema", target, env={"HERON_NOTES": lang})
    assert _detail_only_in(result.output, lang), result.output


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_export_error_follows_build_notes_of_the_site(tmp_path, monkeypatch, lang):
    from heron.scaffold import create

    site = tmp_path / "site"
    create(site, name="Demo", notes=lang)
    monkeypatch.chdir(site)
    monkeypatch.delenv("HERON_NOTES", raising=False)
    target = site / "out"
    target.symlink_to(tmp_path / "nowhere", target_is_directory=True)
    result = _export("schema", target)
    assert result.exit_code == 1 and "E024" in result.output
    assert _detail_only_in(result.output, lang), result.output


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_kit_placement_error_is_in_the_notes_language(tmp_path, lang):
    from heron.scaffold import adopt, create

    root = tmp_path / "site"
    create(root, name="Demo", place_kit=False)
    adopt(root, notes=lang)
    (root / "agents" / "roles").rename(root / "agents" / "roles-old")
    (root / "agents" / "roles").write_text("not a folder\n", encoding="utf-8")
    with pytest.raises(HeronError) as caught:
        adopt(root, notes=lang, agents_flag="true", force=True)
    assert caught.value.code == "E024"
    assert _has_cyrillic(_error_text(caught.value)) is (lang == "ru")
    assert "·" not in caught.value.message


def test_write_dangling_texts_on_both_languages():
    from heron.messages import TEXT

    for key in ("write_dangling", "write_not_folder", "write_folder_hint"):
        assert TEXT["ru"][key] and TEXT["en"][key]
        assert TEXT["ru"][key] != TEXT["en"][key]


# --- E15.S1.T2: схемы комплекта - на языке комплекта -------------------------------


def _cyrillic(text: str) -> bool:
    return any("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in text)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_kit_schemas_are_in_the_kit_language(tmp_path, lang):
    root = tmp_path / "site"
    put(root, lang)
    for name, text in all_schemas(lang).items():
        written = (root / "agents" / "schemas" / name).read_text(encoding="utf-8")
        assert written == text
        assert _cyrillic(written) is (lang == "ru"), name
    # манифест считает эти же байты: обновление не принимает схемы за правку человека
    recorded = load_manifest(root)["files"]
    sums = {entry["path"]: entry["sha256"] for entry in recorded}
    for name, text in all_schemas(lang).items():
        assert sums[f"schemas/{name}"] == hashlib.sha256(text.encode()).hexdigest()
    again = put(root, lang, mode="update")
    assert not again.edited
    assert not [f for f in again.updated if "schemas/" in f]  # манифест перезаписан, схемы нет


def test_kit_language_switch_replaces_the_schemas_too(tmp_path):
    root = tmp_path / "site"
    put(root, "ru")
    plan = put(root, "en", mode="update")
    assert not plan.edited
    text = (root / "agents" / "schemas" / "errors.json").read_text(encoding="utf-8")
    assert text == all_schemas("en")["errors.json"] and not _cyrillic(text)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_docs_export_writes_schemas_in_its_language(tmp_path, lang):
    docs.export(tmp_path / "d", lang)
    for name, text in all_schemas(lang).items():
        assert (tmp_path / "d" / "schemas" / name).read_text(encoding="utf-8") == text
    # то же самое лежит и в комплекте нового сайта
    root = tmp_path / "site"
    put(root, lang)
    for name in SCHEMA_FILES:
        assert (root / "agents" / "schemas" / name).read_bytes() == (
            tmp_path / "d" / "schemas" / name
        ).read_bytes()


def test_docs_export_all_langs_still_has_no_schemas(tmp_path):
    written = docs.export(tmp_path / "d", all_langs=True)
    assert not any("schemas/" in rel for rel in written)


def test_new_english_site_gets_english_schemas(tmp_path, monkeypatch):
    from heron.scaffold import create

    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="Demo", languages=["en"], notes="en")
    for name in SCHEMA_FILES:
        assert not _cyrillic((root / "agents" / "schemas" / name).read_text(encoding="utf-8"))
    ru = tmp_path / "r"
    ru.mkdir()
    create(ru, name="Demo", languages=["en"], notes="ru")
    assert _cyrillic((ru / "agents" / "schemas" / "errors.json").read_text(encoding="utf-8"))
