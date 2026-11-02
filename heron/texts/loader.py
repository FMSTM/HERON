"""Сообщения heron/contracts/loader.py и heron/contracts/frontmatter.py."""

TEXT = {
    "ru": {
        "loader_file_missing": "файл не найден",
        "loader_not_utf8": "файл не в кодировке UTF-8",
        "loader_not_utf8_hint": (
            "пересохраните файл в UTF-8: двоичный файл или другая кодировка читаться не будут"
        ),
        "loader_bad_yaml": "битый YAML: {problem}",
        "loader_bad_yaml_hint": "проверьте отступы и двоеточия - YAML не прощает табуляцию",
        "loader_empty": "файл пуст",
        "loader_not_mapping": "ожидался набор ключей, а в файле {type}",
        "loader_root": "<корень>",
        "loader_item": "{where}: {reason}",
        "loader_hint_missing": "поле обязательно, его нет в файле",
        "loader_hint_extra": "такого поля нет в контракте - опечатка в имени?",
        "loader_bad_value": "значение не подходит",
        "loader_value_error": "Value error, {reason}",
        "loader_invalid_one": "не проходит проверку:\n    {lines}",
        "loader_invalid_many": "не проходит проверку ({n}):\n    {lines}",
        "loader_fm_blank": "поле не может быть пустым",
        "loader_fm_slug": "слаг - латиница, цифры и дефис, без слешей и подчёркиваний",
        "loader_fm_old_url": "{url} - ожидается путь от корня, например /services/old/",
        "loader_fm_title_long": "title длиннее {max} знаков ({length})",
        "loader_fm_description_long": "description длиннее {max} знаков ({length})",
        "loader_fm_image_alt": "картинка задана, а image_alt нет",
        "loader_fm_title_h1_same": (
            "title и h1 совпадают: title пишется под выдачу, h1 под того, кто уже открыл"
        ),
    },
    "en": {
        "loader_file_missing": "file not found",
        "loader_not_utf8": "file is not UTF-8 encoded",
        "loader_not_utf8_hint": (
            "re-save the file as UTF-8: a binary file or another encoding cannot be read"
        ),
        "loader_bad_yaml": "broken YAML: {problem}",
        "loader_bad_yaml_hint": "check indentation and colons: YAML does not tolerate tabs",
        "loader_empty": "file is empty",
        "loader_not_mapping": "a set of keys was expected, but the file contains {type}",
        "loader_root": "<root>",
        "loader_item": "{where}: {reason}",
        "loader_hint_missing": "the field is required and is missing from the file",
        "loader_hint_extra": "the contract has no such field: a typo in the name?",
        "loader_bad_value": "the value does not fit",
        "loader_value_error": "{reason}",
        "loader_invalid_one": "failed validation:\n    {lines}",
        "loader_invalid_many": "failed validation ({n}):\n    {lines}",
        "loader_fm_blank": "the field must not be empty",
        "loader_fm_slug": "a slug is Latin letters, digits and hyphens, without slashes or underscores",
        "loader_fm_old_url": "{url} - a path from the root is expected, for example /services/old/",
        "loader_fm_title_long": "title is longer than {max} characters ({length})",
        "loader_fm_description_long": "description is longer than {max} characters ({length})",
        "loader_fm_image_alt": "an image is set but image_alt is not",
        "loader_fm_title_h1_same": (
            "title and h1 are the same: title is written for search results, "
            "h1 for the reader who has already opened the page"
        ),
    },
}
