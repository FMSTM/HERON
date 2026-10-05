"""Схема `site.yaml` — конфигурации сайта.

Ядро строго проверяет только то, что принадлежит движку: версию, языки, тему,
сборку, плагины, формы. Всё остальное — `contact`, `organization`, любые свои
блоки — проходит насквозь и доступно шаблонам как есть.

Иначе ядро начнёт знать предметную область каждого сайта по отдельности.
Что из этих блоков нужно теме, объявляет сама тема в `theme.yaml`
ключом `requires` — движок проверит наличие, не вникая в смысл.

Спецификация: docs/spec/20-data-contract.md, раздел 7.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from heron.contracts.loader import build, read_yaml
from heron.core.errors import HeronError

LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")
DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

RESERVED = {
    "heron",
    "site",
    "seo",
    "nav",
    "build",
    "plugins",
    "forms",
    "sinks",
    "analytics",
    "gone",
}


# Ключи, у которых бывает значение на каждый язык: `name_ru` сильнее `name`.
# Остальные поля ядра от языка не зависят. Блоки сайта (`contact`,
# `organization`) переводятся тем же суффиксом, но разбирает их тема и
# подстановки schema, а не ядро.
LOCALIZED = {"site": ("name",), "seo": ("title_suffix", "og_default_image")}
SUFFIX_RE = re.compile(r"^(?P<key>[a-z_]+?)_(?P<lang>[a-z]{2}(?:-[a-z]{2})?)$")


def _split_localized(data: Any, keys: tuple[str, ...]) -> Any:
    """Вынуть `ключ_<язык>` в `i18n[ключ][язык]`. Прочее не трогать."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    i18n: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (out.get("i18n") or {}).items()}
    for name in list(out):
        match = SUFFIX_RE.match(str(name))
        if match and match.group("key") in keys:
            i18n.setdefault(match.group("key"), {})[match.group("lang")] = out.pop(name)
    if i18n:
        out["i18n"] = i18n
    return out


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_domain(v: str) -> str:
    v = v.strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not DOMAIN_RE.match(v):
        raise ValueError("домен указывается без схемы и слешей, например example.com")
    return v


class SiteBlock(Strict):
    """Кто мы и на скольких языках."""

    domain: str
    # Домен на окружение: dev-сборка, выложенная на превью-домен, должна
    # ссылаться на себя, а не на боевой сайт. Иначе на деве нечего
    # проверять внешними инструментами: карта сайта, каноникл и разметка
    # показывают чужой адрес. Ключ — то же имя окружения, что управляет
    # индексацией: второго рычага, который можно забыть переключить, быть
    # не должно. Блока нет — поведение прежнее.
    domains: dict[str, str] = Field(default_factory=dict)
    name: str | None = None
    theme: str
    default_lang: str = "en"
    languages: list[str] = Field(default_factory=lambda: ["en"])
    # значения по языкам: name_ru → i18n["name"]["ru"]. Пишут суффиксом.
    i18n: dict[str, dict[str, Any]] = Field(default_factory=dict, repr=False)

    @model_validator(mode="before")
    @classmethod
    def _localized(cls, data: Any) -> Any:
        return _split_localized(data, LOCALIZED["site"])

    @field_validator("domain")
    @classmethod
    def _domain(cls, v: str) -> str:
        return _clean_domain(v)

    @field_validator("domains")
    @classmethod
    def _domains(cls, v: dict[str, str]) -> dict[str, str]:
        return {env: _clean_domain(name) for env, name in v.items()}

    @field_validator("theme")
    @classmethod
    def _theme(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("имя темы — латиница, цифры, дефис и подчёркивание")
        return v

    @field_validator("languages")
    @classmethod
    def _languages(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("нужен хотя бы один язык")
        for lang in v:
            if not LANG_RE.match(lang):
                raise ValueError(
                    f"код языка {lang!r} не похож на код языка: ожидается uk, ru, en-gb"
                )
        if len(set(v)) != len(v):
            raise ValueError("языки повторяются")
        return v

    @model_validator(mode="after")
    def _default_lang_listed(self) -> SiteBlock:
        if self.default_lang not in self.languages:
            raise ValueError(
                f"default_lang {self.default_lang!r} отсутствует в languages {self.languages}"
            )
        return self


class SeoBlock(Strict):
    title_suffix: str = ""
    og_default_image: str | None = None
    # значения по языкам: title_suffix_ru → i18n["title_suffix"]["ru"]
    i18n: dict[str, dict[str, Any]] = Field(default_factory=dict, repr=False)

    @model_validator(mode="before")
    @classmethod
    def _localized(cls, data: Any) -> Any:
        return _split_localized(data, LOCALIZED["seo"])

    twitter_card: str = "summary_large_image"
    llms_txt: bool = True

    # Сведения о сайте для файлов, которые читает нейросеть: связь, часы,
    # чего сайт не делает. Ключ — код языка, значение — готовый markdown.
    # Вставляется дословно: это данные, а не шаблон.
    llms_note: dict[str, str] = Field(default_factory=dict)

    robots_extra: list[str] = Field(default_factory=list)

    # Публикует ли сайт цены в разметке schema.org. По умолчанию нет: поля
    # про деньги (offers, price, priceRange…) в графе — ошибка E020, чтобы
    # стоимость не утекла через разметку, если на страницах её нет.
    allow_prices: bool = False

    feed: str | None = None
    feed_limit: int = 20


class NavBlock(BaseModel):
    """Меню. Состав произвольный: имена групп придумывает тема."""

    model_config = ConfigDict(extra="allow")

    main: list[str] = Field(default_factory=list)


class AnalyticsBlock(Strict):
    """Публичные идентификаторы счётчиков.

    Это не секреты: они видны в исходнике любой страницы и вычитываются
    краулерами. Поэтому им место здесь, рядом с доменом и языками, а не в
    переменных окружения — иначе один и тот же сайт на двух машинах соберётся
    с разными счётчиками, и никто не поймёт почему.

    Вставляются в страницы только когда окружение сборки это разрешает:
    на деве счётчик не должен портить статистику живого сайта.
    """

    metrika: str | None = None
    gtm: str | None = None
    ga4: str | None = None

    @field_validator("metrika", "gtm", "ga4", mode="before")
    @classmethod
    def _as_text(cls, v: Any) -> Any:
        # номер счётчика Метрики в YAML — число; шаблону нужна строка
        return str(v) if isinstance(v, int) else v


class BuildBlock(Strict):
    # Язык комментариев и пояснений, которые кладут `heron init` и
    # `heron page`: SEO-блок страниц, записки, site.yaml, theme.yaml.
    # На сборку не влияет.
    notes: Literal["ru", "en"] = "en"
    fail_on_warning: bool = False
    allow_raw_html: bool = False

    # Откуда берётся дата обновления страницы, если её не задали руками.
    # Умолчание `manual` — прежнее поведение: подъём движка не должен
    # менять даты на живом сайте сам по себе.
    updated_from: Literal["manual", "git", "file"] = "manual"

    # Сколько процессов режет картинки. 0 — по числу ядер машины. Ставят
    # руками там, где ядра делят с другими задачами: в CI сборка сайта не
    # одна на машине, и забрать все ядра значит замедлить соседей.
    workers: int = Field(default=0, ge=0, le=64)


class FormSpec(Strict):
    """Описание формы. Движок её не принимает — принимает heron-relay.

    Движку описание нужно, чтобы отдать теме состав полей и упасть, если тема
    рисует форму, которой нет в конфиге.
    """

    fields: list[str]
    sinks: list[str] = Field(default_factory=list)

    @field_validator("fields")
    @classmethod
    def _fields(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("у формы нет ни одного поля")
        for name in v:
            if not NAME_RE.match(name):
                raise ValueError(f"имя поля {name!r} — латиница, цифры, дефис и подчёркивание")
        return v


def parse_gone(entry: str) -> tuple[str, str, str, str | None]:
    """Разобрать запись `gone`: точный адрес, префикс или адрес с параметром.

    Возвращает `(вид, путь, параметр, значение)`:

    - `/sample-page/` — точный адрес: `("exact", "/sample-page/", "", None)`;
    - `/wp/*` — всё, что начинается с `/wp/`: `("prefix", "/wp/", "", None)`;
    - `/?p=*` — адрес `/` с параметром `p` любого значения:
      `("query", "/", "p", None)`; `/?p=12` — только с этим значением.

    Звёздочка допустима только в конце пути или вместо значения параметра.
    Негодная запись — `ValueError` с объяснением.
    """
    if not entry.startswith("/"):
        raise ValueError(f"gone: {entry!r} — ожидается путь от корня, например /old-page/")
    if "#" in entry:
        raise ValueError(f"gone: {entry!r} — якорь серверу не приходит, уберите #…")
    path, sep, query = entry.partition("?")
    if sep:
        name, eq, value = query.partition("=")
        if "*" in path or not name or not eq or "&" in query or not value:
            raise ValueError(f"gone: {entry!r} — параметр пишется одной парой: /?p=* или /?p=12")
        if "*" in value and value != "*":
            raise ValueError(f"gone: {entry!r} — звёздочка заменяет значение целиком: /?p=*")
        return "query", path, name, None if value == "*" else value
    if path.endswith("*"):
        stem = path[:-1]
        if "*" in stem:
            raise ValueError(f"gone: {entry!r} — звёздочка допустима только в конце: /wp/*")
        return "prefix", stem, "", None
    if "*" in path:
        raise ValueError(f"gone: {entry!r} — звёздочка допустима только в конце: /wp/*")
    return "exact", path, "", None


class SiteConfig(BaseModel):
    """Весь `site.yaml`. Неизвестные блоки верхнего уровня сохраняются как есть."""

    model_config = ConfigDict(extra="allow")

    heron: str
    site: SiteBlock
    seo: SeoBlock = Field(default_factory=SeoBlock)
    nav: NavBlock = Field(default_factory=NavBlock)
    build: BuildBlock = Field(default_factory=BuildBlock)
    analytics: AnalyticsBlock = Field(default_factory=AnalyticsBlock)
    plugins: list[str] = Field(default_factory=list)
    forms: dict[str, FormSpec] = Field(default_factory=dict)
    sinks: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Адреса, на которые сервер отвечает 410: точные, префиксы `/wp/*` и
    # адрес с параметром `/?p=*`. Страницы у них нет и не будет — поэтому
    # они живут здесь, а не во фронтматтере.
    gone: list[str] = Field(default_factory=list)

    @field_validator("gone")
    @classmethod
    def _gone(cls, v: list[str]) -> list[str]:
        for entry in v:
            parse_gone(entry)
        return v

    _by_lang: dict[str, SiteConfig] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _localized_langs_declared(self) -> SiteConfig:
        for block in (self.site, self.seo):
            for key, values in block.i18n.items():
                for lang in values:
                    if lang not in self.site.languages:
                        raise ValueError(
                            f"{key}_{lang}: языка {lang!r} нет в site.languages "
                            f"{self.site.languages}"
                        )
        return self

    def for_lang(self, lang: str) -> SiteConfig:
        """Конфиг глазами страницы этого языка.

        `site.name`, `seo.title_suffix` и `seo.og_default_image` уже
        подставлены для языка: `name_ru` сильнее `name`. Шаблон пишет
        `site.site.name` и получает название на языке страницы — выбирать
        его фильтром на каждом месте никто не станет, и суффикс на чужом
        языке в выдаче останется.
        """
        cached = self._by_lang.get(lang)
        if cached is not None:
            return cached
        site = {k: v[lang] for k, v in self.site.i18n.items() if lang in v}
        seo = {k: v[lang] for k, v in self.seo.i18n.items() if lang in v}
        copy = self.model_copy(
            update={
                "site": self.site.model_copy(update=site),
                "seo": self.seo.model_copy(update=seo),
            }
        )
        self._by_lang[lang] = copy
        return copy

    @model_validator(mode="after")
    def _forms_point_at_existing_sinks(self) -> SiteConfig:
        for form_name, form in self.forms.items():
            unknown = [s for s in form.sinks if s not in self.sinks]
            if unknown:
                raise ValueError(
                    f"форма {form_name!r} ссылается на приёмники, которых нет в sinks: "
                    + ", ".join(unknown)
                )
        return self

    @property
    def extras(self) -> dict[str, Any]:
        """Блоки сайта, которых движок не знает: contact, organization и прочее."""
        return {k: v for k, v in (self.__pydantic_extra__ or {}).items() if k not in RESERVED}

    def get_path(self, dotted: str) -> Any:
        """Достать значение по пути вида `contact.phone`. Нет — вернуть None."""
        node: Any = self.model_dump()
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node


def load_site(path: Path) -> SiteConfig:
    """Прочитать и проверить `site.yaml`."""
    data = read_yaml(path)
    if "heron" not in data:
        raise HeronError(
            code="E011",
            message="нет обязательного ключа `heron` с требуемой версией движка",
            path=str(path),
            hint='добавьте первой строкой, например: heron: ">=0.1,<0.2"',
        )
    return build(SiteConfig, data, path)
