"""Причины отказа проверки ответов конфигуратора — на языке сайта (ru, en).

Проверка ответов одна для страницы конфигуратора и для `heron setup --answers`, а
читает её человек на своём языке. Поэтому валидаторы `answers.py` бросают не
готовую строку, а `Reason`: ключ и поля. Текст собирается при показе, на
языке запуска — `plain(error, lang)`.

Строка `Reason` по умолчанию — английская: её видит pydantic, и сравнения
вида `match=` в тестах и в чужом коде остаются прежними. Ошибки самого
pydantic (нет поля, лишний ключ, не тот тип) переводятся по `type`; на
английском остаётся их собственный текст.

Наборы ключей ru и en совпадают, это проверяет tests/test_setup.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

LANGS = ("ru", "en")

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        # сайт
        "domain_bad": "{value}: домен без схемы и слешей, например example.com",
        "languages_none": "нужен хотя бы один язык",
        "languages_bad": "не код языка: {codes} (ожидается en, de, pt-br)",
        "languages_repeat": "языки повторяются",
        "default_lang_missing": (
            "основного языка {value} нет в языках сайта ({langs}): допишите его в "
            "site.languages или выберите site.default_lang из них"
        ),
        "preview_same": "служебный домен должен отличаться от рабочего",
        # связь
        "contact_empty": "у канала связи нет значения",
        "purpose_bad": "назначение {value}: одно из {names}",
        "phone_bad": "{value} не похоже на телефон: +00 000 000 00 00",
        "email_bad": "{value} не похоже на адрес почты",
        "link_needed": "{kind}: нужна ссылка, https://…",
        # о сайте
        "direction_unknown": "сферы деятельности {value} нет в классификаторе",
        "spec_unknown": "специализации {value} нет в классификаторе",
        "spec_other": "специализация {value} не относится к сфере {direction}",
        "type_unknown": "типа {value} нет в списке; возьмите ближайший более общий",
        "fields_unknown": "поля, которые для типа {kind} не спрашиваются: {names}",
        # счётчики
        "ga4_bad": "Google Analytics {value}: ожидается G-XXXXXXX",
        "gtm_bad": "Tag Manager {value}: ожидается GTM-XXXXXX",
        "metrika_bad": "Яндекс Метрика {value}: только цифры",
        # кэш браузера
        "cache_bad": (
            "nginx.cache.{field} {value}: число секунд или число с единицей s, m, h, d, w, y - "
            "например 3600, 12h, 1d, 7d, 1y"
        ),
        # заголовки и журнал сервера
        "hsts_bad": (
            "nginx.hsts.max_age {value}: число секунд или число с единицей s, m, h, d, w, y - "
            "например 180d, 1y; 0 - заголовок выключен"
        ),
        "hsts_preload": (
            "nginx.hsts: предзагрузка (preload) при сроке {value} - по правилам hstspreload.org "
            "нужны срок не меньше 1y и поддомены (subdomains: true)"
        ),
        "permission_unknown": (
            "nginx.permissions: возможности {name} нет в списке известных браузеру; "
            "похожие: {close}"
        ),
        "permission_bad": (
            "nginx.permissions.{name} {value}: ожидается none, self, * или источники "
            "https://example.com (можно вместе с self)"
        ),
        "log_ip_bad": "nginx.log_ip {value}: ожидается masked, full или off",
        # адреса
        "urls_bad": (
            "urls.trailing_slash {value}: ожидается 'always' (со слешем, как было) "
            "или 'never' (без слеша)"
        ),
        # публикация
        "control_chars": "{field}: служебные символы (перевод строки, NUL, ...) недопустимы",
        "helpers_unknown": "helpers: неизвестные {names}",
        "engine_bad": (
            "engine {value}: prod, beta или версия вида 0.1.0, "
            "можно с закреплением: prod@sha256:<digest>"
        ),
        "repo_bad": "репозиторий {value}: владелец/имя, например you/my-site",
        "docker_name_bad": "{value}: строчные латинские буквы, цифры, точки, дефисы",
        "dockerhub_needs": "для Docker Hub нужны имя пользователя и имя образа",
        "server_needed": "для выкладки статики на сервер нужен адрес сервера",
        "server_bad": "сервер {value}: user@host или host",
        "path_bad": "папка на сервере - абсолютный путь без .. из букв, цифр и . _ - + ~ @",
        "branch_bad": "ветка {value}: буквы, цифры и . _ - + /, например main или release/v1",
        # ответы целиком
        "note_lang": "заметка для ИИ на языке, которого нет у сайта: {codes}",
        "field_lang": "{name}: языка нет у сайта: {codes}",
        "not_number": "{value} - не число",
        "country_bad": "страна {value}: двухбуквенный код, например AT",
        "hours_bad": (
            "часы {value}: ожидается 'Пн-Пт 09:00-18:00' в форме schema.org: Mo-Fr 09:00-18:00"
        ),
        "enum_bad": "значение {value} не из списка {enum}",
        "subtype_bad": "тип {value} не подходит: нужен подвид {of} из списка",
        "bool_bad": "{value}: ожидается да или нет (true или false)",
        "answers_mapping": "ответы: ожидается словарь «ключ: значение»",
        "no_site": "в {root} нет {name}: сначала создайте сайт (heron new)",
        # проверка разметки при сохранении
        "reason_required": "для исключения нужна причина: коротко, почему оставляете как есть",
        "type_not_dropped": "тип не удаляется, исправьте его: выберите другой тип сайта",
        "schema_findings": "разметка не пройдёт проверку: {keys}",
        "schema_mode_bad": "режим {value}: check, drop или except",
        "drop_field": "{label}: {value}",
        "drop_contacts": "Связь: {value}",
        "drop_direction": "Сфера деятельности: {value}",
        "drop_specialization": "Специализация: {value}",
        "drop_type": "Тип сайта: {value}",
        "drop_path": "site.yaml: {path}",
        # ошибки pydantic по type
        "py_missing": "обязательное поле не заполнено",
        "py_extra_forbidden": "неизвестный ключ",
        "py_literal_error": "одно из: {expected}",
        "py_string_type": "ожидается строка",
        "py_bool": "ожидается true или false",
        "py_int": "ожидается целое число",
        "py_float": "ожидается число",
        "py_list_type": "ожидается список",
        "py_dict": "ожидается словарь «ключ: значение»",
        "py_other": "недопустимое значение ({type})",
        # сервер конфигуратора
        "srv_local_only": "только с этой машины",
        "srv_token": "откройте адрес, который напечатан в терминале",
        "srv_not_found": "нет такого адреса",
        "srv_too_large": "слишком большой запрос",
        "srv_port": "не открыть конфигуратор на {host}:{port}: {reason}",
        "srv_port_hint": (
            "порт занят другой программой: возьмите другой, --port {next} "
            "(порт просмотра по умолчанию - следующий за ним; в докере опубликуйте те же "
            "номера, команду с ними движок напечатает при запуске)"
        ),
        "srv_preview_port": "не открыть просмотр студии на {host}:{port}: {reason}",
        "srv_preview_hint": (
            "этот порт - для просмотра и справки темы, он занят другой программой: "
            "возьмите другой флагом --preview-port {next}"
        ),
        "srv_preview_range": "порт просмотра {port} вне диапазона 1-65535",
        "srv_preview_range_hint": (
            "у --port 65535 нет следующего порта: задайте --port меньше или --preview-port"
        ),
        "srv_preview_same": (
            "--preview-port {port} совпадает с --port: просмотру нужен свой порт, "
            "другой источник браузера"
        ),
    },
    "en": {
        "domain_bad": "{value}: domain without scheme and slashes, e.g. example.com",
        "languages_none": "at least one language is needed",
        "languages_bad": "not a language code: {codes} (expected en, de, pt-br)",
        "languages_repeat": "languages repeat",
        "default_lang_missing": (
            "main language {value} is not among the site languages ({langs}): add it to "
            "site.languages or pick site.default_lang from them"
        ),
        "preview_same": "the service domain must differ from the working one",
        "contact_empty": "a contact needs a value",
        "purpose_bad": "purpose {value}: one of {names}",
        "phone_bad": "{value} does not look like a phone: +00 000 000 00 00",
        "email_bad": "{value} does not look like an email",
        "link_needed": "{kind}: a link is expected, https://…",
        "direction_unknown": "field of work {value} is not in the classifier",
        "spec_unknown": "specialization {value} is not in the classifier",
        "spec_other": "specialization {value} is not in {direction}",
        "type_unknown": "type {value} is not in the list; take the nearest broader one",
        "fields_unknown": "fields not asked for type {kind}: {names}",
        "ga4_bad": "Google Analytics {value}: expected G-XXXXXXX",
        "gtm_bad": "Tag Manager {value}: expected GTM-XXXXXX",
        "metrika_bad": "Yandex Metrica {value}: digits only",
        "cache_bad": (
            "nginx.cache.{field} {value}: a number of seconds or a number with a unit "
            "s, m, h, d, w, y - for example 3600, 12h, 1d, 7d, 1y"
        ),
        "hsts_bad": (
            "nginx.hsts.max_age {value}: a number of seconds or a number with a unit "
            "s, m, h, d, w, y - for example 180d, 1y; 0 turns the header off"
        ),
        "hsts_preload": (
            "nginx.hsts: preload with the time {value} - by the hstspreload.org rules it needs "
            "a time of at least 1y and subdomains (subdomains: true)"
        ),
        "permission_unknown": (
            "nginx.permissions: the feature {name} is not among those browsers know; "
            "similar: {close}"
        ),
        "permission_bad": (
            "nginx.permissions.{name} {value}: expected none, self, * or origins "
            "https://example.com (self may go with them)"
        ),
        "log_ip_bad": "nginx.log_ip {value}: expected masked, full or off",
        "urls_bad": (
            "urls.trailing_slash {value}: expected 'always' (with a slash, as before) "
            "or 'never' (without)"
        ),
        "control_chars": "{field}: control characters (newline, NUL, ...) are not allowed",
        "helpers_unknown": "helpers: unknown {names}",
        "engine_bad": (
            "engine {value}: prod, beta, a version like 0.1.0, "
            "optionally pinned: prod@sha256:<digest>"
        ),
        "repo_bad": "repository {value}: owner/name, e.g. you/my-site",
        "docker_name_bad": "{value}: lowercase letters, digits, dots, dashes",
        "dockerhub_needs": "Docker Hub needs your user name and the image name",
        "server_needed": "static files to a server need the server address",
        "server_bad": "server {value}: user@host or host",
        "path_bad": (
            "the folder on the server is an absolute path without .. - "
            "letters, digits and . _ - + ~ @"
        ),
        "branch_bad": "branch {value}: letters, digits and . _ - + /, like main or release/v1",
        "note_lang": "note for AI in a language the site does not have: {codes}",
        "field_lang": "{name}: language not on the site: {codes}",
        "not_number": "{value} is not a number",
        "country_bad": "country {value}: a two-letter code, e.g. AT",
        "hours_bad": "hours {value}: expected 'Mo-Fr 09:00-18:00' in schema.org form",
        "enum_bad": "value {value} is not in the list {enum}",
        "subtype_bad": "type {value} does not fit: a subtype of {of} from the list is required",
        "bool_bad": "{value}: expected true or false",
        "answers_mapping": "answers: a mapping is expected",
        "no_site": "no {name} in {root}: create the site first (heron new)",
        "reason_required": "an exception needs a reason: briefly, why you keep it as it is",
        "type_not_dropped": "the type cannot be removed, please fix it: pick another site type",
        "schema_findings": "the markup will not pass the check: {keys}",
        "schema_mode_bad": "mode {value}: check, drop or except",
        "drop_field": "{label}: {value}",
        "drop_contacts": "Contact: {value}",
        "drop_direction": "Field of work: {value}",
        "drop_specialization": "Specialization: {value}",
        "drop_type": "Site type: {value}",
        "drop_path": "site.yaml: {path}",
        "py_missing": "Field required",
        "py_extra_forbidden": "Extra inputs are not permitted",
        "py_literal_error": "Input should be {expected}",
        "py_string_type": "Input should be a valid string",
        "py_bool": "Input should be a valid boolean",
        "py_int": "Input should be a valid integer",
        "py_float": "Input should be a valid number",
        "py_list_type": "Input should be a valid list",
        "py_dict": "Input should be a valid dictionary",
        "py_other": "invalid value ({type})",
        "srv_local_only": "local only",
        "srv_token": "open the address printed in the terminal",
        "srv_not_found": "not found",
        "srv_too_large": "too large",
        "srv_port": "cannot open the configurator on {host}:{port}: {reason}",
        "srv_port_hint": (
            "the port is used by another program: take another one, --port {next} "
            "(the preview port defaults to the next one; in docker publish the same "
            "numbers, the engine prints the command with them on start)"
        ),
        "srv_preview_port": "cannot open the studio preview on {host}:{port}: {reason}",
        "srv_preview_hint": (
            "this port is for the preview and the theme reference, another program uses it: "
            "take another one with --preview-port {next}"
        ),
        "srv_preview_range": "preview port {port} is out of the range 1-65535",
        "srv_preview_range_hint": (
            "--port 65535 has no next port: give a smaller --port or a --preview-port"
        ),
        "srv_preview_same": (
            "--preview-port {port} is the same as --port: the preview needs a port of its own, "
            "a separate browser origin"
        ),
    },
}

# type ошибки pydantic → ключ: родственные типы делят одну фразу
PYDANTIC = {
    "missing": "py_missing",
    "extra_forbidden": "py_extra_forbidden",
    "literal_error": "py_literal_error",
    "string_type": "py_string_type",
    "bool_type": "py_bool",
    "bool_parsing": "py_bool",
    "int_type": "py_int",
    "int_parsing": "py_int",
    "int_from_float": "py_int",
    "float_type": "py_float",
    "float_parsing": "py_float",
    "list_type": "py_list_type",
    "dict_type": "py_dict",
    "model_type": "py_dict",
    "model_attributes_type": "py_dict",
}


def say(lang: str, key: str, **fields: Any) -> str:
    table = TEXT[lang if lang in LANGS else "en"]
    return table[key].format(**fields)


class Reason(ValueError):
    """Отказ проверки: ключ из `TEXT` и поля. `str()` — английский текст."""

    def __init__(self, key: str, **fields: Any) -> None:
        self.key = key
        self.fields = fields
        super().__init__(say("en", key, **fields))

    def text(self, lang: str) -> str:
        return say(lang, self.key, **self.fields)


def run_lang(root: Path | str | None = None, flag: str | None = None) -> str:
    """Язык запуска, когда его не передали: как у командной строки.

    `--notes` и папка сайта — из параметров текущей команды click, если она
    идёт (`heron setup` зовёт проверку, не передавая язык); затем
    HERON_NOTES, затем `build.notes` из `site.yaml`; иначе en. Тот же порядок,
    что у `resolve_notes` для сообщений терминала.
    """
    import click

    from heron.scaffold import ctx_notes, resolve_notes

    flag = flag or ctx_notes()
    ctx = click.get_current_context(silent=True)
    if ctx is not None and root is None and ctx.params.get("path") is not None:
        root = ctx.params["path"]
    site_yaml = Path(root) / "site.yaml" if root is not None else None
    try:
        return resolve_notes(flag, site_yaml)
    except ValueError:
        return "en"


def _item(item: dict[str, Any], lang: str) -> str:
    """Одна ошибка pydantic: своя причина — на языке, чужая — по type."""
    found = (item.get("ctx") or {}).get("error")
    if isinstance(found, Reason):
        return found.text(lang)
    message = str(item.get("msg", "")).removeprefix("Value error, ")
    if lang == "en" or item.get("type") == "value_error":
        return message
    key = PYDANTIC.get(str(item.get("type")), "py_other")
    # перечень pydantic: "'keep', 'starter' or 'file'" — значения токены, союз переводим
    expected = str((item.get("ctx") or {}).get("expected", ""))
    if lang == "ru":
        expected = expected.replace(" or ", " или ")
    return say(lang, key, expected=expected, type=item.get("type"))


def plain(error: ValueError, lang: str | None = None) -> str:
    """Ошибка проверки ответов человеческим языком: поле и что с ним не так."""
    lang = lang if lang in LANGS else run_lang()
    if isinstance(error, Reason):
        return error.text(lang)
    found = getattr(error, "findings", None)
    if isinstance(found, list):
        keys = ", ".join(str(f.get("key")) for f in found)
        return say(lang, "schema_findings", keys=keys)
    errors = getattr(error, "errors", None)
    if callable(errors):
        parts = []
        for item in errors():
            where = ".".join(str(x) for x in item.get("loc", ()) if x != "__root__")
            message = _item(item, lang)
            parts.append(f"{where}: {message}" if where else message)
        if parts:
            return "; ".join(parts)
    return str(error)
