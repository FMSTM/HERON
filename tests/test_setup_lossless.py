"""Анкета не теряет то, чем не управляет: прочитать и сохранить — без потерь.

Плюс намеренные изменения: тип, домен, решения о публикации.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from heron import setup
from heron.scaffold import create
from heron.setup.answers import read

ENTITY = {
    "@type": ["Organization", "LocalBusiness"],
    "@id": "https://example.test/#node",
    "name": "{{ site.name }}",
    "telephone": "{{ contact.phone }}",
    "geo": {"@type": "GeoCoordinates", "latitude": 1.5, "longitude": 2.5},
    "openingHours": ["Mo-Fr 09:00-18:00"],
    "sameAs": ["https://profile.example.test/x"],
    "medicalSpecialty": "MARKER-specialty",
    "worksFor": {"@type": "Organization", "name": "Org"},
    "areaServed": "Somewhere",
    "founder": {"@type": "Person", "name": "F"},
    "foundingDate": "2001",
}


def _site(tmp_path: Path, **extra) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en", "de"], demo=True)
    data = yaml.safe_load((root / "site.yaml").read_text("utf-8"))
    data.setdefault("contact", {})["phone"] = "+00000000000"
    data["schema"] = {"entity": ENTITY}
    data.update(extra)
    (root / "site.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return root


def _config(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text("utf-8"))


def _resave(root: Path, change=None) -> dict:
    data = read(setup.raw_config(root)).model_dump()
    if change:
        change(data)
    setup.apply(root, setup.Answers.model_validate(data))
    return _config(root)


def _kept(before, after, where="") -> list[str]:
    """Что из прежнего пропало или изменилось (дописанное не в счёт)."""
    if isinstance(before, dict) and isinstance(after, dict):
        lost = []
        for key, value in before.items():
            if key not in after:
                lost.append(f"{where}{key}: пропал")
            else:
                lost += _kept(value, after[key], f"{where}{key}.")
        return lost
    return [] if before == after else [f"{where.rstrip('.')}: {before!r} → {after!r}"]


def test_save_without_changes_is_lossless(tmp_path):
    root = _site(tmp_path)
    before = _config(root)
    after = _resave(root)
    assert after["schema"]["entity"] == ENTITY
    assert _kept(before, after) == []
    # второй раз — ровно то же
    assert _resave(root) == after


def test_intended_change_of_type_keeps_unmanaged_fields(tmp_path):
    root = _site(tmp_path)

    def to_person(data):
        data["about"]["type"] = "Person"
        data["about"]["direction"] = ""
        data["about"]["specialization"] = ""

    entity = _resave(root, to_person)["schema"]["entity"]
    assert entity["@type"] == "Person"
    for key in ("geo", "openingHours", "medicalSpecialty", "founder", "foundingDate"):
        assert entity[key] == ENTITY[key]
    assert entity["@id"] == ENTITY["@id"]


def test_answer_removed_on_purpose_drops_its_key(tmp_path):
    root = _site(tmp_path)

    def no_phone(data):
        data["about"]["contacts"] = [c for c in data["about"]["contacts"] if c["type"] != "phone"]

    data = read(setup.raw_config(root)).model_dump()
    data["about"]["contacts"] = [{"type": "phone", "value": "+00000000000"}]
    setup.apply(root, setup.Answers.model_validate(data))
    assert _config(root)["schema"]["entity"]["telephone"] == "{{ contact.phone }}"
    entity = _resave(root, no_phone)["schema"]["entity"]
    assert "telephone" not in entity
    assert entity["geo"] == ENTITY["geo"]


# --- домен: анкета показывает и меняет реальный прод-домен ---------------------


def test_domain_change_moves_the_effective_prod_domain(tmp_path):
    import re

    from heron.core import build as pipeline
    from heron.core.environment import BuildEnv

    root = _site(tmp_path)
    data = _config(root)
    data["site"]["domain"] = "old.example.test"
    data["site"]["domains"] = {
        "prod": "old.example.test",
        "dev": "dev.example.test",
        "stage": "stage.example.test",
    }
    (root / "site.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert read(setup.raw_config(root)).site.domain == "old.example.test"

    def move(data):
        data["site"]["domain"] = "new.example.test"

    site = _resave(root, move)["site"]
    assert site["domain"] == "new.example.test"
    assert site["domains"] == {
        "prod": "new.example.test",
        "dev": "dev.example.test",
        "stage": "stage.example.test",
    }
    assert not pipeline.run(root, env=BuildEnv.named("prod")).failed
    html = (root / "dist" / "index.html").read_text("utf-8")
    assert re.search(r'rel="canonical" href="https://new\.example\.test/"', html)


def test_unchanged_domain_leaves_both_keys_alone(tmp_path):
    root = _site(tmp_path)
    data = _config(root)
    data["site"]["domain"] = "base.example.test"
    data["site"]["domains"] = {"prod": "prod.example.test"}
    (root / "site.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    site = _resave(root)["site"]
    assert site["domain"] == "base.example.test"
    assert site["domains"] == {"prod": "prod.example.test"}


# --- решения о публикации переживают повторное открытие ------------------------


def test_helpers_off_survive_way_none(tmp_path):
    root = _site(tmp_path)

    def none(data):
        data["publish"].update(way="none", engine="beta", helpers={"build": False})

    _resave(root, none)
    again = read(setup.raw_config(root)).publish
    assert again.way == "none" and again.engine == "beta"
    assert again.helpers == {"build": False, "publish": True, "gitignore": True}
    _resave(root)  # открыли и сохранили — ничего не вернулось
    assert not (root / ".heron" / "scripts" / "build.sh").exists()


def test_branch_survives_pages(tmp_path):
    root = _site(tmp_path)

    def pages(data):
        data["publish"].update(way="static", static_target="pages", branch="site-src")

    _resave(root, pages)
    assert read(setup.raw_config(root)).publish.branch == "site-src"
    _resave(root)
    text = (root / ".github" / "workflows" / "pages.yml").read_text("utf-8")
    assert 'branches: ["site-src"]' in text
