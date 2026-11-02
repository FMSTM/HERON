"""Сообщения записи результата сборки и границ файловых операций."""

TEXT = {
    "ru": {
        "output_reserved_name": "{owner}: {clean} — служебное имя сборки, его пишет сам движок",
        "output_rename_file": "переименуйте файл",
        "output_path_outside": "{owner}: выходной путь {rel} вне папки сборки",
        "output_conflict": "два источника дают один файл сборки {clean}: {held} и {owner}",
        "output_conflict_override_hint": (
            "переименуйте один из них; если {owner} должен заменить "
            "сгенерированный файл, перечислите {clean} в build.overrides"
        ),
        "output_conflict_hint": "переименуйте один из них",
        "output_file_and_folder": "{folder} — и файл ({file_owner}), и папка для {rel} ({owner})",
        "output_rename_either": "переименуйте файл или папку",
        "output_override_unused": (
            "build.overrides: {rel} ничего не подменяет — "
            "нет ни генерированного файла, ни файла в static/"
        ),
        "output_not_utf8": "не UTF-8 (байт {byte})",
        "output_unreadable": "не читается: {reason}",
        "output_file_unreadable": "{rel} из {owner}: {reason}",
        "output_utf8_hint": (
            "сохраните файл в UTF-8 и дайте его прочитать — сборка без проверки "
            "этого файла не выходит"
        ),
        "output_cache_link": "файл кэша стал ссылкой: {source}",
        "output_cache_link_hint": "удалите папку .heron-cache — она пересоздастся при сборке",
        "output_cannot_create": "не удалось создать {path}: {reason}",
        "output_cannot_create_hint": (
            "папка над --out должна быть доступна для записи: "
            "там живут .heron-cache и .<dist>.heron-lock"
        ),
        "output_foreign_file": "в папке сборки чужой файл на месте {rel}",
        "output_foreign_blocker": "в папке сборки чужой файл мешает записать {rel}: {blocker}",
        "output_foreign_hint": "его положил не движок; уберите его или соберите в чистую папку",
        "output_paths_escapes_root": "путь {rel} выходит за пределы {root}/",
        "output_paths_escapes_root_hint": (
            "файлы сайта берутся только из его собственных папок; "
            "уберите `..` и символические ссылки наружу"
        ),
        "output_paths_out_outside": "результат {rel} оказался бы вне папки сборки",
        "output_paths_out_outside_hint": "имя выходного файла должно быть относительным путём без `..`",
        "output_paths_out_link": "результат {clean} ведёт за пределы папки сборки через ссылку",
        "output_paths_out_link_hint": "уберите символические ссылки из папки сборки",
        "output_paths_site_escapes": "путь {rel} выходит за пределы папки сайта",
        "output_paths_site_link": "{shown} ведёт за пределы папки сайта через символическую ссылку",
        "output_paths_site_link_hint": (
            "замените ссылку настоящим файлом или папкой — "
            "движок не пишет и не удаляет файлы вне папки сайта"
        ),
        "output_paths_unreadable": "не читается {path}: {reason}",
        "output_paths_unreadable_hint": "проверьте права и диск: без этой папки сборка вышла бы неполной",
        "output_paths_files_link": "символическая ссылка {link} ведёт за пределы папки",
        "output_paths_files_link_hint": "положите сам файл в папку сайта вместо ссылки на него",
        "output_paths_folder_link": "папка {folder}/ — ссылка за пределы {root}/",
        "output_paths_folder_link_hint": "положите саму папку на место ссылки на неё",
        "output_paths_layout_hint": (
            "укажите --out в отдельную папку: не корень сайта, не папку исходников и не кэш"
        ),
        "output_paths_layout_contains": "папка сборки совпадает с папкой сайта или содержит её",
        "output_paths_layout_dist_overlap": "папка сборки пересекается с исходниками: {folder}/",
        "output_paths_layout_cache_overlap": "кэш пересекается с исходниками: {folder}/",
        "output_paths_layout_cache_dist": "кэш и папка сборки пересекаются",
    },
    "en": {
        "output_reserved_name": "{owner}: {clean} is a reserved build name, the engine writes it itself",
        "output_rename_file": "rename the file",
        "output_path_outside": "{owner}: output path {rel} is outside the build folder",
        "output_conflict": "two sources give one build file {clean}: {held} and {owner}",
        "output_conflict_override_hint": (
            "rename one of them; if {owner} must replace the generated file, "
            "list {clean} in build.overrides"
        ),
        "output_conflict_hint": "rename one of them",
        "output_file_and_folder": "{folder} is both a file ({file_owner}) and a folder for {rel} ({owner})",
        "output_rename_either": "rename the file or the folder",
        "output_override_unused": (
            "build.overrides: {rel} replaces nothing - "
            "there is neither a generated file nor a file in static/"
        ),
        "output_not_utf8": "not UTF-8 (byte {byte})",
        "output_unreadable": "cannot be read: {reason}",
        "output_file_unreadable": "{rel} from {owner}: {reason}",
        "output_utf8_hint": (
            "save the file as UTF-8 and make it readable: a build without checking "
            "this file does not finish"
        ),
        "output_cache_link": "a cache file became a link: {source}",
        "output_cache_link_hint": "delete the .heron-cache folder, it is recreated on build",
        "output_cannot_create": "could not create {path}: {reason}",
        "output_cannot_create_hint": (
            "the folder above --out must be writable: "
            ".heron-cache and .<dist>.heron-lock live there"
        ),
        "output_foreign_file": "a foreign file sits in the build folder at {rel}",
        "output_foreign_blocker": "a foreign file in the build folder prevents writing {rel}: {blocker}",
        "output_foreign_hint": "the engine did not put it there; remove it or build into a clean folder",
        "output_paths_escapes_root": "path {rel} goes outside {root}/",
        "output_paths_escapes_root_hint": (
            "site files are taken only from its own folders; "
            "remove `..` and symbolic links pointing outside"
        ),
        "output_paths_out_outside": "output {rel} would end up outside the build folder",
        "output_paths_out_outside_hint": "the output file name must be a relative path without `..`",
        "output_paths_out_link": "output {clean} leads outside the build folder through a link",
        "output_paths_out_link_hint": "remove symbolic links from the build folder",
        "output_paths_site_escapes": "path {rel} goes outside the site folder",
        "output_paths_site_link": "{shown} leads outside the site folder through a symbolic link",
        "output_paths_site_link_hint": (
            "replace the link with a real file or folder: "
            "the engine does not write or delete files outside the site folder"
        ),
        "output_paths_unreadable": "cannot read {path}: {reason}",
        "output_paths_unreadable_hint": "check permissions and disk: without this folder the build would be incomplete",
        "output_paths_files_link": "symbolic link {link} leads outside the folder",
        "output_paths_files_link_hint": "put the file itself into the site folder instead of linking to it",
        "output_paths_folder_link": "folder {folder}/ is a link outside {root}/",
        "output_paths_folder_link_hint": "put the folder itself in place of the link to it",
        "output_paths_layout_hint": (
            "point --out to a separate folder: not the site root, not a source folder and not the cache"
        ),
        "output_paths_layout_contains": "the build folder is the same as the site folder or contains it",
        "output_paths_layout_dist_overlap": "the build folder overlaps the sources: {folder}/",
        "output_paths_layout_cache_overlap": "the cache overlaps the sources: {folder}/",
        "output_paths_layout_cache_dist": "the cache and the build folder overlap",
    },
}
