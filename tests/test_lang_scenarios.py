"""Сценарии сбоя аудита E15.S1.T1: en-вывод без кириллицы, ru-вывод на русском (E15.S2.T26).

Приёмка F01: перевод охватывает все сценарии из аудита, а не только отдельные
модули. Сайт строится в tmp_path с `build.notes: en` и английским контентом,
команды идут через CliRunner. На сценарий проверяются:

- `check --notes en`: stdout и stderr без кириллицы;
- `check --json --notes en`: `message` и `hint` без кириллицы (значения `kind`
  исключены, F25);
- `build --notes en`: вывод и файл полного списка предупреждений (столбцы
  path и message без кириллицы, первый столбец kind допускает кириллицу);
- те же сценарии с `--notes ru`: подробности на русском;
- сайт с `build.notes: ru` и русским контентом при `--notes en`: вывод без
  кириллицы, и обратно `build.notes: en` при `--notes ru`: русские `message`.

`serve` не запускается: его текст проверяет прямой вызов в тестах
E15.S2.T25 (Переключение: cli, watch, server рендерят по языку, спецификация ru).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.messages import Msg, say
from heron.scaffold import create

CYRILLIC = re.compile(r"[А-Яа-яЁё]")

PAGE_HEAD = "---\ntitle: {title}\nh1: {title}\ndescription: A test page\n{extra}---\n\n"
SECTION = "Intro.\n\n## What it is {{#{sid}}}\n\nText.\n"


def md(title: str = "Test page", extra: str = "", body: str | None = None) -> str:
    return PAGE_HEAD.format(title=title, extra=extra) + (
        SECTION.format(sid="what") if body is None else body
    )


def site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True, notes="en")
    return root


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def edit_site(root: Path, change: Callable[[dict], None]) -> None:
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    change(data)
    (root / "site.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def template(root: Path, body: str) -> None:
    write(
        root,
        "theme/templates/page.html",
        '{% extends "base.html" %}\n{% block content %}\n' + body + "\n{% endblock %}\n",
    )


def outside(tmp_path: Path) -> Path:
    target = tmp_path / "outside"
    target.mkdir()
    (target / "secret.md").write_text(md("Secret"), encoding="utf-8")
    return target


# --- сценарии: каждый портит свежий сайт и возвращает ожидаемый код ошибки -----------


def e001(root: Path, tmp: Path) -> str:
    write(root, "content/en/bad.md", "---\ntitle: [unclosed\n---\n\nText.\n")
    return "E001"


def e002(root: Path, tmp: Path) -> str:
    write(root, "content/en/bad.md", "---\nh1: Only h1\n---\n\nText.\n")
    return "E002"


def e003(root: Path, tmp: Path) -> str:
    body = SECTION.format(sid="same") + "\n## Again {#same}\n\nMore.\n"
    write(root, "content/en/dup.md", md("Dup", body=body))
    return "E003"


def e007(root: Path, tmp: Path) -> str:
    write(
        root,
        "content/en/pic.md",
        md("Pic", extra="image: media/missing-cover.png\n"),
    )
    return "E007"


def e010(root: Path, tmp: Path) -> str:
    template(root, "{{ no_such_variable.value }}")
    return "E010"


def e011_type(root: Path, tmp: Path) -> str:
    edit_site(root, lambda data: data.__setitem__("site", {"domain": ["not", "a", "domain"]}))
    return "E011"


def e011_key(root: Path, tmp: Path) -> str:
    edit_site(root, lambda data: data["site"].__setitem__("no_such_key", 1))
    return "E011"


def e011_yaml(root: Path, tmp: Path) -> str:
    write(root, "site.yaml", "site: [unclosed\n")
    return "E011"


def e012(root: Path, tmp: Path) -> str:
    edit_site(root, lambda data: data.__setitem__("heron", ">=99.0,<100"))
    return "E012"


def e013(root: Path, tmp: Path) -> str:
    (root / "theme" / "theme.yaml").unlink()
    edit_site(root, lambda data: data["site"].__setitem__("theme", "no-such-theme"))
    return "E013"


def e015(root: Path, tmp: Path) -> str:
    edit_site(root, lambda data: data.setdefault("build", {}).__setitem__("allow_raw_html", False))
    write(root, "content/en/raw.md", md("Raw", body="Intro.\n\n<div>raw</div>\n"))
    return "E015"


def e024_content(root: Path, tmp: Path) -> str:
    (root / "content/en").mkdir(parents=True, exist_ok=True)
    os.symlink(outside(tmp) / "secret.md", root / "content/en/leak.md")
    return "E024"


def e024_static(root: Path, tmp: Path) -> str:
    (root / "static").mkdir(exist_ok=True)
    os.symlink(outside(tmp) / "secret.md", root / "static/leak.txt")
    return "E024"


def e024_theme(root: Path, tmp: Path) -> str:
    os.symlink(outside(tmp) / "secret.md", root / "theme/templates/leak.html")
    return "E024"


def e033(root: Path, tmp: Path) -> str:
    template(root, "{% set items = [] %}{{ items.append(1) }}")
    return "E033"


def no_template(root: Path, tmp: Path) -> str:
    write(root, "content/en/odd.md", md("Odd", extra="type: no-such-type\n"))
    return "odd.md"


def no_home(root: Path, tmp: Path) -> str:
    for home in (root / "content/en").glob("index.md"):
        home.unlink()
    return "content/en/index.md"


def untranslated(root: Path, tmp: Path) -> str:
    edit_site(root, lambda data: data["site"].__setitem__("languages", ["en", "fr"]))
    return "content/fr"


def no_site(root: Path, tmp: Path) -> str:
    (root / "site.yaml").unlink()
    return "site.yaml"


def many_warnings(root: Path, tmp: Path) -> str:
    edit_site(root, lambda data: data["site"].__setitem__("languages", ["en", "fr"]))
    for index in range(15):
        write(root, f"content/en/page-{index}.md", md(f"Page {index}"))
    return "page-0.md"


ERRORS: dict[str, Callable[[Path, Path], str]] = {
    "E001": e001,
    "E002": e002,
    "E003": e003,
    "E007": e007,
    "E011-type": e011_type,
    "E011-key": e011_key,
    "E011-yaml": e011_yaml,
    "E012": e012,
    "E013": e013,
    "E015": e015,
    "E024-content": e024_content,
    "E024-static": e024_static,
    "E024-theme": e024_theme,
    "E033": e033,
}
BUILD_ONLY: dict[str, Callable[[Path, Path], str]] = {"E010": e010}
OTHER: dict[str, Callable[[Path, Path], str]] = {
    "no-template": no_template,
    "no-home": no_home,
    "untranslated": untranslated,
    "many-warnings": many_warnings,
    "no-site": no_site,
}
SCENARIOS = {**ERRORS, **BUILD_ONLY, **OTHER}


# --- запуск ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("HERON_NOTES", "HERON_IN_CONTAINER", "HERON_DEBUG"):
        monkeypatch.delenv(name, raising=False)


def run(*args: str):
    return CliRunner().invoke(main, [*args])


def strings(value, skip=("kind", "code")):
    """Все строки JSON, кроме значений под ключами kind и code."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in skip:
                yield from strings(item, skip)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item, skip)
    elif isinstance(value, str):
        yield value


def parse_json(output: str):
    start = output.index("{")
    return json.JSONDecoder().raw_decode(output[start:])[0]


def is_error(code: str) -> bool:
    return code.startswith("E")


def messages_of(data: dict, code: str) -> list[str]:
    """message находок сценария: по полю code, по коду в тексте или по маркеру в path."""
    items = [*data.get("errors", []), *data.get("warnings", [])]
    return [
        item["message"]
        for item in items
        if item.get("code") == code
        or code in item.get("message", "")
        or code in (item.get("path") or "")
    ]


def prepared(tmp_path: Path, name: str):
    root = site(tmp_path)
    code = SCENARIOS[name](root, tmp_path)
    return root, code


@pytest.mark.parametrize("name", [n for n in SCENARIOS if n not in BUILD_ONLY])
def test_check_en_has_no_cyrillic(tmp_path, name):
    root, code = prepared(tmp_path, name)
    result = run("check", str(root), "--notes", "en")
    assert result.output.strip(), name
    assert not CYRILLIC.search(result.output), result.output
    assert code in result.output, (name, result.output)
    if is_error(code) or name == "no-site":
        assert result.exit_code == 1, result.output


@pytest.mark.parametrize("name", ERRORS)
def test_check_json_en_has_no_cyrillic(tmp_path, name):
    root, code = prepared(tmp_path, name)
    result = run("check", str(root), "--json", "--notes", "en")
    assert result.exit_code == 1, result.output
    data = parse_json(result.output)
    found = list(strings(data))
    assert found
    assert not [text for text in found if CYRILLIC.search(text)], found
    assert code in json.dumps(data)


@pytest.mark.parametrize("name", ["many-warnings", "untranslated", "no-template", "no-home"])
def test_check_json_en_warnings_have_no_cyrillic(tmp_path, name):
    root, code = prepared(tmp_path, name)
    result = run("check", str(root), "--json", "--notes", "en")
    data = parse_json(result.output)
    found = list(strings(data))
    assert data["warnings"], json.dumps(data)
    assert messages_of(data, code), (name, json.dumps(data))
    assert not [text for text in found if CYRILLIC.search(text)], found


@pytest.mark.parametrize("flags", [[], ["--json"]])
def test_no_site_en_check_points_to_heron_new_without_cyrillic(tmp_path, flags):
    root, _ = prepared(tmp_path, "no-site")
    result = run("check", str(root), *flags, "--notes", "en")
    assert result.exit_code == 1, result.output
    assert result.output.strip()
    assert "site.yaml" in result.output
    assert "heron new" in result.output
    assert not CYRILLIC.search(result.output), result.output


@pytest.mark.parametrize("flags", [[], ["--json"]])
def test_no_site_ru_check_says_it_in_russian(tmp_path, flags):
    root, _ = prepared(tmp_path, "no-site")
    result = run("check", str(root), *flags, "--notes", "ru")
    assert result.exit_code == 1, result.output
    assert say("ru", "no_site", path=root) in result.output
    assert CYRILLIC.search(result.output)


@pytest.mark.parametrize("name", SCENARIOS)
def test_build_en_has_no_cyrillic(tmp_path, name):
    root, code = prepared(tmp_path, name)
    result = run("build", str(root), "--notes", "en")
    assert not CYRILLIC.search(result.output), result.output
    full = root / ".heron-cache" / "warnings.txt"
    if not is_error(code) and name != "no-site":  # в dev E007 и др. идут предупреждением без кода
        body = result.output + (full.read_text(encoding="utf-8") if full.is_file() else "")
        assert code in body, (name, result.output)
    if full.is_file():
        for line in full.read_text(encoding="utf-8").splitlines():
            kind, where, message = line.split("\t", 2)
            assert not CYRILLIC.search(where + message), line


def test_full_warnings_file_is_written_for_many_warnings(tmp_path):
    root, _ = prepared(tmp_path, "many-warnings")
    result = run("build", str(root), "--notes", "en")
    titles = 15  # page-0 .. page-14: «title and h1 are the same»
    shown = len(re.findall(r"en/page-\d+\.md:", result.output))
    assert 0 < shown < titles, result.output
    assert f"and {titles - shown} more" in result.output, result.output
    full = root / ".heron-cache" / "warnings.txt"
    assert full.is_file(), result.output
    lines = full.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 15
    assert all(len(line.split("\t", 2)) == 3 for line in lines)
    assert not CYRILLIC.search(result.output)


def test_build_en_raw_html_and_sandbox_fail_without_cyrillic(tmp_path):
    for name, code in (("E015", "E015"), ("E033", "E033")):
        root = site(tmp_path / name)
        SCENARIOS[name](root, tmp_path / name)
        result = run("build", str(root), "--notes", "en")
        assert result.exit_code == 1, result.output
        assert code in result.output
        assert not CYRILLIC.search(result.output), result.output


def test_old_urls_without_path_en_has_no_cyrillic(tmp_path):
    root = site(tmp_path)
    old = tmp_path / "old.txt"
    old.write_text("https://example.com\n/gone-page/\n", encoding="utf-8")
    text = run("check", str(root), "--old-urls", str(old), "--notes", "en")
    assert text.output.strip()
    assert not CYRILLIC.search(text.output), text.output
    as_json = run("check", str(root), "--json", "--old-urls", str(old), "--notes", "en")
    data = parse_json(as_json.output)
    found = list(strings(data))
    assert any("gone-page" in item for item in found), found
    assert not [item for item in found if CYRILLIC.search(item)], found


# --- парные сценарии на русском -------------------------------------------------------


RU_SCENARIOS = [n for n in SCENARIOS if n not in BUILD_ONLY]


@pytest.mark.parametrize("name", RU_SCENARIOS)
def test_check_ru_details_are_russian(tmp_path, name):
    root, code = prepared(tmp_path, name)
    result = run("check", str(root), "--notes", "ru")
    assert code in result.output, result.output
    if is_error(code) or name == "no-site":
        assert result.exit_code == 1, result.output
    assert CYRILLIC.search(result.output), result.output
    if name == "no-site":
        assert say("ru", "no_site", path=root) in result.output, result.output


@pytest.mark.parametrize("name", RU_SCENARIOS)
def test_check_json_ru_message_is_russian(tmp_path, name):
    root, code = prepared(tmp_path, name)
    if name == "no-site":  # JSON не печатается: проверяем текст
        result = run("check", str(root), "--json", "--notes", "ru")
        assert say("ru", "no_site", path=root) in result.output, result.output
        return
    result = run("check", str(root), "--json", "--notes", "ru")
    data = parse_json(result.output)
    found = messages_of(data, code)
    assert found, json.dumps(data, ensure_ascii=False)
    assert all(CYRILLIC.search(text) for text in found), found


def test_ru_text_of_e007_matches_the_message(tmp_path):
    root, _ = prepared(tmp_path, "E007")
    result = run("check", str(root), "--json", "--notes", "ru")
    data = parse_json(result.output)
    expected = Msg("media_no_file", src="media/missing-cover.png").text("ru")
    assert any(expected in text for text in strings(data)), (expected, data)


def test_ru_text_of_e011_names_the_site_file(tmp_path):
    root, _ = prepared(tmp_path, "E011-yaml")
    result = run("check", str(root), "--notes", "ru")
    assert result.exit_code == 1, result.output
    assert "E011" in result.output
    assert "site.yaml" in result.output
    assert CYRILLIC.search(result.output)


def test_ru_untranslated_summary_is_russian(tmp_path):
    root, _ = prepared(tmp_path, "many-warnings")
    result = run("build", str(root), "--notes", "ru")
    assert CYRILLIC.search(result.output), result.output
    full = root / ".heron-cache" / "warnings.txt"
    assert full.is_file(), result.output
    for line in full.read_text(encoding="utf-8").splitlines():
        kind, where, message = line.split("\t", 2)
        assert CYRILLIC.search(message), line


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_build_only_error_e010(tmp_path, lang):
    """E010 check не видит: шаблоны рендерит только сборка."""
    root, code = prepared(tmp_path, "E010")
    result = run("build", str(root), "--notes", lang)
    assert result.exit_code == 1, result.output
    assert code in result.output
    assert bool(CYRILLIC.search(result.output)) == (lang == "ru"), result.output


# --- язык запуска против build.notes: сайт на русском при --notes en и обратно -----------

UNKNOWN_PROPS = [f"noSuchProp{index}" for index in range(12)]
RU_BODY = "Вступление.\n\n## Что это {#what}\n\nТекст.\n"


def e007_ru(root: Path, tmp: Path) -> str:
    extra = "image: media/missing-cover.png\n"
    write(root, "content/ru/pic.md", md("Страница", extra=extra, body=RU_BODY))
    return "E007"


def sch002(root: Path, tmp: Path) -> str:
    entity = {"@type": "IndividualPhysician", "@id": "#me"}
    entity.update({prop: "Clinic" for prop in UNKNOWN_PROPS})
    edit_site(root, lambda data: data.__setitem__("schema", {"entity": entity}))
    return "SCH002"


RUN_LANG: dict[str, Callable[[Path, Path], str]] = {
    "E011-type": e011_type,
    "E011-key": e011_key,
    "E011-yaml": e011_yaml,
    "E033": e033,
    "SCH002": sch002,
}
CROSS_RU_SITE = {**RUN_LANG, "E007": e007_ru}
CROSS_EN_SITE = {**RUN_LANG, "E007": e007}


def ru_site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["ru"], demo=True, notes="ru")
    return root


def full_rows(root: Path) -> list[list[str]]:
    full = root / ".heron-cache" / "warnings.txt"
    if not full.is_file():
        return []
    return [line.split("\t", 2) for line in full.read_text(encoding="utf-8").splitlines()]


def assert_en_clean(root: Path, result) -> None:
    """stdout и stderr без кириллицы, плюс файл полного списка."""
    assert not CYRILLIC.search(result.stdout), result.stdout
    assert_stderr_and_file_clean(root, result)


def assert_stderr_and_file_clean(root: Path, result) -> None:
    """В stdout у --json свой разбор: там kind вправе быть русским, как и в файле (F25)."""
    assert not CYRILLIC.search(result.stderr), result.stderr
    for _, where, message in full_rows(root):
        assert not CYRILLIC.search(where + message), message


@pytest.mark.parametrize("name", CROSS_RU_SITE)
def test_ru_site_check_en_has_no_cyrillic(tmp_path, name):
    root = ru_site(tmp_path)
    code = CROSS_RU_SITE[name](root, tmp_path)
    result = run("check", str(root), "--notes", "en")
    assert result.exit_code == (1 if is_error(code) else 0), result.output
    assert code in result.output
    assert_en_clean(root, result)


@pytest.mark.parametrize("name", CROSS_RU_SITE)
def test_ru_site_check_json_en_has_no_cyrillic(tmp_path, name):
    root = ru_site(tmp_path)
    code = CROSS_RU_SITE[name](root, tmp_path)
    result = run("check", str(root), "--json", "--notes", "en")
    data = parse_json(result.stdout)
    assert code in json.dumps(data)
    found = list(strings(data))
    assert not [text for text in found if CYRILLIC.search(text)], found
    assert_stderr_and_file_clean(root, result)


@pytest.mark.parametrize("name", CROSS_RU_SITE)
def test_ru_site_build_en_has_no_cyrillic(tmp_path, name):
    root = ru_site(tmp_path)
    code = CROSS_RU_SITE[name](root, tmp_path)
    result = run("build", str(root), "--notes", "en")
    if name == "E007":  # в окружении dev сборка говорит о нём предупреждением, без кода
        assert result.exit_code == 0, result.output
        assert "media/missing-cover.png" in result.output
    else:
        assert result.exit_code == (1 if is_error(code) else 0), result.output
        assert code in result.output
    assert_en_clean(root, result)


def test_ru_site_full_list_of_schema_findings_is_written_in_en(tmp_path):
    root = ru_site(tmp_path)
    sch002(root, tmp_path)
    result = run("build", str(root), "--notes", "en")
    assert result.exit_code == 0, result.output
    assert [row for row in full_rows(root) if "SCH002" in row[2]], result.output
    assert_en_clean(root, result)


def test_ru_site_old_urls_without_path_en_has_no_cyrillic(tmp_path):
    root = ru_site(tmp_path)
    old = tmp_path / "old.txt"
    old.write_text("https://example.com\n/gone-page/\n", encoding="utf-8")
    text = run("check", str(root), "--old-urls", str(old), "--notes", "en")
    assert "without a path" in text.output, text.output
    assert_en_clean(root, text)
    as_json = run("check", str(root), "--json", "--old-urls", str(old), "--notes", "en")
    found = list(strings(parse_json(as_json.stdout)))
    assert any("gone-page" in item for item in found), found
    assert not [item for item in found if CYRILLIC.search(item)], found


@pytest.mark.parametrize("name", CROSS_EN_SITE)
def test_en_site_check_json_ru_messages_are_russian(tmp_path, name):
    root = site(tmp_path)
    code = CROSS_EN_SITE[name](root, tmp_path)
    data = parse_json(run("check", str(root), "--json", "--notes", "ru").stdout)
    found = messages_of(data, code)
    assert found, json.dumps(data, ensure_ascii=False)
    assert all(CYRILLIC.search(text) for text in found), found


def test_en_site_old_urls_summary_is_russian(tmp_path):
    root = site(tmp_path)
    old = tmp_path / "old.txt"
    old.write_text("https://example.com\n/gone-page/\n", encoding="utf-8")
    result = run("check", str(root), "--old-urls", str(old), "--notes", "ru")
    assert "без пути" in result.output, result.output
