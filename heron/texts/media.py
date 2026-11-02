"""Сообщения ресурсов и нарезки картинок (core/media.py)."""

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "media_both_folders": "в сайте есть и {media}/, и {legacy}/ — движок не знает, какая настоящая",
        "media_both_folders_hint": "перенесите файлы в {media}/ и удалите {legacy}/",
        "media_same_address": "static/{media} и {media}/ дают один адрес: {files}",
        "media_same_address_hint": "держите ресурсы в одном месте: {media}/",
        "media_two_folders": (
            "в /{media}/ отдаются две папки сразу: {media}/ и static/{media} — "
            "перенесите содержимое второй в первую"
        ),
        "media_legacy_folder": (
            "папка ресурсов называется {legacy}/ — переименуйте в {media}/, туда же ложится видео"
        ),
        "media_owner_more": "{page} и ещё {count}",
        "media_heavy": "{src} весит {megabytes} МБ",
        "media_no_poster": "у видео нет постера",
        "media_no_poster_hint": (
            "добавьте video_poster: без него браузер грузит ролик ради первого кадра"
        ),
        "media_no_file": "нет файла {src}",
        "media_no_file_hint": "поправьте путь во фронтматтере или положите картинку",
        "media_small_cover": "обложка меньше {width} px: {src}",
        "media_path_escapes": "путь {src!r} выходит за пределы {media}/",
        "media_path_escapes_hint": (
            "ресурсы берутся только из папки media/; уберите `..` и символические ссылки наружу"
        ),
        "media_cache_is_link": "кэш — ссылка, а не папка: {folder}",
        "media_cache_is_link_hint": "удалите эту ссылку — папка кэша пересоздастся при сборке",
        "media_cache_escapes": "кэш нарезок ведёт за свои пределы через ссылку: {folder}",
        "media_cache_rebuild_hint": "удалите папку .heron-cache — она пересоздастся при сборке",
        "media_slice_is_dir": "на месте нарезки в кэше — папка: {path}",
        "media_missing_on_disk": "картинки {src} нет на диске",
        "media_missing_on_disk_hint": "битая картинка в проде дороже упавшей сборки",
        "media_slice_clash": "{other} и {src} дают одинаковые имена нарезок: {name}",
        "media_slice_clash_hint": (
            "имена нарезок берутся от имени файла без расширения — переименуйте один из мастеров"
        ),
        "media_placed_slices": "нарезка {src}",
        "media_placed_file": "файл {src}",
    },
    "en": {
        "media_both_folders": "the site has both {media}/ and {legacy}/: the engine cannot tell which one is real",
        "media_both_folders_hint": "move the files into {media}/ and delete {legacy}/",
        "media_same_address": "static/{media} and {media}/ give the same address: {files}",
        "media_same_address_hint": "keep the assets in one place: {media}/",
        "media_two_folders": (
            "two folders are served under /{media}/ at once: {media}/ and static/{media}. "
            "Move the contents of the second one into the first"
        ),
        "media_legacy_folder": (
            "the assets folder is called {legacy}/: rename it to {media}/, video goes there too"
        ),
        "media_owner_more": "{page} and {count} more",
        "media_heavy": "{src} weighs {megabytes} MB",
        "media_no_poster": "the video has no poster",
        "media_no_poster_hint": (
            "add video_poster: without it the browser loads the whole clip just for the first frame"
        ),
        "media_no_file": "no file {src}",
        "media_no_file_hint": "fix the path in the frontmatter or put the image in place",
        "media_small_cover": "the cover is narrower than {width} px: {src}",
        "media_path_escapes": "path {src!r} goes outside {media}/",
        "media_path_escapes_hint": (
            "assets are read only from the media/ folder; remove `..` and symlinks pointing outside"
        ),
        "media_cache_is_link": "the cache is a link, not a folder: {folder}",
        "media_cache_is_link_hint": "delete this link: the cache folder is recreated on build",
        "media_cache_escapes": "the rendition cache leads outside itself through a link: {folder}",
        "media_cache_rebuild_hint": "delete the .heron-cache folder: it is recreated on build",
        "media_slice_is_dir": "a folder sits where a rendition should be in the cache: {path}",
        "media_missing_on_disk": "image {src} is not on disk",
        "media_missing_on_disk_hint": "a broken image in production costs more than a failed build",
        "media_slice_clash": "{other} and {src} produce the same rendition names: {name}",
        "media_slice_clash_hint": (
            "rendition names come from the file name without the extension: rename one of the masters"
        ),
        "media_placed_slices": "renditions of {src}",
        "media_placed_file": "file {src}",
    },
}
