"""Статическое покрытие словаря heron/texts (E15.S2, раздел 5, тест А).

Работает без правок при добавлении новых групп: файл группы кладёт задача перевода модуля.
"""

import ast
import re
import string
from pathlib import Path

import pytest

from heron import messages, texts

PKG = Path(messages.__file__).resolve().parent
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
DASHES = ("—", "–")

# группа -> файлы-источники (пути от heron/), раздел 8 плана
GROUPS: dict[str, tuple[str, ...]] = {
    "parser": ("core/parser/frontmatter.py", "core/parser/sections.py", "core/parser/markdown.py"),
    "blocks": ("core/parser/blocks.py", "core/hooks.py", "core/data.py"),
    "loader": ("contracts/loader.py", "contracts/frontmatter.py"),
    "version": ("contracts/version.py", "contracts/wiring.py"),
    "site": ("contracts/site.py", "contracts/theme.py"),
    "tree": ("core/tree.py", "core/resolver.py"),
    "links": ("core/links.py", "core/dates.py", "core/notfound.py"),
    "media": ("core/media.py",),
    "output": ("core/output.py", "core/paths.py"),
    "build": ("core/build.py",),
    "render": ("core/render/env.py", "core/render/pages.py"),
    "markup": ("modules/jsonld.py", "schemaorg/validate.py"),
    "themes": ("themes/__init__.py",),
    "redirects": ("modules/redirects.py", "modules/nginx.py"),
    "scaffold": ("scaffold/page.py", "scaffold/__init__.py"),
    "report": ("core/errors.py", "core/report.py"),
    "edit": (
        "edit/__init__.py",
        "edit/body.py",
        "edit/front.py",
        "edit/langs.py",
        "edit/model.py",
        "edit/slots.py",
        "edit/text.py",
        "edit/validate.py",
    ),
}

# группа -> имена присваиваний верхнего уровня, где кириллица допустима
EXEMPT: dict[str, frozenset[str]] = {
    "report": frozenset({"ERRORS", "SCHEMA_CODES", "LIST", "ROOT"}),
    "scaffold": frozenset(
        {
            "STRINGS",
            "DEMO_TITLES",
            "DEMO_EYEBROW",
            "NAV_HOME",
            "STARTER",
            "BODY",
            "_TYPE_HINTS",
            "_THEME_TITLE",
        }
    ),
    "redirects": frozenset({"_NGINX_COMMENTS", "_COMMENTS", "COMMENTS"}),
}

GROUP_TEXTS = texts.groups()
_FORMATTER = string.Formatter()


def _fields(template: str) -> set[str]:
    return {
        name.split(".")[0].split("[")[0] for _, name, _, _ in _FORMATTER.parse(template) if name
    }


def _all_text_keys() -> set[str]:
    return {key for table in GROUP_TEXTS.values() for lang in table.values() for key in lang}


@pytest.mark.parametrize("group", sorted(GROUP_TEXTS))
def test_group_has_both_languages_with_equal_keys_and_fields(group):
    table = GROUP_TEXTS[group]
    assert set(table) >= {"ru", "en"}, group
    assert set(table["ru"]) == set(table["en"]), group
    for key, ru in table["ru"].items():
        assert _fields(ru) == _fields(table["en"][key]), f"{group}.{key}: поля ru и en разные"


@pytest.mark.parametrize("group", sorted(GROUP_TEXTS))
def test_group_en_is_clean_and_keys_are_prefixed(group):
    table = GROUP_TEXTS[group]
    for key, text in table["en"].items():
        assert not CYRILLIC.search(text), f"{group}.{key}: кириллица в en"
        assert not any(d in text for d in DASHES), f"{group}.{key}: длинное или короткое тире в en"
        assert key == group or key.startswith(group + "_"), f"{group}.{key}: префикс ключа"


def test_group_keys_do_not_touch_core_tables():
    """Ключи групп не задевают ключи messages.py и друг друга."""
    core = _core_keys()
    seen: dict[str, str] = {}
    for group, table in GROUP_TEXTS.items():
        for key in table["ru"]:
            assert key not in core, f"{group}.{key} уже есть в messages.py"
            assert key not in seen, f"{key} в группах {seen[key]} и {group}"
            seen[key] = group


def _core_keys() -> set[str]:
    """Ключи TEXT, заданные в самом messages.py (без вклада heron/texts)."""
    return set(messages.TEXT["ru"]) - _all_text_keys()


def test_loaded_into_messages_text():
    for table in GROUP_TEXTS.values():
        for lang, items in table.items():
            for key, template in items.items():
                assert messages.TEXT[lang][key] == template


def _calls():
    """Все Msg("ключ", ...) и MsgError("ключ", ...) по heron/.

    Возвращает (файл, строка, ключ, имена аргументов).
    """
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in ("Msg", "MsgError"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if path.name == "messages.py":
                continue
            yield path, node.lineno, node.args[0].value, {k.arg for k in node.keywords if k.arg}


def test_every_msg_call_has_template_with_matching_fields():
    for path, line, key, given in _calls():
        where = f"{path.relative_to(PKG)}:{line}"
        assert key in messages.TEXT["ru"] and key in messages.TEXT["en"], (
            f"{where}: нет ключа {key}"
        )
        for lang in ("ru", "en"):
            assert given == _fields(messages.TEXT[lang][key]), f"{where}: поля {key} ({lang})"


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


def _cyrillic_literals(path: Path, exempt: frozenset[str]):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_ids(tree)
    kinds = set(messages.KINDS["en"])
    for top in tree.body:
        names: set[str] = set()
        if isinstance(top, ast.Assign):
            names = {t.id for t in top.targets if isinstance(t, ast.Name)}
        elif isinstance(top, ast.AnnAssign) and isinstance(top.target, ast.Name):
            names = {top.target.id}
        if names & exempt:
            skip |= {id(n) for n in ast.walk(top)}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
            and CYRILLIC.search(node.value)
            and node.value not in kinds
        ):
            yield node.lineno, node.value


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_translated_group_sources_have_no_cyrillic_literals(group):
    if not (PKG / "texts" / f"{group}.py").exists():
        pytest.skip(f"группа {group} ещё не переведена")
    for rel in GROUPS[group]:
        found = list(_cyrillic_literals(PKG / rel, EXEMPT.get(group, frozenset())))
        assert not found, f"{rel}: кириллица вне словаря: {found[:3]}"


def test_groups_table_points_to_existing_files():
    for group, files in GROUPS.items():
        for rel in files:
            assert (PKG / rel).exists(), f"{group}: нет файла {rel}"


def test_kinds_en_covers_redirects():
    assert messages.KINDS["en"]["редиректы"] == "redirects"
