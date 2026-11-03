"""Сообщения build: ru прежний байт в байт, en без кириллицы (E15.S2.T18)."""

import re

import pytest

from heron.core import build, output
from heron.core.errors import Collector, HeronError
from heron.messages import Msg
from heron.texts import build as texts

CYR = re.compile(r"[А-Яа-яЁё]")


def _check(msg, ru: str) -> None:
    assert isinstance(msg, Msg)
    assert msg.text("ru") == ru
    assert str(msg) == ru
    assert not CYR.search(msg.text("en"))


@pytest.mark.parametrize("raw", ["abc", "65", "-1"])
def test_bad_workers(monkeypatch, raw):
    monkeypatch.setenv(build.WORKERS_ENV, raw)
    with pytest.raises(HeronError) as caught:
        build.env_workers()
    err = caught.value
    _check(err.message, f"{build.WORKERS_ENV}={raw!r}: нужно целое число от 0 до 64")
    _check(
        err.hint,
        "0 - по числу ядер, 1 - без пула процессов; пустое значение - как в site.yaml",
    )
    assert err.message.text("en") == (
        f"{build.WORKERS_ENV}={raw!r}: an integer from 0 to 64 is required"
    )


def test_all_keys_have_both_languages_without_cyrillic_in_en():
    assert texts.TEXT["ru"].keys() == texts.TEXT["en"].keys()
    for text in texts.TEXT["en"].values():
        assert not CYR.search(text)
        assert "—" not in text and "–" not in text


def test_no_home_page_texts():
    _check(
        Msg("build_no_home_page", lang="uk", home="/uk/"),
        "у языка 'uk' нет главной страницы: /uk/ ответит 404",
    )
    _check(Msg("build_no_home_page_hint"), "создайте index.md в корне языка")
    assert Msg("build_no_home_page", lang="uk", home="/uk/").text("en") == (
        "language 'uk' has no home page: /uk/ would answer 404"
    )


def test_prod_empty_site_reports_msg(tmp_path):
    from heron.core.environment import BuildEnv
    from heron.scaffold import create
    from tests import sites

    root = tmp_path / "site"
    create(root, name="Example", languages=["en"])
    sites.clear_content(root)
    try:
        result = build.run(
            root, dist=tmp_path / "dist", with_media=False, env=BuildEnv.named("prod")
        )
        errors = result.collector.errors
    except HeronError as error:
        errors = [error]
    by_code = {e.code: e for e in errors}
    assert "E017" in by_code
    _check(by_code["E017"].message, "в проде нечего собирать: ни одной страницы")
    _check(
        by_code["E017"].hint,
        "проверьте путь к контенту и языки в site.yaml; пустую сборку можно делать только в деве",
    )
    assert by_code["E017"].message.text("en") == (
        "nothing to build in production: there are no pages"
    )


def _claim_conflict(tmp_path) -> HeronError:
    """Файл темы и файл static/ дают один и тот же файл сборки."""
    (tmp_path / "static" / "assets").mkdir(parents=True)
    (tmp_path / "static" / "assets" / "a.css").write_text("s", encoding="utf-8")
    (tmp_path / "theme").mkdir()
    (tmp_path / "theme" / "a.css").write_text("t", encoding="utf-8")
    outputs = output.Outputs()
    collector = Collector()
    build._claim_tree(
        outputs, tmp_path / "static", "", "static", lambda rel: f"static/{rel}", collector
    )
    build._claim_tree(
        outputs,
        tmp_path / "theme",
        "assets/",
        "asset",
        lambda rel: Msg("build_owner_theme_asset", rel=rel),
        collector,
    )
    assert len(collector.errors) == 1
    return collector.errors[0]


def test_theme_asset_owner_stays_msg_in_conflict(tmp_path):
    error = _claim_conflict(tmp_path)
    _check(
        error.message,
        "два источника дают один файл сборки assets/a.css: static/assets/a.css и тема assets/a.css",
    )
    assert error.message.text("en") == (
        "two sources give one build file assets/a.css: static/assets/a.css and theme assets/a.css"
    )
    assert not CYR.search(error.hint.text("en"))


def test_theme_asset_conflict_path_keeps_msg(tmp_path):
    _check(_claim_conflict(tmp_path).path, "тема assets/a.css")


def _owner() -> Msg:
    return Msg("media_owner_more", page="a.md", count=2)


def test_error_with_msg_path_has_no_cyrillic_in_en(tmp_path):
    from heron.core import report

    error = _claim_conflict(tmp_path)
    collector = Collector()
    collector.errors.append(error)
    assert not CYR.search(error.render("en"))
    assert "тема assets/a.css" in error.render("ru")
    assert not CYR.search(report._error_text(error, "en"))
    assert "тема assets/a.css" in report._error_text(error, "ru")


def test_warning_with_msg_path_in_summary_and_full_file(tmp_path):
    from heron.core import report

    collector = Collector()
    collector.warn("text", path=_owner(), line=3, kind="media")
    full = tmp_path / "full.txt"
    en = report.summary(collector, full, lang="en")
    assert not CYR.search(en.split("\n", 1)[1].replace("прочее", ""))
    assert "a.md and 2 more:3" in en
    assert "a.md and 2 more:3" in full.read_text(encoding="utf-8")
    ru = report.summary(collector, tmp_path / "ru.txt", lang="ru")
    assert "a.md и ещё 2:3" in ru


def test_cli_fail_renders_msg_path_en(tmp_path, capsys):
    from heron import cli

    error = HeronError("E011", "plain", path=_owner(), line=4)
    with pytest.raises(SystemExit):
        cli._fail(error, "en")
    assert "a.md and 2 more:4" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli._fail(error, "ru")
    assert "a.md и ещё 2:4" in capsys.readouterr().err
