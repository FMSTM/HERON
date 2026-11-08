"""Справка темы: heron/core/render/themeref.py (docs theme-ref, /_heron/theme/)."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "ref_title": "Справка темы {theme} ({name})",
        "ref_text_lead": (
            "Собрана из theme.yaml и демо-страниц сайта. С живыми примерами - служебная "
            "страница {url} в черновой сборке и в `heron serve`."
        ),
        "ref_page_lead": (
            "Служебная страница черновой сборки: собрана из theme.yaml и демо-страниц сайта, "
            "руками её не пишут. В боевую сборку (--env prod), в карту сайта и в поиск она не "
            "попадает. Текстом - `heron docs theme-ref`."
        ),
        "ref_other_langs": "Другие языки:",
        "ref_render_failed": "демо не собралось целиком: {error}",
        "ref_types": "Типы страниц",
        "ref_template": "шаблон: {template}",
        "ref_section": "секция",
        "ref_demo_pages": "демо-страницы: {pages}",
        "ref_none": "нет",
        "ref_modules": "Блоки",
        "ref_no_example": "в демо этот блок не показан",
        "ref_no_view_example": "в демо этот вид не показан",
        "ref_theme_example": "образец из theme.yaml:",
        "ref_example_at": "пример из демо: {where}",
        "ref_page_module_text": (
            "модуль страницы: тема рисует его сама из данных страницы, в markdown его нет"
        ),
        "ref_views": "Виды разделов",
        "ref_views_of": "тип {type}, ключ {key}",
        "ref_view_default": "по умолчанию: без ключа {key} или {key}: {view}",
        "ref_view_key": "включается строкой {key}: {view} во фронтматтере страницы раздела",
        "ref_schema": "Разметка schema.org",
        "ref_styles": "Стили",
        "ref_strings": "Строки интерфейса ({lang})",
        "ref_col_field": "поле",
        "ref_col_type": "тип и ограничения",
        "ref_col_place": "где в markdown",
        "ref_col_hint": "подсказка",
        "ref_col_section": "секция",
        "ref_col_kind": "форма",
        "ref_live": "как выглядит",
        "ref_source": "как написано",
    },
    "en": {
        "ref_title": "Theme reference {theme} ({name})",
        "ref_text_lead": (
            "Built from theme.yaml and the demo pages of the site. With live examples - the "
            "service page {url} in a draft build and in `heron serve`."
        ),
        "ref_page_lead": (
            "A service page of a draft build: it is built from theme.yaml and the demo pages "
            "of the site, nobody writes it by hand. It is not in the production build (--env "
            "prod), in the sitemap or in search. As text - `heron docs theme-ref`."
        ),
        "ref_other_langs": "Other languages:",
        "ref_render_failed": "the demo did not build completely: {error}",
        "ref_types": "Page types",
        "ref_template": "template: {template}",
        "ref_section": "section",
        "ref_demo_pages": "demo pages: {pages}",
        "ref_none": "none",
        "ref_modules": "Blocks",
        "ref_no_example": "the demo does not show this block",
        "ref_no_view_example": "the demo does not show this view",
        "ref_theme_example": "the sample from theme.yaml:",
        "ref_example_at": "example from the demo: {where}",
        "ref_page_module_text": (
            "a page module: the theme draws it from the data of the page, it is not in markdown"
        ),
        "ref_views": "Section views",
        "ref_views_of": "type {type}, key {key}",
        "ref_view_default": "the default: without the key {key} or {key}: {view}",
        "ref_view_key": "turned on by the line {key}: {view} in the front matter of a section page",
        "ref_schema": "schema.org markup",
        "ref_styles": "Styles",
        "ref_strings": "Interface strings ({lang})",
        "ref_col_field": "field",
        "ref_col_type": "type and limits",
        "ref_col_place": "where in markdown",
        "ref_col_hint": "hint",
        "ref_col_section": "section",
        "ref_col_kind": "form",
        "ref_live": "how it looks",
        "ref_source": "how it is written",
    },
}
