"""Конфигуратор: HSTS, возможности браузера и адрес в журнале (nginx.hsts, nginx.permissions,
nginx.log_ip) - вкладка «Сайт» и --answers/--dump."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.contracts.site import load_site
from heron.scaffold import create
from heron.setup import apply, current_answers, load_answers
from heron.setup.answers import Answers


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"])
    return root


def _yaml(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))


def test_defaults_are_not_written(site):
    apply(site, load_answers(current_answers(site)))
    assert "nginx" not in _yaml(site) or not {"hsts", "permissions", "log_ip"} & set(
        _yaml(site)["nginx"]
    )
    dumped = yaml.safe_load(current_answers(site))
    assert dumped["hsts"] == {"max_age": "1y", "subdomains": True, "preload": False}
    assert dumped["permissions"] == {}
    assert dumped["log_ip"] == "masked"


def test_answers_round_trip_writes_only_changes(site):
    data = yaml.safe_load(current_answers(site))
    data["hsts"]["max_age"] = "2y"
    data["permissions"] = {"geolocation": "self", "fullscreen": "self", "autoplay": ""}
    data["log_ip"] = "off"
    apply(site, load_answers(yaml.safe_dump(data)))
    # fullscreen: self - умолчание, autoplay пустой - умолчание: не пишутся
    assert _yaml(site)["nginx"] == {
        "hsts": {"max_age": "2y"},
        "permissions": {"geolocation": "self"},
        "log_ip": "off",
    }
    config = load_site(site / "site.yaml")
    assert config.nginx.hsts.seconds == 2 * 31536000
    assert config.nginx.log_ip == "off"
    dumped = current_answers(site)
    back = yaml.safe_load(dumped)
    assert back["hsts"]["max_age"] == "2y"
    assert back["permissions"] == {"geolocation": "self"}
    assert back["log_ip"] == "off"
    # подать выгрузку обратно - ничего не меняется
    assert apply(site, load_answers(dumped)).written == []


def test_hand_written_forms_and_comments_survive(site):
    path = site / "site.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nnginx:\n  hash_sizes: auto\n  hsts:\n    subdomains: false  # блог без https\n"
        "  permissions:\n    camera: [self]  # руками\n    payment: none\n  log_ip: off\n",
        encoding="utf-8",
    )
    answers = load_answers(current_answers(site))
    assert answers.permissions == {"camera": "self", "payment": "none"}
    assert answers.log_ip == "off" and answers.hsts.subdomains is False
    answers.permissions["geolocation"] = "self"
    apply(site, answers)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["nginx"]["permissions"] == {
        "camera": ["self"],
        "payment": "none",
        "geolocation": "self",
    }
    assert data["nginx"]["hsts"] == {"subdomains": False}
    assert data["nginx"]["log_ip"] is False  # off без кавычек остался как был
    assert "# руками" in text and "# блог без https" in text


def test_returning_to_default_or_removing_drops_the_key(site):
    path = site / "site.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nnginx:\n  permissions:\n    camera: self\n    geolocation: self\n",
        encoding="utf-8",
    )
    answers = load_answers(current_answers(site))
    answers.permissions["camera"] = "none"  # вернули умолчание
    del answers.permissions["geolocation"]  # сняли в конфигураторе
    apply(site, answers)
    assert "permissions" not in (_yaml(site).get("nginx") or {})


@pytest.mark.parametrize(
    ("patch", "words"),
    [
        ({"hsts": {"max_age": "180d", "preload": True}}, "hstspreload.org"),
        ({"hsts": {"preload": True, "subdomains": False}}, "hstspreload.org"),
        ({"hsts": {"max_age": "forever"}}, "nginx.hsts.max_age"),
        ({"permissions": {"geolocaton": "self"}}, "'geolocation'"),
        ({"permissions": {"camera": "everyone"}}, "nginx.permissions.camera"),
        ({"log_ip": "half"}, "nginx.log_ip"),
    ],
)
def test_bad_answers_are_rejected(patch, words):
    with pytest.raises(ValueError, match=words.replace(".", r"\.")):
        Answers.model_validate(patch)


def test_preload_with_a_year_and_subdomains_is_fine(site):
    data = yaml.safe_load(current_answers(site))
    data["hsts"]["preload"] = True
    apply(site, load_answers(yaml.safe_dump(data)))
    assert _yaml(site)["nginx"]["hsts"] == {"preload": True}
    assert load_site(site / "site.yaml").nginx.hsts.header() == (
        "max-age=31536000; includeSubDomains; preload"
    )


def test_cli_answers_and_dump(site, tmp_path):
    answers = tmp_path / "answers.yaml"
    data = yaml.safe_load(current_answers(site))
    data["permissions"] = {"fullscreen": "*"}
    data["log_ip"] = "full"
    answers.write_text(yaml.safe_dump(data), encoding="utf-8")
    runner = CliRunner()
    out = runner.invoke(main, ["setup", str(site), "--answers", str(answers)])
    assert out.exit_code == 0, out.output
    assert _yaml(site)["nginx"] == {"permissions": {"fullscreen": "*"}, "log_ip": "full"}
    dumped = yaml.safe_load(runner.invoke(main, ["setup", str(site), "--dump"]).output)
    assert dumped["permissions"] == {"fullscreen": "*"} and dumped["log_ip"] == "full"
    data["hsts"] = {"max_age": "1d", "preload": True}
    answers.write_text(yaml.safe_dump(data), encoding="utf-8")
    bad = runner.invoke(main, ["setup", str(site), "--answers", str(answers)])
    assert bad.exit_code != 0 and "hstspreload.org" in bad.output


def test_page_has_the_fields():
    page = (Path(__file__).parents[1] / "heron" / "setup" / "page.js").read_text("utf-8")
    for path in ("hsts.max_age", "hsts.", "permissions.", "log_ip"):
        assert f'"{path}' in page, path
    for key in (
        "hsts_t",
        "hsts_about",
        "hsts_age_h",
        "hsts_sub_s",
        "hsts_pre_s",
        "perm_t",
        "perm_about",
        "perm_fullscreen_h",
        "perm_autoplay_h",
        '"perm_picture-in-picture_h"',
        "perm_geolocation_h",
        "perm_camera_h",
        "perm_microphone_h",
        "perm_payment_h",
        "log_t",
        "log_ip_h",
    ):
        assert page.count(f"{key}:") == 2, key  # ru и en
    # preload трудно отменить - подсказка это говорит
    assert "трудно" in page and "hard to undo" in page
