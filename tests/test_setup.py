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

    seen = state(site)
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


# --- причины отказа на языке сайта (E15.S1.T5: F04) ---------------------------

import ast  # noqa: E402
import re  # noqa: E402

from heron.setup import reasons  # noqa: E402
from heron.setup.answers import PURPOSES, classifier, vocab  # noqa: E402
from heron.setup.reasons import Reason, plain  # noqa: E402

CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")
# латиница в русской причине — только токены: значения, ключи, имена сервисов
RU_TOKENS = {
    "Google", "Analytics", "Tag", "Manager", "Docker", "Hub", "NUL", "engine", "prod", "beta",
    "helpers", "user", "host", "main", "release", "heron", "new", "true", "false", "https",
    "digest", "sha", "you", "site", "example", "com", "pt", "br", "en", "de", "AT",
}  # fmt: skip


def _stray_latin(text: str, extra: tuple[str, ...] = ()) -> list[str]:
    """Латинские слова вне токенов: путь поля, значение в кавычках, код, `extra`."""
    plain_text = re.sub(r"'[^']*'|\"[^\"]*\"|<[^>]*>|\S*[./@:_+-]\S*|\b[A-Z]+-X+\b", " ", text)
    allowed = RU_TOKENS | set(extra)
    return [w for w in re.findall(r"[A-Za-z]{2,}", plain_text) if w not in allowed]


def _values(data) -> tuple[str, ...]:
    """Значения из ответов: их сообщение повторяет как есть, это токены."""
    if isinstance(data, dict):
        return tuple(w for v in data.values() for w in _values(v))
    if isinstance(data, list):
        return tuple(w for v in data for w in _values(v))
    return tuple(re.findall(r"[A-Za-z]+", str(data)))


def _keys(error: Exception) -> set[str]:
    if isinstance(error, Reason):
        return {error.key}
    return {
        item["ctx"]["error"].key
        for item in error.errors()
        if isinstance((item.get("ctx") or {}).get("error"), Reason)
    }


def _cases():
    dirs = classifier()
    other = dirs[1]["items"][0]["id"]
    return {
        "domain_bad": {"site": {"domain": "https://bad/"}},
        "languages_none": {"site": {"languages": [" "]}},
        "languages_bad": {"site": {"languages": ["english"]}},
        "languages_repeat": {"site": {"languages": ["en", "en"]}},
        "default_lang_missing": {"site": {"languages": ["en"], "default_lang": "de"}},
        "preview_same": {"site": {"domain": "a.example.com", "preview_domain": "a.example.com"}},
        "contact_empty": {"about": {"contacts": [{"type": "phone", "value": " "}]}},
        "purpose_bad": {
            "about": {"contacts": [{"type": "phone", "purpose": "party", "value": "+1 234 567"}]}
        },
        "phone_bad": {"about": {"contacts": [{"type": "phone", "value": "call me"}]}},
        "email_bad": {"about": {"contacts": [{"type": "email", "value": "nope"}]}},
        "link_needed": {"about": {"contacts": [{"type": "website", "value": "no link"}]}},
        "direction_unknown": {"about": {"direction": "nowhere"}},
        "spec_unknown": {"about": {"specialization": "nothing"}},
        "spec_other": {"about": {"direction": dirs[0]["id"], "specialization": other}},
        "type_unknown": {"about": {"type": "Spaceship"}},
        "fields_unknown": {"about": {"type": "Person", "fields": {"opening_hours": ["x"]}}},
        "ga4_bad": {"analytics": {"ga4": "UA-1"}},
        "gtm_bad": {"analytics": {"gtm": "x"}},
        "metrika_bad": {"analytics": {"metrika": "abc"}},
        "control_chars": {"publish": {"repo": "a\nb"}},
        "helpers_unknown": {"publish": {"helpers": {"x": True}}},
        "engine_bad": {"publish": {"engine": "latest"}},
        "repo_bad": {"publish": {"repo": "bad"}},
        "docker_name_bad": {"publish": {"dockerhub_user": "Bad"}},
        "dockerhub_needs": {"publish": {"way": "dockerhub"}},
        "server_needed": {"publish": {"way": "static", "static_target": "server"}},
        "server_bad": {"publish": {"server": "bad host"}},
        "path_bad": {"publish": {"path": "relative"}},
        "branch_bad": {"publish": {"branch": "a..b"}},
        "note_lang": {"site": {"languages": ["en"]}, "search": {"llms_note": {"de": "x"}}},
        "field_lang": {"site": {"languages": ["en"]}, "about": {"fields": {"name": {"de": "x"}}}},
    }


PYDANTIC_CASES = [
    {"theme": {"source": "bogus"}},
    {"site": {"bogus": 1}},
    {"about": {"contacts": [{"type": "phone"}]}},
    {"site": {"name": 5}},
    {"publish": {"auto": "maybe"}},
    {"site": {"languages": "en"}},
    {"site": 5},
]


def test_reason_tables_match_and_cover_answers():
    assert set(reasons.TEXT["ru"]) == set(reasons.TEXT["en"])
    source = (Path(reasons.__file__).parent / "answers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    raised = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            name = getattr(node.exc.func, "id", "")
            assert name != "ValueError", f"answers.py:{node.lineno}: причина без ключа"
            if name == "Reason":
                raised.append(node.exc.args[0].value)
    assert len(raised) >= 33
    assert set(raised) <= set(reasons.TEXT["en"])
    assert set(raised) == set(_cases()) | {"not_number", "country_bad"}


@pytest.mark.parametrize("key", sorted(_cases()))
def test_every_reason_speaks_the_language(key):
    with pytest.raises(ValueError) as caught:
        Answers.model_validate(_cases()[key])
    assert key in _keys(caught.value)
    ru, en = plain(caught.value, "ru"), plain(caught.value, "en")
    # токены: введённые значения, коды назначений и типов schema.org
    extra = _values(_cases()[key]) + tuple(PURPOSES) + tuple(vocab()["types"])
    assert CYRILLIC.search(ru), ru
    assert not _stray_latin(ru, extra), (ru, _stray_latin(ru, extra))
    assert not CYRILLIC.search(en), en
    # английский текст тот же, что до перевода: его же видит str() ошибки
    for item in caught.value.errors():
        found = (item.get("ctx") or {}).get("error")
        if isinstance(found, Reason):
            assert found.text("en") in en and str(found) == found.text("en")


@pytest.mark.parametrize("patch", PYDANTIC_CASES)
def test_pydantic_errors_are_translated(patch):
    with pytest.raises(ValueError) as caught:
        Answers.model_validate(patch)
    ru, en = plain(caught.value, "ru"), plain(caught.value, "en")
    assert CYRILLIC.search(ru) and not _stray_latin(ru), ru
    assert not CYRILLIC.search(en), en
    assert "Input should" not in ru and "Field required" not in ru


def test_audit_example_in_both_languages():
    with pytest.raises(ValueError) as caught:
        Answers.model_validate({"site": {"domain": "https://bad/"}, "analytics": {"ga4": "UA-1"}})
    assert plain(caught.value, "en") == (
        "site.domain: 'https://bad/': domain without scheme and slashes, e.g. example.com; "
        "analytics: Google Analytics 'UA-1': expected G-XXXXXXX"
    )
    assert plain(caught.value, "ru") == (
        "site.domain: 'https://bad/': домен без схемы и слешей, например example.com; "
        "analytics: Google Analytics 'UA-1': ожидается G-XXXXXXX"
    )


@pytest.mark.parametrize(
    ("key", "ru", "en"),
    [
        ("ga4_bad", "ожидается G-XXXXXXX", "expected G-XXXXXXX"),
        ("gtm_bad", "ожидается GTM-XXXXXX", "expected GTM-XXXXXX"),
    ],
)
def test_counter_reasons_say_what_is_expected_in_both_languages(key, ru, en):
    """E15.S1.T8: английская причина говорит то же, что русская, — «ожидается»."""
    assert reasons.TEXT["ru"][key].endswith(ru)
    assert reasons.TEXT["en"][key].endswith(en)


def test_apply_and_load_reasons(site: Path, tmp_path: Path):
    answers = load_answers(ANSWERS)
    answers.about.fields["country"] = "Austria"
    with pytest.raises(Reason) as caught:
        apply(site, answers)
    assert caught.value.key == "country_bad"
    assert plain(caught.value, "ru") == "страна 'AUSTRIA': двухбуквенный код, например AT"
    answers.about.fields["country"] = "AT"
    answers.about.fields["latitude"] = "north"
    with pytest.raises(Reason) as caught:
        apply(site, answers)
    assert plain(caught.value, "ru") == "'north' — не число"
    with pytest.raises(Reason) as caught:
        load_answers("- a\n")
    assert CYRILLIC.search(plain(caught.value, "ru"))
    (tmp_path / "empty").mkdir()
    with pytest.raises(Reason) as caught:
        apply(tmp_path / "empty", Answers())
    assert caught.value.key == "no_site" and CYRILLIC.search(plain(caught.value, "ru"))


def _notes(root: Path, lang: str) -> None:
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data.setdefault("build", {})["notes"] = lang
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


BAD = "site: {domain: 'https://bad/'}\nanalytics: {ga4: UA-1}\nabout: {contacts: [{type: phone}]}\n"


@pytest.mark.parametrize(
    "notes, flag, env, want",
    [
        ("ru", None, None, "ru"),
        ("en", None, None, "en"),
        ("ru", "en", None, "en"),
        ("en", "ru", None, "ru"),
        ("en", None, "ru", "ru"),
    ],
)
def test_cli_reasons_follow_the_run_language(
    site: Path, tmp_path: Path, monkeypatch, notes, flag, env, want
):
    if env:
        monkeypatch.setenv("HERON_NOTES", env)
    else:
        monkeypatch.delenv("HERON_NOTES", raising=False)
    _notes(site, notes)
    bad = tmp_path / "bad.yaml"
    bad.write_text(BAD, encoding="utf-8")
    args = ["setup", str(site), "--answers", str(bad)] + (["--notes", flag] if flag else [])
    failed = CliRunner().invoke(main, args)
    assert failed.exit_code == 2, failed.output
    text = failed.output
    assert "site.domain" in text and "about.contacts.0.value" in text
    if want == "ru":
        assert "домен без схемы" in text and "обязательное поле" in text, text
        assert not _stray_latin(text.split(":", 1)[1]), _stray_latin(text)
    else:
        assert not CYRILLIC.search(text), text
        assert "domain without scheme" in text and "Field required" in text


def test_server_reasons_follow_the_page_language(site: Path, monkeypatch):
    from tests.test_setup_access import _call, _start, _stop

    monkeypatch.delenv("HERON_NOTES", raising=False)
    _notes(site, "ru")
    port, token, thread = _start(site, "127.0.0.1")
    base = f"http://127.0.0.1:{port}"
    bad = {"answers": {"site": {"domain": "https://bad/"}, "analytics": {"ga4": "UA-1"}}}
    try:
        for lang, word in (("ru", "домен без схемы"), ("en", "domain without scheme")):
            status, body = _call(base + "/api/save", data={**bad, "lang": lang}, token=token)
            error = json.loads(body)["error"]
            assert status == 400 and word in error, error
            assert bool(CYRILLIC.search(error)) is (lang == "ru")
        # язык не прислан — язык сайта (build.notes: ru)
        status, body = _call(base + "/api/save", data=bad, token=token)
        assert "домен без схемы" in json.loads(body)["error"]
        # прочие ответы сервера — тоже на языке сайта
        status, body = _call(base + "/api/state", token="wrong")
        assert status == 403 and CYRILLIC.search(json.loads(body)["error"])
        status, body = _call(base + "/api/nothing", token=token)
        assert status == 404 and CYRILLIC.search(json.loads(body)["error"])
    finally:
        _stop(port, token, thread)


def test_port_error_is_in_the_site_language(site: Path, monkeypatch):
    import socket

    from heron.core.errors import HeronError
    from heron.setup import server

    monkeypatch.delenv("HERON_NOTES", raising=False)
    _notes(site, "ru")
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        monkeypatch.setattr(server._Server, "allow_reuse_address", False)
        with pytest.raises(HeronError) as caught:
            server.run(site, "127.0.0.1", port)
    assert caught.value.code == "E031"
    assert CYRILLIC.search(caught.value.message) and CYRILLIC.search(caught.value.hint)
    assert f"--port {port + 1}" in caught.value.hint


def test_page_sends_its_language_with_save():
    """Переключатель языка страницы (L) уходит с сохранением: причины — на нём."""
    page = (Path(reasons.__file__).parent / "page.html").read_text(encoding="utf-8")
    call = next(line for line in page.splitlines() if 'fetch("/api/save"' in line)
    assert re.search(r"JSON\.stringify\(\{[^}]*\blang: L\b", call), call


# --- тема из анкеты на языке пояснений сайта (E15.S1.T10, W1, F07) -------------------

STARTER_ANSWERS = "site:\n  name: Example\n  languages: [en]\ntheme:\n  source: starter\n"
RU_THEME = "# Что тема ждёт от site.yaml"
EN_THEME = "# What the theme expects from site.yaml"
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _site_with_notes(tmp_path: Path, notes: str) -> Path:
    root = tmp_path / f"site-{notes}"
    create(root, name="Example", languages=["en"], notes=notes)
    return root


def _theme_yaml(root: Path) -> str:
    return (root / "theme" / "theme.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "notes, flag, env, want",
    [
        ("ru", None, None, "ru"),  # build.notes сайта
        ("en", None, None, "en"),
        ("en", None, "ru", "ru"),  # HERON_NOTES главнее build.notes
        ("ru", "en", "ru", "en"),  # флаг главнее всего
        ("en", "ru", None, "ru"),
    ],
)
def test_setup_installs_the_starter_in_the_notes_language(
    tmp_path: Path, monkeypatch, notes, flag, env, want
):
    if env:
        monkeypatch.setenv("HERON_NOTES", env)
    else:
        monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site_with_notes(tmp_path, notes)
    (root / "theme" / "theme.yaml").write_text("name: old\n", encoding="utf-8")
    result = apply(root, load_answers(STARTER_ANSWERS), lang=flag)
    assert result.theme == "starter"
    assert (RU_THEME if want == "ru" else EN_THEME) in _theme_yaml(root)
    css = (root / "theme" / "assets" / "site.css").read_text(encoding="utf-8")
    head = css.split("*/", 1)[0]
    assert bool(CYRILLIC_RE.search(head)) == (want == "ru"), head


def test_setup_command_installs_the_starter_in_the_site_language(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = _site_with_notes(tmp_path, "ru")
    done = CliRunner().invoke(main, ["setup", str(root), "--answers", "-"], input=STARTER_ANSWERS)
    assert done.exit_code == 0, done.output
    assert RU_THEME in _theme_yaml(root)
    en = _site_with_notes(tmp_path, "en")
    done = CliRunner().invoke(
        main, ["setup", str(en), "--answers", "-", "--notes", "ru"], input=STARTER_ANSWERS
    )
    assert done.exit_code == 0, done.output
    assert RU_THEME in _theme_yaml(en)


def test_notes_lang_survives_build_that_is_not_a_block():
    from heron.setup import notes_lang

    assert notes_lang({"build": "x"}) == "en"
    assert notes_lang({"build": [1]}) == "en"
    assert notes_lang({"build": {"notes": "ru"}}) == "ru"
    assert notes_lang({"build": "x"}, "ru") == "ru"
