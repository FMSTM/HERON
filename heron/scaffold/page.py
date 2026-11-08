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

    sections = theme.sections_of(page_type) or ["intro"]
    body: list[str] = []
    for section in sections:
        if section == "intro":
            body.append(words["intro"] + "\n")
            continue
        body.append(f"## {words['heading']} {{#{section}}}\n\n{words['content']}\n")
    if "intro" not in sections:
        body.insert(0, words["intro"] + "\n")
    return head + "\n" + "\n".join(body)
