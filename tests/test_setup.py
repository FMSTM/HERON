"""Конфигуратор `heron setup`: ответы ↔ site.yaml, файлы публикации, ключи.

Спецификация: docs/spec/21-engine.md, «heron setup».
"""

import json
import stat
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.contracts.site import load_site
from heron.scaffold import create
from heron.setup import apply, current_answers, load_answers
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
    city: {en: Vienna, de: Wien}
    country: AT
    latitude: 48.2
    longitude: 16.37
    opening_hours: ["Mo-Fr 08:00-18:00"]
    price_range: "$$"
  contacts:
    - {type: phone, purpose: main, value: "+00 000 000 00 00"}
    - {type: phone, purpose: support, value: "+00 000 000 00 01"}
    - {type: email, value: hello@studio.example.com}
    - {type: telegram, purpose: support, value: "@studio_help"}
    - {type: website, value: https://blog.example.com}
search:
  title_suffix: " — Example Studio"
  llms_note: {en: "Call us."}
analytics:
  metrika: "12345678"
publish:
  way: github
  engine: beta
"""


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"], demo=True)
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["gone"] = ["/old/"]
    data["custom_block"] = {"keep": True}
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return root


def test_vocab_fields_inherit_from_parents():
    fields = fields_of("LocalBusiness")
    assert fields[:2] == ["name", "legal_name"]
    assert "opening_hours" in fields  # своё у местного бизнеса
    assert "street" in fields  # от организации
    assert "job_title" not in fields  # это у человека
    assert "job_title" in fields_of("Person")


def test_classifier_drives_type_and_labels(site: Path):
    answers = load_answers(ANSWERS)
    answers.about.specialization = "health-03"  # стоматология
    apply(site, answers)
    data = yaml.safe_load((site / "site.yaml").read_text(encoding="utf-8"))
    entity = data["schema"]["entity"]
    assert entity["@type"] == "Dentist"
    assert entity["knowsAbout"] == "{{ organization.field_of_work }}"
    assert data["organization"]["field_of_work_de"] == "Healthcare"  # нет немецкой — английская
    again = load_answers(current_answers(site))
    assert (again.about.direction, again.about.specialization) == ("health", "health-03")


def test_person_gets_occupation():
    from heron.setup.answers import merge

    answers = Answers.model_validate(
        {
            "site": {"name": "S", "domain": "s.example.com", "languages": ["ru", "en"]},
            "about": {"type": "Person", "specialization": "legal-02"},
        }
    )
    data = merge({"site": {"theme": "main"}}, answers, ">=0.1")
    assert data["organization"]["specialization"] == "Адвокат"
    assert data["schema"]["entity"]["hasOccupation"]["name"] == "{{ organization.specialization }}"


def test_specialization_must_match_direction():
    with pytest.raises(ValueError, match="not in"):
        Answers.model_validate({"about": {"direction": "legal", "specialization": "health-03"}})


def test_suffix_always_has_a_separator():
    from heron.setup.answers import clean_suffix

    assert clean_suffix("yth") == " — yth"
    assert clean_suffix("| Studio") == " | Studio"
    assert clean_suffix(" — Studio") == " — Studio"
    assert clean_suffix("  ") == ""


def test_helpers_can_be_switched_off(site: Path):
    answers = load_answers(ANSWERS)
    answers.publish.helpers = {"build": False, "publish": False, "gitignore": False}
    apply(site, answers)
    assert not (site / ".heron").exists()
    assert (site / ".github/workflows/image.yml").is_file()  # автосборка — отдельно


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
    assert (site / "content" / "de" / "blocks.md").is_file()
    assert "site.yaml" in result.written
    assert result.backup.startswith(".heron-cache/setup/")


def test_roundtrip_reads_back_what_it_wrote(site: Path):
    apply(site, load_answers(ANSWERS))
    again = load_answers(current_answers(site))
    assert again.about.type == "LocalBusiness"
    assert again.about.fields["city"] == {"en": "Vienna", "de": "Wien"}
    assert again.publish.way == "github" and again.publish.engine == "beta"
    assert [c.value for c in again.about.contacts][:2] == ["+00 000 000 00 00", "+00 000 000 00 01"]
    # второй прогон с теми же ответами ничего не переписывает
    assert apply(site, again).written == []


def test_skipped_answer_removes_the_key(site: Path):
    apply(site, load_answers(ANSWERS))
    answers = load_answers(current_answers(site))
    answers.about.contacts = [c for c in answers.about.contacts if c.type != "phone"]
    del answers.about.fields["country"]
    apply(site, answers)
    data = yaml.safe_load((site / "site.yaml").read_text(encoding="utf-8"))
    assert "phone" not in data["contact"]
    assert "country" not in data["contact"]
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
        path = site / ".heron" / "scripts" / name
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
    assert "rsync" in (site / ".heron/scripts/publish.sh").read_text(encoding="utf-8")


def test_foreign_script_is_not_overwritten(site: Path):
    (site / ".heron" / "scripts").mkdir(parents=True)
    (site / ".heron/scripts/build.sh").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    result = apply(site, load_answers(ANSWERS))
    assert ".heron/scripts/build.sh" in result.kept
    assert "mine" in (site / ".heron/scripts/build.sh").read_text(encoding="utf-8")


def test_contacts_go_to_channels_and_markup(site: Path):
    apply(site, load_answers(ANSWERS))
    data = yaml.safe_load((site / "site.yaml").read_text(encoding="utf-8"))
    contact = data["contact"]
    assert contact["phone"] == "+00 000 000 00 00"  # первый телефон — основной
    assert contact["email"] == "hello@studio.example.com"
    assert len(contact["channels"]) == 5
    entity = data["schema"]["entity"]
    assert entity["telephone"] == "{{ contact.phone }}"
    kinds = {(p["contactType"], p.get("telephone")) for p in entity["contactPoint"]}
    assert ("technical support", "+00 000 000 00 01") in kinds
    assert entity["sameAs"] == ["https://t.me/studio_help"]
    assert data["analytics"]["metrika"] == "12345678"


def test_old_config_contacts_are_read_as_channels():
    answers = read(
        {
            "site": {"languages": ["en"], "domain": "a.example.com"},
            "contact": {"phone": "+00 000 000 00 00", "email": "a@a.example.com"},
            "organization": {"same_as": ["https://t.me/abc", "https://abc.example.com"]},
        }
    )
    assert [(c.type, c.value) for c in answers.about.contacts] == [
        ("phone", "+00 000 000 00 00"),
        ("email", "a@a.example.com"),
        ("telegram", "https://t.me/abc"),
        ("website", "https://abc.example.com"),
    ]


def test_setup_needs_a_site(tmp_path: Path):
    out = CliRunner().invoke(main, ["setup", str(tmp_path)])
    assert out.exit_code == 1
    assert "site.yaml" in out.output
    with pytest.raises(ValueError, match="site.yaml"):
        apply(tmp_path, load_answers(ANSWERS))


def test_github_without_auto_writes_no_workflow(site: Path):
    answers = load_answers(ANSWERS)
    answers.publish.auto = False
    apply(site, answers)
    assert not (site / ".github/workflows/image.yml").exists()
    assert "git push" in (site / ".heron/scripts/publish.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "patch, problem",
    [
        ({"site": {"domain": "https://bad/"}}, "domain"),
        ({"site": {"languages": ["english"]}}, "language"),
        ({"about": {"type": "Spaceship"}}, "type"),
        ({"about": {"type": "Person", "fields": {"opening_hours": ["x"]}}}, "opening_hours"),
        ({"publish": {"way": "dockerhub"}}, "Docker Hub"),
        ({"about": {"contacts": [{"type": "email", "value": "nope"}]}}, "email"),
        ({"analytics": {"ga4": "UA-1"}}, "G-XXXXXXX"),
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


def test_countries_and_directions_in_state(site: Path):
    from heron.setup import state

    seen = state(site, in_container=False)
    austria = next(row for row in seen["countries"] if row[0] == "AT")
    assert austria[1] == "Австрия" and austria[3] == "+43"
    assert len(seen["countries"]) > 240
    assert any(d["id"] == "marketing" for d in seen["classifier"])
    assert sum(len(d["items"]) for d in seen["classifier"]) > 150


def test_country_is_a_code(site: Path):
    answers = load_answers(ANSWERS)
    answers.about.fields["country"] = "at"
    apply(site, answers)
    assert (
        yaml.safe_load((site / "site.yaml").read_text(encoding="utf-8"))["contact"]["country"]
        == "AT"
    )
    answers.about.fields["country"] = "Austria"
    with pytest.raises(ValueError, match="two-letter"):
        apply(site, answers)
