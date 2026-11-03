"""Сообщения разбора блоков, хуков и справочников data/."""

TEXT = {
    "ru": {
        "blocks_unknown_class": "секция {section}: неизвестный класс {name}, определяю по содержимому",
        "blocks_stray_lines": "секция {section}: строки без разделителя «|» пропущены ({stray})",
        "blocks_class_mismatch": (
            "секция {section}: класс {name} не подходит к содержимому, вывожу прозой"
        ),
        "blocks_intro_long": (
            "вводный блок длиннее двух абзацев: третий и далее ({count}) не попадут в шаблон"
        ),
        "blocks_hook_unknown": "неизвестный хук {name}; доступны: {names}, block:<имя>",
        "blocks_hook_crash": "хук {hook} плагина {plugin} упал ({kind}): {detail}",
        "blocks_hook_crash_hint": "это ошибка плагина, а не сайта: исправьте плагин или отключите его в site.yaml",
        "blocks_symlink_outside": "символическая ссылка ведёт за пределы data/",
        "blocks_symlink_hint": "положите сам файл в data/ вместо ссылки на него",
        "blocks_data_unreadable": "справочник не читается: {error}",
    },
    "en": {
        "blocks_unknown_class": "section {section}: unknown class {name}, detecting it from the content",
        "blocks_stray_lines": 'section {section}: lines without the "|" separator were skipped ({stray})',
        "blocks_class_mismatch": (
            "section {section}: class {name} does not fit the content, rendering it as prose"
        ),
        "blocks_intro_long": (
            "the intro block is longer than two paragraphs: the third one onward ({count}) "
            "will not reach the template"
        ),
        "blocks_hook_unknown": "unknown hook {name}; available: {names}, block:<name>",
        "blocks_hook_crash": "hook {hook} of plugin {plugin} crashed ({kind}): {detail}",
        "blocks_hook_crash_hint": "this is a plugin error, not a site error: fix the plugin or disable it in site.yaml",
        "blocks_symlink_outside": "the symbolic link points outside data/",
        "blocks_symlink_hint": "put the file itself into data/ instead of linking to it",
        "blocks_data_unreadable": "the data file cannot be read: {error}",
    },
}
