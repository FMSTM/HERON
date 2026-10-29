"""heron check --old-urls: каждый старый адрес ведёт на страницу, в redirect_from или в gone."""

from __future__ import annotations

from click.testing import CliRunner

from heron.cli import main
from heron.core import links, report, tree
from heron.core.errors import HeronError
from heron.scaffold import create
from tests import sites


def _site(tmp_path, ru_extra=None, **config_over):
    files = {
        "uk/index.md": sites.page("Головна"),
        "ru/index.md": sites.page("Главная"),
        "ru/glavnaja.md": sites.page("Главная страница", **(ru_extra or {})),
        "ru/uslugi.md": sites.page("Услуги"),
    }
    content = sites.build(tmp_path, files)
    config = sites.config(**config_over)
    site, _ = tree.scan(content, config)
    return site, config


def _lost(site, config, *urls):
    warnings, _ = report.old_urls(list(urls), site, config)
    return [w.message for w in warnings]


def test_old_slug_without_language_prefix_is_found_then_silent(tmp_path):
    # случай myspine: в redirect_from только вариант с префиксом /ru/
    site, config = _site(tmp_path, {"redirect_from": ["/ru/staryj-slug"]})
    messages = _lost(site, config, "/staryj-slug")
    assert len(messages) == 1
    assert "/staryj-slug никуда не ведёт" in messages[0] or "leads nowhere" in messages[0]

    site, config = _site(tmp_path / "fixed", {"redirect_from": ["/ru/staryj-slug", "/staryj-slug"]})
    assert _lost(site, config, "/staryj-slug") == []


def test_slash_variants_are_equal(tmp_path):
    site, config = _site(tmp_path, {"redirect_from": ["/old/"]})
    assert _lost(site, config, "/old", "/old/") == []


def test_absolute_url_uses_path_only(tmp_path):
    site, config = _site(tmp_path, {"redirect_from": ["/old/"]})
    assert _lost(site, config, "https://example.com/old/?utm=1#x") == []
    assert len(_lost(site, config, "https://example.com/other/")) == 1


def test_percent_encoding_equals_cyrillic(tmp_path):
    site, config = _site(tmp_path, {"redirect_from": ["/новини/"]})
    assert _lost(site, config, "/%D0%BD%D0%BE%D0%B2%D0%B8%D0%BD%D0%B8/") == []


def test_existing_page_is_fine(tmp_path):
    site, config = _site(tmp_path)
    assert _lost(site, config, "/ru/uslugi/", "/") == []


def test_gone_is_silent(tmp_path):
    site, config = _site(tmp_path, gone=["/wp-admin/*", "/arhiv/"])
    assert _lost(site, config, "/wp-admin/x.php", "/arhiv", "/arhiv/") == []


def test_case_must_match(tmp_path):
    site, config = _site(tmp_path, {"redirect_from": ["/old/"]})
    assert len(_lost(site, config, "/Old/")) == 1


def test_suggest_nearest_page_by_slug(tmp_path):
    site, config = _site(tmp_path)
    page = links.suggest_target("/ru/uslugy/", site, config)
    assert page.url == "/ru/uslugi/"
    message = _lost(site, config, "/ru/uslugy/")[0]
    assert "/ru/uslugi/" in message and "redirect_from" in message


def test_suggest_falls_back_to_home_of_language(tmp_path):
    site, config = _site(tmp_path)
    assert links.suggest_target("/ru/zzzzzz/", site, config).url == "/ru/"
    assert links.suggest_target("/qqqqq/", site, config).url == "/"


def test_read_file_plain_and_csv(tmp_path):
    path = tmp_path / "urls.txt"
    path.write_text(
        "# комментарий\n\n/a/\nhttps://example.com/b/\n"
        "Top pages,Clicks\nhttps://example.com/c/,12\n",
        encoding="utf-8",
    )
    assert report.read_old_urls(path) == ["/a/", "https://example.com/b/", "https://example.com/c/"]


def test_summary_counts(tmp_path):
    site, config = _site(tmp_path, {"redirect_from": ["/old/"]})
    _, summary = report.old_urls(["/old/", "/lost/", "/lost/"], site, config)
    assert "2" in summary and "1" in summary


def test_cli_check_old_urls(tmp_path):
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"])
    urls = tmp_path / "urls.txt"
    urls.write_text("/glavnaja-rus\n", encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(root), "--old-urls", str(urls)])
    assert "/glavnaja-rus" in result.output
    assert "redirect_from" in result.output
    missing = CliRunner().invoke(main, ["check", str(root), "--old-urls", str(tmp_path / "no.txt")])
    assert missing.exit_code != 0


def test_same_url_written_three_ways_counts_once(tmp_path):
    site, config = _site(tmp_path)
    warnings, summary = report.old_urls(
        ["https://example.com/lost/", "/lost", "/lost/"], site, config
    )
    assert len(warnings) == 1
    assert summary.count("1") == 2 and "3" not in summary
    assert links.old_key("https://example.com/lost/") == links.old_key("/lost")


def test_not_utf8_file_is_engine_error(tmp_path):
    path = tmp_path / "urls.csv"
    path.write_bytes("/старый-адрес/\n".encode("cp1251"))
    try:
        report.read_old_urls(path)
    except HeronError as error:
        assert error.code == "E030"
        assert error.hint
    else:
        raise AssertionError("ожидалась HeronError")


def test_cli_not_utf8_file_no_traceback(tmp_path):
    root = tmp_path / "site"
    create(root, name="Example", languages=["en"])
    urls = tmp_path / "urls.csv"
    urls.write_bytes("/старый-адрес/\n".encode("cp1251"))
    result = CliRunner().invoke(main, ["check", str(root), "--old-urls", str(urls)])
    assert result.exit_code != 0
    assert "E030" in result.output
    assert not isinstance(result.exception, UnicodeDecodeError)
