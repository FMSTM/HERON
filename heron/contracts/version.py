"""Сверка версии движка с требованием ключа `heron` из site.yaml.

Проверка идёт до всего остального — раньше загрузки темы и обхода контента.
Единственное, что не даёт сайтам разъехаться по несовместимым движкам.
Спецификация: docs/spec/23-distribution.md, раздел 2.

Требование пишется как в pip: условия через запятую, операторы
`>=`, `<=`, `>`, `<`, `==`, `!=`, `~=` и шаблон `==X.Y.*` / `!=X.Y.*`.
"""

from __future__ import annotations

import re

from heron.core.errors import HeronError
from heron.messages import Msg, MsgError

_NUM = r"[0-9]+(?:\.[0-9]+)*"
_CLAUSE = re.compile(rf"^(~=|>=|<=|==|!=|>|<)\s*({_NUM})(\.\*)?$")


def parse(version: str) -> tuple[int, ...]:
    """Разобрать версию в кортеж чисел. `0.4.1` -> `(0, 4, 1)`."""
    if not re.fullmatch(_NUM, version.strip()):
        raise MsgError("version_not_version", version=version)
    return tuple(int(p) for p in version.strip().split("."))


def _pad(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def _clause_ok(got: tuple[int, ...], op: str, want: tuple[int, ...], wildcard: bool) -> bool:
    if wildcard:
        # `==0.4.*` — совпадает префикс; другие операторы шаблон не принимают
        if op not in ("==", "!="):
            raise MsgError("version_wildcard_op", op=op)
        same = _pad(got, want)[0][: len(want)] == want
        return same if op == "==" else not same
    if op == "~=":
        # `~=0.4.1` = `>=0.4.1, ==0.4.*`; одна цифра в требовании недопустима
        if len(want) < 2:
            raise MsgError("version_compat_short")
        prefix = want[:-1]
        left, right = _pad(got, want)
        return left >= right and _pad(got, prefix)[0][: len(prefix)] == prefix
    left, right = _pad(got, want)
    return {
        ">=": left >= right,
        "<=": left <= right,
        "==": left == right,
        "!=": left != right,
        ">": left > right,
        "<": left < right,
    }[op]


def satisfies(actual: str, spec: str) -> bool:
    """Удовлетворяет ли версия требованию вида `>=0.4,<0.5`."""
    got = parse(actual)
    clauses = [c.strip() for c in spec.split(",") if c.strip()]
    if not clauses:
        raise MsgError("version_empty_spec", spec=spec)
    for clause in clauses:
        m = _CLAUSE.match(clause)
        if not m:
            raise MsgError("version_bad_clause", clause=clause)
        op, want_raw, star = m.groups()
        if not _clause_ok(got, op, parse(want_raw), bool(star)):
            return False
    return True


def _major_minor(version: str) -> str:
    parts = version.split(".")
    return ".".join((parts + ["0"])[:2])


def _wanted_tag(spec: str) -> str | None:
    """Какой тег образа `heron:X.Y` ближе всего к требованию: по нижней границе."""
    for raw in spec.split(","):
        m = _CLAUSE.match(raw.strip())
        if m and m.group(1) in (">=", "~=", "=="):
            return _major_minor(m.group(2))
    return None


def check_version(required: str | None, actual: str, site_yaml: str = "site.yaml") -> None:
    """Проверить совместимость движка или остановить сборку с E012.

    Нет ключа или он не разбирается — E011: это ошибка конфига, а не версии.
    """
    if not required:
        raise HeronError(
            code="E011",
            message=Msg("version_missing_key"),
            path=site_yaml,
            hint=Msg("version_missing_key_hint"),
        )
    try:
        ok = satisfies(actual, required)
    except ValueError as exc:
        raise HeronError(
            code="E011",
            message=exc.args[0] if exc.args and isinstance(exc.args[0], Msg) else Msg("version_raw", text=str(exc)),
            path=site_yaml,
            hint=Msg("version_bad_spec_hint"),
        ) from exc
    if not ok:
        wanted = _wanted_tag(required)
        raise HeronError(
            code="E012",
            message=Msg("version_unsatisfied", actual=actual, required=required),
            path=site_yaml,
            hint=Msg(
                "version_unsatisfied_hint_tag" if wanted else "version_unsatisfied_hint_any",
                wanted=wanted,
                current=_major_minor(actual),
            ),
        )


# прежнее имя: на него ссылаются сборка и экспорт пакета
check = check_version
