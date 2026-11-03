"""Негодные значения site.yaml дают E011 с понятным текстом (E3.S1.T10)."""

from pathlib import Path

import pytest

from heron.contracts.site import load_site
from heron.core.errors import HeronError

BASE = """heron: {heron}
site:
  name: S
  domain: example.com
  theme: t
  languages: [en, ru]
  default_lang: en
{extra}"""


def _write(tmp_path: Path, extra: str = "", heron: str = '">=0.1"') -> Path:
    path = tmp_path / "site.yaml"
    path.write_text(BASE.format(heron=heron, extra=extra), encoding="utf-8")
    return path


@pytest.mark.parametrize("extra", ["i18n: 5\n", "i18n:\n  name: 5\n"])
def test_i18n_bad_shape(tmp_path, extra):
    # i18n верхнего уровня не входит в SiteConfig: кладём в блок site
    path = tmp_path / "site.yaml"
    body = BASE.format(heron='">=0.1"', extra="").rstrip("\n")
    body += "\n  " + extra.replace("\n  ", "\n    ").rstrip("\n") + "\n"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(HeronError) as caught:
        load_site(path)
    assert caught.value.code == "E011"
    assert str(path) in str(caught.value.path)


@pytest.mark.parametrize("line", ["alternate_names_ru: Сайт", "name_ru: 5"])
def test_i18n_bad_value(tmp_path, line):
    path = tmp_path / "site.yaml"
    path.write_text(
        BASE.format(heron='">=0.1"', extra="").rstrip("\n") + f"\n  {line}\n", encoding="utf-8"
    )
    with pytest.raises(HeronError) as caught:
        load_site(path)
    assert caught.value.code == "E011"
    assert line.split(":")[0] in caught.value.message.text("en")


def test_good_suffixed_values_pass(tmp_path):
    path = tmp_path / "site.yaml"
    path.write_text(
        BASE.format(heron='">=0.1"', extra="").rstrip("\n")
        + "\n  alternate_names_ru: [Сайт]\n  name_ru: Сайт\n",
        encoding="utf-8",
    )
    cfg = load_site(path)
    assert cfg.site.i18n["name"]["ru"] == "Сайт"
    assert cfg.site.i18n["alternate_names"]["ru"] == ["Сайт"]


def test_heron_number_without_quotes(tmp_path):
    with pytest.raises(HeronError) as caught:
        load_site(_write(tmp_path, heron="0.1"))
    assert caught.value.code == "E011"
    assert "кавыч" in caught.value.hint.text("ru")
    assert "quotes" in caught.value.hint.text("en")


def test_unknown_engine_version_still_e012(tmp_path):
    path = _write(tmp_path, extra="unknown_key: 1\n", heron='">=99.0"')
    with pytest.raises(HeronError) as caught:
        load_site(path)
    assert caught.value.code == "E012"
