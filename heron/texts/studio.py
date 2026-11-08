"""Сообщения heron/studio/: студия в браузере (heron studio, page add --web)."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "studio_open": (
            "Студия открыта: {url}  - откройте адрес целиком, с ключом после «#». Ctrl+C - выход."
        ),
        "studio_open_on": "Сразу на объекте: {kind} {key}.",
        "studio_bad_request": "запрос студии без нужного значения или с неверным: {field}",
        "studio_section_values": (
            "блок формы {kind} движок узнаёт по содержимому: заполните хотя бы первый пункт"
        ),
        "studio_invalid_hint": (
            "поправьте эти поля в форме - они подсвечены; правила - те же, что у heron check"
        ),
        "studio_upload_type": "файл {name}: в media/ студия кладёт только картинки ({kinds})",
        "studio_upload_bad": "файл {name} не читается как картинка своего типа",
        "studio_upload_svg": (
            "файл {name}: в SVG есть скрипт или обработчик событий, такую картинку студия не кладёт"
        ),
        "studio_upload_large": "картинка больше {mb} МБ: уменьшите её перед загрузкой",
    },
    "en": {
        "studio_open": (
            "The studio is open: {url}  - open the whole address, with the key after “#”. "
            "Ctrl+C to stop."
        ),
        "studio_open_on": "Opened right on: {kind} {key}.",
        "studio_bad_request": "a studio request lacks a needed value or has a wrong one: {field}",
        "studio_section_values": (
            "the engine recognises a {kind} block by its content: fill in at least the first item"
        ),
        "studio_invalid_hint": (
            "fix these fields in the form - they are highlighted; the rules are those of "
            "heron check"
        ),
        "studio_upload_type": "file {name}: the studio puts only pictures into media/ ({kinds})",
        "studio_upload_bad": "file {name} does not read as a picture of its type",
        "studio_upload_svg": (
            "file {name}: the SVG holds a script or an event handler, the studio does not put "
            "such a picture"
        ),
        "studio_upload_large": "the picture is larger than {mb} MB: make it smaller first",
    },
}
