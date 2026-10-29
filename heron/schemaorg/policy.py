"""Политика проверки разметки: откуда находка, строгость, исключения.

Валидатор (heron.schemaorg.validate) знает только узел и путь внутри него.
Здесь находка получает происхождение (файл-источник и ключ), строгость
зависит от окружения, а осознанные исключения человека превращаются в строки
отчёта. Спецификация: docs/spec/21-engine.md, раздел 11.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from heron.contracts.site import SchemaException, SiteConfig
from heron.core.errors import HeronError, Warning_
from heron.messages import say, title
from heron.schemaorg import vocab
from heron.schemaorg.images import image_refs, local_path
from heron.schemaorg.validate import Finding, validate

ENGINE = "engine"
SITE = "site.yaml"
THEME = "theme.yaml"
KIND = "schema.org"
LANGS = ("ru", "en")
_ENGINE_KINDS = frozenset({"BreadcrumbList", "FAQPage"})
_FIELDS = (
    "suggest",
    "domain",
    "members",
    "replacement",
    "types",
    "prop",
    "enum",
    "got",
    "expected",
    "url",
)


def today_for_build() -> date:
    """Сегодня для сроков исключений: SOURCE_DATE_EPOCH, иначе часы."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), UTC).date()
    return date.today()


def texts(finding: Finding, lang: str) -> tuple[str, str]:
    """Подробность и подсказка находки на языке сообщений."""
    fields: dict[str, Any] = {name: "" for name in _FIELDS}
    fields.update(finding.fields)
    fields["release"] = vocab().release
    fields["value"] = finding.value
    code = finding.code.lower()
    return say(lang, f"{code}_detail", **fields), say(lang, f"{code}_hint", **fields)


def _declared_kinds(page: Any, config: SiteConfig, theme: Any):
    from heron.modules import jsonld  # внутри: jsonld тянет heron.schemaorg

    return jsonld.declared_kinds(page, config, theme)


@dataclass
class Entry:
    """Находка с происхождением. Одинаковые ключи с разных страниц схлопнуты."""

    key: str
    code: str
    file: str
    path: str
    value: str
    finding: Finding
    pages: int = 1
    reason: str = ""
    until: date | None = None
    source: str = ""  # для исключений: site | flag

    def detail(self, lang: str) -> str:
        return texts(self.finding, lang)[0]

    def hint(self, lang: str) -> str:
        return texts(self.finding, lang)[1]

    def title(self, lang: str) -> str:
        return title(lang, self.code)


def make_key(code: str, file: str, path: str) -> str:
    return f"{code}:{file}:{path}"


@dataclass
class SchemaSection:
    """Итог проверки разметки для отчёта."""

    release: str = ""
    nodes: int = 0
    env_prod: bool = False
    findings: list[Entry] = field(default_factory=list)
    excepted: list[Entry] = field(default_factory=list)
    unused: list[str] = field(default_factory=list)
    expired: list[Entry] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        severity = "error" if self.env_prod else "warning"
        return {
            "release": self.release,
            "nodes": self.nodes,
            "findings": [
                {
                    "key": e.key,
                    "code": e.code,
                    "file": e.file,
                    "path": e.path,
                    "pages": e.pages,
                    "severity": severity,
                }
                for e in self.findings
            ],
            "excepted": [
                {
                    "key": e.key,
                    "source": e.source,
                    "reason": e.reason,
                    "until": e.until.isoformat() if e.until else None,
                }
                for e in self.excepted
            ],
            "unused": list(self.unused),
            "expired": [
                {"key": e.key, "until": e.until.isoformat() if e.until else None}
                for e in self.expired
            ],
            "pending": list(self.pending),
        }


def _apply(
    found: dict[str, Entry],
    exceptions: Sequence[SchemaException],
    allow: Sequence[str],
    today: date,
) -> tuple[list[Entry], list[Entry], list[Entry], set[str]]:
    """Разложить находки: действующие, исключённые, просроченные; и сработавшие ключи."""
    by_key = {exc.key: exc for exc in exceptions}
    active: list[Entry] = []
    excepted: list[Entry] = []
    expired: list[Entry] = []
    used: set[str] = set()
    for key, entry in found.items():
        exc = by_key.get(key)
        if key in allow:
            used.add(key)
            excepted.append(_with(entry, "flag", exc.reason if exc else "", None))
        elif exc is not None:
            used.add(key)
            if exc.until is None or exc.until >= today:
                excepted.append(_with(entry, "site", exc.reason, exc.until))
            else:
                expired.append(_with(entry, "site", exc.reason, exc.until))
                active.append(entry)
        else:
            active.append(entry)
    return active, excepted, expired, used


def _with(entry: Entry, source: str, reason: str, until: date | None) -> Entry:
    return Entry(
        entry.key,
        entry.code,
        entry.file,
        entry.path,
        entry.value,
        entry.finding,
        entry.pages,
        reason,
        until,
        source,
    )


def _top(path: str) -> str:
    return path.split(".", 1)[0]


@dataclass
class SchemaCheck:
    env_prod: bool
    allow: list[str]
    exceptions: list[SchemaException]
    today: date
    findings: dict[str, Entry] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)
    pending: set[str] = field(default_factory=set)
    nodes: int = 0
    graphs: list[tuple[Any, list[dict[str, Any]]]] = field(default_factory=list)

    def page(self, page: Any, graph: list[dict[str, Any]], config: SiteConfig, theme: Any) -> None:
        """Проверить граф страницы и накопить находки с происхождением."""
        from_theme, declared, own, shared = _declared_kinds(page, config, theme)

        self.graphs.append((page, graph))
        seen: set[str] = set()
        for index, node in enumerate(graph):
            if not node:
                continue
            self.nodes += 1
            result = validate(node)
            self.pending |= result.pending
            for finding in result.findings:
                self._add(seen, page, node, index, finding, declared, from_theme, own, shared)

    def _add(
        self,
        seen: set[str],
        page: Any,
        node: dict[str, Any],
        index: int,
        finding: Finding,
        declared: list[str],
        from_theme: list[str],
        own: dict[str, Any],
        shared: dict[str, Any],
    ) -> None:
        if index < len(declared):
            kind = declared[index]
            file, path = self._declared(page, kind, index, finding.path, from_theme, own, shared)
        elif str(node.get("@type")) in _ENGINE_KINDS:
            file, path = ENGINE, f"{node.get('@type')}.{finding.path}"
        elif self._is_entity(node, shared):
            file, path = SITE, f"schema.entity.{finding.path}"
        else:
            # узел движка, о котором политика пока не знает: не site.yaml
            file, path = ENGINE, f"{node.get('@type')}.{finding.path}"
        key = make_key(finding.code, file, path)
        if key in seen:
            return
        seen.add(key)
        known = self.findings.get(key)
        if known:
            known.pages += 1
        else:
            self.findings[key] = Entry(key, finding.code, file, path, finding.value, finding)

    def images(
        self,
        page: Any,
        graph: list[dict[str, Any]],
        config: SiteConfig,
        exists: Callable[[str], bool],
        theme: Any,
    ) -> None:
        """SCH006: картинка из разметки своего сайта, которой нет в сборке."""
        from_theme, declared, own, shared = _declared_kinds(page, config, theme)
        seen: set[str] = set()
        for index, node in enumerate(graph):
            if not node:
                continue
            for inner, url in image_refs(node):
                rel = local_path(url, config)
                if rel is None or exists(rel):
                    continue
                finding = Finding("SCH006", inner, url, {"prop": inner, "url": url})
                self._add(seen, page, node, index, finding, declared, from_theme, own, shared)

    @staticmethod
    def _is_entity(node: dict[str, Any], shared: dict[str, Any]) -> bool:
        """Сквозной узел site.yaml: тип совпал с объявленным в schema.entity."""
        declared = shared.get("entity")
        if not isinstance(declared, dict) or not declared:
            return False
        return str(node.get("@type")) == str(declared.get("@type"))

    @staticmethod
    def _declared(
        page: Any,
        kind: str,
        index: int,
        inner: str,
        from_theme: list[str],
        own: dict[str, Any],
        shared: dict[str, Any],
    ) -> tuple[str, str]:
        if inner == "@type" or inner.startswith("@type."):
            if index < len(from_theme):
                return THEME, f"types.{page.type}.jsonld.{index}"
            return page.source, f"schema.{kind}"
        head = _top(inner)
        block = own.get(kind)
        if isinstance(block, dict) and head in block:
            return page.source, f"schema.{kind}.{inner}"
        block = shared.get(kind)
        if isinstance(block, dict) and head in block:
            return SITE, f"schema.{kind}.{inner}"
        return ENGINE, f"{kind}.{inner}"

    def finish(self, collector: Any, lang: str) -> SchemaSection:
        """Применить исключения и строгость; записать ошибки и предупреждения."""
        active, excepted, expired, used = _apply(
            self.findings, self.exceptions, self.allow, self.today
        )
        self.used |= used
        for entry in active:
            detail, hint = texts(entry.finding, lang)
            if self.env_prod:
                collector.errors.append(
                    HeronError(
                        entry.code,
                        detail,
                        path=entry.file,
                        hint=f"{hint}\n{say(lang, 'schema_key', finding=entry.key).strip()}",
                    )
                )
            else:
                collector.warnings.append(
                    Warning_(
                        f"{entry.code} {entry.file}:{entry.path} - {detail}",
                        path=entry.file,
                        kind=KIND,
                    )
                )
        unused = [exc.key for exc in self.exceptions if exc.key not in self.findings]
        unused += [key for key in self.allow if key not in self.findings and key not in unused]
        for key in unused:
            collector.warnings.append(Warning_(say(lang, "schema_unused", finding=key), kind=KIND))
        for entry in expired:
            collector.warnings.append(
                Warning_(
                    say(lang, "schema_expired", finding=entry.key, until=entry.until),
                    path=entry.file,
                    kind=KIND,
                )
            )
        return SchemaSection(
            release=vocab().release,
            nodes=self.nodes,
            env_prod=self.env_prod,
            findings=active,
            excepted=excepted,
            unused=unused,
            expired=expired,
            pending=sorted(self.pending),
        )


@dataclass
class SiteFindings:
    active: list[Entry] = field(default_factory=list)
    excepted: list[Entry] = field(default_factory=list)
    expired: list[Entry] = field(default_factory=list)
    unused: list[str] = field(default_factory=list)


def site_findings(
    config: SiteConfig, today: date | None = None, allow: Sequence[str] = ()
) -> SiteFindings:
    """Проверить только узлы site.yaml (без страниц и темы): для анкеты."""
    from heron.modules import jsonld

    today = today or today_for_build()
    shared = config.extras.get("schema", {})
    shared = shared if isinstance(shared, dict) else {}
    found: dict[str, Entry] = {}
    for lang in config.site.languages:
        nodes: list[tuple[str, dict[str, Any]]] = []
        node = jsonld.entity(config, lang)
        if node:
            nodes.append(("entity", node))
        for kind, block in shared.items():
            if kind == "entity" or not isinstance(block, dict):
                continue
            filled = jsonld._fill(block, jsonld._data(config, lang), lang)
            nodes.append((kind, {"@type": kind, **(filled if isinstance(filled, dict) else {})}))
        for kind, graph_node in nodes:
            for finding in validate(graph_node).findings:
                path = f"schema.{kind}.{finding.path}"
                key = make_key(finding.code, SITE, path)
                if key not in found:
                    found[key] = Entry(key, finding.code, SITE, path, finding.value, finding)
    active, excepted, expired, _ = _apply(found, config.schema_exceptions, allow, today)
    unused = [
        exc.key
        for exc in config.schema_exceptions
        if exc.key.split(":", 2)[1] == SITE and exc.key not in found
    ]
    unused += [k for k in allow if k.split(":", 2)[1:2] == [SITE] and k not in found]
    return SiteFindings(active, excepted, expired, unused)
