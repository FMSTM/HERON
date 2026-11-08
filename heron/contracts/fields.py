"""Словарь служебных полей страницы: их описывает движок, а не тема.

SEO-блок (`title`, `h1`, `description`), адрес (`slug`, категория), обложка,
картинка для соцсетей, `noindex`, меню и прочее, что есть у любой страницы
любой темы. Тема их не повторяет: её контракт (`theme.yaml`, `fields` модулей)
описывает только блоки. Опросник, студия и `heron describe` показывают
служебные поля первыми, той же группой и в том же порядке.

Подсказки (`hint` - одна строка, `help` - подробно) - в словаре сообщений,
ключи `field_<имя>_hint` и `field_<имя>_help`, на ru и en; группы - `field_group_<имя>`.

Спецификация: docs/ru/spec/21-engine.md, «Контракт темы».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from heron.contracts.frontmatter import DESCRIPTION_MAX, TITLE_MAX, TRANSLATION_STATES
from heron.messages import say

# Порядок групп - порядок показа в опроснике, студии и describe.
GROUPS = ("seo", "address", "menu", "cover", "social", "publishing", "section")

# Где значение живёт: во фронтматтере страницы, в пути файла, в site.yaml или
# в заголовке секции «## Заголовок {#якорь}».
PLACES = ("frontmatter", "path", "site.yaml", "heading")


@dataclass(frozen=True, slots=True)
class ServiceField:
    """Служебное поле. `key` - ключ фронтматтера или путь в site.yaml."""

    name: str
    type: str
    group: str
    where: str = "frontmatter"
    key: str | None = None
    scope: str = "page"
    required: bool = False
    max_length: int | None = None
    item: str | None = None
    only: str | None = None
    default: Any = None
    default_from: str | None = None

    def hint(self, lang: str) -> str:
        return say(lang, f"field_{self.name}_hint")

    def help(self, lang: str) -> str:
        return say(lang, f"field_{self.name}_help")


SERVICE: tuple[ServiceField, ...] = (
    ServiceField("title", "text", "seo", key="title", required=True, max_length=TITLE_MAX),
    ServiceField("h1", "text", "seo", key="h1", required=True),
    ServiceField(
        "description", "text", "seo", key="description", required=True, max_length=DESCRIPTION_MAX
    ),
    ServiceField("slug", "text", "address", key="slug", default_from="file-name"),
    ServiceField("category", "ref", "address", where="path", key="content/<lang>/<category>/"),
    ServiceField("type", "enum", "address", key="type", default_from="category.children_type"),
    ServiceField("children_type", "enum", "address", key="children_type", only="category"),
    ServiceField("menu", "flag", "menu", where="site.yaml", key="nav.main", default=False),
    ServiceField("nav_title", "text", "menu", key="nav_title", default_from="h1"),
    ServiceField("order", "number", "menu", key="order", default=999),
    ServiceField("image", "image", "cover", key="image", default_from="cover-chain"),
    ServiceField("image_alt", "text", "cover", key="image_alt", max_length=125),
    ServiceField(
        "og_image", "image", "social", key="og_image", default_from="site.yaml:seo.og_default_image"
    ),
    ServiceField("og_title", "text", "social", key="og_title", default_from="title"),
    ServiceField(
        "og_description", "text", "social", key="og_description", default_from="description"
    ),
    ServiceField("noindex", "flag", "publishing", key="noindex", default=False),
    ServiceField("published", "flag", "publishing", key="published", default=True),
    ServiceField("date", "date", "publishing", key="date"),
    ServiceField(
        "updated", "date", "publishing", key="updated", default_from="site.yaml:build.updated_from"
    ),
    ServiceField("redirect_from", "list", "publishing", key="redirect_from", item="link"),
    ServiceField("translation", "enum", "publishing", key="translation"),
    ServiceField(
        "heading", "text", "section", where="heading", key="## …", scope="section", required=True
    ),
    ServiceField(
        "anchor", "text", "section", where="heading", key="{#…}", scope="section", required=True
    ),
)

BY_NAME = {spec.name: spec for spec in SERVICE}

# Допустимые значения служебных полей-перечислений, которые знает сам движок
# (`type` и `children_type` - типы темы, их подставляет describe).
VALUES: dict[str, tuple[str, ...]] = {"translation": TRANSLATION_STATES}


def group_title(lang: str, group: str) -> str:
    return say(lang, f"field_group_{group}")


def of_scope(scope: str) -> list[ServiceField]:
    return [spec for spec in SERVICE if spec.scope == scope]
