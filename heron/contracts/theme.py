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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ThemeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "0.1"
    title: str = ""
    modules: list[str] = Field(default_factory=list)
    types: dict[str, TypeSpec] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)

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
