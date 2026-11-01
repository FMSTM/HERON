"""Сообщения заготовки страницы (scaffold/page.py, scaffold/__init__.py)."""

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "scaffold_bad_slug": "недопустимый слаг {slug!r}",
        "scaffold_bad_slug_hint": "латиница, цифры и дефис: getting-started. Заголовок может быть любым",
        "scaffold_unknown_type_none": "тема не знает тип страницы {page_type!r}; в ней описаны: ни одного",
        "scaffold_unknown_type": "тема не знает тип страницы {page_type!r}; в ней описаны: {known}",
        "scaffold_bad_lang": "языка {lang!r} нет в site.languages",
        "scaffold_bad_folder": "папка {folder!r} выходит за пределы content/{lang}/",
        "scaffold_bad_folder_hint": "относительный путь без `..`: guides/intro",
        "scaffold_exists": "такой файл уже есть",
    },
    "en": {
        "scaffold_bad_slug": "invalid slug {slug!r}",
        "scaffold_bad_slug_hint": "Latin letters, digits and hyphens: getting-started. The title can be anything",
        "scaffold_unknown_type_none": "the theme does not know page type {page_type!r}; it describes: none",
        "scaffold_unknown_type": "the theme does not know page type {page_type!r}; it describes: {known}",
        "scaffold_bad_lang": "language {lang!r} is not in site.languages",
        "scaffold_bad_folder": "folder {folder!r} goes outside content/{lang}/",
        "scaffold_bad_folder_hint": "a relative path without `..`: guides/intro",
        "scaffold_exists": "this file already exists",
    },
}
