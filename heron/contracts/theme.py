"""Схема `theme.yaml` — паспорта темы.

Паспорт служит документацией и основой отчёта `check`, а не жёстким валидатором:
секция, которую тема не использует, — не ошибка, а строка в отчёте.

Здесь же тема объявляет две вещи, которые ядру знать не положено:
`requires` — какие блоки `site.yaml` ей нужны (`contact.phone` и подобное),
`types[*].jsonld` — какой разметкой размечается тип страницы.

Отдельно тема объявляет, чего она ждёт от самого движка: `heron` — версию,
`fields` — поля фронтматтера, к которым обращаются её шаблоны. Без этого
тема, написанная под новый движок, запускается на старом и разваливается
на каждой странице сообщением про опечатку во фронтматтере — хотя опечатки
нет, а есть несовпадение версий.
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

# Тема вправе назвать ожидаемый формат секции: `recovery:timeline`.
# Расхождение — не ошибка сборки, а строка в отчёте: одна и та же секция
# на разных страницах бывает то таблицей, то прозой, и это нормально.
USES_RE = re.compile(r"^(?P<id>[a-z0-9][a-z0-9-]*)(?::(?P<kind>[a-z0-9][a-z0-9-]*))?$")

# Звёздочка вместо перечня: страница принимает любые секции. Так устроены
# статьи — у каждой свой набор блоков, и перечислять их в теме нечем.
ANY = "*"


class TypeSpec(BaseModel):
    """Тип страницы: какие секции использует и чем размечается."""

    model_config = ConfigDict(extra="forbid")

    uses: list[str] = Field(default_factory=list)
    jsonld: list[str] = Field(default_factory=list)
    template: str | None = None

    @field_validator("uses")
    @classmethod
    def _uses(cls, v: list[str]) -> list[str]:
        names = []
        for section in v:
            if section == ANY:
                names.append(section)
                continue
            match = USES_RE.match(section)
            if not match:
                raise ValueError(
                    f"секция {section!r} — латиница, цифры и дефис, "
                    "необязательный формат через двоеточие"
                )
            names.append(match.group("id"))
        if len(set(names)) != len(names):
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
    on: str | None = None
    required: int = 0

    @field_validator("field", "back", "on")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is not None and not NAME_RE.match(v):
            raise ValueError("имя поля связи — латиница, цифры, дефис и подчёркивание")
        return v


class ImagesSpec(BaseModel):
    """Что тема хочет от картинок.

    Пропорции просит тема: это она решает, что карточка каталога квадратная,
    а обложка статьи широкая. Ядро вписывает в них мастер, добивая
    прозрачными полями, а фотографии режет кропом.

    `crop` — исключения: пути, которые кропать всё равно, даже если
    прозрачность у них есть. Пишутся началом пути: `media/bio/`.

    `as_is` — пути, которые не трогать вовсе: файл копируется в сборку как
    есть, без вариантов и конвертаций. Скан документа не иллюстрация: его
    открывают целиком и в одном виде, адаптивные размеры ему не нужны, а
    два десятка вариантов на каждый скан — работа впустую и минуты сборки.
    Пишется так же, началом пути: `media/diplomas/`.
    """

    model_config = ConfigDict(extra="forbid")

    widths: list[int] = Field(default_factory=lambda: [400, 800, 1200, 1600])
    ratios: list[str] = Field(default_factory=lambda: ["1:1", "16:9", "4:3"])
    formats: list[str] = Field(default_factory=lambda: ["avif", "webp"])
    crop: list[str] = Field(default_factory=list)
    as_is: list[str] = Field(default_factory=list)

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
    heron: str | None = None
    fields: list[str] = Field(default_factory=list)
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
        if not spec:
            return []
        return [
            USES_RE.match(name).group("id")  # type: ignore[union-attr]
            for name in spec.uses
            if name != ANY
        ]

    def any_sections(self, page_type: str) -> bool:
        """Тема согласна на любые секции этого типа страниц."""
        spec = self.types.get(page_type)
        return bool(spec) and ANY in spec.uses

    def formats_of(self, page_type: str) -> dict[str, str]:
        """Какой формат секции тема считает ожидаемым. Пусто — любой."""
        spec = self.types.get(page_type)
        if not spec:
            return {}
        out: dict[str, str] = {}
        for name in spec.uses:
            if name == ANY:
                continue
            match = USES_RE.match(name)
            if match and match.group("kind"):
                out[match.group("id")] = match.group("kind")
        return out


def load_theme(path: Path) -> ThemeConfig:
    """Прочитать и проверить `theme.yaml`."""
    return build(ThemeConfig, read_yaml(path, code="E008"), path, code="E008")
