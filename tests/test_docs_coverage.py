"""Покрытие документации: каждый ключ, опция и код из кода упомянут в spec/*.md.

Сравнивает код (поля моделей site/theme, команды и опции click, коды ошибок) с
docs/ru/spec/*.md и docs/en/spec/*.md. Имя считается документированным, если
встречается в обратных кавычках:
- ключ конфига - фрагментом целиком (`feed`), компонентом точечного пути
  (`seo.feed`, `site.domains.prod`) или ключом YAML-фрагмента (`llms_txt: true`);
- опция, команда, код - любым словом внутри фрагмента (`heron build --strict`).
Осознанные пробелы - tests/docs_coverage_allow.yaml; в допуске не должно быть
уже документированного.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
import pydantic
import pytest
import yaml

from heron.cli import main
from heron.contracts import site as site_models
from heron.contracts import theme as theme_models
from heron.core.errors import ERRORS, SCHEMA_CODES

ROOT = Path(__file__).resolve().parents[1]
ALLOW = Path(__file__).with_name("docs_coverage_allow.yaml")
LANGS = ("ru", "en")
TICKED = re.compile(r"`([^`\n]+)`")
CODE = re.compile(r"\b(?:E\d{3}|SCH\d{3})\b")
WORD = re.compile(r"--?[A-Za-z][\w-]*|[\w.\-\[\]]+")
KEY_HEAD = re.compile(r"[\w.\-\[\]<>]+")
FILE_EXT = {
    "md",
    "xml",
    "yaml",
    "yml",
    "json",
    "txt",
    "html",
    "css",
    "js",
    "py",
    "svg",
    "png",
    "webp",
}


def _spec_text(lang: str) -> str:
    files = sorted((ROOT / "docs" / lang / "spec").glob("*.md"))
    assert files, f"нет docs/{lang}/spec/*.md"
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def _tokens(text: str) -> set[str]:
    """Опции, команды, коды: фрагмент в обратных кавычках целиком и по словам."""
    found: set[str] = set()
    for chunk in TICKED.findall(text):
        chunk = chunk.strip()
        found.add(chunk)
        found.update(WORD.findall(chunk))
    return found


def _key_tokens(text: str) -> set[str]:
    """Ключи: фрагмент целиком, компоненты точечного пути в его начале, ключ `k: v`.

    Имя файла (`feed.xml`) ключ `feed` не документирует.
    """
    found: set[str] = set()
    for chunk in TICKED.findall(text):
        chunk = chunk.strip()
        found.add(chunk)
        head = KEY_HEAD.match(chunk)
        if not head:
            continue
        path = re.sub(r"\[[^\]]*\]|<[^>]*>", "", head.group(0))
        parts = [p for p in path.split(".") if p]
        if len(parts) > 1 and parts[-1] in FILE_EXT:
            continue  # имя файла (`feed.xml`, `site.yaml`), а не путь к ключу
        found.update(parts)
    return found


def _models() -> list[type[pydantic.BaseModel]]:
    out: list[type[pydantic.BaseModel]] = []
    for module in (site_models, theme_models):
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, pydantic.BaseModel)
                and obj is not pydantic.BaseModel
                and obj.__module__ == module.__name__
                and obj.__name__ != "Strict"
            ):
                out.append(obj)
    return out


def code_elements() -> dict[tuple[str, str], str]:
    """(kind, name) -> где найден."""
    items: dict[tuple[str, str], str] = {}
    for model in _models():
        for name, field in model.model_fields.items():
            items[("key", field.alias or name)] = f"{model.__module__}.{model.__name__}"

    def walk(cmd: click.Command, path: str) -> None:
        for param in cmd.params:
            if isinstance(param, click.Option):
                for opt in param.opts + param.secondary_opts:
                    if opt.startswith("--"):
                        items[("option", opt)] = path
        if isinstance(cmd, click.Group):
            for sub_name, sub in cmd.commands.items():
                items[("command", sub_name)] = path
                walk(sub, f"{path} {sub_name}")

    walk(main, "heron")
    for code in (*ERRORS, *SCHEMA_CODES):
        items[("code", code)] = "heron.core.errors"
    return items


def _allow() -> list[dict]:
    data = yaml.safe_load(ALLOW.read_text(encoding="utf-8")) or []
    assert isinstance(data, list)
    for row in data:
        assert set(row) == {"name", "kind", "reason"}, row
    return data


def _missing_in(text: str, elements: dict[tuple[str, str], str]) -> set[tuple[str, str]]:
    loose, keys = _tokens(text), _key_tokens(text)
    return {(k, n) for (k, n) in elements if n not in (keys if k == "key" else loose)}


def _missing(lang: str) -> set[tuple[str, str]]:
    return _missing_in(_spec_text(lang), code_elements())


def _stale(rows: list[dict], elements: dict, gaps: dict[str, set]) -> list[str]:
    problems = []
    for row in rows:
        key = (row["kind"], row["name"])
        if key not in elements:
            problems.append(f"{key}: нет в коде")
        elif not any(key in gaps[lang] for lang in gaps):
            problems.append(f"{key}: уже документирован в обоих языках - лишний допуск")
        if not str(row["reason"]).strip():
            problems.append(f"{key}: пустая причина")
    return problems


@pytest.mark.parametrize("lang", LANGS)
def test_everything_in_code_is_documented(lang: str) -> None:
    allowed = {(r["kind"], r["name"]) for r in _allow()}
    gaps = sorted(_missing(lang) - allowed)
    assert not gaps, f"docs/{lang}/spec не упоминает (kind, name): {gaps}"


def test_allow_list_has_no_stale_entries() -> None:
    gaps = {lang: _missing(lang) for lang in LANGS}
    problems = _stale(_allow(), code_elements(), gaps)
    assert not problems, problems


@pytest.mark.parametrize("lang", LANGS)
def test_documented_codes_exist_in_code(lang: str) -> None:
    known = set(ERRORS) | set(SCHEMA_CODES)
    unknown = sorted(set(CODE.findall(_spec_text(lang))) - known)
    assert not unknown, f"docs/{lang}/spec называет коды, которых нет в коде: {unknown}"


# --- Мутации: проверка, что тест действительно краснеет ------------------------


@pytest.mark.parametrize(
    ("chunk", "name", "documented"),
    [
        ("`feed_limit`", "feed_limit", True),
        ("`seo.feed_limit`", "feed_limit", True),
        ("`site.domains.prod`", "domains", True),
        ("`seo.llms_txt: true`", "llms_txt", True),
        ("`images[].ratios`", "ratios", True),
        ("`feed.xml`", "feed", False),
        ("feed_limit без кавычек", "feed_limit", False),
        ("`heron build --feed_limit`", "feed_limit", False),
    ],
)
def test_key_recognition(chunk: str, name: str, documented: bool) -> None:
    gaps = _missing_in(chunk, {("key", name): "x"})
    assert (("key", name) not in gaps) is documented


def test_mutation_removed_key_line_is_named() -> None:
    """Мутация 1: убрать из spec/20 все упоминания ключа - тест называет ключ."""
    elements = code_elements()
    text = _spec_text("ru")
    documented = sorted(
        n for (k, n) in elements if k == "key" and (k, n) not in _missing_in(text, elements)
    )
    assert documented, "в spec нет ни одного документированного ключа"
    victim = documented[0]
    cut = "\n".join(
        line for line in text.splitlines() if not re.search(rf"\b{re.escape(victim)}\b", line)
    )
    assert ("key", victim) in _missing_in(cut, elements)


def test_mutation_fake_model_field_is_reported() -> None:
    """Мутация 2: фиктивное поле модели попадает в пробелы."""
    elements = dict(code_elements())
    elements[("key", "zz_fake_field_e19")] = "fake"
    assert ("key", "zz_fake_field_e19") in _missing_in(_spec_text("ru"), elements)


def test_mutation_documented_key_in_allow_is_stale() -> None:
    """Мутация 3: документированный ключ в допуске - «лишний допуск»."""
    elements = code_elements()
    gaps = {lang: _missing(lang) for lang in LANGS}
    documented = sorted(
        n for (k, n) in elements if k == "key" and all((k, n) not in g for g in gaps.values())
    )
    assert documented
    row = {"name": documented[0], "kind": "key", "reason": "мутация"}
    assert _stale([row], elements, gaps)
