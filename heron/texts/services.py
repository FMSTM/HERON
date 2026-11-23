"""Сообщения встраиваемых сервисов HERON (modules/services.py, `services:` в site.yaml)."""

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "services_chat_no_key": "чат в сборке {env}: ключ не задан - не подключается; ключ появится в кабинете HERON Chat после привязки домена",
        "services_chat_bad_widget": "{where}: ключ виджета {value!r} не похож на ключ HERON Chat",
        "services_chat_widget_hint": "ключ из кабинета HERON Chat: hcw_ и 26 знаков (цифры и латиница без I, L, O, U), например hcw_DTTQXXFWX2X8F6XHB1RQXBRN8G",
        "services_chat_bad_host": "{where}: {field} {value!r} - не адрес https без пути",
        "services_chat_host_hint": "только https и только origin, без пути и слеша в конце: https://dev-hub.heron.software; без host - боевой хост HERON Chat",
        "services_chat_bad_ui": "{where}: ui {value!r} - ожидается full или none",
        "services_chat_ui_hint": "full - своя кнопка чата; none - без кнопки, чат открывает тема",
        "services_reserved": "services.{name} зарезервирован, движок его пока не подключает",
        "services_reserved_hint": "уберите блок из site.yaml: сервис появится в следующих версиях HERON",
        "services_bad_env": "{where}: имя окружения {value!r} не подходит",
        "services_env_hint": "имена окружений сборки - строчная латиница, цифры и дефис: dev, prod, stage",
        "services_chat_cors": "чат включён в сборке {env}: добавьте {domain} в разрешённые адреса чата в кабинете HERON Chat, иначе виджет не откроется (хаб отвечает 403)",
    },
    "en": {
        "services_chat_no_key": "the chat in the {env} build: no key - it is not connected; the key appears in the HERON Chat dashboard after the domain is bound",
        "services_chat_bad_widget": "{where}: the widget key {value!r} does not look like a HERON Chat key",
        "services_chat_widget_hint": "the key from the HERON Chat dashboard: hcw_ and 26 characters (digits and Latin letters without I, L, O, U), e.g. hcw_DTTQXXFWX2X8F6XHB1RQXBRN8G",
        "services_chat_bad_host": "{where}: {field} {value!r} is not an https address without a path",
        "services_chat_host_hint": "https only and origin only, no path and no trailing slash: https://dev-hub.heron.software; without host - the production HERON Chat host",
        "services_chat_bad_ui": "{where}: ui {value!r} - expected full or none",
        "services_chat_ui_hint": "full - the chat's own button; none - no button, the theme opens the chat",
        "services_reserved": "services.{name} is reserved, the engine does not connect it yet",
        "services_reserved_hint": "remove the block from site.yaml: the service comes in later HERON versions",
        "services_bad_env": "{where}: the environment name {value!r} does not fit",
        "services_env_hint": "build environment names are lowercase Latin letters, digits and hyphens: dev, prod, stage",
        "services_chat_cors": "the chat is on in the {env} build: add {domain} to the chat's allowed addresses in the HERON Chat dashboard, otherwise the widget does not open (the hub answers 403)",
    },
}
