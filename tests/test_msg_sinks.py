"""Точки показа рендерят Msg по языку запуска: cli _fail, check --json, watch, setup/server."""

import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron import cli, setup
from heron.core import watch
from heron.core.errors import HeronError
from heron.messages import Msg, rendered
from heron.scaffold import create
from heron.setup import server

CYR = re.compile("[а-яА-ЯёЁ]")


def _error() -> HeronError:
    return HeronError(
        "E030",
        Msg("report_old_not_utf8", byte=3),
        path="old.txt",
        hint=Msg("report_old_not_utf8_hint"),
    )


def test_render_follows_language():
    err = _error()
    en = err.render("en")
    assert "the old URLs file is not UTF-8 (byte 3)" in en
    assert "re-save the file as UTF-8" in en
    assert not CYR.search(en.replace("what to do", ""))
    assert "пересохраните файл" in err.render("ru")
    assert str(err) == err.render("ru")


def test_rendered_keeps_plain_strings():
    assert rendered("plain", "en") == "plain"
    assert rendered(None, "en") is None


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_fail_prints_in_language(capsys, lang):
    with pytest.raises(SystemExit) as exit_info:
        cli._fail(_error(), lang)
    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert ("пересохраните файл" in err) == (lang == "ru")
    assert ("re-save the file as UTF-8" in err) == (lang == "en")


def test_watch_once_renders_error_by_language(monkeypatch, tmp_path, capsys):
    def boom(*args, **kwargs):
        raise _error()

    monkeypatch.setattr(watch.pipeline, "run", boom)
    watch.once(tmp_path, False, lang="en")
    assert "the old URLs file is not UTF-8 (byte 3)" in capsys.readouterr().out
    watch.once(tmp_path, False, lang="ru")
    assert "пересохраните файл" in capsys.readouterr().out


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    create(root, name="S", languages=["en"], demo=True, notes="en")
    return root


def _json(output: str) -> dict:
    return json.JSONDecoder().raw_decode(output[output.index("{") :])[0]


def _old_urls(tmp_path: Path) -> Path:
    path = tmp_path / "old.txt"
    path.write_text("https://example.com\n/gone-page/\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("lang", "message", "hint"),
    [
        ("en", "the old URLs file is not UTF-8", "re-save the file as UTF-8"),
        ("ru", "не в UTF-8", "пересохраните файл"),
    ],
)
def test_check_json_error_follows_language(tmp_path, lang, message, hint):
    root = _site(tmp_path)
    old = tmp_path / "old.txt"
    old.write_bytes(b"/page/\n\xff\xfe\n")
    args = ["check", str(root), "--json", "--old-urls", str(old), "--notes", lang]
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 1, result.output
    item = _json(result.output)["errors"][0]
    assert item["code"] == "E030"
    assert message in item["message"]
    assert hint in item["hint"]


@pytest.mark.parametrize(
    ("lang", "summary"),
    [("en", "old URLs: 2, without a path: 1"), ("ru", "старых адресов: 2, без пути: 1")],
)
def test_old_urls_summary_follows_language(tmp_path, lang, summary):
    root = _site(tmp_path)
    old = _old_urls(tmp_path)
    base = ["check", str(root), "--old-urls", str(old), "--notes", lang]
    text = CliRunner().invoke(cli.main, base)
    assert summary in text.output
    as_json = CliRunner().invoke(cli.main, [*base, "--json"])
    assert _json(as_json.output)["old_urls"]["summary"] == summary


@pytest.mark.parametrize(
    ("lang", "message", "hint"),
    [
        ("en", "the old URLs file is not UTF-8 (byte 3)", "re-save the file as UTF-8"),
        ("ru", "не в UTF-8", "пересохраните файл"),
    ],
)
def test_setup_save_renders_error_in_page_language(tmp_path, monkeypatch, lang, message, hint):
    def refuse(*args, **kwargs):
        raise _error()

    monkeypatch.setattr(setup, "apply", refuse)
    root = _site(tmp_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    box: dict[str, str] = {}
    thread = threading.Thread(
        target=server.run,
        args=(root, "127.0.0.1", port),
        kwargs={"on_ready": lambda token: box.update(token=token)},
        daemon=True,
    )
    thread.start()
    while "token" not in box:
        time.sleep(0.01)

    def post(path: str, data: dict) -> urllib.request.Request:
        return urllib.request.Request(
            f"http://localhost:{port}{path}",
            data=json.dumps(data).encode("utf-8"),
            headers={"X-Heron-Token": box["token"], "Content-Type": "application/json"},
            method="POST",
        )

    try:
        answers = setup.load_answers(setup.current_answers(root)).model_dump(mode="json")
        request = post("/api/save", {"lang": lang, "answers": answers})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        assert caught.value.code == 400
        body = json.loads(caught.value.read().decode("utf-8"))
        assert body["ok"] is False
        assert message in body["error"]
        assert hint in body["hint"]
    finally:
        urllib.request.urlopen(post("/api/stop", {}), timeout=5).read()
        thread.join(timeout=5)


_NOTICE_PLUGIN = """
def register(hooks):
    hooks.on("on_build_finished", lambda site, config, dist: {"late.txt": "x"})
"""


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "a plugin returned files from on_build_finished"),
        ("ru", "плагин вернул файлы из on_build_finished"),
    ],
)
def test_build_notice_follows_language(tmp_path, lang, text):
    root = _site(tmp_path)
    plugin = root / "plugins" / "late"
    plugin.mkdir(parents=True)
    (plugin / "__init__.py").write_text(_NOTICE_PLUGIN, encoding="utf-8")
    config = root / "site.yaml"
    config.write_text(config.read_text(encoding="utf-8") + "\nplugins: [late]\n", encoding="utf-8")
    result = CliRunner().invoke(cli.main, ["build", str(root), "--notes", lang])
    assert result.exit_code == 0, result.output
    assert text in result.output
    if lang == "en":
        assert not re.search("[А-Яа-яЁё]", result.output)
