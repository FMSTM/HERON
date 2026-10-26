"""`heron check` видит изменение данных в шаблонах темы (E033) до сборки.

Сборка рендерит шаблоны в неизменяемой песочнице, и `.append`/`.update`
роняют её с E033; `check` шаблоны не рендерит и раньше такую тему
пропускал. Теперь он разбирает шаблоны самим Jinja и говорит о каждом
вызове с файлом, строкой и рецептом. Каждый «плохой» случай сверяется со
сборкой: тот же код ошибки. Каждый «хороший» — тоже: сборка проходит,
значит check не врёт в обе стороны.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from jinja2 import sandbox

from heron.cli import main
from heron.core import build as pipeline
from heron.core import check as lint
from heron.core.errors import Collector
from heron.core.hooks import Hooks
from heron.core.render import env as envmod
from heron.scaffold import create
from tests import sites

PAGE = "theme/templates/page.html"
HEAD = '{% extends "base.html" %}\n{% block content %}\n'
TAIL = "\n{% endblock %}\n"


def _site(tmp_path: Path, notes: str = "en") -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True, notes=notes)
    return root


def _page(root: Path, body: str) -> None:
    """Шаблон страницы: тело начинается с третьей строки файла."""
    (root / PAGE).write_text(HEAD + body + TAIL, encoding="utf-8")


def _lint(result) -> list:
    return [e for e in result.collector.errors if e.code == "E033"]


def _built(root: Path):
    return pipeline.run(root, dist=root.parent / "dist")


# --- список методов тот же, что у песочницы ------------------------------------


def test_methods_are_exactly_what_the_sandbox_closes():
    closed = set().union(*(names for _, names in sandbox._mutable_spec))
    assert closed == lint.MUTATING


# --- находит, и сборка на том же месте падает с тем же кодом -----------------------


@pytest.mark.parametrize(
    ("body", "call"),
    [
        ("{% set xs = [] %}{% set _ = xs.append(1) %}", "xs.append(…)"),
        ("{% set xs = [] %}{% set _ = xs.extend([1]) %}", "xs.extend(…)"),
        ("{% set xs = [] %}{% set _ = xs.insert(0, 1) %}", "xs.insert(…)"),
        ("{% set xs = [2, 1] %}{% set _ = xs.sort() %}", "xs.sort(…)"),
        ("{% set xs = [1, 2] %}{% set _ = xs.reverse() %}", "xs.reverse(…)"),
        ("{% set xs = [1] %}{% set _ = xs.pop() %}", "xs.pop(…)"),
        ("{% set xs = [1] %}{% set _ = xs.remove(1) %}", "xs.remove(…)"),
        ("{% set xs = [1] %}{% set _ = xs.clear() %}", "xs.clear(…)"),
        ("{% set d = {} %}{% set _ = d.update({'a': 1}) %}", "d.update(…)"),
        ("{% set d = {} %}{% set _ = d.setdefault('a', 1) %}", "d.setdefault(…)"),
        ("{% set d = {'a': 1} %}{% set _ = d.popitem() %}", "d.popitem(…)"),
        # данные сайта — так же
        ("{{ languages.append('xx') }}", "languages.append(…)"),
        ("{{ data.update({'x': 1}) }}", "data.update(…)"),
        # обходные записи — песочница закрывает и их
        ("{% set xs = [] %}{% set _ = (xs|attr('append'))(1) %}", "xs|attr('append')(…)"),
        ("{% set xs = [] %}{% set _ = xs['append'](1) %}", "xs['append'](…)"),
        # вызов в выражении {{ }}, а не в set
        ("{% set xs = [] %}{{ xs.append(1) }}", "xs.append(…)"),
    ],
)
def test_mutation_is_found_by_check_and_fails_the_build(tmp_path, body, call):
    root = _site(tmp_path)
    _page(root, body)

    checked = pipeline.check(root)
    found = _lint(checked)
    assert len(found) == 1, [e.message for e in checked.collector.errors]
    error = found[0]
    assert error.path == PAGE
    assert error.line == 3
    assert error.message.startswith(call)
    assert "E033" in error.message
    assert error.hint

    built = _built(root)
    assert built.failed
    assert "E033" in {e.code for e in built.collector.errors}


def test_set_add_and_discard_are_found(tmp_path):
    """Множество из шаблона не построить, но из плагина или данных — можно."""
    root = _site(tmp_path)
    _page(root, "{{ tags.add('x') }}\n{{ tags.discard('x') }}")
    found = _lint(pipeline.check(root))
    assert [(e.line, e.message.split(" ")[0]) for e in found] == [
        (3, "tags.add(…)"),
        (4, "tags.discard(…)"),
    ]


def test_every_call_is_reported_with_its_own_line(tmp_path):
    root = _site(tmp_path)
    _page(
        root,
        "{% set seen = [] %}{% set out = [] %}\n"
        "{% for p in pages.pages %}{% if p.url not in seen %}"
        "{% set _ = seen.append(p.url) %}{% set _ = out.append(p) %}{% endif %}{% endfor %}\n"
        "<p>{{ out|length }}</p>\n"
        "{% set d = {} %}\n"
        "{% if true %}{% set _ = d.update({'a': 1}) %}{% endif %}",
    )
    found = _lint(pipeline.check(root))
    assert [(e.line, e.message.split(" ")[0]) for e in found] == [
        (4, "seen.append(…)"),
        (4, "out.append(…)"),
        (7, "d.update(…)"),
    ]


# --- где искать: partials, макросы, подключённые файлы --------------------------------


def test_partial_is_reported_by_its_own_file_and_line(tmp_path):
    root = _site(tmp_path)
    partials = root / "theme" / "partials"
    partials.mkdir(exist_ok=True)
    (partials / "list.html").write_text(
        "{% macro collect(items) %}\n"
        "{% set out = [] %}\n"
        "{% for i in items %}{% set _ = out.append(i) %}{% endfor %}\n"
        "{{ out|join(',') }}\n"
        "{% endmacro %}\n",
        encoding="utf-8",
    )
    _page(root, '{% import "partials/list.html" as m %}{{ m.collect([1, 2]) }}')
    found = _lint(pipeline.check(root))
    assert [(e.path, e.line) for e in found] == [("theme/partials/list.html", 3)]
    assert _built(root).failed


def test_file_outside_template_folders_is_followed_by_include(tmp_path):
    """assets/ не шаблоны, но подключённый include файл — шаблон."""
    root = _site(tmp_path)
    icons = root / "theme" / "assets" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    (icons / "dot.svg").write_text(
        "<svg>\n{% set xs = [] %}{% set _ = xs.append(1) %}\n</svg>\n", encoding="utf-8"
    )
    # тот же текст в неподключённом файле assets/ — не шаблон
    (icons / "spare.html").write_text("{{ [].append(1) }}\n", encoding="utf-8")
    _page(root, '{% include "assets/icons/dot.svg" %}')
    found = _lint(pipeline.check(root))
    assert [(e.path, e.line) for e in found] == [("theme/assets/icons/dot.svg", 2)]


def test_template_nobody_renders_is_still_reported_and_build_is_unchanged(tmp_path):
    """check смотрит всю тему; сборка, которая файл не рендерит, проходит как раньше."""
    root = _site(tmp_path)
    (root / "theme" / "templates" / "spare.html").write_text(
        "{% set xs = [] %}{% set _ = xs.append(1) %}\n", encoding="utf-8"
    )
    found = _lint(pipeline.check(root))
    assert [(e.path, e.line) for e in found] == [("theme/templates/spare.html", 1)]
    built = _built(root)
    assert not built.failed, [str(e) for e in built.collector.errors]


# --- ложных срабатываний нет: check молчит, сборка проходит ---------------------------


CLEAN = [
    # JS в <script>: для Jinja это текст
    "<script>\nel.classList.add('on'); queue.push(1); list.append(2);\n"
    "map.set('a', 1); obj.update({});\n</script>",
    # чтение словаря и списка
    "{% set d = {'a': 1} %}{{ d.get('a') }}{% for k, v in d.items() %}{{ k }}{% endfor %}"
    "{{ d.keys()|list|length }}{{ d.values()|list|length }}{{ [1, 2].index(2) }}",
    # namespace: присваивание, а не вызов
    "{% set ns = namespace(xs=[], d={}) %}{% for p in pages.pages %}"
    "{% set ns.xs = ns.xs + [p.url] %}{% set ns.d = dict(ns.d, last=p.url) %}{% endfor %}"
    "{{ ns.xs|length }}{{ ns.d|length }}",
    # фильтры, сложение списков, новый словарь
    "{% set xs = pages.pages|rejectattr('url', 'equalto', '/')|list %}"
    "{% set ys = xs + [page] %}{% set zs = ys|unique(case_sensitive=True, attribute='url')"
    "|sort(attribute='url')|reverse|list %}{% set d = dict({'a': 1}, b=2) %}"
    "{{ zs|length }}{{ d|length }}{{ ys|map(attribute='url')|join(',') }}",
    # raw и комментарий — не код
    "{% raw %}{{ xs.append(1) }}{% set _ = d.update({}) %}{% endraw %}"
    "{# {% set _ = xs.append(1) %} #}",
    # ключ данных с именем метода — чтение, не вызов
    "{% set item = {'sort': 3, 'add': 'x'} %}{{ item.sort }}{{ item.add }}",
    # строковые методы с похожими именами
    "{{ 'a-b'.split('-')|join }}{{ ' x '.strip() }}{{ 'ab'.removeprefix('a') }}",
    # модуль темы с именем метода: mod отдаёт рендер на любое имя
    (
        "{{ mod.update() }}{{ mod.add() }}{{ mod.clear('no-such-section') }}",
        {"theme/modules/update.html": "u", "theme/modules/add.html": "a"},
    ),
    # псевдоним импорта — модуль шаблона, h.update() — его макрос
    (
        "{% import 'partials/h.html' as h %}{{ h.update() }}{{ h.pop(1) }}",
        {
            "theme/partials/h.html": "{% macro update() %}u{% endmacro %}"
            "{% macro pop(x) %}{{ x }}{% endmacro %}"
        },
    ),
    # self.<блок>() — блок шаблона с именем метода
    "{% block update %}u{% endblock %}{{ self.update() }}{% block sort %}s{% endblock %}"
    "{{ self.sort() }}",
]


def _files(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("case", CLEAN)
def test_no_false_positive_and_the_build_agrees(tmp_path, case):
    body, files = case if isinstance(case, tuple) else (case, {})
    root = _site(tmp_path)
    _page(root, body)
    _files(root, files)
    checked = pipeline.check(root)
    assert _lint(checked) == [], [e.message for e in checked.collector.errors]
    built = _built(root)
    assert not built.failed, [str(e) for e in built.collector.errors]


@pytest.mark.parametrize(
    ("body", "files", "call"),
    [
        # имя движка, переопределённое в шаблоне, — уже не объект движка
        ("{% set mod = [] %}{{ mod.append(1) }}", {}, "mod.append(…)"),
        ("{% set t = {} %}{{ t.update({'a': 1}) }}", {}, "t.update(…)"),
        # псевдоним импорта, переопределённый списком
        (
            "{% import 'partials/h.html' as h %}{% set h = [] %}{{ h.append(1) }}",
            {"theme/partials/h.html": "{% macro update() %}u{% endmacro %}"},
            "h.append(…)",
        ),
        # from-import приносит и переменную шаблона, а она бывает словарём
        (
            "{% from 'partials/c.html' import cfg %}{{ cfg.update({'a': 1}) }}",
            {"theme/partials/c.html": "{% set cfg = {} %}"},
            "cfg.update(…)",
        ),
        # содержимое модуля импорта — по-прежнему данные
        (
            "{% import 'partials/c.html' as c %}{{ c.cfg.update({'a': 1}) }}",
            {"theme/partials/c.html": "{% set cfg = {} %}"},
            "c.cfg.update(…)",
        ),
    ],
)
def test_known_names_do_not_hide_real_mutation(tmp_path, body, files, call):
    root = _site(tmp_path)
    _page(root, body)
    _files(root, files)

    found = _lint(pipeline.check(root))
    assert [(e.path, e.line) for e in found] == [(PAGE, 3)]
    assert found[0].message.startswith(call)

    built = _built(root)
    assert built.failed
    assert "E033" in {e.code for e in built.collector.errors}


def test_context_objects_are_engine_objects_not_containers(tmp_path, monkeypatch):
    """CONTEXT_OBJECTS сверяется с настоящим контекстом страницы (env.context)."""
    seen: list[dict] = []
    original = envmod.context

    def spy(*args, **kwargs):
        scope = original(*args, **kwargs)
        seen.append(scope)
        return scope

    monkeypatch.setattr(envmod, "context", spy)
    root = _site(tmp_path)
    assert not _built(root).failed
    assert seen
    scope = seen[0]
    assert set(scope) >= lint.CONTEXT_OBJECTS
    for name in lint.CONTEXT_OBJECTS:
        value = scope[name]
        assert not any(sandbox.modifies_known_mutable(value, m) for m in lint.MUTATING), name
    containers = {
        name
        for name, value in scope.items()
        if any(sandbox.modifies_known_mutable(value, m) for m in lint.MUTATING)
    }
    assert {"data", "nav", "languages", "hreflang"} <= containers
    assert not containers & lint.CONTEXT_OBJECTS


def test_js_file_in_assets_is_not_a_template(tmp_path):
    root = _site(tmp_path)
    js = root / "theme" / "assets" / "app.js"
    js.parent.mkdir(parents=True, exist_ok=True)
    js.write_text("const xs = []; xs.append = 1; [].sort(); s.add(1);\n", encoding="utf-8")
    (root / "theme" / "assets" / "page.html").write_text(
        "<script>[].sort()</script>{{ x.append(1) }}\n", encoding="utf-8"
    )
    assert _lint(pipeline.check(root)) == []


def test_bundled_theme_is_clean(tmp_path):
    root = _site(tmp_path)
    assert _lint(pipeline.check(root)) == []


def test_broken_template_is_left_to_the_build(tmp_path):
    """Битый синтаксис — не E033: check не падает, сборка скажет E010."""
    root = _site(tmp_path)
    (root / "theme" / "templates" / "spare.html").write_text(
        "{% if %}{{ xs.append(1) }}\n", encoding="utf-8"
    )
    checked = pipeline.check(root)
    assert _lint(checked) == []


def test_link_out_of_the_theme_is_not_read(tmp_path):
    root = _site(tmp_path)
    outside = tmp_path / "outside.html"
    outside.write_text("{{ [].append(1) }}\n", encoding="utf-8")
    (root / "theme" / "partials").mkdir(exist_ok=True)
    (root / "theme" / "partials" / "away.html").symlink_to(outside)
    assert _lint(pipeline.check(root)) == []


# --- глобальные значения плагина: тип известен ---------------------------------------


class Basket:
    """Свой объект плагина с методами add и update — песочница их не закрывает."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, item: str) -> str:
        return item

    def update(self, **_: str) -> str:
        return ""


def _globals_lint(tmp_path: Path, source: str, **values) -> list:
    theme = tmp_path / "theme"
    (theme / "templates").mkdir(parents=True)
    (theme / "templates" / "page.html").write_text(source, encoding="utf-8")
    hooks = Hooks()
    for name, value in values.items():
        hooks.add_global(name, value)
    collector = Collector()
    lint.mutations(tmp_path, theme, sites.config(), collector, hooks)
    return collector.errors


def test_plugin_object_with_own_methods_is_not_reported(tmp_path):
    errors = _globals_lint(
        tmp_path, "{{ basket.add('a') }}{{ basket.update(x='1') }}", basket=Basket()
    )
    assert errors == []


def test_plugin_list_is_reported(tmp_path):
    errors = _globals_lint(tmp_path, "{{ shelf.append('a') }}", shelf=["x"])
    assert [(e.path, e.line) for e in errors] == [("theme/templates/page.html", 1)]


def test_name_bound_in_template_shadows_the_plugin_global(tmp_path):
    errors = _globals_lint(
        tmp_path, "{% set basket = [] %}{{ basket.append('a') }}", basket=Basket()
    )
    assert len(errors) == 1


def test_plugin_object_from_real_plugin_passes_check_and_build(tmp_path):
    root = _site(tmp_path)
    plugin = root / "plugins" / "lintbasket"
    plugin.mkdir(parents=True)
    (plugin / "__init__.py").write_text(
        "class Basket:\n"
        "    def add(self, item):\n        return item\n\n"
        "def register(hooks):\n    hooks.add_global('basket', Basket())\n",
        encoding="utf-8",
    )
    yaml_path = root / "site.yaml"
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8") + "\nplugins: [lintbasket]\n", encoding="utf-8"
    )
    _page(root, "<i>{{ basket.add('ok') }}</i>")
    assert _lint(pipeline.check(root)) == []
    built = _built(root)
    assert not built.failed, [str(e) for e in built.collector.errors]


# --- язык и подсказка-рецепт -------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "en", "ru"),
    [
        ("{% set xs = [] %}{% set _ = xs.append(1) %}", "xs + [item]", "xs + [item]"),
        ("{% set d = {} %}{% set _ = d.update({}) %}", "dict(d, key=value)", "dict(d, key=value)"),
        ("{% set xs = [1] %}{% set _ = xs.pop() %}", "rejectattr", "rejectattr"),
        ("{% set xs = [1] %}{% set _ = xs.sort() %}", "sort(attribute=", "sort(attribute="),
    ],
)
def test_hint_is_a_recipe_for_the_method(tmp_path, body, en, ru):
    for notes, needle in (("en", en), ("ru", ru)):
        root = _site(tmp_path / notes, notes=notes)
        _page(root, body)
        (error,) = _lint(pipeline.check(root))
        assert needle in error.hint
        assert "{%" in error.hint or "|" in error.hint
        assert "heron docs theme" in error.hint


def test_message_follows_build_notes(tmp_path):
    body = "{% set xs = [] %}{% set _ = xs.append(1) %}"
    texts = {}
    for notes in ("en", "ru"):
        root = _site(tmp_path / notes, notes=notes)
        _page(root, body)
        (error,) = _lint(pipeline.check(root))
        texts[notes] = (error.message, error.hint)
    assert "changes data in place" in texts["en"][0]
    assert "namespace" in texts["en"][1]
    assert "меняет данные на месте" in texts["ru"][0]
    assert "стройте новый список" in texts["ru"][1]
    assert not any("Ѐ" <= ch <= "ӿ" for ch in "".join(texts["en"]))


# --- CLI: check и check --json --------------------------------------------------------


def test_check_json_lists_e033_like_other_errors(tmp_path):
    root = _site(tmp_path)
    _page(root, "{% set xs = [] %}\n{% set _ = xs.append(1) %}")
    result = CliRunner().invoke(main, ["check", str(root), "--json"])
    assert result.exit_code == 1, result.output
    report = json.loads(result.output)
    assert report["ok"] is False
    (error,) = [e for e in report["errors"] if e["code"] == "E033"]
    assert set(error) == {"code", "path", "line", "message", "hint"}
    assert error["path"] == PAGE
    assert error["line"] == 4
    assert error["message"].startswith("xs.append(…)")
    assert "namespace" in error["hint"]


def test_check_json_clean_theme_stays_ok(tmp_path):
    root = _site(tmp_path)
    result = CliRunner().invoke(main, ["check", str(root), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ok"] is True


def test_check_text_output_names_file_and_line(tmp_path):
    root = _site(tmp_path, notes="ru")
    _page(root, "{% set d = {} %}{% set _ = d.update({'a': 1}) %}")
    result = CliRunner().invoke(main, ["check", str(root)])
    assert result.exit_code == 1
    assert f"E033 {PAGE}:3: d.update(…) меняет данные на месте" in result.output
    assert "dict(d, key=value)" in result.output
