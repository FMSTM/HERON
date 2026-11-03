"""Негодные строки темы, сбои шаблона и плагина: код, файл, страница (E4.S3.T3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from heron.core import build as pipeline
from heron.core.errors import Collector, HeronError
from heron.core.hooks import Hooks
from heron.core.render import env as envmod
from heron.scaffold import create


def make(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"])
    (root / "content/en/a.md").write_text(
        "---\ntitle: A\nh1: A page\ndescription: D\n---\n\nText.\n", encoding="utf-8"
    )
    return root


def strings_file(root: Path) -> Path:
    path = root / "theme/i18n/en.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def codes(result) -> list[str]:
    return [e.code for e in result.collector.errors]


@pytest.mark.parametrize(
    "content",
    [b"key: [unclosed\n", b"\xff\xfe\x00bad", b"- one\n- two\n"],
    ids=["broken-yaml", "not-utf8", "list"],
)
def test_bad_strings_file_is_e008_in_build_and_check(tmp_path: Path, content: bytes) -> None:
    root = make(tmp_path)
    path = strings_file(root)
    path.write_bytes(content)
    for run in (pipeline.run, pipeline.check):
        try:
            result = run(root)
            errors = result.collector.errors
        except HeronError:
            pytest.fail("ошибка файла строк не должна обрывать проход")
        found = [e for e in errors if e.code == "E008" and "i18n" in (e.path or "")]
        assert found, [e.code for e in errors]
        assert found[0].path.endswith("en.yaml")


def test_empty_strings_file_is_not_an_error(tmp_path: Path) -> None:
    root = make(tmp_path)
    strings_file(root).write_text("", encoding="utf-8")
    result = pipeline.run(root)
    assert "E008" not in codes(result)
    assert envmod.load_strings(root / "theme", "en", Collector()).__class__.__name__ == "Strings"


def test_bad_strings_file_does_not_hide_other_errors(tmp_path: Path) -> None:
    root = make(tmp_path)
    strings_file(root).write_text("key: [unclosed\n", encoding="utf-8")
    (root / "content/en/odd.md").write_text(
        "---\ntitle: O\nh1: O\ntype: no-such-type\ndescription: D\n---\n\nT.\n", encoding="utf-8"
    )
    result = pipeline.check(root)
    paths = [e.path or "" for e in result.collector.errors if e.code == "E008"]
    assert any("i18n" in p for p in paths)
    assert any("odd.md" in p for p in paths)


def test_template_runtime_exception_is_e010_and_others_render(tmp_path: Path) -> None:
    root = make(tmp_path)
    page = root / "theme/templates/page.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace("</h1>", "</h1>{% for x in 5 %}{% endfor %}", 1),
        encoding="utf-8",
    )
    result = pipeline.run(root)
    found = [e for e in result.collector.errors if e.code == "E010"]
    assert found
    assert "page.html" in str(found[0].message)
    assert "TypeError" in str(found[0].message)
    assert (found[0].path or "").endswith(".md")


PLUGIN = """
def register(hooks):
    hooks.on("{hook}", {handler})
"""


def plugin(root: Path, hook: str, handler: str) -> None:
    folder = root / "plugins/probe"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text(
        "from heron.core.errors import HeronError\n"
        "from heron.messages import Msg\n"
        "def boom(*a, **k):\n    raise RuntimeError('kaboom')\n"
        "def own(*a, **k):\n    raise HeronError(code='E099', message='mine')\n"
        + PLUGIN.format(hook=hook, handler=handler),
        encoding="utf-8",
    )
    cfg = root / "site.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "\nplugins: [probe]\n", encoding="utf-8")


def test_plugin_crash_in_page_rendered_is_e014(tmp_path: Path) -> None:
    root = make(tmp_path)
    plugin(root, "on_page_rendered", "boom")
    result = pipeline.run(root)
    found = [e for e in result.collector.errors if e.code == "E014"]
    assert found
    text = str(found[0].message)
    assert "on_page_rendered" in text and "kaboom" in text and "probe" in text


def test_plugin_crash_in_on_config_is_heron_error(tmp_path: Path) -> None:
    root = make(tmp_path)
    plugin(root, "on_config", "boom")
    with pytest.raises(HeronError) as info:
        pipeline.run(root)
    assert info.value.code == "E014"


def test_plugin_heron_error_keeps_its_code() -> None:
    hooks = Hooks()

    def own(*args):
        raise HeronError(code="E099", message="mine")

    hooks.on("on_page_rendered", own)
    with pytest.raises(HeronError) as info:
        hooks.pipe("on_page_rendered", None, "x")
    assert info.value.code == "E099"
    hooks.on("on_config", own)
    with pytest.raises(HeronError) as info:
        hooks.call("on_config")
    assert info.value.code == "E099"


def test_hooks_wrap_plain_exceptions() -> None:
    hooks = Hooks()
    hooks.on("on_config", lambda: 1 / 0)
    with pytest.raises(HeronError) as info:
        hooks.call("on_config")
    assert info.value.code == "E014"
    assert "ZeroDivisionError" in str(info.value.message)
