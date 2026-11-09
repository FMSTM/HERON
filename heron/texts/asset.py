"""Сообщения версий файлов темы и ресурсов: asset(), копии с хешем (core/versions.py)."""

TEXT = {
    "ru": {
        "asset_unknown": "asset({path}): такого файла нет ни в assets/ темы, ни в media/ сайта",
        "asset_unknown_hint": "путь от папки assets/ темы - asset('site.css'), asset('fonts/a.woff2') - или от корня сайта для ресурсов - asset('media/logo.svg'); проверьте имя и регистр букв",
        "asset_external": "asset({path}): чужой адрес, asset() берёт только файлы сайта",
        "asset_css_cycle": "стили импортируют друг друга по кругу: {loop}; ссылка, замыкающая круг, остаётся без хеша в имени и кэшируется как файл без версии",
        "asset_hash_like_name": "{rel}: имя уже выглядит как имя с хешем (.<10 знаков hex>.), nginx отдаёт его на год с immutable; если содержимое под этим именем меняется - переименуйте файл",
        "asset_changed": "{rel}: в сборке не тот файл, хеш которого шаблон получил до рендера",
        "asset_changed_hint": "файл подменили после рендера (плагин on_generate или static/ с тем же путём); оставьте один источник этого файла",
    },
    "en": {
        "asset_unknown": "asset({path}): there is no such file in the theme assets/ or in the site media/",
        "asset_unknown_hint": "a path from the theme assets/ folder - asset('site.css'), asset('fonts/a.woff2') - or from the site root for resources - asset('media/logo.svg'); check the name and the letter case",
        "asset_external": "asset({path}): an external address, asset() takes only site files",
        "asset_css_cycle": "styles import each other in a circle: {loop}; the link that closes the circle stays without a hash in the name and is cached as a file without a version",
        "asset_hash_like_name": "{rel}: the name already looks like a hashed name (.<10 hex chars>.), nginx serves it for a year with immutable; if the content under this name changes, rename the file",
        "asset_changed": "{rel}: the build has a different file than the one whose hash the template got before rendering",
        "asset_changed_hint": "the file was replaced after rendering (an on_generate plugin or static/ with the same path); keep one source of this file",
    },
}
