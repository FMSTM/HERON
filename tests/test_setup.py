"""Конфигуратор `heron setup`: ответы ↔ site.yaml, файлы публикации, ключи.

Спецификация: docs/spec/21-engine.md, «heron setup».
"""

import json
import os
import stat
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.contracts.site import load_site
from heron.scaffold import create
from heron.setup import apply, current_answers, load_answers, state
from heron.setup.answers import Answers, fields_of, read

ANSWERS = """
site:
  name: Example Studio
  domain: studio.example.com
  preview_domain: preview.studio.example.com
  languages: [en, de]
about:
  type: LocalBusiness
  fields:
    name: Example Studio
    about: {en: "We make things.", de: "Wir machen Dinge."}
    telephone: "+00 000 000 00 00"
    city: {en: Vienna, de: Wien}
    country: AT
    latitude: 48.2
    longitude: 16.37
    opening_hours: ["Mo-Fr 08:00-18:00"]
    price_range: "$$"
search:
  title_suffix: " — Example Studio"
  llms_note: {en: "Call us."}
publish:
  way: git
  engine: beta
"""


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"], fish=True)
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["gone"] = ["/old/"]
    data["custom_block"] = {"keep": True}
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def keys_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HERON_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("HERON_IN_CONTAINER", raising=False)


def test_vocab_fields_inherit_from_parents():
    fields = fields_of("Dentist")
    assert fields[:2] == ["name", "about"]
    assert "opening_hours" in fields  # от LocalBusiness
    assert "street" in fields  # от Organization
    assert "job_title" not in fields  # это у Person


def test_apply_writes_valid_config_and_keeps_foreign_blocks(site: Path):
    result = apply(site, load_answers(ANSWERS))
    config = load_site(site / "site.yaml")
    assert config.site.domain == "studio.example.com"
    assert config.site.domains == {"dev": "preview.studio.example.com"}
    assert config.site.languages == ["en", "de"]
    assert config.gone == ["/old/"]
    assert config.extras["custom_block"] == {"keep": True}
    contact = config.extras["contact"]
    assert contact["city"] == "Vienna" and contact["city_de"] == "Wien"
    assert contact["geo"] == {"latitude": 48.2, "longitude": 16.37}
    entity = config.extras["schema"]["entity"]
    assert entity["@type"] == "LocalBusiness"
    assert entity["address"]["addressLocality"] == "{{ contact.city }}"
    # цены выключены: в разметку уровень цен не идёт, хотя ответ сохранён
    assert "priceRange" not in entity
    assert config.extras["organization"]["price_range"] == "$$"
    # новый язык — папка с главной и демо
    assert (site / "content" / "de" / "index.md").is_file()
    assert (site / "content" / "de" / "forms.md").is_file()
    assert "site.yaml" in result.written
    assert result.backup.startswith(".heron-cache/setup/")


def test_roundtrip_reads_back_what_it_wrote(site: Path):
    apply(site, load_answers(ANSWERS))
    again = load_answers(current_answers(site))
    assert again.about.type == "LocalBusiness"
    assert again.about.fields["city"] == {"en": "Vienna", "de": "Wien"}
    assert again.publish.way == "git" and again.publish.engine == "beta"
    # второй прогон с теми же ответами ничего не переписывает
    assert apply(site, again).written == []


def test_skipped_answer_removes_the_key(site: Path):
    apply(site, load_answers(ANSWERS))
    answers = load_answers(current_answers(site))
    del answers.about.fields["telephone"]
    apply(site, answers)
    data = yaml.safe_load((site / "site.yaml").read_text(encoding="utf-8"))
    assert "phone" not in data["contact"]
    assert "telephone" not in data["schema"]["entity"]


def test_prices_go_to_markup_only_when_allowed(site: Path):
    answers = load_answers(ANSWERS)
    answers.search.allow_prices = True
    apply(site, answers)
    data = yaml.safe_load((site / "site.yaml").read_text(encoding="utf-8"))
    assert data["schema"]["entity"]["priceRange"] == "{{ organization.price_range }}"
    assert data["seo"]["allow_prices"] is True


def test_git_way_writes_workflow_and_scripts(site: Path):
    apply(site, load_answers(ANSWERS))
    workflow = (site / ".github/workflows/image.yml").read_text(encoding="utf-8")
    assert "FMSTM/HERON/.github/workflows/site-image.yml@beta" in workflow
    assert "engine: beta" in workflow
    for name in ("build.sh", "publish.sh"):
        path = site / "scripts" / name
        assert path.stat().st_mode & stat.S_IXUSR
    assert "dist/" in (site / ".gitignore").read_text(encoding="utf-8")


def test_changing_the_way_removes_only_own_files(site: Path):
    apply(site, load_answers(ANSWERS))
    mine = site / ".github" / "workflows" / "own.yml"
    mine.write_text("name: own\n", encoding="utf-8")
    answers = load_answers(ANSWERS)
    answers.publish.way = "static"
    answers.publish.server = "deploy@host.example.com"
    result = apply(site, answers)
    assert ".github/workflows/image.yml" in result.removed
    assert mine.is_file()
    assert "rsync" in (site / "scripts/publish.sh").read_text(encoding="utf-8")


def test_foreign_script_is_not_overwritten(site: Path):
    (site / "scripts").mkdir()
    (site / "scripts" / "build.sh").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    result = apply(site, load_answers(ANSWERS))
    assert "scripts/build.sh" in result.kept
    assert "mine" in (site / "scripts/build.sh").read_text(encoding="utf-8")


def test_keys_go_outside_the_site_folder(site: Path, tmp_path: Path):
    answers = load_answers(ANSWERS)
    answers.keys.db_key = "secret-value"
    result = apply(site, answers)
    assert result.keys_saved == ["db_key"]
    stored = tmp_path / "config" / "sites" / "studio.example.com.env"
    assert stored.read_text(encoding="utf-8") == "HERON_DB_KEY=secret-value\n"
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    for path in site.rglob("*"):
        if path.is_file():
            assert b"secret-value" not in path.read_bytes(), path
    # страница видит только «задан / нет»
    seen = state(site, in_container=False)
    assert seen["keys"]["set"]["db_key"] is True
    assert "secret-value" not in json.dumps(seen)


def test_in_container_without_config_keys_are_refused(site: Path, monkeypatch):
    monkeypatch.delenv("HERON_CONFIG_DIR")
    answers = load_answers(ANSWERS)
    answers.keys.db_key = "secret-value"
    result = apply(site, answers, in_container=True)
    assert "keys_not_saved" in result.warnings
    assert (site / "scripts" / "keys.sh").is_file()


@pytest.mark.parametrize(
    "patch, problem",
    [
        ({"site": {"domain": "https://bad/"}}, "domain"),
        ({"site": {"languages": ["english"]}}, "language"),
        ({"about": {"type": "Spaceship"}}, "type"),
        ({"about": {"type": "Person", "fields": {"opening_hours": ["x"]}}}, "opening_hours"),
        ({"publish": {"way": "dockerhub"}}, "Docker Hub"),
        ({"publish": {"engine": "latest"}}, "engine"),
    ],
)
def test_bad_answers_are_explained(patch, problem):
    with pytest.raises(ValueError, match=problem):
        Answers.model_validate(patch)


def test_read_survives_a_raw_config():
    answers = read({"site": {"languages": ["en"], "domain": "not a domain"}})
    assert answers.site.languages == ["en"]


def test_cli_answers_and_dump(site: Path, tmp_path: Path):
    path = tmp_path / "answers.yaml"
    path.write_text(ANSWERS, encoding="utf-8")
    runner = CliRunner()
    done = runner.invoke(main, ["setup", str(site), "--answers", str(path)])
    assert done.exit_code == 0, done.output
    assert "site.yaml" in done.output
    dumped = runner.invoke(main, ["setup", str(site), "--dump"])
    assert "LocalBusiness" in dumped.output
    bad = tmp_path / "bad.yaml"
    bad.write_text("site: {domain: 'x y'}\n", encoding="utf-8")
    failed = runner.invoke(main, ["setup", str(site), "--answers", str(bad)])
    assert failed.exit_code == 2


def test_built_site_carries_the_entity(site: Path):
    from heron.core import build as pipeline

    apply(site, load_answers(ANSWERS))
    result = pipeline.run(site)
    assert not result.collector.errors, [str(e) for e in result.collector.errors]
    html = (site / "dist" / "de" / "index.html").read_text(encoding="utf-8")
    assert '"addressLocality": "Wien"' in html


def test_schema_command():
    runner = CliRunner()
    out = runner.invoke(main, ["schema"])
    data = json.loads(out.output)
    assert "site" in data["properties"]
    setup = json.loads(runner.invoke(main, ["schema", "--setup"]).output)
    assert "publish" in setup["properties"]


def test_recipe_command():
    out = CliRunner().invoke(main, ["recipe"])
    assert out.exit_code == 0
    assert "nginx-unprivileged" in out.output


def test_no_keys_in_env_of_tests():
    assert "HERON_DB_KEY" not in os.environ
