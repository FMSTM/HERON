"""Ответы конфигуратора и их место в `site.yaml`.

Конфигуратор спрашивает каждый факт один раз и пишет его в одно место. Здесь
обе стороны: `read` достаёт ответы из существующего `site.yaml` (повторный
запуск показывает то, что уже записано), `merge` кладёт ответы обратно, не
трогая того, чего конфигуратор не знает: `gone`, `forms`, `nginx`, свои блоки
сайта переживают любое число запусков.

Ключей доступа здесь нет: в site.yaml и git им не место. Модель ответов —
та же для формы в браузере и для
`heron setup --answers файл`, поэтому агент и человек проходят одну проверку.
"""

from __future__ import annotations

import contextlib
import copy
import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from heron.contracts.site import LANG_RE, NAME_RE, CacheBlock
from heron.contracts.site import domain as clean_domain
from heron.contracts.site import duration as cache_duration
from heron.setup.reasons import Reason

HERE = Path(__file__).parent

WAYS = ("github", "dockerhub", "static", "none")
ENVS = ("dev", "prod")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
DOCKER_NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*\Z")
# Движок для сборки сайта: канал (prod, beta), версия или канал с digest.
# Ветка git: подмножество правил git check-ref-format, в котором нет ни
# символов оболочки, ни YAML. Она уходит в git push и в workflow.
BRANCH_RE = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9_.+-]|/(?!/))*\Z")
# Папка на сервере: абсолютный путь из букв, цифр и . _ - + ~ @. Путь
# разбирает ещё и оболочка на сервере (rsync передаёт его ssh), поэтому
# кавычек и подстановок в нём не бывает вовсе.
SERVER_PATH_RE = re.compile(r"^/[A-Za-z0-9._+~@/-]*\Z")
SERVER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.@-]*\Z")
ENGINE_RE = re.compile(r"^(?:prod|beta|dev|\d+\.\d+\.\d+)(?:@sha256:[0-9a-f]{64})?\Z")
ENTITY_ID = "#entity"
DAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
_DAY = "(?:Mo|Tu|We|Th|Fr|Sa|Su)"
_TIME = r"(?:[01]\d|2[0-3]):[0-5]\d|24:00"
_SPAN = rf"(?:{_TIME})-(?:{_TIME})"
# schema.org openingHours: «Mo-Fr 08:30-15:00», «Mo,We,Fr 09:00-13:00»;
# несколько промежутков через запятую
HOURS_RE = re.compile(rf"^{_DAY}(?:-{_DAY})?(?:,{_DAY}(?:-{_DAY})?)* {_SPAN}(?:,{_SPAN})*\Z")


@cache
def vocab() -> dict[str, Any]:
    """Справочник типов schema.org и полей конфигуратора."""
    return yaml.safe_load((HERE / "vocab.yaml").read_text(encoding="utf-8"))


@cache
def classifier() -> list[dict[str, Any]]:
    """Сферы деятельности со специализациями (classifier.yaml)."""
    data = yaml.safe_load((HERE / "classifier.yaml").read_text(encoding="utf-8"))
    return data["directions"]


def direction(ident: str) -> dict[str, Any] | None:
    return next((d for d in classifier() if d["id"] == ident), None)


def specialization(ident: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for item in classifier():
        for spec in item["items"]:
            if spec["id"] == ident:
                return item, spec
    return None


def label_for(entry: dict[str, Any], lang: str) -> str:
    """Подпись на языке сайта: русская или английская, другие языки — английская."""
    return str(entry.get(lang) or entry.get("en") or "")


def lineage(kind: str) -> list[str]:
    """Тип и все его родители, от общего к частному."""
    types = vocab()["types"]
    chain: list[str] = []
    while kind and kind in types and kind not in chain:
        chain.insert(0, kind)
        kind = types[kind].get("parent")
    return chain


def fields_of(kind: str) -> list[str]:
    """Поля типа: общие, затем поля родителей, затем свои."""
    out: list[str] = list(vocab()["common"])
    for name in lineage(kind):
        for field_name in vocab()["types"][name].get("fields", []):
            if field_name not in out:
                out.append(field_name)
    return out


def _precise_types(about: Any) -> list[str]:
    """Типы специализации из классификатора как список (type там строка или список)."""
    found = specialization(about.specialization) if about.specialization else None
    raw = found[1].get("type") if found else None
    if not raw:
        return []
    return [raw] if isinstance(raw, str) else [str(x) for x in raw]


def final_types(about: Any) -> list[str]:
    """Итоговые типы узла списком: вид и, если есть, типы специализации.

    Organization и LocalBusiness заменяются типами специализации; остальные виды
    (Corporation, NGO, EducationalOrganization) остаются первым элементом без
    дублей; Person и вид без специализации - только вид.
    """
    kind = about.type
    if not kind:
        return []
    precise = _precise_types(about)
    if not precise or lineage(kind)[0] == "Person" or precise == [kind]:
        return [kind]
    if kind in ("Organization", "LocalBusiness"):
        return precise
    return [kind, *[t for t in precise if t != kind]]


def prop_head(prop: str) -> str:
    """Свойство schema.org, к которому относится поле: `address.streetAddress` -> `address`."""
    return prop.split(".", 1)[0]


def fields_for(about: Any) -> list[str]:
    """Поля конфигуратора, допустимые итоговому типу: свойство разметки есть у типа по словарю."""
    kind = about.type
    if not kind:
        return list(vocab()["common"])
    if lineage(kind)[0] == "Person":
        return fields_of(kind)
    from heron.schemaorg import vocab as schema_vocab

    types = final_types(about)
    fields = vocab()["fields"]
    return [
        name
        for name in fields_of(kind)
        if schema_vocab().allows(types, prop_head(fields[name]["prop"]))
    ]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SiteAnswers(Model):
    name: str = ""
    domain: str = ""
    preview_domain: str = ""
    languages: list[str] = Field(default_factory=lambda: ["en"])
    default_lang: str = ""

    @field_validator("domain", "preview_domain")
    @classmethod
    def _domain(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        found = clean_domain(value)
        if found is None:
            raise Reason("domain_bad", value=repr(value))
        return found

    @field_validator("languages")
    @classmethod
    def _languages(cls, value: list[str]) -> list[str]:
        out = [item.strip().lower() for item in value if item and item.strip()]
        if not out:
            raise Reason("languages_none")
        bad = [item for item in out if not LANG_RE.match(item)]
        if bad:
            raise Reason("languages_bad", codes=", ".join(bad))
        if len(set(out)) != len(out):
            raise Reason("languages_repeat")
        return out

    @model_validator(mode="after")
    def _default(self, info: ValidationInfo) -> SiteAnswers:
        if not self.default_lang:
            self.default_lang = self.languages[0]
        # чтение записанного site.yaml (read) оставляет основной язык как есть: страница
        # конфигуратора предложит дописать его в языки, а не начнёт блок «Сайт» с нуля
        stale = bool(info.context and info.context.get("stale"))
        if self.default_lang not in self.languages and not stale:
            raise Reason(
                "default_lang_missing",
                value=repr(self.default_lang),
                langs=", ".join(self.languages),
            )
        if self.preview_domain and self.preview_domain == self.domain:
            raise Reason("preview_same")
        return self


class ThemeAnswers(Model):
    # keep — оставить тему как есть; name — тема каталога HERON (белая —
    # `starter`); url — архив по ссылке; file — архив с диска. `starter` —
    # то же, что name=starter: так тему зовут агенты и старые ответы.
    source: Literal["keep", "starter", "name", "url", "file"] = "keep"
    value: str = ""

    @field_validator("source", mode="before")
    @classmethod
    def _later(cls, value: Any) -> Any:
        # «решу потом» убран из конфигуратора: белая тема и так стоит у нового сайта
        return "keep" if value == "later" else value


# Каналы связи: что это за канал и для чего он. Тип решает, как значение
# становится ссылкой; назначение — contactType точки связи в schema.org.
CONTACT_TYPES = (
    "phone",
    "email",
    "website",
    "whatsapp",
    "telegram",
    "viber",
    "signal",
    "instagram",
    "facebook",
    "linkedin",
    "youtube",
    "tiktok",
    "x",
    "other",
)
PURPOSES = {
    # назначение → contactType schema.org
    "main": "customer service",
    "sales": "sales",
    "marketing": "marketing",
    "support": "technical support",
    "booking": "reservations",
    "press": "press",
}
PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()./-]{4,}\Z")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+\Z")
HANDLE_RE = re.compile(r"^@?[A-Za-z0-9_.]{2,64}\Z")


def contact_url(kind: str, value: str) -> str | None:
    """Адрес канала для ссылки и для sameAs. Телефон и почта ссылками не считаются."""
    value = value.strip()
    if kind in ("phone", "email"):
        return None
    if value.startswith(("https://", "http://")):
        return value
    digits = re.sub(r"[^0-9]", "", value)
    if kind == "whatsapp" and digits:
        return f"https://wa.me/{digits}"
    if kind == "viber" and digits:
        return f"viber://chat?number=%2B{digits}"
    handle = value.lstrip("@")
    bases = {
        "telegram": "https://t.me/",
        "instagram": "https://www.instagram.com/",
        "tiktok": "https://www.tiktok.com/@",
        "x": "https://x.com/",
        "youtube": "https://www.youtube.com/@",
    }
    if kind in bases and HANDLE_RE.match(value):
        return bases[kind] + handle
    if kind == "website" and "." in value and " " not in value:
        return "https://" + value
    return None


class ContactAnswer(Model):
    type: Literal[CONTACT_TYPES] = "phone"  # type: ignore[valid-type]
    purpose: str = ""
    value: str

    @field_validator("value")
    @classmethod
    def _value(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise Reason("contact_empty")
        return value

    @field_validator("purpose")
    @classmethod
    def _purpose(cls, value: str) -> str:
        value = (value or "").strip()
        if value and value not in PURPOSES:
            raise Reason("purpose_bad", value=repr(value), names=", ".join(PURPOSES))
        return value

    @model_validator(mode="after")
    def _shape(self) -> ContactAnswer:
        if self.type == "phone" and not PHONE_RE.match(self.value):
            raise Reason("phone_bad", value=repr(self.value))
        if self.type == "email" and not EMAIL_RE.match(self.value):
            raise Reason("email_bad", value=repr(self.value))
        if self.type in ("website", "facebook", "linkedin") and not contact_url(
            self.type, self.value
        ):
            raise Reason("link_needed", kind=self.type)
        return self

    @property
    def url(self) -> str | None:
        return contact_url(self.type, self.value)


class AboutAnswers(Model):
    type: str = ""
    # сфера деятельности и специализация — по классификатору (classifier.yaml)
    direction: str = ""
    specialization: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    contacts: list[ContactAnswer] = Field(default_factory=list)

    @model_validator(mode="after")
    def _classified(self) -> AboutAnswers:
        if self.direction and direction(self.direction) is None:
            raise Reason("direction_unknown", value=repr(self.direction))
        if self.specialization:
            found = specialization(self.specialization)
            if found is None:
                raise Reason("spec_unknown", value=repr(self.specialization))
            if self.direction and found[0]["id"] != self.direction:
                raise Reason(
                    "spec_other",
                    value=repr(self.specialization),
                    direction=repr(self.direction),
                )
            self.direction = found[0]["id"]
        return self

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        if value and value not in vocab()["types"]:
            raise Reason("type_unknown", value=repr(value))
        return value

    @model_validator(mode="after")
    def _known(self, info: ValidationInfo) -> AboutAnswers:
        # чтение записанного site.yaml (read) не ломается на устаревших полях
        if info.context and info.context.get("stale"):
            return self
        allowed = set(fields_for(self))
        unknown = sorted(set(self.fields) - allowed)
        if unknown:
            raise Reason("fields_unknown", kind=self.type or "-", names=", ".join(unknown))
        return self


SEPARATORS = ("—", "–", "-", "|", "·", ":", "/")


def clean_suffix(value: str) -> str:
    """Хвост заголовка всегда отделён: « - Название», а не «О насНазвание».

    Начинается с разделителя — вокруг него ставятся пробелы. Начинается
    с текста — перед ним ставится « - ». Пустой остаётся пустым.
    """
    value = (value or "").rstrip()
    text = value.strip()
    if not text:
        return ""
    if text[0] in SEPARATORS:
        rest = text[1:].strip()
        return f" {text[0]} {rest}" if rest else ""
    return f" - {text}"


class SearchAnswers(Model):
    title_suffix: str = ""
    llms_note: dict[str, str] = Field(default_factory=dict)
    og_image: str = ""
    allow_prices: bool = False

    @field_validator("title_suffix")
    @classmethod
    def _suffix(cls, value: str) -> str:
        return clean_suffix(value)


class AnalyticsAnswers(Model):
    """Публичные номера счётчиков: видны в исходнике страницы, это не секреты."""

    ga4: str = ""
    gtm: str = ""
    metrika: str = ""

    @field_validator("ga4", "gtm", "metrika", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @model_validator(mode="after")
    def _shape(self) -> AnalyticsAnswers:
        if self.ga4 and not re.match(r"^G-[A-Z0-9]{4,}$", self.ga4):
            raise Reason("ga4_bad", value=repr(self.ga4))
        if self.gtm and not re.match(r"^GTM-[A-Z0-9]{4,}$", self.gtm):
            raise Reason("gtm_bad", value=repr(self.gtm))
        if self.metrika and not self.metrika.isdigit():
            raise Reason("metrika_bad", value=repr(self.metrika))
        return self


class CacheAnswers(Model):
    """Сроки кэша браузера - ключи nginx.cache в site.yaml (22 §5)."""

    versioned: str = CacheBlock.model_fields["versioned"].default
    assets: str = CacheBlock.model_fields["assets"].default
    media: str = CacheBlock.model_fields["media"].default

    @field_validator("versioned", "assets", "media", mode="before")
    @classmethod
    def _duration(cls, value: Any, info: ValidationInfo) -> str:
        text = "" if value is None else str(value).strip().lower()
        if not text:
            return CacheBlock.model_fields[info.field_name].default
        try:
            cache_duration(text)
        except ValueError:
            raise Reason("cache_bad", field=info.field_name, value=repr(value)) from None
        return text


class PublishAnswers(Model):
    way: Literal["github", "dockerhub", "static", "none"] = "none"
    # GitHub: собирать и публиковать образ самому GitHub на каждый push.
    # Выключено — workflow не пишется, публикация — git push и своя сборка.
    auto: bool = True
    env: Literal["dev", "prod"] = "dev"
    engine: str = "prod"
    branch: str = "main"
    repo: str = ""
    dockerhub_user: str = ""
    image: str = ""
    static_target: Literal["server", "pages"] = "server"
    server: str = ""
    path: str = ""
    # Помощники для удобства: какие файлы конфигуратор кладёт рядом с site.yaml.
    # Скрипты — в скрытую папку .heron/scripts/, в сборку сайта они не идут.
    helpers: dict[str, bool] = Field(
        default_factory=lambda: {"build": True, "publish": True, "gitignore": True}
    )

    @field_validator("*", mode="before")
    @classmethod
    def _no_control_chars(cls, value: Any, info: ValidationInfo) -> Any:
        """Одно место для всех строк публикации: служебный символ в значении
        (перевод строки, возврат каретки, NUL, табуляция) ломает скрипты и
        workflow. branch и engine обрезаются по краям ниже, их проверяем после обрезки."""
        if isinstance(value, str):
            text = value.strip() if info.field_name in ("branch", "engine") else value
            if any(unicodedata.category(c) == "Cc" for c in text):
                raise Reason("control_chars", field=info.field_name)
        return value

    @field_validator("helpers", mode="before")
    @classmethod
    def _helpers(cls, value: Any) -> Any:
        base = {"build": True, "publish": True, "gitignore": True}
        if isinstance(value, dict):
            unknown = sorted(set(value) - set(base))
            if unknown:
                raise Reason("helpers_unknown", names=", ".join(unknown))
            base.update({k: bool(v) for k, v in value.items()})
        return base

    @field_validator("way", mode="before")
    @classmethod
    def _way(cls, value: Any) -> Any:
        return "github" if value == "git" else value

    @field_validator("engine")
    @classmethod
    def _engine(cls, value: str) -> str:
        value = (value or "prod").strip()
        if not ENGINE_RE.match(value):
            raise Reason("engine_bad", value=repr(value))
        return value

    @model_validator(mode="after")
    def _needed(self) -> PublishAnswers:
        if self.repo and not REPO_RE.match(self.repo):
            raise Reason("repo_bad", value=repr(self.repo))
        for value in (self.dockerhub_user, self.image):
            if value and not DOCKER_NAME_RE.match(value):
                raise Reason("docker_name_bad", value=repr(value))
        if self.way == "dockerhub" and not (self.dockerhub_user and self.image):
            raise Reason("dockerhub_needs")
        if self.way == "static" and self.static_target == "server" and not self.server:
            raise Reason("server_needed")
        if self.server and not SERVER_RE.match(self.server):
            raise Reason("server_bad", value=repr(self.server))
        if self.path and (".." in self.path.split("/") or not SERVER_PATH_RE.match(self.path)):
            raise Reason("path_bad")
        return self

    @field_validator("branch")
    @classmethod
    def _branch(cls, value: str) -> str:
        value = (value or "main").strip()
        bad = (
            not BRANCH_RE.match(value)
            or ".." in value
            or value.endswith((".", "/", ".lock"))
            or "/." in value
        )
        if bad:
            raise Reason("branch_bad", value=repr(value))
        return value


class Answers(Model):
    site: SiteAnswers = Field(default_factory=SiteAnswers)
    theme: ThemeAnswers = Field(default_factory=ThemeAnswers)
    about: AboutAnswers = Field(default_factory=AboutAnswers)
    search: SearchAnswers = Field(default_factory=SearchAnswers)
    analytics: AnalyticsAnswers = Field(default_factory=AnalyticsAnswers)
    publish: PublishAnswers = Field(default_factory=PublishAnswers)
    cache: CacheAnswers = Field(default_factory=CacheAnswers)
    # решение по находкам разметки из файла ответов (ключ schema); в site.yaml не пишется
    _schema: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _languages_of_notes(self) -> Answers:
        stray = sorted(set(self.search.llms_note) - set(self.site.languages))
        if stray:
            raise Reason("note_lang", codes=", ".join(stray))
        for name, value in self.about.fields.items():
            if isinstance(value, dict):
                extra = sorted(set(value) - set(self.site.languages))
                if extra:
                    raise Reason("field_lang", name=name, codes=", ".join(extra))
        return self


# --- site.yaml → ответы ---------------------------------------------------------


def _get(data: Any, dotted: str) -> Any:
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set(data: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _drop(data: dict, dotted: str) -> None:
    parts = dotted.split(".")
    node: Any = data
    trail: list[tuple[dict, str]] = []
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return
        trail.append((node, part))
        node = node[part]
    if isinstance(node, dict):
        node.pop(parts[-1], None)
    # пустые родительские блоки, оставшиеся после удаления, убираем
    for parent, key in reversed(trail):
        if parent.get(key) == {}:
            parent.pop(key)


_STALE = {"stale": True}


def read(data: dict[str, Any]) -> Answers:
    """Ответы из уже записанного `site.yaml` — мягко, без падений."""
    site = data.get("site") or {}
    languages = [str(x) for x in (site.get("languages") or ["en"])]
    default = str(site.get("default_lang") or languages[0])
    domains = site.get("domains") or {}
    out: dict[str, Any] = {
        "site": {
            "name": str(site.get("name") or ""),
            # рабочий домен — тот, с которым собирается прод: site.domains.prod
            # сильнее site.domain (build.for_env)
            "domain": str(domains.get("prod") or site.get("domain") or ""),
            "preview_domain": str(domains.get("dev") or ""),
            "languages": languages,
            "default_lang": default,
        }
    }
    entity = _get(data, "schema.entity") or {}
    raw_type = entity.get("@type") if isinstance(entity, dict) else None
    kind, guessed = _read_type(raw_type)
    picked_direction, picked_spec = _read_classified(data, kind, guessed)
    fields: dict[str, Any] = {}
    for name in fields_of(kind) if kind else vocab()["common"]:
        spec = vocab()["fields"][name]
        value = _get(data, spec["to"])
        if spec.get("localized"):
            parent, _, leaf = spec["to"].rpartition(".")
            block = _get(data, parent) or {}
            per_lang = {
                lang: block.get(f"{leaf}_{lang}")
                for lang in languages
                if lang != default and isinstance(block, dict) and block.get(f"{leaf}_{lang}")
            }
            if per_lang:
                value = {default: value or "", **per_lang}
        if value in (None, "", []) and isinstance(entity, dict):
            value = _read_from_entity(entity, name, spec.get("prop"))
        if value not in (None, "", []):
            fields[name] = value
    out["about"] = {
        "type": kind,
        "direction": picked_direction,
        "specialization": picked_spec,
        "fields": fields,
        "contacts": _read_contacts(data),
    }
    seo = data.get("seo") or {}
    analytics = data.get("analytics") or {}
    out["search"] = {
        "title_suffix": str(seo.get("title_suffix") or ""),
        "llms_note": {
            str(k): str(v) for k, v in (seo.get("llms_note") or {}).items() if k in languages
        },
        "og_image": str(seo.get("og_default_image") or ""),
        "allow_prices": bool(seo.get("allow_prices")),
    }
    out["analytics"] = {key: str(analytics.get(key) or "") for key in ("ga4", "gtm", "metrika")}
    publish = data.get("publish") or {}
    if isinstance(publish, dict):
        known = PublishAnswers.model_fields
        out["publish"] = {k: v for k, v in publish.items() if k in known}
    cache = _get(data, "nginx.cache")
    if isinstance(cache, dict):
        out["cache"] = {k: v for k, v in cache.items() if k in CacheAnswers.model_fields}
    try:
        return Answers.model_validate(out, context=_STALE)
    except ValueError:
        # Сырой конфиг не повод отказать в конфигураторе: он и нужен, чтобы
        # конфиг поправить. Берём то, что проходит по отдельности.
        answers = Answers()
        for block in ("site", "about", "search", "analytics", "publish", "cache"):
            with contextlib.suppress(ValueError):
                setattr(
                    answers,
                    block,
                    type(getattr(answers, block)).model_validate(
                        out.get(block) or {}, context=_STALE
                    ),
                )
        return answers


def _literal_at(node: Any, path: str) -> str | None:
    """Литерал по пути вложенного узла (practicesAt.address.streetAddress); дыры {{ }} не берём."""
    for part in path.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if isinstance(node, str) and node.strip() and "{{" not in node:
        return node
    return None


def _read_from_entity(entity: dict[str, Any], name: str, prop: str | None = None) -> Any:
    """Ответ врача из готового узла, если в `organization.*` его нет."""
    from heron.schemaorg import short

    if name == "medical_specialty":
        raw = entity.get("medicalSpecialty")
        items = [raw] if isinstance(raw, str) else list(raw or [])
        names = [short(str(x)) for x in items if isinstance(x, str)]
        return list(dict.fromkeys(x for x in names if x))
    if name == "practices_at_type":
        practices = entity.get("practicesAt")
        kind = practices.get("@type") if isinstance(practices, dict) else None
        return kind if isinstance(kind, str) else None
    if prop and prop.split(".")[0] in ("practicesAt", "hospitalAffiliation"):
        return _literal_at(entity, prop)
    return None


def _read_type(raw: Any) -> tuple[str, str]:
    """Тип из записанной разметки: (вид для конфигуратора, точный тип специализации)."""
    kinds = vocab()["types"]
    values = raw if isinstance(raw, list) else [raw]
    values = [v for v in values if isinstance(v, str)]
    kind = next((v for v in values if v in kinds), "")
    precise = next((v for v in values if v not in kinds), "")
    if precise and not kind:
        kind = "LocalBusiness"  # точный тип без вида — местный бизнес
    return kind, precise


def _read_classified(data: dict[str, Any], kind: str, precise: str) -> tuple[str, str]:
    """Сфера и специализация по записанным подписям, иначе по точному типу."""
    work = _get(data, "organization.field_of_work")
    spec = _get(data, "organization.specialization")
    person = bool(kind) and lineage(kind)[0] == "Person"
    for item in classifier():
        names = {item.get("ru"), item.get("en")}
        if work and work not in names:
            continue
        for entry in item["items"]:
            labels = entry.get("person", {}) if person else entry
            if spec and spec in {labels.get("ru"), labels.get("en")}:
                return item["id"], entry["id"]
            entry_types = entry.get("type")
            entry_types = [entry_types] if isinstance(entry_types, str) else (entry_types or [])
            if not spec and precise and precise in entry_types and not work:
                return item["id"], entry["id"]
        if work:
            return item["id"], ""
    return "", ""


def _read_contacts(data: dict[str, Any]) -> list[dict[str, str]]:
    """Каналы связи: `contact.channels`, а у старого конфига — телефон, почта, профили."""
    channels = _get(data, "contact.channels")
    out: list[dict[str, str]] = []
    if isinstance(channels, list):
        for item in channels:
            if isinstance(item, dict) and item.get("value"):
                out.append(
                    {
                        "type": str(item.get("type") or "other"),
                        "purpose": str(item.get("purpose") or ""),
                        "value": str(item["value"]),
                    }
                )
        return out
    for kind, path in (("phone", "contact.phone"), ("email", "contact.email")):
        value = _get(data, path)
        if isinstance(value, str) and value.strip():
            out.append({"type": kind, "purpose": "", "value": value.strip()})
    for url in _get(data, "organization.same_as") or []:
        if isinstance(url, str) and url.strip():
            out.append({"type": _kind_of_url(url), "purpose": "", "value": url.strip()})
    return out


def _kind_of_url(url: str) -> str:
    hosts = {
        "t.me": "telegram",
        "wa.me": "whatsapp",
        "instagram.com": "instagram",
        "facebook.com": "facebook",
        "linkedin.com": "linkedin",
        "youtube.com": "youtube",
        "tiktok.com": "tiktok",
        "x.com": "x",
        "twitter.com": "x",
    }
    for host, kind in hosts.items():
        if host in url:
            return kind
    return "website"


# --- ответы → site.yaml ---------------------------------------------------------


def _entity(answers: Answers) -> dict[str, Any] | None:
    """Узел schema.org сайта: только поля, на которые есть ответ.

    Значения не копируются, а подставляются из site.yaml (`{{ contact.phone }}`):
    телефон меняется в одном месте, и разметка меняется вместе с подвалом.
    """
    kind = answers.about.type
    if not kind:
        return None
    node: dict[str, Any] = {"@type": entity_type(answers.about), "@id": ENTITY_ID}
    person = lineage(kind)[0] == "Person"
    from heron.schemaorg import vocab as schema_vocab

    types = final_types(answers.about)

    def ok(prop: str) -> bool:
        return person or schema_vocab().allows(types, prop)

    if (answers.about.direction or answers.about.specialization) and ok("knowsAbout"):
        node["knowsAbout"] = "{{ organization.field_of_work }}"
    if answers.about.specialization and person and ok("hasOccupation"):
        node["hasOccupation"] = {
            "@type": "Occupation",
            "name": "{{ organization.specialization }}",
        }
    for name in fields_for(answers.about):
        if name not in answers.about.fields:
            continue
        spec = vocab()["fields"][name]
        if spec.get("money") and not answers.search.allow_prices:
            continue
        hole = "{{ " + spec["to"] + " }}"
        prop = spec["prop"]
        if _is_nested(prop):
            continue  # вложенные узлы строит _nested ниже
        if spec.get("kind") == "enum" and spec.get("emit") == "url":
            values = answers.about.fields[name]
            values = [values] if isinstance(values, str) else list(values or [])
            if values and ok(prop):
                node[prop] = ["https://schema.org/" + str(x) for x in values]
            continue
        if prop == "address.house":
            continue  # дом входит в streetAddress вместе с улицей, ниже
        if prop.startswith("address."):
            address = node.setdefault("address", {"@type": "PostalAddress"})
            if prop == "address.streetAddress" and "house" in answers.about.fields:
                hole = "{{ contact.street }}, {{ contact.house }}"
            address[prop.split(".", 1)[1]] = hole
        elif prop.startswith("geo."):
            geo = node.setdefault("geo", {"@type": "GeoCoordinates"})
            geo[prop.split(".", 1)[1]] = hole
        elif prop == "worksFor.name":
            node["worksFor"] = {"@type": "Organization", "name": hole}
        elif spec.get("kind") == "media":
            node[prop] = "{{ site.base }}" + "{{ " + spec["to"] + " }}"
        else:
            node[prop] = hole
    if (
        "house" in answers.about.fields
        and "street" not in answers.about.fields
        and "house" in fields_for(answers.about)
    ):
        address = node.setdefault("address", {"@type": "PostalAddress"})
        address["streetAddress"] = "{{ contact.house }}"
    _nested(node, answers.about)
    if not person and "medicalSpecialty" not in node and ok("medicalSpecialty"):
        specialties = _specialties(answers.about)
        if specialties:  # по задаче E17.S4.T2 - литералом, только на типах, где свойство допустимо
            node["medicalSpecialty"] = ["https://schema.org/" + x for x in specialties]
    _entity_contacts(node, answers.about.contacts, None if person else types)
    node.setdefault("url", "{{ site.base }}")
    return node


_FLAT_HEADS = ("address", "geo", "worksFor")


def _is_nested(prop: str) -> bool:
    """Свойство с точкой, чья голова не address/geo/worksFor: вложенный узел."""
    return "." in prop and prop_head(prop) not in _FLAT_HEADS


def _put(node: dict[str, Any], dotted: str, value: Any) -> None:
    """Записать значение по пути `a.b.c`, создавая промежуточные словари."""
    parts = dotted.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = node[part] = {}
        node = child
    node[parts[-1]] = value


def _nested_type(about: AboutAnswers, root: str, path: str = "") -> str:
    """`@type` вложенного узла: адрес - PostalAddress; место работы - из ответа;
    остальные - первый класс диапазона свойства по словарю schema.org."""
    from heron.schemaorg import vocab as schema_vocab

    if path.endswith("address"):
        return "PostalAddress"
    if root == "practicesAt":
        chosen = about.fields.get("practices_at_type")
        if chosen:
            return str(chosen)
    ranges = schema_vocab().ranges(root)
    return ranges[0] if ranges else ""


def _nested(node: dict[str, Any], about: AboutAnswers) -> None:
    """Вложенные узлы (practicesAt, hospitalAffiliation) из полей с точкой в prop.

    Узел появляется, только если есть его имя. Пустое поле с `fallback` берёт
    значение сайта, если у сайта есть ответ на поле-источник.
    """
    fields = vocab()["fields"]
    allowed = fields_for(about)
    roots: dict[str, list[tuple[str, str, str]]] = {}
    for name in allowed:
        spec = fields[name]
        prop = spec["prop"]
        if not _is_nested(prop) or prop.endswith(".@type"):
            continue
        if name in about.fields:
            hole = "{{ " + spec["to"] + " }}"
        elif spec.get("fallback") and any(
            fields[src]["to"] == spec["fallback"] and src in about.fields for src in fields
        ):
            hole = "{{ " + spec["fallback"] + " }}"
        else:
            continue
        roots.setdefault(prop_head(prop), []).append((name, prop, hole))
    for root, items in roots.items():
        if not any(prop == f"{root}.name" and name in about.fields for name, prop, _ in items):
            continue
        sub: dict[str, Any] = {"@type": _nested_type(about, root)}
        for _name, prop, hole in items:
            tail = prop.split(".", 1)[1]
            if "." in tail:
                inner = tail.rsplit(".", 1)[0]
                _put(sub, inner + ".@type", _nested_type(about, root, inner))
            _put(sub, tail, hole)
        node[root] = sub


def entity_type(about: AboutAnswers) -> str | list[str]:
    """Тип узла: вид организации и, если есть, точный тип специализации.

    Местный бизнес и организация вообще получают тип специализации вместо
    своего (стоматология → Dentist: это и есть местный бизнес). Компания,
    некоммерческая или учебная организация — оба типа списком: так schema.org
    и записывает организацию, которая одновременно и то, и другое.
    """
    types = final_types(about)
    return types[0] if len(types) == 1 else types


def _specialties(about: AboutAnswers) -> list[str]:
    found = specialization(about.specialization) if about.specialization else None
    raw = found[1].get("specialty") if found else None
    if not raw:
        return []
    return [raw] if isinstance(raw, str) else [str(x) for x in raw]


def _entity_contacts(
    node: dict[str, Any], contacts: list[ContactAnswer], types: list[str] | None = None
) -> None:
    """Связь в разметке: основной телефон и почта, точки связи по назначению, профили.

    Телефон и почта — подстановкой из `contact.phone`/`contact.email`, как у
    всего остального. Точки связи и профили — списком: их состав пишет конфигуратор
    при каждом сохранении, из того же `contact.channels`.
    """
    from heron.schemaorg import vocab as schema_vocab

    def ok(prop: str) -> bool:
        return types is None or schema_vocab().allows(types, prop)

    kinds = {item.type for item in contacts}
    if "phone" in kinds and ok("telephone"):
        node["telephone"] = "{{ contact.phone }}"
    if "email" in kinds and ok("email"):
        node["email"] = "{{ contact.email }}"
    points = []
    for item in contacts:
        if item.purpose and item.type in ("phone", "email"):
            key = "telephone" if item.type == "phone" else "email"
            points.append(
                {"@type": "ContactPoint", "contactType": PURPOSES[item.purpose], key: item.value}
            )
    if points and ok("contactPoint"):
        node["contactPoint"] = points
    urls = [
        item.url
        for item in contacts
        if item.url and item.url.startswith("https://") and item.type != "website"
    ]
    if urls and ok("sameAs"):
        node["sameAs"] = list(dict.fromkeys(urls))


def _clean_hours(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.splitlines()
    out: list[str] = []
    for item in value or []:
        line = str(item).strip()
        if not line:
            continue
        if not HOURS_RE.match(line) or not _spans_ordered(line):
            raise Reason("hours_bad", value=repr(line))
        out.append(line)
    return out


def _minutes(clock: str) -> int:
    hours, _, minutes = clock.partition(":")
    return int(hours) * 60 + int(minutes)


def _spans_ordered(line: str) -> bool:
    """Закрытие позже открытия; 24:00 и 00:00 как конец допустимы."""
    for opens, closes in re.findall(rf"({_TIME})-({_TIME})", line.partition(" ")[2]):
        end = _minutes(closes) or 24 * 60
        if end <= _minutes(opens):
            return False
    return True


def _clean_enum(spec: dict[str, Any], value: Any) -> Any:
    from heron.schemaorg import short
    from heron.schemaorg import vocab as schema_vocab

    enum = spec["enum"]
    if spec.get("multiple"):
        items = [value] if isinstance(value, str) else list(value or [])
    else:
        items = [value] if value not in (None, "") else []
    seen: list[str] = []
    for item in items:
        text = short(str(item))
        if not text:
            continue
        if not schema_vocab().is_member(enum, text):
            raise Reason("enum_bad", value=repr(text), enum=enum)
        if text not in seen:
            seen.append(text)
    if spec.get("multiple"):
        return seen
    return seen[0] if seen else ""


def _clean_subtype(spec: dict[str, Any], value: Any) -> Any:
    from heron.schemaorg import vocab as schema_vocab

    if value in (None, ""):
        return ""
    text = str(value).strip()
    if text not in spec.get("options", []) or not schema_vocab().is_subtype(text, spec["of"]):
        raise Reason("subtype_bad", value=repr(text), of=spec["of"])
    return text


def _clean_bool(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise Reason("bool_bad", value=repr(value))


def _clean_value(spec: dict[str, Any], value: Any) -> Any:
    kind = spec.get("kind")
    if kind == "lines":
        if isinstance(value, str):
            value = [line.strip() for line in value.splitlines()]
        return [str(item).strip() for item in value or [] if str(item).strip()]
    if kind == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise Reason("not_number", value=repr(value)) from None
    if kind == "country" and isinstance(value, str):
        value = value.strip().upper()
        if value and not re.fullmatch(r"[A-Z]{2}", value):
            raise Reason("country_bad", value=repr(value))
        return value
    if kind == "media" and isinstance(value, str):
        return value.strip().removeprefix("./").removeprefix("/")
    if kind == "hours":
        return _clean_hours(value)
    if kind == "enum":
        return _clean_enum(spec, value)
    if kind == "subtype":
        return _clean_subtype(spec, value)
    if kind == "bool":
        return _clean_bool(value)
    return value.strip() if isinstance(value, str) else value


def merge(data: dict[str, Any], answers: Answers, spec: str) -> dict[str, Any]:
    """Новый site.yaml: прежний конфиг с ответами поверх.

    Ключи, которыми ведает конфигуратор, переписываются (пустой ответ —
    ключ убирается: «ничего не придумано»). Всё прочее остаётся как было.
    """
    out = copy.deepcopy(data) if data else {}
    out.setdefault("heron", spec)
    site = out.setdefault("site", {})
    a = answers.site
    if a.name:
        site["name"] = a.name
    domains = dict(site.get("domains") or {})
    # Рабочий домен — тот, что реально у прода: site.domains.prod, если он
    # задан, иначе site.domain. Поменяли его в конфигураторе — меняются оба, иначе
    # прод собирался бы со старым. Не меняли — файл остаётся как был.
    effective = domains.get("prod") or site.get("domain")
    if a.domain and a.domain != effective:
        site["domain"] = a.domain
        if "prod" in domains:
            domains["prod"] = a.domain
    else:
        site["domain"] = site.get("domain") or a.domain or "example.com"
    if a.preview_domain:
        domains["dev"] = a.preview_domain
    else:
        domains.pop("dev", None)
    if domains:
        site["domains"] = domains
    else:
        site.pop("domains", None)
    site.setdefault("theme", "main")
    site["default_lang"] = a.default_lang
    site["languages"] = [a.default_lang] + [x for x in a.languages if x != a.default_lang]

    # кто сайт: поля по справочнику, языковые значения — хвостом _<язык>
    default = a.default_lang
    kind = answers.about.type
    asked = fields_of(kind) if kind else list(vocab()["common"])
    for name in vocab()["fields"]:
        spec_field = vocab()["fields"][name]
        target = spec_field["to"]
        parent, _, leaf = target.rpartition(".")
        block = _get(out, parent)
        if isinstance(block, dict):
            for key in [
                k for k in block if re.fullmatch(rf"{re.escape(leaf)}_[a-z]{{2}}(-[a-z]{{2}})?", k)
            ]:
                block.pop(key)
        value = answers.about.fields.get(name) if name in asked else None
        if isinstance(value, dict) and spec_field.get("localized"):
            main = _clean_value(spec_field, value.get(default, ""))
            if main not in (None, "", []):
                _set(out, target, main)
            else:
                _drop(out, target)
            for lang, item in value.items():
                item = _clean_value(spec_field, item)
                if lang != default and item not in (None, "", []):
                    _set(out, f"{parent}.{leaf}_{lang}", item)
            continue
        value = _clean_value(spec_field, value) if value is not None else None
        if value in (None, "", []):
            _drop(out, target)
        else:
            _set(out, target, value)

    # сфера и специализация — подписями на языках сайта: их видит и тема,
    # и разметка (knowsAbout, профессия человека)
    org = out.setdefault("organization", {})
    for key in [k for k in org if re.fullmatch(r"(field_of_work|specialization)(_.+)?", k)]:
        org.pop(key)
    about = answers.about
    person = bool(about.type) and lineage(about.type)[0] == "Person"
    found = specialization(about.specialization) if about.specialization else None
    work = direction(about.direction) if about.direction else (found[0] if found else None)
    for lang in [a.default_lang, *[x for x in a.languages if x != a.default_lang]]:
        tail = "" if lang == a.default_lang else f"_{lang}"
        if work:
            org[f"field_of_work{tail}"] = label_for(work, lang)
        if found:
            labels = found[1].get("person", {}) if person else found[1]
            org[f"specialization{tail}"] = label_for(labels, lang)
    if not org:
        out.pop("organization")

    for name in ("organization", "contact"):
        if isinstance(out.get(name), dict):
            out[name] = _tidy(out[name])

    # связь: все каналы списком, первый телефон и первая почта — отдельно:
    # их зовут подвал темы и подстановки разметки
    contact = out.get("contact") if isinstance(out.get("contact"), dict) else {}
    channels = [
        {k: v for k, v in item.model_dump().items() if v} for item in answers.about.contacts
    ]
    for kind, key in (("phone", "phone"), ("email", "email")):
        first = next((c.value for c in answers.about.contacts if c.type == kind), None)
        if first:
            contact[key] = first
        else:
            contact.pop(key, None)
    if channels:
        contact["channels"] = channels
    else:
        contact.pop("channels", None)
    if contact:
        out["contact"] = _tidy(contact)
    else:
        out.pop("contact", None)
    # профили раньше жили списком organization.same_as — теперь они каналы
    if isinstance(out.get("organization"), dict):
        out["organization"].pop("same_as", None)
        if not out["organization"]:
            out.pop("organization")

    schema = out.get("schema") if isinstance(out.get("schema"), dict) else {}
    # Узел разметки сливается в три стороны. База — то, что конфигуратор сам
    # записала бы для прежнего конфига; если ответ не менялся, ключ берётся
    # из site.yaml как есть. Так переживают сохранение поля, которых конфигуратор
    # не знает (geo, openingHours, medicalSpecialty, founder…), точный
    # @type и чужой @id — и меняется только то, что человек поменял в конфигураторе.
    previous = schema.get("entity") if isinstance(schema.get("entity"), dict) else {}
    base = _entity(read(data)) if previous else None
    entity = _three_way(previous, base or {}, _entity(answers) or {})
    if entity:
        schema["entity"] = entity
    else:
        schema.pop("entity", None)
    if schema:
        out["schema"] = schema
    else:
        out.pop("schema", None)

    seo = out.setdefault("seo", {})
    s = answers.search
    seo["title_suffix"] = s.title_suffix
    notes = {k: v for k, v in s.llms_note.items() if v.strip()}
    if notes:
        seo["llms_note"] = notes
    else:
        seo.pop("llms_note", None)
    if s.og_image:
        seo["og_default_image"] = s.og_image.strip().removeprefix("./").removeprefix("/")
    else:
        seo.pop("og_default_image", None)
    if s.allow_prices:
        seo["allow_prices"] = True
    else:
        seo.pop("allow_prices", None)
    analytics = out.setdefault("analytics", {})
    for key in ("ga4", "gtm", "metrika"):
        value = getattr(answers.analytics, key)
        if value:
            analytics[key] = value
        elif key == "metrika":
            analytics.pop(key, None)
        else:
            analytics[key] = None

    p = answers.publish
    off = sorted(k for k, v in p.helpers.items() if not v)
    if p.way == "none":
        # «Пока не знаю» — но решения о помощниках и движок для скрипта
        # сборки уже приняты: без них повторное открытие конфигуратора вернуло бы
        # умолчания и переписало помощники.
        block = {"way": "none"}
        if p.engine != "prod":
            block["engine"] = p.engine
        if off:
            block["helpers"] = {k: False for k in off}
        if len(block) > 1:
            out["publish"] = block
        else:
            out.pop("publish", None)
    else:
        block: dict[str, Any] = {"way": p.way, "env": p.env, "engine": p.engine}
        if off:
            block["helpers"] = {k: False for k in off}
        if p.way == "github":
            block.update(branch=p.branch or "main", auto=p.auto)
            if p.repo:
                block["repo"] = p.repo
        elif p.way == "dockerhub":
            block.update(dockerhub_user=p.dockerhub_user, image=p.image)
        else:
            block["static_target"] = p.static_target
            if p.static_target == "pages":
                block["branch"] = p.branch or "main"  # из неё собирает pages.yml
            if p.static_target == "server":
                block.update(server=p.server, path=p.path or "/var/www/" + site["domain"])
        out["publish"] = block

    _merge_cache(out, answers.cache)
    if not NAME_RE.match(str(site.get("theme"))):
        site["theme"] = "main"
    return out


def _merge_cache(out: dict[str, Any], cache: CacheAnswers) -> None:
    """Сроки кэша в nginx.cache: пишется только то, что человек поменял.

    Ответ совпал с записанным в файле (или с умолчанием, когда ключа нет) -
    файл не трогается: ключ, вписанный руками, остаётся как был, а умолчание
    не появляется в каждом site.yaml после первого сохранения.
    """
    nginx = out.get("nginx") if isinstance(out.get("nginx"), dict) else None
    block = nginx.get("cache") if nginx is not None and isinstance(nginx.get("cache"), dict) else {}
    changed = dict(block)
    for key in CacheAnswers.model_fields:
        answer = getattr(cache, key)
        written = block.get(key)
        current = str(written).strip().lower() if written not in (None, "") else None
        if answer == (current or CacheAnswers.model_fields[key].default):
            continue
        changed[key] = answer
    if changed == block:
        return
    nginx = dict(nginx or {})
    nginx["cache"] = changed
    out["nginx"] = nginx


LANG_TAIL = re.compile(r"^(?P<key>.+?)_(?P<lang>[a-z]{2}(?:-[a-z]{2})?)$")


_MISSING = object()


def _three_way(theirs: Any, base: Any, ours: Any) -> Any:
    """Слить узел: `theirs` — в site.yaml, `base` — что дал бы конфигуратор для
    него, `ours` — что она даёт для новых ответов.

    Ответ не менялся (`ours == base`) — остаётся записанное в файле, будь то
    поле руками или поле конфигуратора. Менялся — берётся новое; пропал из ответов —
    ключ убирается. Словари сливаются по ключам.
    """
    if isinstance(theirs, dict) and isinstance(ours, dict):
        base = base if isinstance(base, dict) else {}
        out: dict[str, Any] = {}
        for key in [*theirs, *[k for k in ours if k not in theirs]]:
            value = _three_way(
                theirs.get(key, _MISSING), base.get(key, _MISSING), ours.get(key, _MISSING)
            )
            if value is not _MISSING:
                out[key] = value
        return out
    if ours == base:
        return theirs
    return ours


def _tidy(block: dict[str, Any]) -> dict[str, Any]:
    """Перевод — сразу за своим ключом: `city`, `city_de`, затем `country`.

    Иначе каждое сохранение переставляло бы строки, и в git копились бы
    правки, в которых ничего не поменялось.
    """
    bases = [k for k in block if not (LANG_TAIL.match(k) and LANG_TAIL.match(k)["key"] in block)]
    out: dict[str, Any] = {}
    for key in bases:
        out[key] = block[key]
        for other in sorted(block):
            match = LANG_TAIL.match(other)
            if match and match["key"] == key:
                out[other] = block[other]
    out.update({k: v for k, v in block.items() if k not in out})
    return out


ORDER = (
    "heron",
    "site",
    "organization",
    "contact",
    "schema",
    "seo",
    "nav",
    "analytics",
    "publish",
    "build",
    "plugins",
)


def ordered(data: dict[str, Any]) -> dict[str, Any]:
    """Блоки в привычном порядке: сначала свои, затем незнакомые как были."""
    out = {key: data[key] for key in ORDER if key in data}
    out.update({key: value for key, value in data.items() if key not in out})
    return out


# --- находки проверки разметки при сохранении --------------------------------------

SCHEMA_MODES = ("check", "drop", "except")
# свойство разметки -> поле конфигуратора, которое не лежит в vocab.yaml по prop
_PROP_FIELD = {
    "telephone": "contacts",
    "email": "contacts",
    "contactPoint": "contacts",
    "sameAs": "contacts",
    "knowsAbout": "direction",
    "hasOccupation": "specialization",
    "@type": "type",
}
_ENTITY_PREFIX = "schema.entity."


class SchemaFindings(ValueError):
    """Итоговый site.yaml не пройдёт проверку разметки: список находок по контракту 409."""

    def __init__(self, findings: list[dict[str, Any]]) -> None:
        self.findings = findings
        keys = ", ".join(str(f.get("key")) for f in findings)
        super().__init__(f"markup will not pass the check: {keys}")


def field_for(path: str) -> str | None:
    """Поле конфигуратора, которому принадлежит находка по пути `schema.entity.<свойство>`."""
    if not path.startswith(_ENTITY_PREFIX):
        return None
    prop = path[len(_ENTITY_PREFIX) :]
    head = prop.split(".", 1)[0]
    if head in _PROP_FIELD:
        return _PROP_FIELD[head]
    for name, spec in vocab()["fields"].items():
        own = str(spec.get("prop") or "")
        if own and (prop == own or prop.startswith(own + ".")):
            return name
    # находка на самом объекте (worksFor) - поле его вложенного свойства (worksFor.name)
    for name, spec in vocab()["fields"].items():
        own = str(spec.get("prop") or "")
        if own.startswith(prop + "."):
            return name
    return None


def findings_payload(entries: list[Any], answers: Answers, lang: str) -> list[dict[str, Any]]:
    """Находки в виде записи ответа 409 (с привязкой к полям и текстом drop_label)."""
    from heron.setup.reasons import say

    out = []
    for entry in entries:
        field_name = field_for(entry.path)
        value = str(entry.value or "")
        if field_name in vocab()["fields"]:
            spec = vocab()["fields"][field_name]
            shown = answers.about.fields.get(field_name, value)
            if isinstance(shown, dict):
                shown = next(iter(shown.values()), value)
            if isinstance(shown, list):
                shown = ", ".join(str(x) for x in shown)
            drop_label = say(lang, "drop_field", label=label_for(spec["label"], lang), value=shown)
        elif field_name is not None:
            drop_label = say(lang, "drop_" + field_name, value=value)
        else:
            drop_label = say(lang, "drop_path", path=entry.path)
        out.append(
            {
                "key": entry.key,
                "code": entry.code,
                "title": entry.title(lang),
                "detail": entry.detail(lang),
                "hint": entry.hint(lang),
                "field": field_name,
                "path": entry.path,
                "value": value,
                "drop_label": drop_label,
            }
        )
    return out


def drop(
    answers: Answers, data: dict[str, Any], findings: list[dict[str, Any]]
) -> tuple[Answers, dict[str, Any], list[str]]:
    """Убрать значения, на которые указали находки: из ответов, а без поля - из data по пути.

    Возвращает копию ответов, data и drop_label убранного. Тип узла не удаляется.
    """
    kept = answers.model_copy(deep=True)
    labels = []
    for item in findings:
        name = item.get("field")
        if name == "type":
            raise Reason("type_not_dropped")
        if name == "contacts":
            value = str(item.get("value") or "")
            prop = str(item["path"]).rsplit(".", 1)[-1]
            kinds = {"telephone": {"phone"}, "email": {"email"}}.get(prop)
            kept.about.contacts = [
                c
                for c in kept.about.contacts
                if not (
                    (value and c.value == value)
                    or (
                        not value
                        and (c.type in kinds if kinds else c.type not in ("phone", "email"))
                    )
                )
            ]
        elif name == "direction":
            kept.about.direction = ""
            kept.about.specialization = ""
        elif name == "specialization":
            kept.about.specialization = ""
        elif name in vocab()["fields"]:
            kept.about.fields.pop(name, None)
        else:
            _drop(data, str(item["path"]))
        labels.append(str(item["drop_label"]))
    return kept, data, labels
