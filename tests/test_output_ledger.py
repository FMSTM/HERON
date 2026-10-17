"""Повторная сборка корректна, неудачная — безопасна, у каждого файла один владелец.

Раньше каждый этап писал в dist/ сам: удалённая страница жила там вечно,
static/ молча заменял сгенерированное, а строгая сборка падала уже после
записи. Теперь пишет один commit и только после успешной сборки.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from heron.core import build as pipeline
from heron.core import media
from heron.scaffold import create

PAGE = "---\ntitle: {t}\nh1: {t} page\ndescription: D\n{extra}---\n\nText {t}.\n"


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1790000000")


def make(tmp_path: Path, langs=("en", "ru"), name="site") -> Path:
    root = tmp_path / name
    root.mkdir()
    create(root, name="demo", languages=list(langs))
    write(root, "en/about.md", PAGE.format(t="About", extra=""))
    write(root, "en/team.md", PAGE.format(t="Team", extra=""))
    if "ru" in langs:
        write(root, "ru/about.md", PAGE.format(t="О нас", extra=""))
    return root


def write(root: Path, rel: str, text: str) -> None:
    path = root / "content" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def site_yaml(root: Path, change) -> None:
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def ok(root: Path, **kw) -> pipeline.Result:
    result = pipeline.run(root, **kw)
    assert not result.failed, [str(e) for e in result.collector.errors] + [
        w.message for w in result.collector.warnings
    ]
    return result


def snapshot(dist: Path) -> dict[str, tuple[str, int]]:
    """Содержимое и время каждого файла — чтобы видеть любую запись."""
    return {
        p.relative_to(dist).as_posix(): (
            hashlib.sha256(p.read_bytes()).hexdigest(),
            p.stat().st_mtime_ns,
        )
        for p in sorted(dist.rglob("*"))
        if p.is_file()
    }


def text(root: Path, rel: str) -> str:
    return (root / "dist" / rel).read_text(encoding="utf-8")


# --- устаревшее удаляется -------------------------------------------------


def test_deleted_page_leaves_the_build(tmp_path):
    root = make(tmp_path)
    ok(root)
    assert (root / "dist/team/index.html").is_file()
    (root / "content/en/team.md").unlink()
    ok(root)
    assert not (root / "dist/team").exists()
    assert "/team/" not in text(root, "sitemap-en.xml")


def test_unpublished_page_leaves_the_build(tmp_path):
    root = make(tmp_path)
    ok(root)
    write(root, "en/team.md", PAGE.format(t="Team", extra="published: false\n"))
    ok(root)
    assert not (root / "dist/team/index.html").exists()
    assert "/team/" not in text(root, "llms.txt")


def test_renamed_file_and_changed_slug_move_the_page(tmp_path):
    root = make(tmp_path)
    ok(root)
    (root / "content/en/team.md").rename(root / "content/en/people.md")
    write(root, "en/about.md", PAGE.format(t="About", extra="slug: about-us\n"))
    ok(root)
    assert not (root / "dist/team").exists()
    assert not (root / "dist/about").exists()
    assert (root / "dist/people/index.html").is_file()
    assert (root / "dist/about-us/index.html").is_file()
    # зависимые результаты пересчитаны: карта сайта и переводы
    sitemap = text(root, "sitemap-en.xml")
    assert "/people/" in sitemap and "/about-us/" in sitemap and "/team/" not in sitemap
    assert "/about-us/" in text(root, "ru/about/index.html")  # hreflang перевода


def test_removed_language_leaves_the_build(tmp_path):
    root = make(tmp_path)
    ok(root)
    assert (root / "dist/ru/index.html").is_file()
    site_yaml(root, lambda d: d["site"].update(languages=["en"]))
    shutil.rmtree(root / "content/ru")
    ok(root)
    assert not (root / "dist/ru").exists()
    assert not (root / "dist/sitemap-ru.xml").exists()


def test_theme_and_site_data_changes_reach_every_page(tmp_path):
    root = make(tmp_path)
    ok(root)
    page = root / "theme/templates/page.html"
    page.write_text(page.read_text(encoding="utf-8").replace("</h1>", "</h1><i>v2</i>", 1), "utf-8")
    site_yaml(root, lambda d: d["site"].update(name="Renamed"))
    ok(root)
    for rel in ("about/index.html", "team/index.html", "ru/about/index.html"):
        assert "<i>v2</i>" in text(root, rel), rel
    for rel in ("index.html", "about/index.html", "ru/about/index.html"):
        assert "Renamed" in text(root, rel), rel


def test_foreign_files_are_kept(tmp_path):
    root = make(tmp_path)
    ok(root)
    (root / "dist/keep.txt").write_text("mine", encoding="utf-8")
    (root / "content/en/team.md").unlink()
    ok(root)
    assert (root / "dist/keep.txt").read_text(encoding="utf-8") == "mine"


# --- неудачная сборка не трогает прошлую -----------------------------------


def test_strict_failure_keeps_the_previous_build_intact(tmp_path):
    root = make(tmp_path)
    ok(root, strict=True)
    before = snapshot(root / "dist")
    # только предупреждение (title = h1): без строгого режима сборка прошла бы
    write(root, "en/about.md", "---\ntitle: Same\nh1: Same\ndescription: D\n---\n\nNew.\n")
    (root / "content/en/team.md").unlink()
    loose = pipeline.check(root)
    assert not loose.collector.errors and loose.collector.warnings
    result = pipeline.run(root, strict=True)
    assert result.failed
    assert snapshot(root / "dist") == before


def test_fail_on_warning_is_the_same_as_strict(tmp_path):
    root = make(tmp_path)
    ok(root)
    before = snapshot(root / "dist")
    site_yaml(root, lambda d: d.setdefault("build", {}).update(fail_on_warning=True))
    # только предупреждение (title = h1): без строгого режима сборка прошла бы
    write(root, "en/about.md", "---\ntitle: Same\nh1: Same\ndescription: D\n---\n\nNew.\n")
    result = pipeline.run(root)
    assert result.strict and result.failed
    assert snapshot(root / "dist") == before
    assert pipeline.check(root).failed


def test_error_keeps_the_previous_build_intact(tmp_path):
    root = make(tmp_path)
    ok(root)
    before = snapshot(root / "dist")
    write(root, "en/team.md", "---\ntitle: T\n---\n\nno h1\n")  # E002
    result = pipeline.run(root)
    assert result.failed
    assert snapshot(root / "dist") == before


def test_replacing_never_writes_into_a_shared_inode(tmp_path):
    """Старая версия файла, на которую есть другая жёсткая ссылка, цела."""
    root = make(tmp_path)
    ok(root)
    backup = tmp_path / "backup.html"
    os.link(root / "dist/about/index.html", backup)
    old = backup.read_bytes()
    write(root, "en/about.md", PAGE.format(t="About v2", extra=""))
    ok(root)
    assert backup.read_bytes() == old
    assert "About v2" in text(root, "about/index.html")


# --- владельцы выходных путей ---------------------------------------------


@pytest.mark.parametrize("name", ["index.html", "robots.txt", "sitemap.xml", "about/index.html"])
def test_static_cannot_silently_replace_generated_files(tmp_path, name):
    root = make(tmp_path)
    target = root / "static" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("from static", encoding="utf-8")
    result = pipeline.run(root)
    assert "E026" in [e.code for e in result.collector.errors]
    assert not (root / "dist").exists()


def test_static_can_replace_a_generator_when_declared(tmp_path):
    root = make(tmp_path)
    (root / "static").mkdir(exist_ok=True)
    (root / "static/robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    site_yaml(root, lambda d: d.setdefault("build", {}).update(overrides=["robots.txt"]))
    ok(root)
    assert text(root, "robots.txt") == "User-agent: *\n"


def test_override_cannot_replace_a_page(tmp_path):
    root = make(tmp_path)
    (root / "static").mkdir(exist_ok=True)
    (root / "static/index.html").write_text("x", encoding="utf-8")
    site_yaml(root, lambda d: d.setdefault("build", {}).update(overrides=["index.html"]))
    result = pipeline.run(root)
    assert "E026" in [e.code for e in result.collector.errors]


def test_unused_override_warns(tmp_path):
    root = make(tmp_path)
    site_yaml(root, lambda d: d.setdefault("build", {}).update(overrides=["humans.txt"]))
    result = pipeline.run(root)
    assert any("humans.txt" in w.message for w in result.collector.warnings)


def test_static_against_theme_asset(tmp_path):
    root = make(tmp_path)
    css = next((root / "theme/assets").rglob("*.css"))
    rel = css.relative_to(root / "theme").as_posix()
    target = root / "static" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")
    result = pipeline.run(root)
    assert "E026" in [e.code for e in result.collector.errors]


def test_file_and_folder_with_one_name_conflict(tmp_path):
    root = make(tmp_path)
    (root / "static").mkdir(exist_ok=True)
    (root / "static/about").write_text("x", encoding="utf-8")  # а /about/ — страница
    result = pipeline.run(root)
    assert "E026" in [e.code for e in result.collector.errors]


# --- повторная сборка переиспользует дорогое --------------------------------


def photo_site(tmp_path: Path, name: str) -> Path:
    root = make(tmp_path, name=name)
    site_yaml(root, lambda d: d.setdefault("build", {}).update(workers=1))
    (root / "media").mkdir(exist_ok=True)
    Image.new("RGB", (1200, 900), (40, 90, 160)).save(root / "media/photo.jpg")
    write(root, "en/about.md", PAGE.format(t="About", extra="") + "\n![Photo](media/photo.jpg)\n")
    page = root / "theme/templates/page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            "<h1>{{ page.h1 }}</h1>",
            "<h1>{{ page.h1 }}</h1>{{ picture('media/photo.jpg', '1:1', alt='p') }}",
        ),
        encoding="utf-8",
    )
    return root


def test_warm_build_rewrites_nothing_and_encodes_nothing(tmp_path, monkeypatch):
    root = photo_site(tmp_path, "site")
    first = ok(root)
    assert any(rel.endswith(".webp") for rel in first.applied.written)
    before = snapshot(root / "dist")

    calls: list[str] = []
    original = media.slice_master
    monkeypatch.setattr(
        media, "slice_master", lambda *a, **k: calls.append(a[0]) or original(*a, **k)
    )
    second = ok(root)
    assert calls == []  # ни одной нарезки заново
    assert second.applied.written == [] and second.applied.removed == []
    assert snapshot(root / "dist") == before  # ни байта, ни времени


def test_cold_and_warm_builds_are_byte_identical(tmp_path):
    warm = photo_site(tmp_path, "warm")
    ok(warm)
    write(warm, "en/team.md", PAGE.format(t="Team v2", extra=""))
    ok(warm)
    cold = photo_site(tmp_path, "cold")
    write(cold, "en/team.md", PAGE.format(t="Team v2", extra=""))
    ok(cold)

    def contents(dist: Path) -> dict[str, str]:
        return {rel: digest for rel, (digest, _) in snapshot(dist).items()}

    assert contents(warm / "dist") == contents(cold / "dist")


def test_changed_page_rewrites_only_what_depends_on_it(tmp_path):
    root = photo_site(tmp_path, "site")
    ok(root)
    write(root, "en/team.md", PAGE.format(t="Team v2", extra=""))
    applied = ok(root).applied
    assert "team/index.html" in applied.written
    assert not any(rel.endswith((".webp", ".jpg")) for rel in applied.written)
    assert "media/photo-1x1-800.jpg" in applied.kept


def test_manifest_lists_exactly_the_owned_files(tmp_path):
    from heron.core import output

    root = make(tmp_path)
    result = ok(root)
    assert output.previous(root / "dist") == set(result.written)
