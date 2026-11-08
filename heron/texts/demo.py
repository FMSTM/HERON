"""Сообщения демо темы: heron/core/demo.py и проверка демо в heron/themes (pack)."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "demo_gap_type": "тип {type}: нет ни одной демо-страницы",
        "demo_gap_module": "блок {module} ({kinds}): не показан ни на одной демо-странице",
        "demo_gap_page_module": (
            "модуль страницы {module}: ни на одной демо-странице ничего не нарисовал"
        ),
        "demo_gap_view": (
            "вид раздела {view} (типы {types}): нет страницы раздела со строкой {key}: {view} "
            "и страницами внутри"
        ),
        "demo_gap_view_default": (
            "вид раздела {view} (по умолчанию, типы {types}): нет страницы раздела без ключа "
            "{key} и со страницами внутри"
        ),
        "demo_incomplete": (
            "демо темы {theme} показывает не всё, что объявил theme.yaml ({count} "
            "{count:пропуск|пропуска|пропусков}):\n    {gaps}"
        ),
        "demo_incomplete_hint": (
            "демо - это контент сайта, из которого упаковывают тему: у каждого типа нужна "
            "демо-страница, каждый блок и каждый вид раздела - хотя бы на одной. Что объявила "
            "тема - `heron describe`, что показано - `heron docs theme-ref`; проверить - "
            "`heron check --theme`"
        ),
        "demo_incomplete_old": (
            "демо темы {theme} показывает не всё ({count} "
            "{count:пропуск|пропуска|пропусков}); тема без описания полей (fields) - поэтому "
            "предупреждение, у темы с fields это ошибка E037:\n    {gaps}"
        ),
        "demo_no_site": (
            "в папке {path} нет site.yaml: демо темы - контент сайта, и без site.yaml его "
            "языки и страницы не прочитать"
        ),
        "demo_no_site_hint": (
            "упакуйте тему из папки сайта, где она стоит и где лежит её демо: `heron theme "
            "pack <папка сайта>`"
        ),
    },
    "en": {
        "demo_gap_type": "type {type}: no demo page at all",
        "demo_gap_module": "block {module} ({kinds}): not shown on any demo page",
        "demo_gap_page_module": "page module {module}: drew nothing on any demo page",
        "demo_gap_view": (
            "section view {view} (types {types}): no section page with the line {key}: {view} "
            "and pages inside"
        ),
        "demo_gap_view_default": (
            "section view {view} (the default, types {types}): no section page without the "
            "key {key} and with pages inside"
        ),
        "demo_incomplete": (
            "the demo of theme {theme} does not show everything theme.yaml declares ({count} "
            "{count:gap|gaps}):\n    {gaps}"
        ),
        "demo_incomplete_hint": (
            "the demo is the content of the site the theme is packed from: every type needs a "
            "demo page, every block and every section view - at least one. What the theme "
            "declares - `heron describe`, what is shown - `heron docs theme-ref`; to check - "
            "`heron check --theme`"
        ),
        "demo_incomplete_old": (
            "the demo of theme {theme} does not show everything ({count} {count:gap|gaps}); "
            "the theme has no field description (fields), so this is a warning, for a theme "
            "with fields it is error E037:\n    {gaps}"
        ),
        "demo_no_site": (
            "the folder {path} has no site.yaml: the demo of a theme is the content of a "
            "site, and without site.yaml its languages and pages cannot be read"
        ),
        "demo_no_site_hint": (
            "pack the theme from the site folder where it is installed and where its demo "
            "lives: `heron theme pack <site folder>`"
        ),
    },
}
