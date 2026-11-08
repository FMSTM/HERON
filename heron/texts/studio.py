"""Сообщения heron/studio/: студия в браузере (heron studio, page add --web)."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "studio_open": (
            "Студия открыта: {url}  - откройте адрес целиком, с ключом после «#». Ctrl+C - выход."
        ),
        "studio_open_on": "Сразу на объекте: {kind} {key}.",
        "studio_preview_self": (
            "Просмотр страниц и справку темы студия откроет сама (порт {preview}) - "
            "больше ничего делать не нужно."
        ),
        "studio_container": (
            "HERON работает в контейнере: откройте адрес на своём компьютере. "
            "В docker run оба порта публикуются только на эту машину: "
            "-p 127.0.0.1:{port}:{port} -p 127.0.0.1:{preview}:{preview}. "
            "Опубликовали на компьютере другие номера, со сдвигом на одно и то же число - "
            "замените в адресе {port} на свой номер, просмотр найдёт свой порт сам."
        ),
        "studio_confirm_pending": (
            "{langs} уйдут из публикации до перевода: новый блок там ещё не переведён "
            "(translation: pending) - продолжить?"
        ),
        "studio_confirm_drops": (
            "{lines}\n\nЧтобы страницы остались в prod, отмените и заполните поля раздела на "
            "этих языках. Записать раздел без перевода?"
        ),
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
        "studio_preview_self": (
            "The studio opens the page preview and the theme reference by itself "
            "(port {preview}) - nothing else to do."
        ),
        "studio_container": (
            "HERON runs in a container: open the address on your computer. "
            "Both ports are published in docker run to this machine only: "
            "-p 127.0.0.1:{port}:{port} -p 127.0.0.1:{preview}:{preview}. "
            "Published other numbers on the computer, shifted by the same amount - "
            "put your number instead of {port} in the address, the preview finds its port itself."
        ),
        "studio_confirm_pending": (
            "{langs} will leave publication until translated: the new block is not translated "
            "there yet (translation: pending) - continue?"
        ),
        "studio_confirm_drops": (
            "{lines}\n\nTo keep the pages in prod, cancel and fill in the section fields in "
            "these languages. Write the section without a translation?"
        ),
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
