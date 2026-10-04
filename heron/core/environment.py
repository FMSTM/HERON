"""Окружение сборки: чем прод отличается от дева.

Один и тот же контент собирается по-разному в зависимости от того, куда
поедет результат. Отличий ровно два, и оба — про то, что видит внешний мир:
пускаем ли поисковики и вставляем ли счётчики.

Хранить это в `site.yaml` нельзя: конфигурация сайта одна, а окружений много,
и дев-сборка того же контента не должна отличаться от прода ни одной буквой
контента. Поэтому окружение приходит снаружи — флагом или переменной среды,
а в HERON лежит файлом `env/.env.<сайт>.<окружение>`.

Окружение сайта и версия движка — разные вещи, и путать их нельзя.
Дев-сборка сайта означает «закрыто от индексации, без счётчиков», а не
«собрать сырым движком»: человек, который правит контент, не должен
получать чужие ошибки разработки. Версию движка выбирают отдельно.

Ошибка «залили дев в сеть, его сожрал гугл, склейка дублей на полгода» стоит
дороже любого удобства, поэтому по умолчанию индексация ЗАКРЫТА: открыть её
нужно осознанно, а забыть закрыть — нельзя.

Спецификация: docs/spec/23-distribution.md, раздел 5.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEV = "dev"
PROD = "prod"
NAMES = (DEV, PROD)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


@dataclass(frozen=True, slots=True)
class BuildEnv:
    """Окружение сборки. Шаблонам доступно как `env`."""

    name: str = DEV
    indexable: bool = False
    analytics: bool = False
    version: str = ""
    built_at: str = ""
    revision: str = ""

    @property
    def is_prod(self) -> bool:
        return self.name == PROD

    @property
    def stamp(self) -> str:
        """Короткая метка сборки для служебного флажка в теме.

        Нужна, чтобы по одному взгляду на страницу понимать, какая именно
        статика сейчас отдаётся: «почему правка не видна» чаще всего значит
        «крутится вчерашний образ», а не «сборка сломалась».
        """
        parts = [p for p in (self.version, self.built_at, self.revision) if p]
        return " · ".join(parts)

    def stamped(self, site_root: Path | None = None) -> BuildEnv:
        """То же окружение, но с версией, временем и ревизией контента."""
        from heron import __version__

        return BuildEnv(
            name=self.name,
            indexable=self.indexable,
            analytics=self.analytics,
            version=__version__,
            built_at=datetime.now().astimezone().strftime("%d.%m.%Y %H:%M"),
            revision=_revision(site_root) if site_root else "",
        )

    @classmethod
    def named(cls, name: str) -> BuildEnv:
        """Окружение по имени. Прод открыт наружу, всё остальное — нет."""
        prod = name == PROD
        return cls(name=name, indexable=prod, analytics=prod)

    @classmethod
    def resolve(cls, name: str | None = None) -> BuildEnv:
        """Имя из флага, затем из SITE_ENV; отдельные ключи перебивают дефолт.

        Явные SITE_INDEXABLE и SITE_ANALYTICS нужны для прод-подобного
        превью: собрать как прод, но закрыть от индексации.
        """
        chosen = (name or os.environ.get("SITE_ENV") or DEV).strip().lower() or DEV
        base = cls.named(chosen)
        return cls(
            name=base.name,
            indexable=_flag("SITE_INDEXABLE", base.indexable),
            analytics=_flag("SITE_ANALYTICS", base.analytics),
        )


def _revision(site_root: Path) -> str:
    """Короткий коммит папки контента, если рядом есть git.

    Читаем файлы, а не зовём git: папка монтируется только на чтение,
    а в образе движка git может отсутствовать вовсе. Нет .git — нет и
    ревизии, это не ошибка.
    """
    git = site_root / ".git"
    try:
        if git.is_file():  # рабочее дерево вынесено, в файле путь к настоящей папке
            git = (site_root / git.read_text(encoding="utf-8").split(":", 1)[1].strip()).resolve()
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head[:7]
        ref = head.split(" ", 1)[1].strip()
        direct = git / ref
        if direct.exists():
            return direct.read_text(encoding="utf-8").strip()[:7]
        for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0][:7]
    except (OSError, IndexError, UnicodeDecodeError):
        return ""
    return ""
