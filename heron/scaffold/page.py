"""Заготовка страницы.

Сайт ведёт не разработчик. Набор секций своего типа не надо помнить
и подсматривать в чужом файле: команда кладёт файл со всеми секциями,
которые ждёт тема, и построчными подсказками.
"""

from __future__ import annotations

import re
from pathlib import Path

from heron.contracts.site import load_site
from heron.contracts.theme import load_theme
from heron.core.errors import HeronError
from heron.core.resolver import theme as find_theme
from heron.scaffold import seo_block

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def write_page(
    root: Path,
    page_type: str,
    slug: str,
    lang: str | None = None,
    folder: str = "",
) -> Path:
    """Создать файл страницы со всеми секциями типа."""
    if not SLUG.match(slug):
        raise HeronError(
            code="E005",
            message=f"недопустимый слаг {slug!r}",
            hint="латиница, цифры и дефис: getting-started. Заголовок может быть любым",
        )

    config = load_site(root / "site.yaml")
    found = find_theme(root, config.site.theme)
    theme = load_theme(found.path / "theme.yaml")

    if page_type not in theme.types:
        known = ", ".join(sorted(theme.types)) or "ни одного"
        raise HeronError(
            code="E008",
            message=f"тема не знает тип страницы {page_type!r}; в ней описаны: {known}",
            path=str(found.path / "theme.yaml"),
        )

    lang = lang or config.site.default_lang
    target = root / "content" / lang / folder / f"{slug}.md"
    if target.exists():
        raise HeronError(code="E004", message="такой файл уже есть", path=str(target))

    sections = theme.sections_of(page_type) or ["intro"]
    body: list[str] = []
    for section in sections:
        if section == "intro":
            body.append("Вводный абзац — то, что попадёт в сниппет.\n")
            continue
        body.append(f"## TODO заголовок {{#{section}}}\n\nTODO содержимое.\n")

    title = slug.replace("-", " ").capitalize()
    target.parent.mkdir(parents=True, exist_ok=True)
    comments = config.build.comments
    todo = {"ru": "TODO: что человек получит на странице", "en": "TODO: what the visitor gets"}
    head = seo_block(title, title, todo[comments], page_type=page_type, comments=comments)
    target.write_text(head + "\n" + "\n".join(body), encoding="utf-8")
    return target
