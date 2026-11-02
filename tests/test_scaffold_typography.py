"""Строки заготовки сайта без длинного и короткого тире (копирайтинг, E15.S2.T52)."""

from __future__ import annotations

from pathlib import Path

import pytest

from heron import scaffold
from heron.scaffold import agents, page

DASHES = ("—", "–")


def _strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (tuple, list)):
        for v in value:
            yield from _strings(v)


def _has_dash(text: str) -> bool:
    return any(d in text for d in DASHES)


def test_page_body_has_no_dashes() -> None:
    texts = list(_strings(page.BODY))
    assert texts
    for text in texts:
        assert not _has_dash(text), text


def test_demo_titles_have_no_dashes_and_substitute_name() -> None:
    texts = list(_strings(scaffold.DEMO_TITLES))
    assert texts
    for text in texts:
        assert not _has_dash(text), text
    for lang, pages in scaffold.DEMO_TITLES.items():
        title = pages["index"][0].replace("{name}", "X")
        assert title.startswith("X - "), (lang, title)


def test_starter_home_titles_have_no_dashes() -> None:
    for lang, pages in scaffold.STARTER.items():
        title = pages["home"][0]
        assert not _has_dash(title), (lang, title)
        assert title.replace("{name}", "X").startswith("X - "), (lang, title)


def test_agents_header_placeholders_are_hyphen(tmp_path: Path) -> None:
    (tmp_path / "site.yaml").write_text("site:\n  name: Demo\n", encoding="utf-8")
    result = agents.fields(tmp_path, None, "ru")
    assert result["languages"] == "-"
    assert result["default_lang"] == "-"
    assert result["domain"] == "-"
    for value in result.values():
        assert "—" not in value


def test_mutation_dash_in_body_is_detected(monkeypatch) -> None:
    body = {lang: dict(items) for lang, items in page.BODY.items()}
    body["en"]["intro"] = "Intro — text"
    monkeypatch.setattr(page, "BODY", body)
    assert any(_has_dash(t) for t in _strings(page.BODY))


# Файлы заготовки, которые ложатся в сайт пользователя (E15.S2.T56).
# Исключений нет: notes/ и agents-root/ проверяет отдельная задача E15.S2.T61.
SCAFFOLD_ROOT = Path(scaffold.__file__).parent
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt", ".html", ".css", ".js", ".json"}


def _dash_files(root: Path) -> list[str]:
    bad = []
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix in TEXT_SUFFIXES
            and _has_dash(path.read_text(encoding="utf-8"))
        ):
            bad.append(str(path.relative_to(root)))
    return bad


def test_scaffold_demo_and_text_files_have_no_dashes() -> None:
    checked = 0
    for sub in ("demo", "text"):
        base = SCAFFOLD_ROOT / sub
        assert base.is_dir(), base
        checked += sum(1 for p in base.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
        assert _dash_files(base) == [], sub
    assert checked > 0


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_new_site_content_and_site_yaml_have_no_dashes(tmp_path: Path, lang: str) -> None:
    root = tmp_path / "s"
    root.mkdir()
    scaffold.create(root, name="demo", languages=[lang], notes=lang)
    files = [root / "site.yaml", *sorted((root / "content").rglob("*"))]
    files = [f for f in files if f.is_file()]
    assert len(files) > 1
    for f in files:
        assert not _has_dash(f.read_text(encoding="utf-8")), f


def test_mutation_dash_in_demo_index_is_detected(tmp_path: Path) -> None:
    demo = tmp_path / "demo" / "ru"
    demo.mkdir(parents=True)
    src = (SCAFFOLD_ROOT / "demo" / "ru" / "index.md").read_text(encoding="utf-8")
    lines = src.splitlines()
    lines[-1] = lines[-1] + " — тире"
    (demo / "index.md").write_text("\n".join(lines), encoding="utf-8")
    assert _dash_files(tmp_path / "demo") == ["ru/index.md"]
