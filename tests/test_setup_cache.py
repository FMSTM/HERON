"""Конфигуратор: сроки кэша браузера (nginx.cache) - вкладка «Сайт» и --answers/--dump."""

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
    assert "cache" not in (_yaml(site).get("nginx") or {})
    assert load_answers(current_answers(site)).cache.model_dump() == {
        "versioned": "1y",
        "assets": "1d",
        "media": "1d",
    }


def test_answers_round_trip(site):
    text = current_answers(site)
    data = yaml.safe_load(text)
    data["cache"] = {"versioned": "30d", "assets": "2h", "media": "7d"}
    apply(site, load_answers(yaml.safe_dump(data)))
    assert _yaml(site)["nginx"]["cache"] == {"versioned": "30d", "assets": "2h", "media": "7d"}
    config = load_site(site / "site.yaml")
    assert config.nginx.cache.seconds("assets") == 7200
    dumped = current_answers(site)
    assert yaml.safe_load(dumped)["cache"] == {"versioned": "30d", "assets": "2h", "media": "7d"}
    # подать выгрузку обратно - ничего не меняется
    assert apply(site, load_answers(dumped)).written == []


def test_hand_written_key_and_other_nginx_keys_survive(site):
    path = site / "site.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\nnginx:\n  hash_sizes: auto\n  cache:\n    media: 1d  # руками\n",
        encoding="utf-8",
    )
    answers = load_answers(current_answers(site))
    answers.cache.assets = "12h"
    apply(site, answers)
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["nginx"] == {"hash_sizes": "auto", "cache": {"media": "1d", "assets": "12h"}}
    assert "# руками" in text


@pytest.mark.parametrize("value", ["2x", "1.5d", "-5", "forever"])
def test_bad_time_is_rejected(value):
    with pytest.raises(ValueError, match="nginx.cache.assets"):
        Answers.model_validate({"cache": {"assets": value}})


def test_cli_answers_and_dump(site, tmp_path):
    answers = tmp_path / "answers.yaml"
    data = yaml.safe_load(current_answers(site))
    data["cache"]["media"] = "3d"
    answers.write_text(yaml.safe_dump(data), encoding="utf-8")
    runner = CliRunner()
    out = runner.invoke(main, ["setup", str(site), "--answers", str(answers)])
    assert out.exit_code == 0, out.output
    assert _yaml(site)["nginx"]["cache"] == {"media": "3d"}
    dumped = runner.invoke(main, ["setup", str(site), "--dump"])
    assert yaml.safe_load(dumped.output)["cache"]["media"] == "3d"
    data["cache"]["media"] = "3 days"
    answers.write_text(yaml.safe_dump(data), encoding="utf-8")
    bad = runner.invoke(main, ["setup", str(site), "--answers", str(answers)])
    assert bad.exit_code != 0 and "nginx.cache.media" in bad.output


def test_page_has_cache_fields():
    page = (Path(__file__).parents[1] / "heron" / "setup" / "page.js").read_text("utf-8")
    for path in ("cache.versioned", "cache.assets", "cache.media"):
        assert f'"{path}"' in page
    for key in ("cache_t", "cache_about", "cache_v_h", "cache_a_h", "cache_m_h"):
        assert page.count(f"{key}:") == 2, key  # ru и en
