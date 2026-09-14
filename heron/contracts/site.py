"""Схема `site.yaml` — конфигурации сайта.

Ядро строго проверяет только то, что принадлежит движку: версию, языки, тему,
сборку, плагины, формы. Всё остальное — `contact`, `organization`, любые свои
блоки — проходит насквозь и доступно шаблонам как есть.

Иначе ядро начнёт знать про медицину у одного сайта и про юриспруденцию
у другого. Что из этих блоков нужно теме, объявляет сама тема в `theme.yaml`
ключом `requires` — движок проверит наличие, не вникая в смысл.

Спецификация: docs/spec/20-data-contract.md, раздел 7.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from heron.contracts.loader import build, read_yaml
from heron.core.errors import HeronError

LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")
DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

RESERVED = {"heron", "site", "seo", "nav", "build", "plugins", "forms", "sinks"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SiteBlock(Strict):
    """Кто мы и на скольких языках."""

    domain: str
    name: str | None = None
    theme: str
    default_lang: str = "uk"
    languages: list[str] = Field(default_factory=lambda: ["uk"])

    @field_validator("domain")
    @classmethod
    def _domain(cls, v: str) -> str:
        v = v.strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
        if not DOMAIN_RE.match(v):
            raise ValueError("домен указывается без схемы и слешей, например example.com")
        return v

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
    twitter_card: str = "summary_large_image"
    llms_txt: bool = True
    robots_extra: list[str] = Field(default_factory=list)
    feed: str | None = None
    feed_limit: int = 20


class NavBlock(BaseModel):
    """Меню. Состав произвольный: имена групп придумывает тема."""

    model_config = ConfigDict(extra="allow")

    main: list[str] = Field(default_factory=list)


class BuildBlock(Strict):
    fail_on_warning: bool = False
    allow_raw_html: bool = False


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


class SiteConfig(BaseModel):
    """Весь `site.yaml`. Неизвестные блоки верхнего уровня сохраняются как есть."""

    model_config = ConfigDict(extra="allow")

    heron: str
    site: SiteBlock
    seo: SeoBlock = Field(default_factory=SeoBlock)
    nav: NavBlock = Field(default_factory=NavBlock)
    build: BuildBlock = Field(default_factory=BuildBlock)
    plugins: list[str] = Field(default_factory=list)
    forms: dict[str, FormSpec] = Field(default_factory=dict)
    sinks: dict[str, dict[str, Any]] = Field(default_factory=dict)

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
