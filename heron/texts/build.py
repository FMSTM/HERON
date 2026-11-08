"""Сообщения heron/core/build.py."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "build_theme_no_fields": (
            "тема {theme} не описала поля блоков (fields в theme.yaml): опросник и студия "
            "покажут только SEO-блок и служебные поля. Как описать - `heron docs theme`, "
            "«Поля блоков и подсказки»; что уже есть - `heron describe`"
        ),
        "build_theme_hints": (
            "тема {theme}: нет подсказки hint на языках темы ({langs}):\n    {missing}"
        ),
        "build_theme_hints_hint": (
            "у каждого типа, секции из sections, модуля, поля и вида нужен hint_<язык> "
            "на каждом языке из languages темы (или hint без суффикса); проверить - "
            "`heron check`"
        ),
        "build_bad_workers": "{env}={raw!r}: нужно целое число от 0 до 64",
        "build_bad_workers_hint": (
            "0 - по числу ядер, 1 - без пула процессов; пустое значение - как в site.yaml"
        ),
        "build_prod_no_pages": "в проде нечего собирать: ни одной страницы",
        "build_prod_no_pages_hint": (
            "проверьте путь к контенту и языки в site.yaml; "
            "пустую сборку можно делать только в деве"
        ),
        "build_prod_empty_default_lang": (
            "в проде пуст язык по умолчанию {default!r}: корень сайта ответил бы 404"
        ),
        "build_prod_empty_default_lang_hint": (
            "заполните content/{default}/ или назначьте default_lang "
            "языком, на котором контент уже есть"
        ),
        "build_owner_page": "страница {where}",
        "build_owner_page_404": "страница 404",
        "build_owner_sitemap": "генератор sitemap",
        "build_owner_robots": "генератор robots.txt",
        "build_owner_llms": "генератор llms.txt",
        "build_owner_redirects": "генератор карт 301/410",
        "build_owner_nginx": "генератор конфига nginx",
        "build_owner_feed": "генератор ленты",
        "build_owner_plugin_generate": "плагин (on_generate)",
        "build_owner_theme_asset": "тема assets/{rel}",
        "build_nginx_empty": "{name} пуст",
        "build_nginx_empty_hint": (
            "пустой конфиг - сайт без 301, 410 и 404; уберите подмену "
            "из build.overrides или верните содержимое"
        ),
        "build_plugin_word": "плагин",
        "build_finish_failed": "{name}: {kind}: {error}",
        "build_finished_returned_files": (
            "плагин вернул файлы из on_build_finished - они не записаны: "
            "файлы сборки объявляются в on_generate(site, config)"
        ),
        "build_no_home_page": "у языка {lang!r} нет главной страницы: {home} ответит 404",
        "build_no_home_page_hint": "создайте index.md в корне языка",
    },
    "en": {
        "build_theme_no_fields": (
            "theme {theme} has not described the fields of its blocks (fields in theme.yaml): "
            "the questionnaire and the studio will show only the SEO block and the service "
            'fields. How to describe them - `heron docs theme`, "Block fields and hints"; '
            "what is there already - `heron describe`"
        ),
        "build_theme_hints": (
            "theme {theme}: no hint in the languages of the theme ({langs}):\n    {missing}"
        ),
        "build_theme_hints_hint": (
            "every type, section in sections, module, field and view needs hint_<lang> in "
            "every language of languages of the theme (or hint without a suffix); to "
            "check - `heron check`"
        ),
        "build_bad_workers": "{env}={raw!r}: an integer from 0 to 64 is required",
        "build_bad_workers_hint": (
            "0 means one per core, 1 means no process pool; an empty value falls back to site.yaml"
        ),
        "build_prod_no_pages": "nothing to build in production: there are no pages",
        "build_prod_no_pages_hint": (
            "check the content path and the languages in site.yaml; "
            "an empty build is only allowed in dev"
        ),
        "build_prod_empty_default_lang": (
            "the default language {default!r} is empty in production: "
            "the site root would answer 404"
        ),
        "build_prod_empty_default_lang_hint": (
            "fill content/{default}/ or set default_lang to a language that already has content"
        ),
        "build_owner_page": "page {where}",
        "build_owner_page_404": "page 404",
        "build_owner_sitemap": "sitemap generator",
        "build_owner_robots": "robots.txt generator",
        "build_owner_llms": "llms.txt generator",
        "build_owner_redirects": "301/410 map generator",
        "build_owner_nginx": "nginx config generator",
        "build_owner_feed": "feed generator",
        "build_owner_plugin_generate": "plugin (on_generate)",
        "build_owner_theme_asset": "theme assets/{rel}",
        "build_nginx_empty": "{name} is empty",
        "build_nginx_empty_hint": (
            "an empty config means a site without 301, 410 and 404; remove the override "
            "from build.overrides or restore its content"
        ),
        "build_plugin_word": "plugin",
        "build_finish_failed": "{name}: {kind}: {error}",
        "build_finished_returned_files": (
            "a plugin returned files from on_build_finished: they are not written; "
            "build files are declared in on_generate(site, config)"
        ),
        "build_no_home_page": "language {lang!r} has no home page: {home} would answer 404",
        "build_no_home_page_hint": "create index.md in the language root",
    },
}
