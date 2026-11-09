"""Статическая проверка шаблонов темы для `heron check`: изменение данных (E033).

Шаблоны собираются в неизменяемой песочнице (21 §7): `.append`, `.update`
и другие методы, которые меняют список, словарь или множество на месте,
падают со `SecurityError`, и сборка отказывает с `E033`. `check` шаблоны
не рендерит, поэтому раньше такую тему пропускал: «готово» по check,
а прод-сборка падает.

Здесь шаблоны не исполняются, а разбираются самим Jinja (`Environment.parse`)
в дерево. Ищется вызов метода из того же списка, что закрывает песочница.
Из дерева сами собой выпадают текст вне тегов (JS в `<script>`, файлы
`.js`), `{% raw %}` и комментарии `{# #}`: для Jinja это не код. Не
считаются и `namespace`: `{% set ns.x = … %}` — присваивание, а не вызов.

Тип значения статически не известен: `x.update(…)` у своего объекта темы
(например, у глобальной функции плагина) песочница пропустила бы. Поэтому
глобальные значения окружения проверяются по-настоящему: если имя не
переопределено в шаблоне и его значение не меняемый контейнер — молчим.

Сборку модуль не трогает: её E033 по-прежнему дают сам рендер и песочница.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, nodes
from jinja2.exceptions import TemplateNotFound, TemplateSyntaxError
from jinja2.sandbox import modifies_known_mutable

from heron.contracts.site import SiteConfig
from heron.core import paths, urls
from heron.core.errors import Collector, HeronError
from heron.core.render import env as envmod
from heron.messages import Msg

CODE = "E033"

# Ровно то, что закрывает ImmutableSandboxedEnvironment (jinja2.sandbox
# _mutable_spec): list, dict, set, deque. Расхождение ловит тест.
MUTATING: frozenset[str] = frozenset(
    {
        # список и deque
        "append",
        "appendleft",
        "extend",
        "extendleft",
        "insert",
        "sort",
        "reverse",
        "rotate",
        # удаление
        "pop",
        "popleft",
        "popitem",
        "remove",
        "discard",
        "clear",
        # словарь и множество
        "update",
        "setdefault",
        "add",
        "difference_update",
        "symmetric_difference_update",
    }
)

# Какую подсказку дать: по смыслу метода, рецепт из гайда по темам.
ADDS = {"append", "appendleft", "extend", "extendleft", "insert", "add"}
KEYS = {"update", "setdefault"}
ORDER = {"sort", "reverse", "rotate"}

# Файлы, которые движок рендерит как шаблоны. assets/ и i18n/ — не шаблоны:
# их не разбираем, если только шаблон сам не подключает такой файл.
SUFFIXES = {".html", ".htm", ".j2", ".jinja", ".jinja2"}
NOT_TEMPLATES = {"assets", "i18n"}

# Имена, которые движок кладёт в контекст страницы (`env.context`), с типом,
# который песочница не закрывает: `mod` отдаёт рендер модуля на любое имя
# (`mod.update()` — шаблон modules/update.html), `t` — строки интерфейса,
# `env` — окружение сборки, остальное — функции. Контейнеры контекста
# (`data`, `nav`, `languages`, `hreflang`) сюда не входят: их изменение
# песочница закрывает. Совпадение с `env.context` сверяет тест.
CONTEXT_OBJECTS: frozenset[str] = frozenset(
    {"mod", "t", "env", "page_of", "picture", "media_url", "jsonld", "cover_url", "robots_meta"}
)


def mutations(
    site_root: Path | None,
    theme_dir: Path,
    config: SiteConfig,
    collector: Collector,
    hooks=None,
) -> None:
    """Найти в шаблонах темы изменение данных и сказать о каждом вызове `E033`.

    Окружение то же, что у сборки (`env.make`): тот же синтаксис, те же
    глобальные значения плагинов.
    """
    theme_dir = Path(theme_dir)
    if not theme_dir.is_dir():
        return
    env = envmod.make(theme_dir, config, hooks)
    root = Path(site_root).resolve() if site_root is not None else None

    queue = sorted(_candidates(theme_dir))
    seen: set[str] = set(queue)
    while queue:
        rel = queue.pop(0)
        tree = _parse(env, theme_dir, rel)
        if tree is None:
            continue
        for name in _references(tree):
            if name not in seen and _template_file(theme_dir, name) is not None:
                seen.add(name)
                queue.append(name)
        shown = _shown(theme_dir, rel, root)
        for line, call, method in _calls(tree, env):
            collector.errors.append(
                HeronError(
                    code=CODE,
                    message=Msg("sandbox_mutation", call=call),
                    path=shown,
                    line=line,
                    hint=Msg(_hint_key(method)),
                )
            )


def _candidates(theme_dir: Path) -> list[str]:
    """Шаблоны темы: файлы с суффиксом шаблона вне assets/ и i18n/.

    Ссылки не обходятся: файл, который ведёт за пределы темы, сборка и так
    не прочтёт (E024 в `ThemeLoader`), а читать чужое ради проверки незачем.
    """
    found: list[str] = []
    for folder, dirs, files in os.walk(theme_dir, followlinks=False):
        here = Path(folder)
        if here == theme_dir:
            dirs[:] = [d for d in dirs if d not in NOT_TEMPLATES]
        dirs.sort()
        for name in sorted(files):
            path = here / name
            if path.suffix.lower() in SUFFIXES and paths.inside(theme_dir, path):
                found.append(path.relative_to(theme_dir).as_posix())
    return found


def _template_file(theme_dir: Path, name: str) -> Path | None:
    """Файл шаблона по имени из extends/include/import, если он внутри темы."""
    if not name or paths.escapes(name):
        return None
    path = theme_dir / name
    if path.is_file() and paths.inside(theme_dir, path):
        return path
    return None


def _parse(env: Environment, theme_dir: Path, rel: str) -> nodes.Template | None:
    """Дерево шаблона. Не читается или синтаксис битый — молчим: это скажет сборка (E010)."""
    path = theme_dir / rel
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        return env.parse(source, name=rel, filename=str(path))
    except TemplateSyntaxError:
        return None
    except Exception:  # noqa: BLE001 — расширение плагина упало на разборе: это не наш вопрос
        return None


def _references(tree: nodes.Template) -> list[str]:
    """Имена шаблонов, которые этот подключает: extends, include, import, from."""
    out: list[str] = []
    for node in tree.find_all((nodes.Extends, nodes.Include, nodes.Import, nodes.FromImport)):
        target = node.template
        values = target.items if isinstance(target, (nodes.List, nodes.Tuple)) else [target]
        for value in values:
            if isinstance(value, nodes.Const) and isinstance(value.value, str):
                out.append(value.value)
    return out


def _calls(tree: nodes.Template, env: Environment) -> list[tuple[int, str, str]]:
    """Вызовы меняющих методов: (строка, как записан вызов, метод)."""
    bound = {n.name for n in tree.find_all(nodes.Name) if n.ctx in ("store", "param")}
    bound |= {macro.name for macro in tree.find_all(nodes.Macro)}
    # Псевдоним `{% import … as h %}` — модуль шаблона, а не контейнер:
    # `h.update()` вызывает его макрос. Имена `{% from … import x %}` сюда
    # не входят: так приходит и переменная шаблона, а она бывает списком.
    modules = {node.target for node in tree.find_all(nodes.Import)}
    found: list[tuple[int, str, str]] = []
    for call in tree.find_all(nodes.Call):
        target = call.node
        method: str | None = None
        owner: nodes.Node | None = None
        written = ""
        if isinstance(target, nodes.Getattr) and target.attr in MUTATING:
            method, owner = target.attr, target.node
            written = f"{_text(owner)}.{method}(…)"
        elif (
            isinstance(target, nodes.Getitem)
            and isinstance(target.arg, nodes.Const)
            and target.arg.value in MUTATING
        ):
            method, owner = target.arg.value, target.node
            written = f"{_text(owner)}[{target.arg.value!r}](…)"
        elif (
            isinstance(target, nodes.Filter)
            and target.name == "attr"
            and target.args
            and isinstance(target.args[0], nodes.Const)
            and target.args[0].value in MUTATING
        ):
            method, owner = target.args[0].value, target.node
            written = f"{_text(owner)}|attr({method!r})(…)"
        if method is None or owner is None:
            continue
        if _known_object(owner, bound, modules):
            continue
        if _harmless_global(owner, method, env, bound):
            continue
        found.append((call.lineno, written, method))
    found.sort(key=lambda item: item[0])
    return found


def _known_object(owner: nodes.Node, bound: set[str], modules: set[str]) -> bool:
    """Владелец вызова — имя, чей тип движок знает и это не контейнер.

    `self` — блоки шаблона (`self.<блок>()`), псевдоним импорта — модуль
    шаблона, имена из `CONTEXT_OBJECTS` — объекты и функции движка.
    Переопределённое в шаблоне имя (`set`, `for`, параметр макроса) уже
    не то, что дал движок: о нём говорим.
    """
    if not isinstance(owner, nodes.Name) or owner.name in bound:
        return False
    return owner.name == "self" or owner.name in modules or owner.name in CONTEXT_OBJECTS


def _harmless_global(owner: nodes.Node, method: str, env: Environment, bound: set[str]) -> bool:
    """Глобальное значение окружения, у которого этот метод песочница не закрывает.

    Плагин вправе отдать шаблону свой объект с методом `add` или `update`:
    песочница закрывает только меняемые контейнеры (list, dict, set, deque).
    Имя, переопределённое в самом шаблоне (`set`, `for`, параметр макроса),
    уже не глобальное — его тип не известен, и о нём говорим.
    """
    if not isinstance(owner, nodes.Name) or owner.name in bound:
        return False
    if owner.name not in env.globals:
        return False
    value: Any = env.globals[owner.name]
    return not modifies_known_mutable(value, method)


def _text(node: nodes.Node) -> str:
    """Как выражение записано в шаблоне — коротко, для сообщения."""
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        return f"{_text(node.node)}.{node.attr}"
    if isinstance(node, nodes.Getitem):
        if isinstance(node.arg, nodes.Const):
            return f"{_text(node.node)}[{node.arg.value!r}]"
        return f"{_text(node.node)}[…]"
    if isinstance(node, nodes.Call):
        return f"{_text(node.node)}(…)"
    if isinstance(node, nodes.Filter):
        return f"{_text(node.node)}|{node.name}" if node.node is not None else node.name
    if isinstance(node, nodes.List):
        return "[…]"
    if isinstance(node, nodes.Dict):
        return "{…}"
    return "…"


def _hint_key(method: str) -> str:
    if method in ADDS:
        return "sandbox_hint_add"
    if method in KEYS:
        return "sandbox_hint_keys"
    if method in ORDER:
        return "sandbox_hint_order"
    return "sandbox_hint_remove"


def _shown(theme_dir: Path, rel: str, root: Path | None) -> str:
    """Путь шаблона для человека: от корня сайта, если тема в нём, иначе полный."""
    path = theme_dir / rel
    if root is not None:
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def missing_templates(
    site,
    theme,
    theme_dir: Path,
    config: SiteConfig,
    collector: Collector,
    hooks=None,
) -> None:
    """Сказать `E008` о странице, у типа которой в теме нет шаблона.

    Имя шаблона берётся так же, как при сборке (`pages.template_name`),
    наличие проверяется тем же загрузчиком темы. Шаблон не рендерится.
    Одна находка на страницу.
    """
    from heron.core.render import pages as pagesmod

    theme_dir = Path(theme_dir)
    env = envmod.make(theme_dir, config, hooks)
    for page in site.pages:
        name = pagesmod.template_name(page, theme)
        try:
            env.loader.get_source(env, name)
        except TemplateNotFound:
            collector.errors.append(
                HeronError(
                    code="E008",
                    message=Msg("render_template_missing", type=page.type, name=name),
                    path=page.source,
                    hint=Msg("render_template_missing_hint", name=name),
                )
            )
        except HeronError:
            continue


_COMMENTS = re.compile(r"\{#.*?#\}|<!--.*?-->", re.S)
_SCRIPT = re.compile(r"<script\b([^>]*)>", re.I | re.S)
_SRC = re.compile(r"(?<![\w-])src\s*=", re.I)
_TYPE = re.compile(r"""(?<![\w-])type\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.I)
_EXECUTABLE = {"", "text/javascript", "application/javascript", "module"}


def _blank(match: re.Match[str]) -> str:
    """Комментарий заменяется переводами строк: номера строк дальше не сдвигаются."""
    return "\n" * match.group(0).count("\n")


def inline_scripts(theme_dir: Path, site_root: Path | None, collector: Collector) -> None:
    """Предупредить об инлайн-скрипте в теме: CSP сайта (`script-src 'self'`) его заблокирует.

    Тема лежит в сайте копией и новых файлов от движка не получает, поэтому
    заготовка до E15.S1.T20 с инлайн-кодом после пересборки теряет скрипт молча.
    Не считаются теги с `src` и неисполняемые типы (`application/ld+json`,
    `application/json` и другие). Комментарии `{# #}` и `<!-- -->` не читаются.
    """
    theme_dir = Path(theme_dir)
    if not theme_dir.is_dir():
        return
    root = Path(site_root).resolve() if site_root is not None else None
    for path in sorted(theme_dir.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = _COMMENTS.sub(_blank, text)
        rel = path.relative_to(theme_dir).as_posix()
        for tag in _SCRIPT.finditer(text):
            attrs = tag.group(1)
            if _SRC.search(attrs):
                continue
            kind = _TYPE.search(attrs)
            value = next((g for g in kind.groups() if g is not None), "") if kind else ""
            if value.strip().lower() not in _EXECUTABLE:
                continue
            collector.warn(
                Msg("theme_inline_script", line=text.count("\n", 0, tag.start()) + 1),
                path=_shown(theme_dir, rel, root),
                line=text.count("\n", 0, tag.start()) + 1,
                kind="контент",
            )


# Адрес /assets/ в шаблоне: в кавычках, в url(…), после `=` или пробела.
# Адрес на чужом домене (`https://cdn…/assets/`) не считается: перед ним не граница.
_HARDCODED = re.compile(r"""(?:(?<=["'(=\s])|^)/assets/""", re.M)
# Строка с путём /assets/ или /media/ в скрипте темы.
_JS_PATH = re.compile(r"""["'`](/(?:assets|media)/[^"'`\s]*)""")
_JS_BLOCK = re.compile(r"/\*.*?\*/", re.S)
JS_SUFFIXES = {".js", ".mjs"}


def asset_paths(theme_dir: Path, site_root: Path | None, collector: Collector) -> None:
    """Предупредить о ручных адресах файлов темы (21 §7, «Версии файлов»).

    В шаблоне `/assets/…` сборка и так перепишет на имя с хешем, но
    `asset('…')` проверяется: опечатка - ошибка E045, а не битая ссылка.
    В скрипте темы (`.js`) имена не переписываются вовсе: такой файл
    кэшируется на срок без версии, и после обновления темы посетитель
    может получить вчерашний.
    """
    theme_dir = Path(theme_dir)
    if not theme_dir.is_dir():
        return
    root = Path(site_root).resolve() if site_root is not None else None
    for rel in _candidates(theme_dir):
        try:
            text = (theme_dir / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = _COMMENTS.sub(_blank, text)
        lines = sorted({text.count("\n", 0, m.start()) + 1 for m in _HARDCODED.finditer(text)})
        for line in lines:
            collector.warn(
                Msg("theme_asset_hardcoded", line=line),
                path=_shown(theme_dir, rel, root),
                line=line,
                kind="контент",
            )
    assets = theme_dir / "assets"
    if not assets.is_dir():
        return
    for path in sorted(assets.rglob("*")):
        if path.suffix.lower() not in JS_SUFFIXES or not path.is_file():
            continue
        if not paths.inside(theme_dir, path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = _JS_BLOCK.sub(_blank, text)
        rel = path.relative_to(theme_dir).as_posix()
        for match in _JS_PATH.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            collector.warn(
                Msg("theme_js_asset_path", line=line, path=match.group(1)),
                path=_shown(theme_dir, rel, root),
                line=line,
                kind="контент",
            )


# Код шаблона (`{{ page.url }}`, `{% set href = … %}`): каким станет значение
# атрибута, известно только после рендера. Код заменяется меткой той же длины
# (переводы строк остаются - номера строк не сдвигаются), и значение с меткой
# не проверяется, а `href = …` внутри `{% set %}` атрибутом не считается.
_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
_MARK = "\x00"
RELATIVE = "E046"


def _masked(match: re.Match[str]) -> str:
    return "".join(char if char == "\n" else _MARK for char in match.group(0))


def relative_links(
    theme_dir: Path, site_root: Path | None, config: SiteConfig, collector: Collector
) -> None:
    """Относительные адреса в шаблонах темы при `urls.trailing_slash: never` - E046 (20 §2).

    На адресе без слеша браузер разрешает `site.css` и `../x` от папки
    страницы: на `/ru/cases/x` это `/ru/cases/site.css`. Значения, собранные
    шаблоном, не проверяются - про них знает только рендер.
    """
    theme_dir = Path(theme_dir)
    if config.urls.slash or not theme_dir.is_dir():
        return
    root = Path(site_root).resolve() if site_root is not None else None
    for rel in _candidates(theme_dir):
        try:
            text = (theme_dir / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = _JINJA.sub(_masked, _COMMENTS.sub(_blank, text))
        for start, value in urls.attr_urls(text):
            if _MARK in value or not urls.relative(value):
                continue
            line = text.count("\n", 0, start) + 1
            collector.error(
                RELATIVE,
                Msg("tree_relative_link", href=value),
                path=_shown(theme_dir, rel, root),
                line=line,
                hint=Msg("tree_relative_link_hint"),
            )
