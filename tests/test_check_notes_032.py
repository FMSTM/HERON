"""0.3.2: сведения в `check --json` и сведение о подписи крошек в теме.

- `check --json` отдаёт сведения отдельным списком `notes` - `{code, kind, path,
  line, message}`; прежние ключи на месте, `ok` и `--strict` от сведений не зависят;
- тема, которая подписывает крошки не `crumb_name` (`crumb.h1`, `crumb.nav_title`,
  `crumb.meta.nav_title`), получает в `check` сведение с файлом и строкой.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from PIL import Image

from heron.cli import main
from heron.core.check import breadcrumb_labels
from heron.core.errors import Collector

KEYS = {"ok", "version", "strict", "pages", "errors", "warnings", "kit", "schema", "pending"}


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    return tmp_path / "demo"


def _check(root, *extra):
    result = CliRunner().invoke(main, ["check", str(root), "--json", "--notes", "en", *extra])
    return result, json.loads(result.output)


def test_notes_are_a_separate_list_and_old_keys_stay(site):
    image = site / "media" / "small.jpg"
    Image.new("RGB", (900, 600), (90, 60, 30)).save(image)
    page = site / "content" / "en" / "docs.md"
    text = page.read_text(encoding="utf-8")
    page.write_text(
        text.replace("\nh1:", "\nimage: media/small.jpg\nimage_alt: Small\nh1:", 1),
        encoding="utf-8",
    )
    result, data = _check(site, "--strict")
    assert result.exit_code == 0, result.output
    assert set(data) >= KEYS and "notes" in data
    assert data["ok"] is True and data["warnings"] == []
    note = next(n for n in data["notes"] if n["code"] == "media_small_cover")
    assert set(note) == {"code", "kind", "path", "line", "message"}
    assert note["path"] == "en/docs.md"
    assert "narrower than 1200 px: media/small.jpg" in note["message"]


def test_geo_note_is_in_json(site):
    path = site / "site.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\ncontact:\n  geo: [50.45, "30.52345"]\n'
        + 'schema:\n  entity:\n    "@type": LocalBusiness\n    "@id": "#org"\n'
        + '    geo:\n      "@type": GeoCoordinates\n'
        + '      latitude: "{{ contact.geo.0 }}"\n      longitude: "{{ contact.geo.1 }}"\n',
        encoding="utf-8",
    )
    _, data = _check(site)
    geo = [n for n in data["notes"] if n["code"] == "report_geo_short"]
    assert [n["message"].split(" - ")[0] for n in geo] == ["schema.entity.geo.latitude: 50.45"]


def test_no_site_json_has_empty_notes(tmp_path):
    result = CliRunner().invoke(main, ["check", str(tmp_path / "nope"), "--json"])
    data = json.loads(result.output)
    assert data["notes"] == [] and data["ok"] is False


# --- подпись крошек -------------------------------------------------------------------


def _theme(tmp_path, body: str):
    theme = tmp_path / "theme"
    (theme / "modules").mkdir(parents=True)
    (theme / "modules" / "breadcrumbs.html").write_text(body, encoding="utf-8")
    collector = Collector()
    breadcrumb_labels(theme, tmp_path, collector)
    assert collector.warnings == [] and collector.errors == []
    return collector.notes


@pytest.mark.parametrize(
    "label", ["crumb.h1", "crumb.nav_title", "crumb.meta.nav_title", "crumb.title"]
)
def test_old_crumb_label_gives_a_note(tmp_path, label):
    notes = _theme(
        tmp_path,
        "{% if page.breadcrumbs %}\n<nav>\n{% for crumb in page.breadcrumbs %}"
        f'<a href="{{{{ crumb.url }}}}">{{{{ {label} }}}}</a>{{% endfor %}}\n'
        "</nav>\n{% endif %}\n",
    )
    assert len(notes) == 1
    assert notes[0].path == "theme/modules/breadcrumbs.html" and notes[0].line == 3
    assert label in str(notes[0].message)


@pytest.mark.parametrize(
    "label",
    [
        "crumb.crumb_name",
        "crumb.meta.nav_title or crumb.h1",
        "t.home if not crumb.key else crumb.crumb_name",
    ],
)
def test_crumb_name_or_its_equivalent_gives_no_note(tmp_path, label):
    body = (
        "{% for crumb in page.breadcrumbs %}"
        f'<a href="{{{{ crumb.url }}}}">{{{{ {label} }}}}</a>{{% endfor %}}'
    )
    assert _theme(tmp_path, body) == []


def test_other_loops_are_not_read(tmp_path):
    body = (
        "{% for item in nav.main %}{{ item.h1 }}{% endfor %}"
        "{% for c in page.children %}{{ c.h1 }}{% endfor %}"
    )
    assert _theme(tmp_path, body) == []


def test_starter_theme_has_no_crumb_note_and_old_theme_passes_strict(site):
    _, data = _check(site, "--strict")
    assert not [n for n in data["notes"] if n["code"] == "check_crumb_label"]
    module = site / "theme" / "modules" / "breadcrumbs.html"
    module.write_text(
        module.read_text(encoding="utf-8").replace("crumb.crumb_name", "crumb.h1"),
        encoding="utf-8",
    )
    result, data = _check(site, "--strict")
    assert result.exit_code == 0 and data["ok"] is True
    assert [n["path"] for n in data["notes"] if n["code"] == "check_crumb_label"] == [
        "theme/modules/breadcrumbs.html"
    ]
