"""Заготовка: украинская демо-витрина (E15.S1.T23)."""

from __future__ import annotations

import re

import yaml
from click.testing import CliRunner

from heron import scaffold
from heron.cli import main
from heron.scaffold import DEMO, DEMO_PAGES, DEMO_TITLES, _demo_links

UK_LETTERS = re.compile(r"[іїє]")


def _new(tmp_path, langs):
    site = tmp_path / "site"
    runner = CliRunner()
    result = runner.invoke(main, ["new", str(site), "--lang", langs, "-y"])
    assert result.exit_code == 0, result.output
    return site, runner


def _split(text):
    _, head, body = text.split("---", 2)
    return head, body


def test_uk_demo_pages_come_from_demo_uk(tmp_path):
    site, _ = _new(tmp_path, "uk,ru,en")
    assert "uk" in scaffold.DEMO_LANGS
    for page in DEMO_PAGES:
        path = site / "content" / "uk" / f"{page}.md"
        assert path.is_file(), path
        head, body = _split(path.read_text(encoding="utf-8"))
        expected = _demo_links((DEMO / "uk" / f"{page}.md").read_text(encoding="utf-8"))
        assert body.strip() == expected.strip()
        assert UK_LETTERS.search(body)
        title, h1, _desc, _nav = (p.format(name="my-site") for p in DEMO_TITLES["uk"][page])
        meta = yaml.safe_load(head)
        assert meta["title"] == title
        assert meta["h1"] == h1


def test_uk_site_builds_strict(tmp_path):
    site, runner = _new(tmp_path, "uk,ru,en")
    result = runner.invoke(main, ["build", str(site), "--strict"])
    assert result.exit_code == 0, result.output


def test_en_site_still_uses_demo_en(tmp_path):
    site, _ = _new(tmp_path, "en")
    for page in DEMO_PAGES:
        _, body = _split((site / "content" / "en" / f"{page}.md").read_text(encoding="utf-8"))
        expected = _demo_links((DEMO / "en" / f"{page}.md").read_text(encoding="utf-8"))
        assert body.strip() == expected.strip()


def test_no_dashes_in_uk_texts(tmp_path):
    site, _ = _new(tmp_path, "uk,ru,en")
    for values in DEMO_TITLES["uk"].values():
        assert not any(ch in part for part in values for ch in "—–")
    for page in (site / "content" / "uk").glob("*.md"):
        text = page.read_text(encoding="utf-8")
        assert "—" not in text and "–" not in text, page
