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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

    nav_title: str | None = None
    slug: str | None = None
    type: str | None = None
    children_type: str | None = None

    image: str | None = None
    image_alt: str | None = None
    og_image: str | None = None
    og_title: str | None = None
    og_description: str | None = None

    # Видео страницы. Локальный путь отдаётся файлом, полный адрес —
    # вставкой стороннего плеера; список площадок не зашиваем, иначе
    # каждый новый хостинг будет правкой движка.
    video: str | None = None
    video_poster: str | None = None
    video_title: str | None = None

    order: int = 999
    updated: date | None = None
    published: bool = True
    noindex: bool = False
    redirect_from: list[str] = Field(default_factory=list)
    gone: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _empty_means_default(cls, data):
        """Ключ без значения — это «не заполнено», а не ошибка.

        Контракт данных прямо велит оставлять необязательные поля пустыми
        вместе с комментарием-подсказкой, иначе через полгода никто
        не вспомнит, что их можно заполнить. YAML отдаёт такой ключ как
        None, и валиться на этом — значит воевать с собственным правилом.

        Обязательные поля это не спасает: их отсутствие ловится раньше,
        в parse_meta, и с внятным сообщением.
        """
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data

    @field_validator("nav_title")
    @classmethod
    def _nav_title(cls, v: str | None) -> str | None:
        """Короткое имя для меню и хлебных крошек.

        Имя файла — это адрес, и оно латиницей. Когда сайт не на
        латинице, в меню нужно слово на его языке, а `title` для этого не
        годится: он написан под поисковую выдачу и длинный. Поэтому
        страница объявляет своё короткое имя сама, и живёт оно рядом с
        ней — у каждого языка свой файл, синхронизировать нечего.
        """
        if v is None:
            return None
        v = v.strip()
        return v or None

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
