"""Сообщения схем site.yaml и theme.yaml."""

TEXT = {
    "ru": {
        "site_domain": "домен указывается без схемы и слешей, например example.com",
        "site_theme_name": "имя темы - латиница, цифры, дефис и подчёркивание",
        "site_lang_none": "нужен хотя бы один язык",
        "site_lang_code": "код языка {lang} не похож на код языка: ожидается uk, ru, en-gb",
        "site_lang_dup": "языки повторяются",
        "site_default_lang": "default_lang {default} отсутствует в languages {languages}",
        "site_agents": "build.agents: {value} - ожидается true, kit или false",
        "site_duration": (
            "срок кэша {value}: число секунд или число с единицей s, m, h, d, w, y - "
            "например 3600, 30m, 12h, 1d, 7d, 1y"
        ),
        "site_duration_big": "срок кэша {value}: больше 68 лет (2^31-1 секунд) не бывает",
        "site_hsts_preload": (
            "nginx.hsts: preload {max_age} - по правилам hstspreload.org для списка предзагрузки "
            "нужны max_age не меньше 1y и subdomains: true"
        ),
        "site_permission_shape": "nginx.permissions - словарь «возможность: значение»",
        "site_permission_unknown": (
            "nginx.permissions: возможности {name} нет в списке известных браузеру; "
            "похожие: {close}"
        ),
        "site_permission_value": (
            "nginx.permissions.{name}: значение {value} - ожидается none, self, * или источники "
            "https://example.com (можно вместе с self)"
        ),
        "site_log_ip": "nginx.log_ip: {value} - ожидается masked, full или off",
        "site_form_no_fields": "у формы нет ни одного поля",
        "site_field_name": "имя поля {name} - латиница, цифры, дефис и подчёркивание",
        "site_gone_root": "gone: {entry} - ожидается путь от корня, например /old-page/",
        "site_gone_anchor": "gone: {entry} - якорь серверу не приходит, уберите #…",
        "site_gone_param": "gone: {entry} - параметр пишется одной парой: /?p=* или /?p=12",
        "site_gone_star_value": "gone: {entry} - звёздочка заменяет значение целиком: /?p=*",
        "site_gone_star_end": "gone: {entry} - звёздочка допустима только в конце: /wp/*",
        "site_exc_key": "ключ исключения: ожидается SCH00N:<файл>:<путь>",
        "site_exc_reason": "у исключения нет причины",
        "site_plugin_name": "plugins: недопустимое имя {name}: латиница, цифры, _ и -",
        "site_plugin_dup": "plugins: имя плагина повторяется",
        "site_exc_dup": "исключение задано дважды: {key}",
        "site_i18n_shape": "i18n - словарь словарей: ключ, под ним язык и значение",
        "site_i18n_value": "{key}_{lang}: значение не того типа, нужно {expected}",
        "site_heron_not_string": "ключ `heron` - не строка: {value}",
        "site_heron_not_string_hint": 'возьмите требование в кавычки, например: heron: ">=0.1,<0.2"',
        "site_i18n_lang": "{key}_{lang}: языка '{lang}' нет в site.languages {languages}",
        "site_form_sinks": "форма {form} ссылается на приёмники, которых нет в sinks: {sinks}",
        "site_no_heron": "нет обязательного ключа `heron` с требуемой версией движка",
        "site_no_heron_hint": 'добавьте первой строкой, например: heron: ">=0.1,<0.2"',
        "site_th_section_name": (
            "секция {section} - латиница, цифры и дефис, необязательный формат через двоеточие"
        ),
        "site_th_section_kind": "секция {section}: формы {kind} нет. Есть: {kinds}",
        "site_th_section_dup": "секции повторяются",
        "site_th_relation_name": "имя поля связи - латиница, цифры, дефис и подчёркивание",
        "site_th_ratio": "пропорция {ratio} задаётся как 16:9",
        "site_th_widths": "ширины - положительные числа",
        "site_th_name": "имя темы - латиница, цифры, дефис и подчёркивание",
        "site_th_type_field_md": (
            "своё поле типа {name}: у него нет md - значение лежит в SEO-блоке страницы "
            "под именем поля; место в markdown бывает только у полей блока"
        ),
        "site_th_type_field_reserved": (
            "своё поле типа {name} совпадает с полем движка: такие поля описывает движок "
            "(heron describe, «служебные поля»). Возьмите другое имя. Занятые: {names}"
        ),
        "site_th_fields_shape": (
            "fields верхнего уровня theme.yaml - список имён полей движка, которые читают "
            "шаблоны (fields: [date, updated]), а здесь записано другое: похоже на описание "
            "полей блока или страницы"
        ),
        "site_th_fields_shape_hint": (
            "поля блока - в modules.<блок>.fields или types.<тип>.sections.<секция>.fields, "
            "свои поля фронтматтера страницы - в types.<тип>.fields; верхний fields оставьте "
            "списком имён или уберите. Пример - `heron docs theme`, «Поля»"
        ),
        "site_th_module_name": "имя модуля {module} - латиница, цифры, дефис и подчёркивание",
        "site_th_hint_text": "{key}: подсказка - строка текста",
        "site_th_field_name": "имя поля {name} - строчная латиница, цифры и подчёркивание, с буквы",
        "site_th_field_md": "поле: места {md} в markdown нет. Есть: {places}",
        "site_th_field_list": "поле {name}: у списка задаётся item (тип пункта) или fields (поля пункта), одно из двух",
        "site_th_field_list_item": "поле {name}: список списков пишется через fields пункта",
        "site_th_field_not_list": "поле {name}: item и fields бывают только у списка, а тип - {type}",
        "site_th_field_enum": "поле {name}: у enum нужен перечень values",
        "site_th_field_values": "поле {name}: values бывают только у enum, а тип - {type}",
        "site_th_field_image": "поле {name}: ratio и min_width бывают только у image, а тип - {type}",
        "site_th_field_dup": "поле {name} повторяется",
        "site_th_field_ref": "{field}: типа страниц {ref} в теме нет. Есть: {known}",
        "site_th_module_kind": "модуль: формы {kind} нет. Есть: {kinds}",
        "site_th_views_empty": "views: нужен хотя бы один вид в options",
        "site_th_view_name": "имя вида {view} - латиница, цифры, дефис и подчёркивание",
        "site_th_view_default": "views: вида по умолчанию {view} нет в options. Есть: {views}",
        "site_th_section_unused": "sections: секции {section} нет в uses ({uses})",
        "site_th_language": "язык подсказок {lang}: код вида ru или pt-br",
        "site_th_children_type": "тип {type}: children_type {children} - такого типа в теме нет. Есть: {known}",
    },
    "en": {
        "site_domain": "write the domain without a scheme or slashes, for example example.com",
        "site_theme_name": "the theme name is Latin letters, digits, hyphen and underscore",
        "site_lang_none": "at least one language is required",
        "site_lang_code": "the language code {lang} does not look like one: expected uk, ru, en-gb",
        "site_lang_dup": "languages are repeated",
        "site_default_lang": "default_lang {default} is missing from languages {languages}",
        "site_agents": "build.agents: {value} - expected true, kit or false",
        "site_duration": (
            "cache time {value}: a number of seconds or a number with a unit s, m, h, d, w, y - "
            "for example 3600, 30m, 12h, 1d, 7d, 1y"
        ),
        "site_duration_big": "cache time {value}: more than 68 years (2^31-1 seconds) is not allowed",
        "site_hsts_preload": (
            "nginx.hsts: preload {max_age} - by the hstspreload.org rules the preload list "
            "needs max_age of at least 1y and subdomains: true"
        ),
        "site_permission_shape": "nginx.permissions is a mapping of feature: value",
        "site_permission_unknown": (
            "nginx.permissions: the feature {name} is not among those browsers know; "
            "similar: {close}"
        ),
        "site_permission_value": (
            "nginx.permissions.{name}: the value {value} - expected none, self, * or origins "
            "https://example.com (self may go with them)"
        ),
        "site_log_ip": "nginx.log_ip: {value} - expected masked, full or off",
        "site_form_no_fields": "the form has no fields",
        "site_field_name": "the field name {name} must be Latin letters, digits, hyphen and underscore",
        "site_gone_root": "gone: {entry} - expected a path from the root, for example /old-page/",
        "site_gone_anchor": "gone: {entry} - the server never receives an anchor, remove the #...",
        "site_gone_param": "gone: {entry} - write the parameter as a single pair: /?p=* or /?p=12",
        "site_gone_star_value": "gone: {entry} - the asterisk replaces the whole value: /?p=*",
        "site_gone_star_end": "gone: {entry} - the asterisk is allowed only at the end: /wp/*",
        "site_exc_key": "exception key: expected SCH00N:<file>:<path>",
        "site_exc_reason": "the exception has no reason",
        "site_plugin_name": "plugins: invalid name {name}: Latin letters, digits, _ and -",
        "site_plugin_dup": "plugins: a plugin name is repeated",
        "site_exc_dup": "the exception is set twice: {key}",
        "site_i18n_shape": "i18n is a mapping of mappings: key, then language, then value",
        "site_i18n_value": "{key}_{lang}: wrong value type, expected {expected}",
        "site_heron_not_string": "the `heron` key is not a string: {value}",
        "site_heron_not_string_hint": 'put the requirement in quotes, for example: heron: ">=0.1,<0.2"',
        "site_i18n_lang": "{key}_{lang}: the language '{lang}' is not in site.languages {languages}",
        "site_form_sinks": "form {form} refers to sinks that are missing from sinks: {sinks}",
        "site_no_heron": "the required key `heron` with the engine version is missing",
        "site_no_heron_hint": 'add it as the first line, for example: heron: ">=0.1,<0.2"',
        "site_th_section_name": (
            "section {section} must be Latin letters, digits and hyphen, "
            "with an optional form after a colon"
        ),
        "site_th_section_kind": "section {section}: there is no form {kind}. Available: {kinds}",
        "site_th_section_dup": "sections are repeated",
        "site_th_relation_name": "the relation field name is Latin letters, digits, hyphen and underscore",
        "site_th_ratio": "the ratio {ratio} is written as 16:9",
        "site_th_widths": "widths are positive numbers",
        "site_th_name": "the theme name is Latin letters, digits, hyphen and underscore",
        "site_th_type_field_md": (
            "own field {name} of a type has no md: its value lives in the SEO block of the "
            "page under the field name; a place in markdown exists only for block fields"
        ),
        "site_th_type_field_reserved": (
            "own field {name} of a type is the name of an engine field: those are described by "
            'the engine (heron describe, "service fields"). Take another name. Taken: {names}'
        ),
        "site_th_fields_shape": (
            "the top-level fields of theme.yaml is a list of names of engine fields the "
            "templates read (fields: [date, updated]), and something else is written here: it "
            "looks like a description of block or page fields"
        ),
        "site_th_fields_shape_hint": (
            "block fields go into modules.<block>.fields or types.<type>.sections.<section>.fields, "
            "the own front matter fields of a page - into types.<type>.fields; keep the top-level "
            'fields a list of names or remove it. An example - `heron docs theme`, "Fields"'
        ),
        "site_th_module_name": "the module name {module} must be Latin letters, digits, hyphen and underscore",
        "site_th_hint_text": "{key}: a hint is a line of text",
        "site_th_field_name": "the field name {name} is lowercase Latin letters, digits and underscore, starting with a letter",
        "site_th_field_md": "field: there is no markdown place {md}. Available: {places}",
        "site_th_field_list": "field {name}: a list has item (the type of an item) or fields (the fields of an item), one of the two",
        "site_th_field_list_item": "field {name}: a list of lists is written with fields of the item",
        "site_th_field_not_list": "field {name}: only a list has item and fields, and the type is {type}",
        "site_th_field_enum": "field {name}: an enum needs a list of values",
        "site_th_field_values": "field {name}: only an enum has values, and the type is {type}",
        "site_th_field_image": "field {name}: only an image has ratio and min_width, and the type is {type}",
        "site_th_field_dup": "the field {name} is repeated",
        "site_th_field_ref": "{field}: the theme has no page type {ref}. Available: {known}",
        "site_th_module_kind": "module: there is no form {kind}. Available: {kinds}",
        "site_th_views_empty": "views: options needs at least one view",
        "site_th_view_name": "the view name {view} is Latin letters, digits, hyphen and underscore",
        "site_th_view_default": "views: the default view {view} is not in options. Available: {views}",
        "site_th_section_unused": "sections: the section {section} is not in uses ({uses})",
        "site_th_language": "hint language {lang}: a code like ru or pt-br",
        "site_th_children_type": "type {type}: children_type {children} - the theme has no such type. Available: {known}",
    },
}
