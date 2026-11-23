"""Встраиваемые сервисы HERON: `services:` в site.yaml (20 §5, 22 §5).

Сервис - чужой для сайта скрипт, который движок подключает сам: тема ничего
не пишет, а CSP открывается ровно под этот сервис и ровно в тех сборках, где
он включён. Каждый сервис объявляет три вещи:

- что вставить в страницу и куда (`insert`: пока только `body-end`, перед
  `</body>`; место вставки в контенте или шаблоне - `marker` - зарезервировано
  за магазином);
- какие origin ему нужны по директивам CSP (`script-src`, `connect-src`,
  `frame-src`, `img-src`) - только `https://хост[:порт]`, без `*`, без схем
  целиком и без `'unsafe-eval'`;
- флаги для темы (`services.<имя>` в контексте шаблона): включён ли сервис и
  как, чтобы тема убрала или сдвинула свою кнопку.

Первый сервис - HERON Chat (`services.chat`). Магазин (`services.shop`)
зарезервирован: ключ есть, сборка на нём останавливается с E047. Счётчики
`analytics` - пока свой блок (их CSP строит `modules/nginx`), сюда переедут
отдельным решением; механизм под это готов: у сервиса может быть согласие.

Чат - функциональный сервис: грузится сразу, без согласия посетителя (он
кладёт id посетителя в localStorage, как корзина или выбранный язык); это
упоминается в политике конфиденциальности сайта (guide/05).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from heron.contracts.site import ChatOverride, ChatService, SiteConfig
from heron.core.errors import Collector
from heron.messages import Msg

CODE = "E047"

# Ключ виджета HERON Chat: hcw_ и 26 знаков Crockford base32 (без I, L, O, U) -
# та же регулярка, что в загрузчике виджета (chat/l.js).
CHAT_KEY = re.compile(r"^hcw_[0-9A-HJKMNP-TV-Z]{26}\Z")
CHAT_UI = ("full", "none")
CHAT_LOADER = "/chat/l.js"
# Хост HERON Chat по умолчанию - единственное место, где он записан. Сайт
# перебивает его ключом `services.chat.host` (дев - https://dev-hub.heron.software).
# chat.heron.software - сайт продукта, не хост виджета: оттуда не грузить.
CHAT_HOST = "https://hub.heron.software"

# Директивы, в которые сервис вправе добавить origin.
DIRECTIVES = ("script-src", "connect-src", "frame-src", "img-src")
# Origin для CSP: https, хост, необязательный порт. Ни пути, ни `*`, ни схемы
# целиком: такую политику движок не соберёт, даже если сервис попросит.
ORIGIN = re.compile(
    r"^https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+(?::\d{1,5})?\Z"
)
RESERVED = ("shop",)
# Где вставлять: `body-end` - перед последним `</body>`; `marker` - место в
# контенте или шаблоне (зарезервировано за магазином, сейчас не делается).
INSERTS = ("body-end", "marker")


@dataclass(frozen=True, slots=True)
class Active:
    """Сервис, включённый в этой сборке."""

    name: str
    # директива CSP -> origin
    csp: dict[str, tuple[str, ...]]
    # куда вставлять и что: язык страницы -> HTML
    insert: str = "body-end"
    tag: Any = None
    flags: dict[str, Any] = field(default_factory=dict)


def origin(value: str | None) -> str | None:
    """`https://хост[:порт]` в каноническом виде или None: путь, запрос, `*` - не origin."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.query or parts.fragment or parts.username:
        return None
    if parts.path not in ("", "/"):
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    candidate = f"https://{host}" + (f":{port}" if port and port != 443 else "")
    return candidate if ORIGIN.match(candidate) else None


# --- HERON Chat ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChatSettings:
    """Значения чата для одной сборки: блок плюс свои значения окружения."""

    widget: str
    host: str
    api: str | None
    ui: str


def _chat_for(chat: ChatService, env_name: str) -> ChatSettings | None:
    """Чат этого окружения или None, если в нём он выключен."""
    override: ChatOverride | None = None
    env = chat.env
    if env is not None:
        if isinstance(env, list):
            if env_name not in env:
                return None
        else:
            if env_name not in env:
                return None
            override = env[env_name]
    base = {"widget": chat.widget, "host": chat.host, "api": chat.api, "ui": chat.ui}
    if override is not None:
        base.update({k: v for k, v in override.model_dump().items() if v not in (None, "")})
    return ChatSettings(
        widget=base["widget"] or "",
        host=base["host"] or CHAT_HOST,
        api=base["api"] or None,
        ui=base["ui"] or "full",
    )


def _chat_problems(settings: ChatSettings, where: str) -> list[tuple[Msg, Msg]]:
    out: list[tuple[Msg, Msg]] = []
    if not settings.widget:
        out.append((Msg("services_chat_no_widget", where=where), Msg("services_chat_widget_hint")))
    elif not CHAT_KEY.match(settings.widget):
        out.append(
            (
                Msg("services_chat_bad_widget", where=where, value=settings.widget),
                Msg("services_chat_widget_hint"),
            )
        )
    if origin(settings.host) is None:
        out.append(
            (
                Msg("services_chat_bad_host", where=where, field="host", value=settings.host),
                Msg("services_chat_host_hint"),
            )
        )
    if settings.api and origin(settings.api) is None:
        out.append(
            (
                Msg("services_chat_bad_host", where=where, field="api", value=settings.api),
                Msg("services_chat_host_hint"),
            )
        )
    if settings.ui not in CHAT_UI:
        out.append(
            (
                Msg("services_chat_bad_ui", where=where, value=settings.ui),
                Msg("services_chat_ui_hint"),
            )
        )
    return out


def _chat_tag(settings: ChatSettings) -> Any:
    host = origin(settings.host)
    api = origin(settings.api) if settings.api else None

    def render(lang: str) -> str:
        attrs = [
            f'src="{html.escape(host + CHAT_LOADER)}"',
            f'data-widget="{html.escape(settings.widget)}"',
            f'data-lang="{html.escape(lang)}"',
        ]
        if api and api != host:
            attrs.append(f'data-api="{html.escape(api)}"')
        if settings.ui == "none":
            attrs.append('data-ui="none"')
        return "<script async " + " ".join(attrs) + "></script>"

    return render


def _chat_active(chat: ChatService, env_name: str) -> Active | None:
    settings = _chat_for(chat, env_name)
    if settings is None or _chat_problems(settings, "chat"):
        return None
    host = origin(settings.host)
    api = origin(settings.api) if settings.api else host
    connect = tuple(dict.fromkeys([host, api]))
    return Active(
        name="chat",
        # загрузчик - со своего хоста; fetch, long-poll и маяк /seen - на api (по
        # умолчанию тот же origin). img-src, font-src и frame-src виджету не нужны;
        # style-src 'unsafe-inline' (его <style> в Shadow DOM) у сайта уже есть.
        csp={"script-src": (host,), "connect-src": connect},
        insert="body-end",
        tag=_chat_tag(settings),
        flags={"enabled": True, "ui": settings.ui},
    )


# --- общее ----------------------------------------------------------------------------


def _envs(chat: ChatService) -> list[str] | None:
    env = chat.env
    if env is None:
        return None
    return list(env) if isinstance(env, list) else list(env.keys())


def verify(config: SiteConfig, collector: Collector) -> None:
    """E047: ключ, хост и окружения сервисов; зарезервированное - отказ.

    Проверяется каждое объявленное окружение: ошибка в значениях прода видна и
    в черновой сборке, а не в день выкладки.
    """
    services = config.services
    if services.shop is not None:
        collector.error(
            CODE,
            Msg("services_reserved", name="shop"),
            path="site.yaml",
            hint=Msg("services_reserved_hint"),
        )
    chat = services.chat
    if chat is None:
        return
    names = _envs(chat)
    checks: list[tuple[str, ChatSettings]] = []
    if names is None:
        checks.append(("services.chat", _chat_for(chat, "")))  # type: ignore[arg-type]
    else:
        for name in names:
            if not re.match(r"^[a-z][a-z0-9-]*\Z", str(name)):
                collector.error(
                    CODE,
                    Msg("services_bad_env", where="services.chat.env", value=str(name)),
                    path="site.yaml",
                    hint=Msg("services_env_hint"),
                )
                continue
            settings = _chat_for(chat, name)
            if settings is not None:
                checks.append((f"services.chat (env {name})", settings))
    seen: set[str] = set()
    for where, settings in checks:
        for message, hint in _chat_problems(settings, where):
            if str(message) in seen:
                continue
            seen.add(str(message))
            collector.error(CODE, message, path="site.yaml", hint=hint)


def active(config: SiteConfig, env_name: str) -> list[Active]:
    """Сервисы, включённые в сборке этого окружения, в постоянном порядке."""
    out: list[Active] = []
    chat = config.services.chat
    if chat is not None:
        got = _chat_active(chat, env_name)
        if got is not None:
            out.append(got)
    return out


def csp(config: SiteConfig, env_name: str) -> dict[str, list[str]]:
    """Origin включённых сервисов по директивам CSP, без повторов.

    Защита от ошибки в самом движке: origin не того вида в политику не
    попадает никогда, даже если сервис его объявил.
    """
    out: dict[str, list[str]] = {name: [] for name in DIRECTIVES}
    for service in active(config, env_name):
        for directive, origins in service.csp.items():
            if directive not in out:
                continue
            for value in origins:
                if ORIGIN.match(value) and value not in out[directive]:
                    out[directive].append(value)
    return out


def cors_notes(config: SiteConfig, env_name: str, collector: Collector) -> None:
    """Сведение: чат включён в непроизводственной сборке - домен в кабинет чата.

    Хаб чата пускает только адреса из настроек виджета в кабинете (по умолчанию
    домен сайта и www.домен). Дев-домен туда надо добавить руками, иначе виджет
    не откроется (403). Не предупреждение: сборка от этого не зависит.
    """
    if env_name == "prod" or not any(s.name == "chat" for s in active(config, env_name)):
        return
    domain = config.site.domains.get(env_name) or config.site.domain
    collector.note(
        Msg("services_chat_cors", env=env_name, domain=domain),
        path="site.yaml",
        kind="прочее",
    )


def theme_flags(config: SiteConfig, env_name: str) -> dict[str, dict[str, Any]]:
    """`services` в контексте шаблона: у каждого известного сервиса `enabled` и свои флаги."""
    flags: dict[str, dict[str, Any]] = {"chat": {"enabled": False, "ui": None}}
    for service in active(config, env_name):
        flags[service.name] = dict(service.flags)
    return flags


_BODY_END = re.compile(r"</body\s*>", re.I)


def insert(text: str, lang: str, services: list[Active]) -> str:
    """Теги сервисов перед последним `</body>`; нет его - в конец документа."""
    tags = [s.tag(lang) for s in services if s.insert == "body-end" and s.tag is not None]
    if not tags:
        return text
    block = "\n".join(tags) + "\n"
    found = list(_BODY_END.finditer(text))
    if not found:
        return text + ("" if text.endswith("\n") else "\n") + block
    at = found[-1].start()
    return text[:at] + block + text[at:]
