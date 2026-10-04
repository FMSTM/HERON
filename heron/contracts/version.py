"""Сверка версии движка с требованием ключа `heron` из site.yaml.

Проверка идёт до всего остального — раньше загрузки темы и обхода контента.
Единственное, что не даёт сайтам разъехаться по несовместимым движкам.
Спецификация: docs/spec/23-distribution.md, раздел 2.
"""

from __future__ import annotations

import re

from heron.core.errors import HeronError

_CLAUSE = re.compile(r"^(>=|<=|==|!=|>|<)\s*([0-9]+(?:\.[0-9]+)*)$")


def parse(version: str) -> tuple[int, ...]:
    """Разобрать версию в кортеж чисел. `0.4.1` -> `(0, 4, 1)`."""
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)*", version.strip()):
        raise ValueError(f"не версия: {version!r}")
    return tuple(int(p) for p in version.strip().split("."))


def _pad(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def satisfies(actual: str, spec: str) -> bool:
    """Удовлетворяет ли версия требованию вида `>=0.4,<0.5`."""
    got = parse(actual)
    for raw in spec.split(","):
        clause = raw.strip()
        if not clause:
            continue
        m = _CLAUSE.match(clause)
        if not m:
            raise ValueError(f"не разобрать требование версии: {clause!r}")
        op, want_raw = m.groups()
        left, right = _pad(got, parse(want_raw))
        ok = {
            ">=": left >= right,
            "<=": left <= right,
            "==": left == right,
            "!=": left != right,
            ">": left > right,
            "<": left < right,
        }[op]
        if not ok:
            return False
    return True


def check(required: str | None, actual: str, site_yaml: str = "site.yaml") -> None:
    """Проверить совместимость или остановить сборку с E012."""
    if not required:
        raise HeronError(
            code="E011",
            message="в site.yaml нет обязательного ключа `heron` с требуемой версией движка",
            path=site_yaml,
            hint='добавьте первой строкой, например: heron: ">=0.1,<0.2"',
        )
    try:
        ok = satisfies(actual, required)
    except ValueError as exc:
        raise HeronError(
            code="E011",
            message=str(exc),
            path=site_yaml,
            hint='формат требования — как в pip, например ">=0.4,<0.5"',
        ) from exc
    if not ok:
        major_minor = ".".join(actual.split(".")[:2])
        raise HeronError(
            code="E012",
            message=f"движок версии {actual} не удовлетворяет требованию {required!r}",
            path=site_yaml,
            hint=(
                f"возьмите подходящий образ (текущий даёт heron:{major_minor}) "
                "или поднимите требование в site.yaml, проверив совместимость"
            ),
        )
