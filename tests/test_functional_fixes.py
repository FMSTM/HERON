"""Функциональные расхождения из аудита — каждое наблюдаемым поведением."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from heron.core import build as pipeline
from heron.core import links, tree, watch
from heron.core.environment import BuildEnv
from heron.core.errors import HeronError
from heron.core.parser import markdown
from heron.scaffold import create
from tests import sites

ROOT = Path(__file__).resolve().parents[1]
PAGE = "---\ntitle: {t}\nh1: {t} page\ndescription: D\n{extra}---\n\n{body}\n"


def make(tmp_path: Path, langs=("en",)) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=list(langs))
    return root


def write(root: Path, rel: str, text: str) -> None:
    path = root / "content" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- scripts/site.sh new ---------------------------------------------------------


def test_site_sh_new_runs_before_engine_settings_are_needed(tmp_path):
    """`new` звал is_source_checkout и $STABLE до того, как они объявлены."""
    heron = tmp_path / "heron"
    (heron / "scripts").mkdir(parents=True)
    (heron / "env").mkdir()
    shutil.copy(ROOT / "scripts/site.sh", heron / "scripts/site.sh")
    shutil.copy(ROOT / "env/.env.example", heron / "env/.env.example")
    stub = tmp_path / "bin"
    stub.mkdir()
    calls = tmp_path / "docker-calls.txt"
    (stub / "docker").write_text(f'#!/bin/sh\necho "$@" >> {calls}\nexit 0\n', encoding="utf-8")
    (stub / "docker").chmod(0o755)
    (tmp_path / "sites").mkdir()
    done = subprocess.run(
        ["bash", str(heron / "scripts/site.sh"), "demo", "new", str(tmp_path / "sites/demo")],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"},
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "ghcr.io/fmstm/heron:prod new demo" in calls.read_text(encoding="utf-8")
    assert (heron / "env/.env.demo.dev").is_file()  # всё — внутри временной папки


# --- главная у каждого языка ------------------------------------------------------


def test_language_without_home_is_e028_in_prod_and_warning_in_dev(tmp_path):
    root = make(tmp_path, ("en", "ru"))
    (root / "content/ru/index.md").unlink()
    write(root, "ru/about.md", PAGE.format(t="О нас", extra="", body="Text."))
    prod = pipeline.run(root, env=BuildEnv.named("prod"))
    assert "E028" in [e.code for e in prod.collector.errors]
    assert not (root / "dist").exists()
    dev = pipeline.run(root)
    assert not dev.failed
    assert any("главной" in w.message for w in dev.collector.warnings)


# --- наблюдатель -------------------------------------------------------------


def test_watcher_sees_deletes_renames_and_same_time_edits(tmp_path):
    root = make(tmp_path)
    write(root, "en/a.md", PAGE.format(t="A", extra="", body="Text."))
    first = watch.snapshot(root)

    (root / "content/en/a.md").rename(root / "content/en/b.md")
    second = watch.snapshot(root)
    assert set(watch.changed(first, second)) == {"content/en/a.md", "content/en/b.md"}

    (root / "content/en/b.md").unlink()
    third = watch.snapshot(root)
    assert watch.changed(second, third) == ["content/en/b.md"]

    path = root / "site.yaml"
    stat = path.stat()
    path.write_text(path.read_text(encoding="utf-8") + "\n# x\n", encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # то же время, другой размер
    assert watch.changed(third, watch.snapshot(root)) == ["site.yaml"]


def test_watcher_walks_each_folder_once_and_skips_build_output(tmp_path, monkeypatch):
    root = make(tmp_path)
    pipeline.run(root)
    walked: list[Path] = []
    original = Path.rglob
    monkeypatch.setattr(Path, "rglob", lambda self, p: walked.append(self) or original(self, p))
    found = watch.snapshot(root)
    assert len(walked) == len(set(walked))  # ни одна папка дважды
    assert not any(name.startswith(("dist/", ".heron-cache/")) for name in found)


# --- язык + ключ ----------------------------------------------------------------


def test_two_files_with_one_key_are_e029(tmp_path):
    root = make(tmp_path)
    write(root, "en/services.md", PAGE.format(t="S", extra="slug: offer\n", body="Text."))
    write(root, "en/services/_index.md", PAGE.format(t="Section", extra="", body="Text."))
    result = pipeline.run(root)
    assert "E029" in [e.code for e in result.collector.errors]


# --- ссылки во всех представлениях секции ----------------------------------------


def localized_site(tmp_path):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/about.md": sites.page("Про нас"),
        "ru/index.md": sites.page("Главная"),
        "ru/about.md": sites.page("О нас", slug="o-nas"),
        "ru/page.md": (
            "---\ntitle: P\nh1: P page\ndescription: D\n---\n\n"
            "Lead [about](/about/).\n\nPromise [about](/about/).\n\n"
            "## Steps {#steps}\n\nIntro [about](/about/).\n\n"
            "1. **One.** First.\n2. **Two.** Second.\n\n"
            "Note [about](/about/).\n\n"
            "## Quote {#quote}\n\n> Callout [about](/about/).\n\n- one\n- two\n"
        ),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site.page("page", "ru")


def test_links_are_localized_in_every_section_view(tmp_path):
    page = localized_site(tmp_path)
    good = 'href="/ru/o-nas/"'
    assert good in page.intro.lead and good in page.intro.promise
    steps = page.sections["steps"]
    assert good in steps.lead and good in steps.note
    quote = page.sections["quote"]
    assert good in quote.callout
    for section in (page.intro, steps, quote):
        assert all(link["href"] == "/ru/o-nas/" for link in section.links), section.links
        for name in ("html", "lead", "note", "callout", "promise"):
            assert 'href="/about/"' not in getattr(section, name)


# --- ссылки через определения ---------------------------------------------------


def test_reference_links_are_checked_and_code_is_not(tmp_path):
    root = make(tmp_path)
    body = (
        "See [the offer][offer].\n\n"
        "```md\n[broken](/in-code/)\n```\n\n"
        "And `[x](/inline-code/)`.\n\n"
        "[offer]: /nowhere/\n"
    )
    write(root, "en/a.md", PAGE.format(t="A", extra="", body=body))
    result = pipeline.run(root)
    said = [w for w in result.collector.warnings if w.kind == "ссылки"]
    assert [w.message for w in said] == ["ссылка /nowhere/ никуда не ведёт"]
    assert said[0].line is not None


# --- llms.txt ---------------------------------------------------------------------


def test_llms_lists_only_indexable_children(tmp_path):
    root = make(tmp_path)
    write(root, "en/services/_index.md", PAGE.format(t="Services", extra="", body="Text."))
    write(root, "en/services/open.md", PAGE.format(t="Open", extra="", body="Text."))
    write(
        root, "en/services/hidden.md", PAGE.format(t="Hidden", extra="noindex: true\n", body="T.")
    )
    pipeline.run(root)
    text = (root / "dist/llms.txt").read_text(encoding="utf-8")
    assert "/services/open/" in text
    assert "/services/hidden/" not in text


# --- сырой HTML в коде -----------------------------------------------------------


def test_html_examples_in_code_are_not_raw_html(tmp_path):
    body = (
        'Use `<div class="x">` here.\n\n```html\n<script>alert(1)</script>\n```\n\nLine<br>break.'
    )
    markdown.guard_raw_html(body, "a.md", allow=False)
    root = make(tmp_path)
    write(root, "en/a.md", PAGE.format(t="A", extra="", body=body))
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    html = (root / "dist/a/index.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html and "<script>alert" not in html


def test_real_raw_html_is_e015_with_its_line():
    with pytest.raises(HeronError) as error:
        markdown.guard_raw_html("Text.\n\nMore <span>x</span>.\n", "a.md", allow=False, offset=5)
    assert error.value.code == "E015" and error.value.line == 8


def test_fail_on_warning_reaches_the_api(tmp_path):
    root = make(tmp_path)
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data.setdefault("build", {})["fail_on_warning"] = True
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    write(root, "en/a.md", "---\ntitle: Same\nh1: Same\ndescription: D\n---\n\nT.\n")
    assert pipeline.check(root).failed
    assert pipeline.run(root).failed
    # сборка с предупреждением при fail_on_warning не пишет
    assert not (root / "dist").exists()


@pytest.mark.parametrize(("lang", "head"), [("en", "## Pages"), ("de", "## Seiten")])
def test_llms_loose_pages_heading_follows_the_site_language(tmp_path, lang, head):
    """Заголовок раздела был «Сторінки» для uk и «Страницы» для всех прочих."""
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=[lang])
    write(root, f"{lang}/about.md", PAGE.format(t="About", extra="", body="Text."))
    pipeline.run(root)
    text = (root / "dist/llms.txt").read_text(encoding="utf-8")
    assert head in text
    assert "Страницы" not in text and "Сторінки" not in text
