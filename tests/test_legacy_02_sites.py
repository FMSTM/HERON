"""Сайт 0.2 под движком 0.3: правка страницы не заводит того, о чём не просили.

Образец - `tests/fixtures/site-0.2/`: сайт, созданный движком 0.2.0 (`heron new
--lang ru,en,de`, `heron page page roofing --folder services`, `heron page page
about` на ru и en), страницы дописаны, `heron: ">=0.2,<0.4"`. Папка `services/`
без `_index.md` (так делал 0.2), `services/roofing` - только на ru, `about` на en
переведён частично (`translation: pending`).

Правило (приёмка 0.3.0, блокер B1): правка существующей страницы пишет только
файлы, текст которых меняется; файлов других языков и категорий выше она не
создаёт, пока человек о них не попросил (поле этого языка, `pending`, создание,
перенос). `--dump`, затем `--answers` - байт в байт без изменений.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron import studio
from heron.cli import main
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.edit import console
from heron.edit import entity as ops

FIXTURE = Path(__file__).parent / "fixtures" / "site-0.2"
LANGS = ["ru", "en", "de"]


@pytest.fixture
def old(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "site"
    shutil.copytree(FIXTURE, root)
    return root


def run(*args, input=None):
    return CliRunner().invoke(main, [str(a) for a in args], input=input)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".heron-cache" not in path.parts
    }


def keys(root: Path) -> list[tuple[str, bool]]:
    ctx = ops.context(root, "ru")
    return [(node.key, node.category) for node in ops.tree(ctx) if not node.implicit]


def test_the_fixture_is_a_02_site_with_an_implicit_folder(old):
    assert 'heron: ">=0.2,<0.4"' in (old / "site.yaml").read_text("utf-8")
    assert (old / "content/ru/services/roofing.md").is_file()
    assert not any((old / "content" / lang / "services/_index.md").exists() for lang in LANGS)
    assert not (old / "content/en/services").exists()


def test_dump_then_answers_changes_nothing_on_every_page(old, tmp_path):
    """Каждая страница сайта 0.2, в том числе в неявной папке и частично переведённая."""
    before = snapshot(old)
    found = keys(old)
    assert ("services/roofing", False) in found and ("about", False) in found
    for key, category in found:
        command = "category" if category else "page"
        dumped = run(command, "add", key or "/", old, "--dump")
        assert dumped.exit_code == 0, dumped.output
        answers = tmp_path / "answers.yaml"
        answers.write_text(dumped.output, encoding="utf-8")
        again = run(command, "add", key or "/", old, "--answers", answers, "-y")
        assert again.exit_code == 0, (key, again.output)
        assert snapshot(old) == before, key


def test_the_reviewers_case_creates_no_category_and_no_copies(old, tmp_path):
    dumped = run("page", "add", "services/roofing", old, "--dump")
    answers = tmp_path / "d.yaml"
    answers.write_text(dumped.output, encoding="utf-8")
    result = run("page", "add", "services/roofing", old, "--answers", answers, "-y")
    assert result.exit_code == 0, result.output
    for lang in LANGS:
        assert not (old / "content" / lang / "services/_index.md").exists()
    for lang in LANGS[1:]:
        assert not (old / "content" / lang / "services/roofing.md").exists()
    # и боевая сборка 0.3 проходит, как проходила до правки
    built = pipeline.run(old, dist=tmp_path / "dist", env=BuildEnv.resolve("prod"))
    assert not built.collector.errors, [e.code for e in built.collector.errors]


def test_a_real_edit_writes_only_the_main_file(old, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text(yaml.safe_dump({"ru": {"h1": "Кровля под ключ"}}, allow_unicode=True))
    before = snapshot(old)
    result = run("page", "add", "services/roofing", old, "--answers", answers, "-y")
    assert result.exit_code == 0, result.output
    after = snapshot(old)
    changed = {rel for rel in after if after[rel] != before.get(rel)}
    assert changed == {"content/ru/services/roofing.md"}
    assert set(after) == set(before)


def test_console_enter_through_everything_writes_nothing(old):
    """Опросник: Enter на каждом вопросе, затем «Записать? Y» - диск тот же."""
    before = snapshot(old)
    ctx = ops.context(old, "ru")
    entity = ops.open_entity(ctx, "services/roofing")
    asked: list[str] = []
    printed: list[str] = []
    io = console.Io(
        lambda prompt: (asked.append(prompt), "")[1], lambda t="", *a: printed.append(t)
    )
    session = console.Console(entity, io, "ru")
    session.run()
    assert session.confirm()
    # категория - та же (неявная папка есть в списке), не корень
    assert entity.target == "services/roofing"
    ops.save(entity)
    assert snapshot(old) == before
    summary = "\n".join(printed)
    assert "content/en/services/roofing.md - файла нет, не создаётся" in summary
    assert "категория services будет создана" not in summary


def test_studio_save_writes_only_what_changed(old):
    before = snapshot(old)
    request = {
        "target": {"kind": "page", "key": "services/roofing"},
        "answers": {"ru": {"h1": "Кровля под ключ"}},
    }
    result = studio.save(old, request, "ru")
    assert result["saved"]["written"] == ["content/ru/services/roofing.md"]
    assert result["saved"]["created"] == [] and result["saved"]["categories"] == []
    after = snapshot(old)
    assert set(after) == set(before)
    # в форме языки без файла так и помечены: запись их не создаёт
    files = result["state"]["files"]
    assert files["en"] == {**files["en"], "exists": False, "planned": False}


def test_studio_save_without_changes_writes_nothing(old):
    before = snapshot(old)
    result = studio.save(old, {"target": {"kind": "page", "key": "services/roofing"}}, "ru")
    assert result["saved"]["written"] == [] and result["saved"]["created"] == []
    assert snapshot(old) == before


def test_a_translation_asked_for_creates_that_language_only(old, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text(
        yaml.safe_dump({"en": {"title": "Roofing works"}, "de": "pending"}, allow_unicode=True)
    )
    result = run("page", "add", "services/roofing", old, "--answers", answers, "-y")
    assert result.exit_code == 0, result.output
    en = (old / "content/en/services/roofing.md").read_text("utf-8")
    de = (old / "content/de/services/roofing.md").read_text("utf-8")
    assert 'title: "Roofing works"' in en or "title: Roofing works" in en
    assert "translation: pending" in en and "translation: pending" in de
    # категории папка не получила: её никто не просил
    assert not any((old / "content" / lang / "services/_index.md").exists() for lang in LANGS)


def test_check_warns_about_the_implicit_folder(old):
    result = pipeline.check(old, notes_lang="en")
    assert not result.collector.errors
    found = [w for w in result.collector.warnings if "services" in w.message.text("en")]
    assert len(found) == 1, [w.message.text("en") for w in result.collector.warnings]
    assert "heron category add services" in found[0].message.text("en")
    assert found[0].path == "ru/services/"


def test_page_list_shows_the_implicit_folder_as_a_category(old):
    text = run("page", "list", old, "--notes", "en")
    assert text.exit_code == 0, text.output
    lines = text.output.splitlines()
    folder = next(line for line in lines if line.strip().startswith("services/"))
    assert "_index.md" in folder and "heron category add services" in folder
    page = lines[lines.index(folder) + 1]
    assert page.startswith("    roofing"), page  # под папкой, с отступом
    data = json.loads(run("page", "list", old, "--json").output)
    node = next(item for item in data["items"] if item["key"] == "services")
    assert node["category"] is True and node["implicit"] is True
    assert all(not item["implicit"] for item in data["items"] if item["key"] != "services")


def test_category_add_makes_the_folder_explicit(old):
    result = run("category", "add", "services", old, "-y")
    assert result.exit_code == 0, result.output
    for lang in LANGS:
        assert (old / "content" / lang / "services/_index.md").is_file()
    # страница внутри осталась только на ru
    assert not (old / "content/en/services/roofing.md").exists()


def test_a_new_page_in_the_implicit_folder_still_creates_the_category(old, tmp_path):
    """Создание - явная просьба: новая страница и её категория - на всех языках, как в 0.3."""
    result = run("page", "add", "services/painting", old, "-y")
    assert result.exit_code == 0, result.output
    for lang in LANGS:
        assert (old / "content" / lang / "services/painting.md").is_file()
        assert (old / "content" / lang / "services/_index.md").is_file()
