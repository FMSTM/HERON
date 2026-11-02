"""Сообщения heron/core/tree.py и heron/core/resolver.py."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "tree_no_lang_tree": "нет дерева контента для языка {lang!r}",
        "tree_symlink_escape": "символическая ссылка ведёт за пределы content/",
        "tree_symlink_escape_hint": "положите сам файл в content/ вместо ссылки на него",
        "tree_bad_file_name": "недопустимое имя файла {name!r}",
        "tree_bad_file_name_hint": "слаг - латиница, цифры и дефис: getting-started.md",
        "tree_bad_url_segment": "недопустимый сегмент адреса {segment!r} (имя папки или slug раздела)",
        "tree_bad_url_segment_hint": (
            "папки - латиница, цифры и дефис; или задайте slug в _index.md раздела"
        ),
        "tree_url_taken": "адрес {url} уже занят файлом {source}",
        "tree_url_taken_hint": "переименуйте файл или задайте другой slug во фронтматтере",
        "tree_key_taken": "ключ страницы {page_key!r} ({lang}) уже у файла {source}",
        "tree_key_taken_hint": (
            "у страницы и раздела одного уровня не может быть одного имени; переименуйте файл"
        ),
        "tree_home_key": (
            "ключ home в подстановках schema означает главную: "
            "эта страница через pages.home недоступна - переименуйте файл"
        ),
        "tree_empty_lang": "в языке {lang!r} нет ни одной страницы",
        "tree_theme_local": "локальная",
        "tree_package": "пакет {value}",
        "tree_theme_load_failed": "тема {name!r} установлена, но не загружается: {error}",
        "tree_theme_not_found": "тема {name!r} не найдена ни локально, ни среди установленных",
        "tree_theme_not_found_hint": (
            "положите её в {folder}/ или установите пакет heron-theme-{name}"
        ),
        "tree_plugin_escape": "плагин {name!r} ведёт за пределы plugins/ через ссылку",
        "tree_plugin_escape_hint": "положите папку плагина в plugins/ вместо ссылки",
        "tree_plugin_no_register": "в плагине {name!r} нет функции register(hooks)",
        "tree_plugins_dir_escape": "папка {folder}/ ведёт за пределы сайта через ссылку",
        "tree_plugins_dir_escape_hint": (
            "сделайте {folder}/ настоящей папкой внутри сайта вместо ссылки"
        ),
        "tree_plugin_bad_name": "плагин {name!r}: недопустимое имя",
        "tree_plugin_bad_name_hint": "имя плагина - латиница, цифры, _ и -, не с дефиса",
        "tree_plugin_local": "локальный",
        "tree_plugin_load_failed": "плагин {name!r} упал при загрузке: {error}",
        "tree_plugin_not_installed": "плагин {name!r} не установлен и не найден в {folder}/",
        "tree_plugin_not_installed_hint": (
            "уберите из plugins или установите пакет, дающий {name!r}"
        ),
    },
    "en": {
        "tree_no_lang_tree": "no content tree for language {lang!r}",
        "tree_symlink_escape": "the symbolic link points outside content/",
        "tree_symlink_escape_hint": "put the file itself into content/ instead of a link to it",
        "tree_bad_file_name": "invalid file name {name!r}",
        "tree_bad_file_name_hint": "a slug is Latin letters, digits and hyphens: getting-started.md",
        "tree_bad_url_segment": "invalid address segment {segment!r} (a folder name or a section slug)",
        "tree_bad_url_segment_hint": (
            "folders are Latin letters, digits and hyphens; or set slug in the section's _index.md"
        ),
        "tree_url_taken": "address {url} is already taken by file {source}",
        "tree_url_taken_hint": "rename the file or set a different slug in the front matter",
        "tree_key_taken": "page key {page_key!r} ({lang}) already belongs to file {source}",
        "tree_key_taken_hint": (
            "a page and a section on the same level cannot share a name; rename the file"
        ),
        "tree_home_key": (
            "the key home in schema substitutions means the home page: "
            "this page is not reachable through pages.home, rename the file"
        ),
        "tree_empty_lang": "language {lang!r} has no pages",
        "tree_theme_local": "local",
        "tree_package": "package {value}",
        "tree_theme_load_failed": "theme {name!r} is installed but fails to load: {error}",
        "tree_theme_not_found": "theme {name!r} is found neither locally nor among installed packages",
        "tree_theme_not_found_hint": (
            "put it into {folder}/ or install the package heron-theme-{name}"
        ),
        "tree_plugin_escape": "plugin {name!r} points outside plugins/ through a link",
        "tree_plugin_escape_hint": "put the plugin folder into plugins/ instead of a link",
        "tree_plugin_no_register": "plugin {name!r} has no register(hooks) function",
        "tree_plugins_dir_escape": "folder {folder}/ points outside the site through a link",
        "tree_plugins_dir_escape_hint": (
            "make {folder}/ a real folder inside the site instead of a link"
        ),
        "tree_plugin_bad_name": "plugin {name!r}: invalid name",
        "tree_plugin_bad_name_hint": (
            "a plugin name is Latin letters, digits, _ and -, not starting with a hyphen"
        ),
        "tree_plugin_local": "local",
        "tree_plugin_load_failed": "plugin {name!r} failed to load: {error}",
        "tree_plugin_not_installed": "plugin {name!r} is not installed and not found in {folder}/",
        "tree_plugin_not_installed_hint": (
            "remove it from plugins or install the package that provides {name!r}"
        ),
    },
}
