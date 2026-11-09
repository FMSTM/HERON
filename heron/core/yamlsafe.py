"""YAML движка: один вход для всех файлов и два режима.

Якорь и ссылка (`&a`, `*a`) у PyYAML - общая ссылка на один объект. Девять
уровней по десять ссылок («billion laughs») - килобайт текста, `safe_load`
отдаёт его мгновенно, но любой обход - проверка полей, поиск картинок,
`json.dumps` - разворачивает миллиард узлов. Поэтому:

- **сайт** (`load`, умолчание: site.yaml, фронтматтер, data/) - якоря можно,
  `heron.edit` уже держит поля с ними только для чтения. Но если в документе
  есть ссылки, развёрнутый он не больше MAX_NODES узлов и MAX_DEPTH уровней,
  а ссылка на саму себя - отказ. Подсчёт - по графу узлов после разбора, до
  построения объектов, с запоминанием узла, на который ссылаются: проверка
  бомбы стоит столько же, сколько её текст. Документ без ссылок не считается
  вовсе - большой файл data/ остаётся как был.
- **тема** (`load(..., theme=True)`, `anchor_in`) - тема приходит чужим
  архивом (`heron theme get`), её файлы (theme.yaml, i18n, демо) якорей и
  ссылок не содержат вовсе: отказ на первом таком событии парсера, до узлов.

Ошибки - наследники `yaml.YAMLError`: место, где файл читается, говорит о них
своим кодом, как о любом битом YAML; `read_yaml` и фронтматтер - отдельным
сообщением.

Спецификация: docs/ru/spec/21-engine.md, раздел 11 (пределы).
"""

from __future__ import annotations

from typing import Any

import yaml

MAX_NODES = 100_000
MAX_DEPTH = 64


class Anchors(yaml.YAMLError):
    """Якорь или ссылка в файле темы."""

    def __init__(self, mark: yaml.Mark | None) -> None:
        super().__init__("anchor or alias")
        self.problem = "YAML anchors and aliases are not allowed in theme files"
        self.problem_mark = mark


class Expands(yaml.YAMLError):
    """Документ со ссылками разворачивается больше предела или в самого себя."""

    def __init__(self, mark: yaml.Mark | None) -> None:
        super().__init__("expands too much")
        self.problem = f"YAML expands too much (anchors/aliases): over {MAX_NODES} nodes"
        self.problem_mark = mark


class _Theme(yaml.SafeLoader):
    """SafeLoader без якорей: отказ на событии, до узла."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        event = self.peek_event()
        if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None) is not None:
            raise Anchors(event.start_mark)
        return super().compose_node(parent, index)


def load(text: str, *, theme: bool = False) -> Any:
    """`yaml.safe_load` с пределом: сайт - развёртка ссылок, тема - без якорей."""
    loader = (_Theme if theme else yaml.SafeLoader)(text)
    try:
        node = loader.get_single_node()
        if node is None:
            return None
        if not theme:
            bound(node)
        return loader.construct_document(node)
    finally:
        loader.dispose()


def bound(root: yaml.Node) -> None:
    """Развёрнутый граф узлов не больше MAX_NODES и MAX_DEPTH, без петель - или Expands.

    Каждый узел считается один раз: размер узла, на который ссылаются,
    запоминается. Документ без ссылок (узлов столько же, сколько в развёртке)
    проходит без пределов.
    """
    cap = MAX_NODES + 1
    sizes: dict[int, tuple[int, int]] = {}
    active: set[int] = set()

    def visit(node: yaml.Node) -> tuple[int, int]:
        key = id(node)
        if key in sizes:
            return sizes[key]
        if key in active:
            raise Expands(node.start_mark)  # ссылка на саму себя
        active.add(key)
        count, depth = 1, 1
        if isinstance(node, yaml.SequenceNode):
            children = node.value
        elif isinstance(node, yaml.MappingNode):
            children = [item for pair in node.value for item in pair]
        else:
            children = []
        for child in children:
            size, deep = visit(child)
            count = min(count + size, cap)
            depth = max(depth, deep + 1)
        active.discard(key)
        sizes[key] = (count, depth)
        return count, depth

    count, depth = visit(root)
    aliased = count > len(sizes)
    if aliased and (count > MAX_NODES or depth > MAX_DEPTH):
        raise Expands(root.start_mark)


def anchor_in(text: str) -> int | None:
    """Строка (с 1) первого якоря или ссылки в YAML; нет их - None.

    Только события парсера, без узлов и объектов. Битый YAML - None: о нём
    скажет своя проверка.
    """
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None) is not None:
                return event.start_mark.line + 1
    except yaml.YAMLError:
        return None
    return None


def file_anchor(name: str, text: str) -> int | None:
    """Строка первого якоря или ссылки в файле темы: `.yaml`/`.yml` целиком, `.md` - фронтматтер.

    Прочие файлы - None. Нужна `theme get` до распаковки, `theme pack` до архива
    и `heron check --theme`.
    """
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix in ("yaml", "yml"):
        return anchor_in(text)
    if suffix != "md":
        return None
    from heron.core.parser.frontmatter import FRONTMATTER

    match = FRONTMATTER.match(text)
    if not match:
        return None
    line = anchor_in(match.group("body"))
    return line + 1 if line else None  # строка `---` перед фронтматтером
