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
from heron.core import paths
from heron.core.errors import HeronError
from heron.core.resolver import theme as find_theme
from heron.messages import Msg
from heron.scaffold import seo_block

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
            message=Msg("scaffold_bad_slug", slug=slug),
            hint=Msg("scaffold_bad_slug_hint"),
        )

    config = load_site(root / "site.yaml")
    found = find_theme(root, config.site.theme)
    theme = load_theme(found.path / "theme.yaml")

    if page_type not in theme.types:
        known = ", ".join(sorted(theme.types))
        raise HeronError(
            code="E008",
            message=(
                Msg("scaffold_unknown_type", page_type=page_type, known=known)
                if known
                else Msg("scaffold_unknown_type_none", page_type=page_type)
            ),
            path=str(found.path / "theme.yaml"),
        )

    lang = lang or config.site.default_lang
    if lang not in config.site.languages:
        raise HeronError(
            code="E005",
            message=Msg("scaffold_bad_lang", lang=lang),
            hint=", ".join(config.site.languages),
        )
    clean = paths.normalize(folder)
    if clean == ".":
        clean = ""
    if paths.escapes(clean) or any(part.startswith(".") for part in clean.split("/") if part):
        raise HeronError(
            code=paths.CODE,
            message=Msg("scaffold_bad_folder", folder=folder, lang=lang),
            hint=Msg("scaffold_bad_folder_hint"),
        )
    rel = "/".join(part for part in ("content", lang, clean, f"{slug}.md") if part)
    target = paths.in_site(root, rel)
    if target.exists():
        raise HeronError(code="E004", message=Msg("scaffold_exists"), path=str(target))

    import os

    # Заготовка — подсказка автору, а не текст страницы: она на языке
    # пояснений, как SEO-блок над ней. Язык страницы (`lang`) — язык того
    # текста, которым автор заменит подсказки.
    notes = (os.environ.get("HERON_NOTES", "").strip() or config.build.notes).lower()
    notes = notes if notes in BODY else "en"
    words = BODY[notes]

    sections = theme.sections_of(page_type) or ["intro"]
    body: list[str] = []
    for section in sections:
        if section == "intro":
            body.append(words["intro"] + "\n")
            continue
        body.append(f"## {words['heading']} {{#{section}}}\n\n{words['content']}\n")

    title = slug.replace("-", " ").capitalize()
    target.parent.mkdir(parents=True, exist_ok=True)
    head = seo_block(title, title, words["description"], page_type=page_type, notes=notes)
    target.write_text(head + "\n" + "\n".join(body), encoding="utf-8")
    return target
