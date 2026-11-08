"""Заготовка файла страницы и категории.

Сайт ведёт не разработчик. Набор секций своего типа не надо помнить
и подсматривать в чужом файле: заготовка кладёт полный SEO-блок с
комментариями и все секции, которые ждёт тема, с построчными подсказками.

Заготовку пишут команды `heron page add` и `heron category add`
(`heron/edit/entity.py`) - сразу на всех языках сайта.
"""

from __future__ import annotations

import json
import re

from heron.contracts.theme import ThemeConfig
from heron.scaffold import _TYPE_HINTS, seo_block

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\Z")

# Подсказки заготовки на языке пояснений сайта (build.notes, HERON_NOTES).
# TODO — метка, по которой автор находит недописанное, она не переводится.
BODY = {
    "ru": {
        "intro": "Вводный абзац - то, что попадёт в сниппет.",
        "heading": "TODO заголовок",
        "content": "TODO содержимое.",
        "description": "TODO: что человек получит на странице",
    },
    "en": {
        "intro": "Intro paragraph - what goes into the search snippet.",
        "heading": "TODO heading",
        "content": "TODO content.",
        "description": "TODO: what the visitor gets",
    },
}
MARKER = "\n# children_type:"


HEADING = re.compile(
    r"^##[ \t]+.*?\{#[^\s}]+(?P<classes>(?:[ \t]+\.[A-Za-z0-9_-]+)*)[ \t]*\}[ \t]*$"
)


def _section(theme: ThemeConfig, page_type: str, section: str, notes: str, words) -> str:
    """Заготовка секции в той форме, которую ждёт тема: содержимое - образец модуля.

    Форма - из `uses` (`"how:steps"`), образец - `example` модуля этой формы на языке
    пояснений. Заголовок - метка TODO (её ловит боевая сборка), класс якоря - из
    образца (`{#tabs .tabs}`): без него вкладки и галерею не узнать. Образца нет -
    абзац TODO, как раньше.
    """
    kind = theme.formats_of(page_type).get(section)
    module = theme.module_for(kind) if kind else None
    spec = theme.module_specs.get(module) if module else None
    example = (spec.text("example", notes) if spec is not None else None) or ""
    lines = example.strip("\n").splitlines()
    match = HEADING.match(lines[0]) if lines else None
    if match is None:
        return f"## {words['heading']} {{#{section}}}\n\n{words['content']}\n"
    rest = lines[1:]
    stop = next((i for i, line in enumerate(rest) if line.startswith("## ")), len(rest))
    content = "\n".join(rest[:stop]).strip("\n")
    classes = match.group("classes").strip()
    anchor = f"#{section}" + (f" {classes}" if classes else "")
    return f"## {words['heading']} {{{anchor}}}\n\n{content}\n"


def _own_value(field, notes: str, words) -> object:
    """Значение обязательного своего поля в заготовке: образец темы или метка TODO."""
    example = field.text("example", notes)
    if field.type == "enum":
        return field.values[0]
    if field.type == "flag":
        return False
    if field.type == "number":
        return 0
    if field.type == "list":
        return [example or words["heading"]]
    return example or words["heading"]


def _own_fields(head: str, fields, notes: str, words) -> str:
    """Свои поля типа в SEO-блок заготовки перед закрывающей `---`.

    Обязательное - со значением (первое из `values`, образец темы или TODO: его
    поймает боевая сборка, E040), необязательное - заготовкой `# имя:` с подсказкой:
    опросник и студия раскомментируют её на месте.
    """
    lines = []
    for field in fields:
        hint = field.text("hint", notes) or ""
        if field.required:
            value = json.dumps(_own_value(field, notes, words), ensure_ascii=False)
            lines.append(f"{field.name}: {value}" + (f"   # {hint}" if hint else ""))
        else:
            lines.append(f"# {field.name + ':':<26} # {hint}".rstrip(" #"))
    body, sep, tail = head.rstrip("\n").rpartition("\n---")
    if not sep:
        return head
    return body + "\n" + "\n".join(lines) + sep + tail + "\n"


def title_of(key: str) -> str:
    """Заголовок по умолчанию: последняя часть ключа словами, `about-agency` - `About agency`."""
    name = key.strip("/").rsplit("/", 1)[-1]
    return name.replace("-", " ").capitalize() or name


def stub(
    theme: ThemeConfig,
    page_type: str,
    title: str,
    notes: str,
    *,
    category: bool = False,
    children_type: str | None = None,
    view: str | None = None,
) -> str:
    """Текст нового файла: SEO-блок и все секции типа `page_type`.

    Категория (`_index.md`) получает ещё `children_type` - тип страниц внутри -
    и ключ вида отображения из `views` своего типа, если вид выбран.
    """
    notes = notes if notes in BODY else "en"
    words = BODY[notes]
    head = seo_block(title, title, words["description"], page_type=page_type, notes=notes)
    spec = theme.types.get(page_type)
    views = spec.views if spec is not None else None
    lines = ""
    if view and views is not None:
        lines += (
            f"\n{views.key}: {json.dumps(view, ensure_ascii=False)}\n# ↑ {_TYPE_HINTS[notes][2]}"
        )
    elif category and views is not None:
        # заготовка: опросник и --answers ставят вид на это место, с подсказкой
        lines += f"\n# {views.key + ':':<26} # {_TYPE_HINTS[notes][2]}"
    if category and children_type:
        lines += f"\nchildren_type: {json.dumps(children_type, ensure_ascii=False)}"
        # строка-заготовка `# children_type:` заменяется настоящим ключом
        head = re.sub(r"\n# children_type:[^\n]*", lines, head, count=1)
    elif lines:
        head = head.replace(MARKER, lines + MARKER, 1)

    if spec is not None and spec.fields:
        head = _own_fields(head, spec.fields, notes, words)
    sections = theme.sections_of(page_type) or ["intro"]
    body: list[str] = []
    for section in sections:
        if section == "intro":
            body.append(words["intro"] + "\n")
            continue
        body.append(_section(theme, page_type, section, notes, words))
    if "intro" not in sections:
        body.insert(0, words["intro"] + "\n")
    return head + "\n" + "\n".join(body)
