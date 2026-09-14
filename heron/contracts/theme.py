"""Схема `theme.yaml` — паспорта темы.

Паспорт служит документацией и основой отчёта `check`, а не жёстким валидатором:
секция, которую тема не использует, — не ошибка, а строка в отчёте.

Здесь же тема объявляет две вещи, которые ядру знать не положено:
`requires` — какие блоки `site.yaml` ей нужны (`contact.phone` и подобное),
`types[*].jsonld` — какой разметкой размечается тип страницы.
Ядро проверяет наличие и подставляет, не вникая в предметную область.

Спецификация: docs/spec/20-data-contract.md, раздел 8.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from heron.contracts.loader import build, read_yaml

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SECTION_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class TypeSpec(BaseModel):
    """Тип страницы: какие секции использует и чем размечается."""

    model_config = ConfigDict(extra="forbid")

    uses: list[str] = Field(default_factory=list)
    jsonld: list[str] = Field(default_factory=list)
    template: str | None = None

    @field_validator("uses")
    @classmethod
    def _uses(cls, v: list[str]) -> list[str]:
        for section in v:
            if not SECTION_RE.match(section):
                raise ValueError(f"идентификатор секции {section!r} — латиница, цифры и дефис")
        if len(set(v)) != len(v):
            raise ValueError("секции повторяются")
        return v


class LinkSpec(BaseModel):
    """Связь между страницами, объявленная темой.

    Ядро не знает, что процедура «лечит» состояние, — оно знает, что поле
    `treats` содержит слаги страниц типа `condition`, и умеет их найти,
    проверить и построить обратную ссылку. Предметная область остаётся
    в теме, механика в ядре.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    type: str | None = None
    back: str | None = None
    required: int = 0

    @field_validator("field", "back")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is not None and not NAME_RE.match(v):
            raise ValueError("имя поля связи — латиница, цифры, дефис и подчёркивание")
        return v


class ImagesSpec(BaseModel):
    """Что тема хочет от картинок.

    Пропорции просит тема: это она решает, что карточка каталога квадратная,
    а обложка статьи широкая. Ядро режет из мастера то, что попросили.
    """

    model_config = ConfigDict(extra="forbid")

    widths: list[int] = Field(default_factory=lambda: [400, 800, 1200, 1600])
    ratios: list[str] = Field(default_factory=lambda: ["1:1", "16:9", "4:3"])
    formats: list[str] = Field(default_factory=lambda: ["avif", "webp"])

    @field_validator("ratios")
    @classmethod
    def _ratios(cls, v: list[str]) -> list[str]:
        for ratio in v:
            parts = ratio.split(":")
            if len(parts) != 2 or not all(p.isdigit() and int(p) > 0 for p in parts):
                raise ValueError(f"пропорция {ratio!r} задаётся как 16:9")
        return v

    @field_validator("widths")
    @classmethod
    def _widths(cls, v: list[int]) -> list[int]:
        if not v or any(width <= 0 for width in v):
            raise ValueError("ширины — положительные числа")
        return sorted(set(v))


class ThemeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "0.1"
    title: str = ""
    modules: list[str] = Field(default_factory=list)
    types: dict[str, TypeSpec] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    links: list[LinkSpec] = Field(default_factory=list)
    images: ImagesSpec = Field(default_factory=ImagesSpec)
    forms: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _human_yaml(cls, data):
        """`version: 0.1` и `404:` — не ошибки автора, а особенности YAML.

        Число превращаем в строку, числовые ключи типов — тоже: падать
        на этом значит воевать с человеком вместо того, чтобы ему помогать.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "version" in data and not isinstance(data["version"], str):
            data["version"] = str(data["version"])
        types = data.get("types")
        if isinstance(types, dict):
            data["types"] = {str(key): value for key, value in types.items()}
        return data

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("имя темы — латиница, цифры, дефис и подчёркивание")
        return v

    @field_validator("modules")
    @classmethod
    def _modules(cls, v: list[str]) -> list[str]:
        for module in v:
            if not NAME_RE.match(module):
                raise ValueError(f"имя модуля {module!r} — латиница, цифры, дефис и подчёркивание")
        return v

    def sections_of(self, page_type: str) -> list[str]:
        spec = self.types.get(page_type)
        return list(spec.uses) if spec else []


def load_theme(path: Path) -> ThemeConfig:
    """Прочитать и проверить `theme.yaml`."""
    return build(ThemeConfig, read_yaml(path, code="E008"), path, code="E008")
