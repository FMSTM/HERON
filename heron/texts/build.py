"""Сообщения heron/core/build.py."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "build_pending_held": (
            "перевод на {lang} не готов (translation: pending): боевая сборка эту версию "
            "не публикует - ни страницы, ни ссылок на неё в меню, sitemap и hreflang"
        ),
        "build_type_field_required": (
            "поле {field} обязательно для страниц типа {type} (types.{type}.fields в theme.yaml)"
        ),
        "build_type_field_type": "{field}: ждём {kind}, а записано {value!r}",
        "build_type_field_value": "{field}: {value!r} - нет среди допустимых: {values}",
        "build_type_field_hint": (
            "впишите {field} в SEO-блок страницы или откройте её командой `heron page add` "
            "с её ключом: поле и подсказка - в группе «Поля темы»"
        ),
        "build_type_field_length": "{field}: {length} знаков, тема ждёт от {min} до {max}",
        "build_type_field_items": "{field}: пунктов {count}, тема ждёт от {min} до {max}",
        "build_placeholder": ("{field}: текст заготовки «{text}» - страница ещё не дописана"),
        "build_placeholder_hint": (
            "замените текст заготовки своим (или уберите секцию): `heron page add` с ключом "
            "страницы откроет её на правку. Черновая сборка покажет страницу, боевая - нет"
        ),
        "build_anchors_differ": (
            "якоря секций на {lang} не те, что на {other}: нет {missing}, лишние {extra}. "
            "Якорь - часть структуры страницы, он один на всех языках"
        ),
        "build_pending_category": (
            "категория {category} на {lang} не переведена (translation: pending в её _index.md): "
            "боевая сборка не публикует её вместе со страницами внутри, и эту тоже. "
            "Переведите категорию: `heron category add {category}`"
        ),
        "build_pending_shown": (
            "перевод на {lang} не готов (translation: pending): здесь страница с плашкой, "
            "боевая сборка её не опубликует. Перевели - удалите строку translation"
        ),
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
        "build_owner_theme_ref": "справка темы (черновая сборка)",
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
        "build_home_pending": (
            "главная языка {lang!r} не переведена (translation: pending): боевая сборка её "
            "не публикует, и {home} ответит 404"
        ),
        "build_home_pending_hint": (
            "переведите главную и уберите строку translation (`heron page add / --lang {lang}`) "
            "или уберите язык {lang} из site.languages, пока перевода нет"
        ),
    },
    "en": {
        "build_pending_held": (
            "the {lang} translation is not ready (translation: pending): the production build "
            "does not publish this version - no page, no links to it in the menu, sitemap and "
            "hreflang"
        ),
        "build_type_field_required": (
            "the field {field} is required for pages of type {type} (types.{type}.fields in "
            "theme.yaml)"
        ),
        "build_type_field_type": "{field}: expected {kind}, written {value!r}",
        "build_type_field_value": "{field}: {value!r} is not among the allowed: {values}",
        "build_type_field_hint": (
            "write {field} into the SEO block of the page or open it with `heron page add` and "
            'its key: the field and its hint are in the group "Theme fields"'
        ),
        "build_type_field_length": "{field}: {length} characters, the theme expects {min} to {max}",
        "build_type_field_items": "{field}: {count} items, the theme expects {min} to {max}",
        "build_placeholder": '{field}: placeholder text "{text}" - the page is not finished',
        "build_placeholder_hint": (
            "replace the placeholder with your own text (or remove the section): `heron page "
            "add` with the key of the page opens it for editing. A draft build shows the page, "
            "the production build does not"
        ),
        "build_anchors_differ": (
            "the section anchors in {lang} differ from {other}: missing {missing}, extra {extra}. "
            "An anchor is part of the page structure, one for all languages"
        ),
        "build_pending_category": (
            "the category {category} is not translated into {lang} (translation: pending in its "
            "_index.md): the production build does not publish it together with the pages "
            "inside, this one too. Translate the category: `heron category add {category}`"
        ),
        "build_pending_shown": (
            "the {lang} translation is not ready (translation: pending): shown here with a "
            "banner, the production build will not publish it. Once translated, delete the "
            "translation line"
        ),
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
        "build_owner_theme_ref": "theme reference (draft build)",
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
        "build_home_pending": (
            "the home page of language {lang!r} is not translated (translation: pending): the "
            "production build does not publish it, and {home} would answer 404"
        ),
        "build_home_pending_hint": (
            "translate the home page and delete the translation line (`heron page add / --lang "
            "{lang}`) or remove {lang} from site.languages until there is a translation"
        ),
    },
}
