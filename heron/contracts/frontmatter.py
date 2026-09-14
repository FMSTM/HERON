"""Схема фронтматтера страницы.

Обязательны три поля на любой странице: `title`, `h1`, `description`.
Остальное имеет значения по умолчанию, а поля, которых движок не знает
(`treats`, `procedures`, `date` и любые свои), сохраняются в `extra`
и доступны теме — ядро в их смысл не вникает.

Длины `title` и `description` не валятся, а попадают в предупреждения:
сборку ломать из-за лишнего знака в заголовке нельзя.

Спецификация: docs/spec/20-data-contract.md, раздел 4.2.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from heron.core.errors import Warning_

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
URL_PATH_RE = re.compile(r"^/[^\s?#]*$")

TITLE_MAX = 60
DESCRIPTION_MAX = 155


class PageMeta(BaseModel):
    """Фронтматтер одной страницы."""

    model_config = ConfigDict(extra="allow")

    title: str
    h1: str
    description: str

    slug: str | None = None
    type: str | None = None
    children_type: str | None = None

    image: str | None = None
    image_alt: str | None = None
    og_image: str | None = None
    og_title: str | None = None
    og_description: str | None = None

    order: int = 999
    updated: date | None = None
    published: bool = True
    noindex: bool = False
    redirect_from: list[str] = Field(default_factory=list)
    gone: list[str] = Field(default_factory=list)

    @field_validator("title", "h1", "description")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("поле не может быть пустым")
        return v.strip()

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        if v is not None and not SLUG_RE.match(v):
            raise ValueError("слаг — латиница, цифры и дефис, без слешей и подчёркиваний")
        return v

    @field_validator("redirect_from", "gone")
    @classmethod
    def _old_urls(cls, v: list[str]) -> list[str]:
        for url in v:
            if not URL_PATH_RE.match(url):
                raise ValueError(f"{url!r} — ожидается путь от корня, например /services/old/")
        return v

    @property
    def extra(self) -> dict[str, Any]:
        """Поля, которых нет в контракте: treats, procedures, date и прочие."""
        return dict(self.__pydantic_extra__ or {})

    def lint(self, path: str) -> list[Warning_]:
        """Мягкие замечания. Сборку не останавливают, попадают в отчёт check."""
        out: list[Warning_] = []
        if len(self.title) > TITLE_MAX:
            out.append(Warning_(f"title длиннее {TITLE_MAX} знаков ({len(self.title)})", path=path))
        if len(self.description) > DESCRIPTION_MAX:
            out.append(
                Warning_(
                    f"description длиннее {DESCRIPTION_MAX} знаков ({len(self.description)})",
                    path=path,
                )
            )
        if self.image and not self.image_alt:
            out.append(Warning_("картинка задана, а image_alt нет", path=path))
        if self.title == self.h1:
            out.append(
                Warning_(
                    "title и h1 совпадают: title пишется под выдачу, h1 под того, кто уже открыл",
                    path=path,
                )
            )
        return out
