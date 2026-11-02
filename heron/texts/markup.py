"""Сообщения разметки JSON-LD и проверки schema.org (modules/jsonld.py, schemaorg/validate.py)."""

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "markup_no_replacement": "нет замены, уберите",
        "markup_enum_member_hint": "это значение перечисления {enum}, не тип",
        "markup_got_number": "число",
        "markup_got_string": "строка",
        "markup_json_unparsable": "разметка страницы не разбирается как JSON: {error}",
        "markup_theme_expects": "тема ждёт разметку {want}, а в графе её нет",
        "markup_theme_expects_hint": "проверьте блок schema в site.yaml и во фронтматтере страницы",
        "markup_no_entity": "нет сквозного узла сайта",
        "markup_entity_empty": "в сквозном узле объявлены адрес или координаты, а значения пустые",
        "markup_entity_empty_hint": "заполните в site.yaml то, на что ссылается schema.entity: например contact.city и contact.geo",
        "markup_money": "в разметке есть поля про деньги: {fields}",
        "markup_money_hint": "сайт не публикует цены (seo.allow_prices: false) — уберите эти поля из блока schema или разрешите цены в site.yaml",
    },
    "en": {
        "markup_no_replacement": "no replacement, remove it",
        "markup_enum_member_hint": "this is a value of the enumeration {enum}, not a type",
        "markup_got_number": "number",
        "markup_got_string": "string",
        "markup_json_unparsable": "page markup does not parse as JSON: {error}",
        "markup_theme_expects": "the theme expects {want} markup, but the graph has none",
        "markup_theme_expects_hint": "check the schema block in site.yaml and in the page front matter",
        "markup_no_entity": "the site-wide node is missing",
        "markup_entity_empty": "the site-wide node declares an address or coordinates, but the values are empty",
        "markup_entity_empty_hint": "fill in what schema.entity refers to in site.yaml, for example contact.city and contact.geo",
        "markup_money": "the markup has money fields: {fields}",
        "markup_money_hint": "the site does not publish prices (seo.allow_prices: false); remove these fields from the schema block or allow prices in site.yaml",
    },
}
