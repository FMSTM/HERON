"""Конвейер сборки целиком: от папки до dist/."""

import pytest

from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.scaffold import create


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    return root


def test_fresh_scaffold_builds(site):
    result = pipeline.run(site)
    assert not result.failed
    assert (site / "dist" / "index.html").is_file()
    assert (site / "dist" / "404" / "index.html").is_file()


def test_generated_files_are_there(site):
    result = pipeline.run(site)
    assert "sitemap.xml" in result.written
    assert "robots.txt" in result.written
    assert "llms.txt" in result.written


def test_url_becomes_folder_with_index(tmp_path, site):
    (site / "content" / "uk" / "bio.md").write_text(
        "---\ntitle: Біо\nh1: Про мене\ndescription: Опис\n---\n\nТекст.\n",
        encoding="utf-8",
    )
    pipeline.run(site)
    assert (site / "dist" / "bio" / "index.html").is_file()


def test_two_builds_are_byte_identical(site):
    """Воспроизводимость — то, что отличает сборщик от генератора случайностей."""
    pipeline.run(site)
    first = (site / "dist" / "index.html").read_bytes()
    sitemap_first = (site / "dist" / "sitemap-uk.xml").read_bytes()
    pipeline.run(site)
    assert (site / "dist" / "index.html").read_bytes() == first
    assert (site / "dist" / "sitemap-uk.xml").read_bytes() == sitemap_first


def test_theme_assets_copied(site):
    pipeline.run(site)
    assert (site / "dist" / "assets" / "site.css").is_file()


def test_draft_is_skipped_unless_asked(site):
    (site / "content" / "uk" / "draft.md").write_text(
        "---\ntitle: Чернетка\nh1: Чернетка\ndescription: Опис\npublished: false\n---\n\nТекст.\n",
        encoding="utf-8",
    )
    assert "draft/index.html" not in pipeline.run(site).written
    assert "draft/index.html" in pipeline.run(site, drafts=True).written


def test_version_mismatch_stops_everything(site):
    config = (site / "site.yaml").read_text(encoding="utf-8")
    (site / "site.yaml").write_text(
        config.replace('heron: ">=0.1,<0.2"', 'heron: ">=9.0"'), "utf-8"
    )
    with pytest.raises(HeronError) as exc:
        pipeline.run(site)
    assert exc.value.code == "E012"


def test_broken_content_reports_without_writing(site):
    (site / "content" / "uk" / "bad.md").write_text("без фронтматтера\n", encoding="utf-8")
    result = pipeline.run(site)
    assert result.failed
    assert [e.code for e in result.collector.errors] == ["E001"]


def test_check_does_not_write_anything(site):
    result = pipeline.check(site)
    assert not result.failed
    assert not (site / "dist").exists()
    assert result.report is not None


def test_report_counts_pages(site):
    result = pipeline.run(site)
    assert result.report.pages_by_lang["uk"] == 2
