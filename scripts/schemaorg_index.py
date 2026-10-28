#!/usr/bin/env python3
"""Сборка компактного индекса словаря schema.org из закреплённого релиза.

Скрипт разработчика, не команда heron. Только stdlib. Повторный прогон на том же
источнике даёт байт-в-байт тот же файл.

    python3 scripts/schemaorg_index.py [--release 29.3] [--commit <sha>]
        [--sha256 <hex>] [--source <файл>] [--out <файл>]

Коды выхода: 0 - индекс записан; 2 - sha256 не совпал, нет источника, файл не разбирается.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

RELEASE = "29.3"
COMMIT = "020b8681dad2e50c1dd9e2700a703b0bb1c5c6fa"
SHA256 = "3accdd18eb0b1e118938de8fb301ad0e332ed8e7b27ccecf3f753a8712ad1d73"
URL = (
    "https://raw.githubusercontent.com/schemaorg/schemaorg/{commit}"
    "/data/releases/{release}/schemaorg-all-https.jsonld"
)
ROOT = Path(__file__).resolve().parent.parent

CLASS = "rdfs:Class"
PROPERTY = "rdf:Property"
DATATYPE = "schema:DataType"
SECTIONS = ("pending", "health-lifesci", "auto", "bib", "attic", "meta")


class SourceError(Exception):
    """Источник не получен, не совпал по sha256 или не разбирается."""


def name(term_id: str) -> str:
    return term_id.removeprefix("schema:")


def ids(value: Any) -> list[str]:
    """Список @id из dict или list (строки берутся как есть)."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            if "@id" in item:
                out.append(name(str(item["@id"])))
        else:
            out.append(name(str(item)))
    return sorted(set(out))


def types(term: dict[str, Any]) -> list[str]:
    value = term.get("@type", [])
    return [value] if isinstance(value, str) else list(value)


def part(term: dict[str, Any]) -> str:
    """Раздел schema.org из schema:isPartOf; нет - core."""
    for ref in ids(term.get("schema:isPartOf")):
        host = ref.split("://", 1)[-1].split(".", 1)[0]
        if host in SECTIONS:
            return host
    return "core"


def meta(term: dict[str, Any]) -> dict[str, Any]:
    ext = part(term)
    superseded = ids(term.get("schema:supersededBy"))
    return {"ext": ext, "superseded_by": superseded, "attic": ext == "attic"}


def build(raw: bytes, *, release: str, commit: str, sha256: str, url: str) -> dict[str, Any]:
    try:
        graph = json.loads(raw.decode("utf-8"))["@graph"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SourceError(f"файл не разбирается: {exc}") from exc

    terms = {name(t["@id"]): t for t in graph if isinstance(t, dict) and "@id" in t}
    datatypes: dict[str, list[str]] = {}
    classes: dict[str, dict[str, Any]] = {}
    properties: dict[str, dict[str, Any]] = {}
    enums: dict[str, set[str]] = {}
    members: dict[str, list[str]] = {}
    member_meta: dict[str, dict[str, Any]] = {}

    for key, term in terms.items():
        kinds = types(term)
        if PROPERTY in kinds:
            entry = {
                "domain": ids(term.get("schema:domainIncludes")),
                "range": ids(term.get("schema:rangeIncludes")),
                **meta(term),
            }
            inverse = ids(term.get("schema:inverseOf"))
            if inverse:
                entry["inverse"] = inverse[0]
            properties[key] = entry
            continue
        parents = ids(term.get("rdfs:subClassOf"))
        is_class = CLASS in kinds
        if is_class or parents:
            entry = {"parents": parents, **meta(term)}
            if not is_class:
                entry["dual"] = True
            classes[key] = entry
        if DATATYPE in kinds:
            continue
        enum_types = sorted(name(k) for k in kinds if k not in (CLASS, PROPERTY, DATATYPE))
        for enum in enum_types:
            enums.setdefault(enum, set()).add(key)
        if enum_types:
            members[key] = enum_types
            if key not in classes:
                member_meta[key] = meta(term)

    # типы данных: DataType в @type и все их потомки по rdfs:subClassOf
    for key, term in terms.items():
        if DATATYPE in types(term):
            datatypes[key] = ids(term.get("rdfs:subClassOf"))
    grew = True
    while grew:
        grew = False
        for key, term in terms.items():
            parents = ids(term.get("rdfs:subClassOf"))
            if key not in datatypes and any(p in datatypes for p in parents):
                datatypes[key] = parents
                grew = True

    every = [*classes.values(), *properties.values(), *member_meta.values()]
    return {
        "release": release,
        "source": {"url": url, "commit": commit, "sha256": sha256, "bytes": len(raw)},
        "license": {
            "name": "CC BY-SA 3.0",
            "url": "https://creativecommons.org/licenses/by-sa/3.0/",
            "attribution": (
                f"Schema.org vocabulary, release {release}, https://schema.org; "
                "compacted into an index by HERON"
            ),
        },
        "counts": {
            "classes": len(classes),
            "properties": len(properties),
            "enums": len(enums),
            # вхождения значений в перечисления: Radiography входит в два
            "members": sum(len(v) for v in enums.values()),
            "superseded": sum(1 for e in every if e["superseded_by"]),
            "attic": sum(1 for e in every if e["attic"]),
        },
        "datatypes": datatypes,
        "classes": classes,
        "properties": properties,
        "enums": {k: sorted(v) for k, v in enums.items()},
        "members": members,
        "member_meta": member_meta,
    }


def dump(index: dict[str, Any]) -> str:
    return json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def read_source(source: Path | None, url: str) -> bytes:
    if source is not None:
        try:
            return source.read_bytes()
        except OSError as exc:
            raise SourceError(f"не читается {source}: {exc}") from exc
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - закреплённый https
            data: bytes = response.read()
            return data
    except (urllib.error.URLError, OSError) as exc:
        raise SourceError(f"нет сети ({exc}): укажите --source <файл>") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", default=RELEASE)
    parser.add_argument("--commit", default=COMMIT)
    parser.add_argument("--sha256", default=SHA256)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    url = URL.format(commit=args.commit, release=args.release)
    out = args.out or ROOT / "heron" / "schemaorg" / f"schemaorg-{args.release}.json"
    try:
        raw = read_source(args.source, url)
        got = hashlib.sha256(raw).hexdigest()
        if got != args.sha256:
            raise SourceError(f"sha256 не совпадает: ожидался {args.sha256}, получен {got}")
        text = dump(build(raw, release=args.release, commit=args.commit, sha256=got, url=url))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    except (SourceError, OSError) as exc:
        print(f"schemaorg_index: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"schemaorg_index: {out} ({len(text.encode('utf-8'))} байт)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
