"""Адреса GitHub на файлы движка ведут на существующие пути дерева.

Демо-страница каждого нового сайта, анкета setup, документация и комплект для
агентов ссылаются на репозиторий движка абсолютными адресами
``https://github.com/FMSTM/HERON/(blob|tree)/<ветка>/<путь>``. Ветки beta и prod
раздают это же дерево (23 §9), поэтому путь после ветки обязан существовать здесь.
``blob`` на папку и ``tree`` на файл GitHub перенаправляет сам (так устроен
``docs_url`` комплекта: ``blob/<канал>/docs/<язык>/``), поэтому вид не проверяется.
После переезда docs/ → docs/ru/ (E12.S1) старые адреса на
docs/guide давали 404, а тесты внешние адреса не проверяли (E13.S1.T16).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Где ищем: всё, что уходит пользователю или агенту. tests/ не входит — там
# адреса собираются из частей и подставляются нарочно.
SCAN = ("heron", "docs/ru", "README.md", "AGENTS.md", "skills")

# Ветки, которые раздают это же дерево.
SAME_TREE = frozenset({"beta", "prod"})

# Ветка без «<» и «{»: шаблоны вида blob/<канал>/ и blob/{channel}/ — не адреса.
URL = re.compile(
    r"https://github\.com/FMSTM/HERON/(?P<kind>blob|tree)/"
    r"(?P<branch>[A-Za-z0-9._-]+)/(?P<path>[^\s)\"'`<>#?\]]*)"
)


def _files(root: Path) -> list[Path]:
    found: list[Path] = []
    for name in SCAN:
        top = root / name
        if top.is_file():
            found.append(top)
        elif top.is_dir():
            found.extend(
                p for p in sorted(top.rglob("*")) if p.is_file() and "__pycache__" not in p.parts
            )
    return found


def _links(root: Path) -> list[tuple[str, int, str, str, str]]:
    """(файл, строка, вид, ветка, путь) для каждого адреса в дереве."""
    links: list[tuple[str, int, str, str, str]] = []
    for file in _files(root):
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # картинки и прочие двоичные файлы
        for number, line in enumerate(text.splitlines(), start=1):
            for match in URL.finditer(line):
                path = match["path"].rstrip(".,;:")
                links.append(
                    (
                        file.relative_to(root).as_posix(),
                        number,
                        match["kind"],
                        match["branch"],
                        path,
                    )
                )
    return links


def _broken(root: Path) -> list[str]:
    problems: list[str] = []
    for where, number, kind, branch, path in _links(root):
        place = f"{where}:{number}: {kind}/{branch}/{path}"
        if branch not in SAME_TREE:
            problems.append(f"{place} — ветка {branch} не раздаёт это дерево")
            continue
        if not (root / path).exists():
            problems.append(f"{place} — такого пути нет в дереве")
    return problems


def test_github_links_point_to_existing_paths() -> None:
    assert _broken(ROOT) == []


def test_scan_sees_the_known_links() -> None:
    """Проверка не пустая: адреса из демо-страницы, анкеты и docs/ru найдены."""
    found = {(where, kind, branch, path) for where, _, kind, branch, path in _links(ROOT)}
    assert ("heron/scaffold/demo/ru/docs.md", "tree", "beta", "docs/ru/guide") in found
    assert ("heron/scaffold/demo/en/docs.md", "tree", "beta", "docs/ru/guide") in found
    assert ("heron/setup/page.html", "blob", "beta", "docs/ru/guide/06-deploy.md") in found
    assert ("docs/ru/README.md", "blob", "prod", "AGENTS.md") in found
    assert ("docs/ru/guide/06-deploy.md", "blob", "prod", "env/.env.example") in found
    assert ("docs/ru/spec/20-data-contract.md", "blob", "prod", "docs/ru/") in found


def _tree(tmp_path: Path, text: str) -> Path:
    (tmp_path / "docs/ru/guide").mkdir(parents=True)
    (tmp_path / "docs/ru/guide/06-deploy.md").write_text("# deploy\n", encoding="utf-8")
    (tmp_path / "heron").mkdir()
    (tmp_path / "heron/page.html").write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        # Старые адреса до переезда docs/ → docs/ru/.
        ("[g](https://github.com/FMSTM/HERON/tree/beta/docs/guide)", "пути нет"),
        ('"https://github.com/FMSTM/HERON/blob/beta/docs/guide/06-deploy.md"', "пути нет"),
        ("https://github.com/FMSTM/HERON/blob/prod/docs/ru/guide/07-none.md#x", "пути нет"),
        ("https://github.com/FMSTM/HERON/blob/main/docs/ru/guide/06-deploy.md", "ветка main"),
    ],
)
def test_broken_link_is_reported(tmp_path: Path, text: str, reason: str) -> None:
    problems = _broken(_tree(tmp_path, text + "\n"))
    assert len(problems) == 1
    assert problems[0].startswith("heron/page.html:1: ")
    assert reason in problems[0]


@pytest.mark.parametrize(
    "text",
    [
        "[g](https://github.com/FMSTM/HERON/tree/beta/docs/ru/guide)",
        "[d](https://github.com/FMSTM/HERON/blob/prod/docs/ru/guide/06-deploy.md#этапы).",
        "docs_url: https://github.com/FMSTM/HERON/blob/prod/docs/ru/",
        "https://github.com/FMSTM/HERON/blob/<канал>/docs/<язык>/",
        'f"https://github.com/FMSTM/HERON/blob/{channel}/docs/"',
        "https://github.com/FMSTM/HERON https://github.com/FMSTM/HERON/actions/workflows/ci.yml",
    ],
)
def test_good_link_and_templates_pass(tmp_path: Path, text: str) -> None:
    assert _broken(_tree(tmp_path, text + "\n")) == []


def test_e033_hint_names_existing_spec() -> None:
    """Подсказка E033 называет файл спецификации, который есть в дереве."""
    source = (ROOT / "heron/core/render/pages.py").read_text(encoding="utf-8")
    hints = re.findall(r"вызовы из (\S+\.md)", source)
    assert hints, "подсказка E033 не найдена в heron/core/render/pages.py"
    for path in hints:
        assert (ROOT / path).is_file(), path


# Комментарии шаблонов скелета: кладутся в site.yaml и theme.yaml каждого
# нового сайта. Пути docs/… в них — пути репозитория движка, темы `heron docs` —
# темы этой версии движка. После переезда docs/ → docs/ru/ комментарий site.yaml
# ещё ссылался на docs/spec/20-data-contract.md (E13.S1.T20, W2).
TEXT = ROOT / "heron" / "scaffold" / "text"
DOC_PATH = re.compile(r"(?<![\w./-])docs/[\w./-]*[\w/]")
DOCS_TOPIC = re.compile(r"heron docs ([a-z@][\w@-]*)")


def _template_refs(text_root: Path) -> list[tuple[str, int, str, str]]:
    """(файл, строка, вид, значение) для путей docs/… и тем heron docs в комментариях."""
    refs: list[tuple[str, int, str, str]] = []
    for file in sorted(p for p in text_root.rglob("*") if p.is_file()):
        rel = file.relative_to(ROOT).as_posix() if file.is_relative_to(ROOT) else file.name
        for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.lstrip().startswith("#"):
                continue
            refs.extend((rel, number, "path", m[0]) for m in DOC_PATH.finditer(line))
            refs.extend((rel, number, "topic", m[1]) for m in DOCS_TOPIC.finditer(line))
    return refs


def _broken_template_refs(text_root: Path, root: Path) -> list[str]:
    from heron import docs

    problems: list[str] = []
    for where, number, kind, value in _template_refs(text_root):
        if kind == "path" and not (root / value).exists():
            problems.append(f"{where}:{number}: {value} — такого пути нет в дереве")
        if kind == "topic" and docs.topic(value) is None:
            problems.append(f"{where}:{number}: heron docs {value} — такой темы нет")
    return problems


def test_scaffold_text_comments_point_to_existing_docs() -> None:
    assert _broken_template_refs(TEXT, ROOT) == []


def test_scaffold_text_scan_sees_site_yaml_refs() -> None:
    found = {(where, kind, value) for where, _, kind, value in _template_refs(TEXT)}
    for lang in ("ru", "en"):
        where = f"heron/scaffold/text/{lang}/site.yaml"
        assert (where, "path", "docs/ru/spec/20-data-contract.md") in found
        assert (where, "topic", "contract") in found


@pytest.mark.parametrize(
    ("line", "needle"),
    [
        ("# Описание: docs/spec/20-data-contract.md, раздел 5.", "docs/spec/20-data-contract.md"),
        ("# All keys: heron docs nosuchtopic, section 5", "heron docs nosuchtopic"),
    ],
)
def test_broken_template_ref_is_reported(tmp_path: Path, line: str, needle: str) -> None:
    (tmp_path / "ru").mkdir()
    (tmp_path / "ru" / "site.yaml").write_text(f"{line}\nkey: docs/not/a/comment\n", "utf-8")
    problems = _broken_template_refs(tmp_path, ROOT)
    assert len(problems) == 1
    assert problems[0].startswith("site.yaml:1: ")
    assert needle in problems[0]
