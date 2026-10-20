"""Ответы конфигуратора и их место в `site.yaml`.

Конфигуратор спрашивает каждый факт один раз и пишет его в одно место. Здесь
обе стороны: `read` достаёт ответы из существующего `site.yaml` (повторный
запуск показывает то, что уже записано), `merge` кладёт ответы обратно, не
трогая того, чего конфигуратор не знает: `gone`, `forms`, `nginx`, свои блоки
сайта переживают любое число запусков.

Ключи доступа сюда не попадают никогда: у них своё хранилище вне папки
сайта (`heron.setup.keys`). Модель ответов — та же для формы в браузере и для
`heron setup --answers файл`, поэтому агент и человек проходят одну проверку.
"""

from __future__ import annotations

import contextlib
import copy
import re
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from heron.contracts.site import LANG_RE, NAME_RE
from heron.contracts.site import domain as clean_domain

HERE = Path(__file__).parent

WAYS = ("git", "dockerhub", "static", "none")
ENVS = ("dev", "prod")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DOCKER_NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
# Движок для сборки сайта: канал (prod, beta), версия или канал с digest.
ENGINE_RE = re.compile(r"^(?:prod|beta|dev|\d+\.\d+\.\d+)(?:@sha256:[0-9a-f]{64})?$")
ENTITY_ID = "#entity"


@cache
def vocab() -> dict[str, Any]:
    """Справочник типов schema.org и полей конфигуратора."""
    return yaml.safe_load((HERE / "vocab.yaml").read_text(encoding="utf-8"))


def lineage(kind: str) -> list[str]:
    """Тип и все его родители, от общего к частному."""
    types = vocab()["types"]
    chain: list[str] = []
    while kind and kind in types and kind not in chain:
        chain.insert(0, kind)
        kind = types[kind].get("parent")
    return chain


def fields_of(kind: str) -> list[str]:
    """Поля типа: общие, затем поля родителей, затем свои."""
    out: list[str] = list(vocab()["common"])
    for name in lineage(kind):
        for field_name in vocab()["types"][name].get("fields", []):
            if field_name not in out:
                out.append(field_name)
    return out


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SiteAnswers(Model):
    name: str = ""
    domain: str = ""
    preview_domain: str = ""
    languages: list[str] = Field(default_factory=lambda: ["en"])
    default_lang: str = ""

    @field_validator("domain", "preview_domain")
    @classmethod
    def _domain(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        found = clean_domain(value)
        if found is None:
            raise ValueError(f"{value!r}: domain without scheme and slashes, e.g. example.com")
        return found

    @field_validator("languages")
    @classmethod
    def _languages(cls, value: list[str]) -> list[str]:
        out = [item.strip().lower() for item in value if item and item.strip()]
        if not out:
            raise ValueError("at least one language is needed")
        bad = [item for item in out if not LANG_RE.match(item)]
        if bad:
            raise ValueError(f"not a language code: {', '.join(bad)} (expected en, de, pt-br)")
        if len(set(out)) != len(out):
            raise ValueError("languages repeat")
        return out

    @model_validator(mode="after")
    def _default(self) -> SiteAnswers:
        if not self.default_lang:
            self.default_lang = self.languages[0]
        if self.default_lang not in self.languages:
            raise ValueError(f"main language {self.default_lang!r} is not in the list")
        if self.preview_domain and self.preview_domain == self.domain:
            raise ValueError("the service domain must differ from the working one")
        return self


class ThemeAnswers(Model):
    # keep — оставить тему как есть; starter — встроенная стартовая;
    # name — тема каталога HERON; url — архив по ссылке; file — архив с диска;
    # later — решу потом (ставится стартовая).
    source: Literal["keep", "starter", "name", "url", "file", "later"] = "keep"
    value: str = ""
    demo: bool = True


class AboutAnswers(Model):
    type: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        if value and value not in vocab()["types"]:
            raise ValueError(f"type {value!r} is not in the list; take the nearest broader one")
        return value

    @model_validator(mode="after")
    def _known(self) -> AboutAnswers:
        allowed = set(fields_of(self.type)) if self.type else set(vocab()["common"])
        unknown = sorted(set(self.fields) - allowed)
        if unknown:
            raise ValueError(f"fields not asked for type {self.type or '—'}: {', '.join(unknown)}")
        return self


class SearchAnswers(Model):
    title_suffix: str = ""
    llms_note: dict[str, str] = Field(default_factory=dict)
    og_image: str = ""
    ga4: str = ""
    gtm: str = ""
    allow_prices: bool = False


class PublishAnswers(Model):
    way: Literal["git", "dockerhub", "static", "none"] = "none"
    env: Literal["dev", "prod"] = "dev"
    engine: str = "prod"
    branch: str = "main"
    repo: str = ""
    dockerhub_user: str = ""
    image: str = ""
    static_target: Literal["server", "pages"] = "server"
    server: str = ""
    path: str = ""

    @field_validator("engine")
    @classmethod
    def _engine(cls, value: str) -> str:
        value = (value or "prod").strip()
        if not ENGINE_RE.match(value):
            raise ValueError(
                f"engine {value!r}: prod, beta, a version like 0.1.0, "
                "optionally pinned: prod@sha256:<digest>"
            )
        return value

    @model_validator(mode="after")
    def _needed(self) -> PublishAnswers:
        if self.repo and not REPO_RE.match(self.repo):
            raise ValueError(f"repository {self.repo!r}: owner/name, e.g. you/my-site")
        for value in (self.dockerhub_user, self.image):
            if value and not DOCKER_NAME_RE.match(value):
                raise ValueError(f"{value!r}: lowercase letters, digits, dots, dashes")
        if self.way == "dockerhub" and not (self.dockerhub_user and self.image):
            raise ValueError("Docker Hub needs your user name and the image name")
        if self.way == "static" and self.static_target == "server" and not self.server:
            raise ValueError("static files to a server need the server address")
        if self.server and not re.match(r"^[A-Za-z0-9_.@-]+$", self.server):
            raise ValueError(f"server {self.server!r}: user@host or host")
        if self.path and (".." in self.path.split("/") or not self.path.startswith("/")):
            raise ValueError("the folder on the server is an absolute path without ..")
        return self


class KeysAnswers(Model):
    """Ключи. В site.yaml и git не попадают, хранятся вне папки сайта."""

    github_token: str = ""
    dockerhub_token: str = ""
    db_url: str = ""
    db_key: str = ""


class Answers(Model):
    site: SiteAnswers = Field(default_factory=SiteAnswers)
    theme: ThemeAnswers = Field(default_factory=ThemeAnswers)
    about: AboutAnswers = Field(default_factory=AboutAnswers)
    search: SearchAnswers = Field(default_factory=SearchAnswers)
    publish: PublishAnswers = Field(default_factory=PublishAnswers)
    keys: KeysAnswers = Field(default_factory=KeysAnswers)

    @model_validator(mode="after")
    def _languages_of_notes(self) -> Answers:
        stray = sorted(set(self.search.llms_note) - set(self.site.languages))
        if stray:
            raise ValueError(
                f"note for AI in a language the site does not have: {', '.join(stray)}"
            )
        for name, value in self.about.fields.items():
            if isinstance(value, dict):
                extra = sorted(set(value) - set(self.site.languages))
                if extra:
                    raise ValueError(f"{name}: language not on the site: {', '.join(extra)}")
        return self


# --- site.yaml → ответы ---------------------------------------------------------


def _get(data: Any, dotted: str) -> Any:
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set(data: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _drop(data: dict, dotted: str) -> None:
    parts = dotted.split(".")
    node: Any = data
    trail: list[tuple[dict, str]] = []
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return
        trail.append((node, part))
        node = node[part]
    if isinstance(node, dict):
        node.pop(parts[-1], None)
    # пустые родительские блоки, оставшиеся после удаления, убираем
    for parent, key in reversed(trail):
        if parent.get(key) == {}:
            parent.pop(key)


def read(data: dict[str, Any]) -> Answers:
    """Ответы из уже записанного `site.yaml` — мягко, без падений."""
    site = data.get("site") or {}
    languages = [str(x) for x in (site.get("languages") or ["en"])]
    default = str(site.get("default_lang") or languages[0])
    domains = site.get("domains") or {}
    out: dict[str, Any] = {
        "site": {
            "name": str(site.get("name") or ""),
            "domain": str(site.get("domain") or ""),
            "preview_domain": str(domains.get("dev") or ""),
            "languages": languages,
            "default_lang": default,
        }
    }
    entity = _get(data, "schema.entity") or {}
    kind = entity.get("@type") if isinstance(entity, dict) else None
    kind = kind if isinstance(kind, str) and kind in vocab()["types"] else ""
    fields: dict[str, Any] = {}
    for name in fields_of(kind) if kind else vocab()["common"]:
        spec = vocab()["fields"][name]
        value = _get(data, spec["to"])
        if spec.get("localized"):
            parent, _, leaf = spec["to"].rpartition(".")
            block = _get(data, parent) or {}
            per_lang = {
                lang: block.get(f"{leaf}_{lang}")
                for lang in languages
                if lang != default and isinstance(block, dict) and block.get(f"{leaf}_{lang}")
            }
            if per_lang:
                value = {default: value or "", **per_lang}
        if value not in (None, "", []):
            fields[name] = value
    out["about"] = {"type": kind, "fields": fields}
    seo = data.get("seo") or {}
    analytics = data.get("analytics") or {}
    out["search"] = {
        "title_suffix": str(seo.get("title_suffix") or ""),
        "llms_note": {
            str(k): str(v) for k, v in (seo.get("llms_note") or {}).items() if k in languages
        },
        "og_image": str(seo.get("og_default_image") or ""),
        "ga4": str(analytics.get("ga4") or ""),
        "gtm": str(analytics.get("gtm") or ""),
        "allow_prices": bool(seo.get("allow_prices")),
    }
    publish = data.get("publish") or {}
    if isinstance(publish, dict):
        known = PublishAnswers.model_fields
        out["publish"] = {k: v for k, v in publish.items() if k in known}
    try:
        return Answers.model_validate(out)
    except ValueError:
        # Сырой конфиг не повод отказать в конфигураторе: он и нужен, чтобы
        # конфиг поправить. Берём то, что проходит по отдельности.
        answers = Answers()
        for block in ("site", "about", "search", "publish"):
            with contextlib.suppress(ValueError):
                setattr(
                    answers,
                    block,
                    type(getattr(answers, block)).model_validate(out.get(block) or {}),
                )
        return answers


# --- ответы → site.yaml ---------------------------------------------------------


def _entity(answers: Answers) -> dict[str, Any] | None:
    """Узел schema.org сайта: только поля, на которые есть ответ.

    Значения не копируются, а подставляются из site.yaml (`{{ contact.phone }}`):
    телефон меняется в одном месте, и разметка меняется вместе с подвалом.
    """
    kind = answers.about.type
    if not kind:
        return None
    node: dict[str, Any] = {"@type": kind, "@id": ENTITY_ID}
    for name in fields_of(kind):
        if name not in answers.about.fields:
            continue
        spec = vocab()["fields"][name]
        if spec.get("money") and not answers.search.allow_prices:
            continue
        hole = "{{ " + spec["to"] + " }}"
        prop = spec["prop"]
        if prop.startswith("address."):
            address = node.setdefault("address", {"@type": "PostalAddress"})
            address[prop.split(".", 1)[1]] = hole
        elif prop.startswith("geo."):
            geo = node.setdefault("geo", {"@type": "GeoCoordinates"})
            geo[prop.split(".", 1)[1]] = hole
        elif prop == "worksFor.name":
            node["worksFor"] = {"@type": "Organization", "name": hole}
        elif spec.get("kind") == "media":
            node[prop] = "{{ site.base }}" + "{{ " + spec["to"] + " }}"
        else:
            node[prop] = hole
    node.setdefault("url", "{{ site.base }}")
    return node


def _clean_value(spec: dict[str, Any], value: Any) -> Any:
    kind = spec.get("kind")
    if kind == "lines":
        if isinstance(value, str):
            value = [line.strip() for line in value.splitlines()]
        return [str(item).strip() for item in value or [] if str(item).strip()]
    if kind == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{value!r} is not a number") from None
    if kind == "media" and isinstance(value, str):
        return value.strip().removeprefix("./").removeprefix("/")
    return value.strip() if isinstance(value, str) else value


def merge(data: dict[str, Any], answers: Answers, spec: str) -> dict[str, Any]:
    """Новый site.yaml: прежний конфиг с ответами поверх.

    Ключи, которыми ведает конфигуратор, переписываются (пустой ответ —
    ключ убирается: «ничего не придумано»). Всё прочее остаётся как было.
    """
    out = copy.deepcopy(data) if data else {}
    out.setdefault("heron", spec)
    site = out.setdefault("site", {})
    a = answers.site
    if a.name:
        site["name"] = a.name
    site["domain"] = a.domain or site.get("domain") or "example.com"
    domains = dict(site.get("domains") or {})
    if a.preview_domain:
        domains["dev"] = a.preview_domain
    else:
        domains.pop("dev", None)
    if domains:
        site["domains"] = domains
    else:
        site.pop("domains", None)
    site.setdefault("theme", "main")
    site["default_lang"] = a.default_lang
    site["languages"] = [a.default_lang] + [x for x in a.languages if x != a.default_lang]

    # кто сайт: поля по справочнику, языковые значения — хвостом _<язык>
    default = a.default_lang
    kind = answers.about.type
    asked = fields_of(kind) if kind else list(vocab()["common"])
    for name in vocab()["fields"]:
        spec_field = vocab()["fields"][name]
        target = spec_field["to"]
        parent, _, leaf = target.rpartition(".")
        block = _get(out, parent)
        if isinstance(block, dict):
            for key in [
                k for k in block if re.fullmatch(rf"{re.escape(leaf)}_[a-z]{{2}}(-[a-z]{{2}})?", k)
            ]:
                block.pop(key)
        value = answers.about.fields.get(name) if name in asked else None
        if isinstance(value, dict) and spec_field.get("localized"):
            main = _clean_value(spec_field, value.get(default, ""))
            if main not in (None, "", []):
                _set(out, target, main)
            else:
                _drop(out, target)
            for lang, item in value.items():
                item = _clean_value(spec_field, item)
                if lang != default and item not in (None, "", []):
                    _set(out, f"{parent}.{leaf}_{lang}", item)
            continue
        value = _clean_value(spec_field, value) if value is not None else None
        if value in (None, "", []):
            _drop(out, target)
        else:
            _set(out, target, value)

    for name in ("organization", "contact"):
        if isinstance(out.get(name), dict):
            out[name] = _tidy(out[name])

    entity = _entity(answers)
    schema = out.get("schema") if isinstance(out.get("schema"), dict) else {}
    if entity:
        schema["entity"] = entity
    else:
        schema.pop("entity", None)
    if schema:
        out["schema"] = schema
    else:
        out.pop("schema", None)

    seo = out.setdefault("seo", {})
    s = answers.search
    seo["title_suffix"] = s.title_suffix
    notes = {k: v for k, v in s.llms_note.items() if v.strip()}
    if notes:
        seo["llms_note"] = notes
    else:
        seo.pop("llms_note", None)
    if s.og_image:
        seo["og_default_image"] = s.og_image.strip().removeprefix("./").removeprefix("/")
    else:
        seo.pop("og_default_image", None)
    if s.allow_prices:
        seo["allow_prices"] = True
    else:
        seo.pop("allow_prices", None)
    analytics = out.setdefault("analytics", {})
    analytics["ga4"] = s.ga4 or None
    analytics["gtm"] = s.gtm or None

    p = answers.publish
    if p.way == "none":
        out.pop("publish", None)
    else:
        block: dict[str, Any] = {"way": p.way, "env": p.env, "engine": p.engine}
        if p.way == "git":
            block.update(branch=p.branch or "main")
            if p.repo:
                block["repo"] = p.repo
        elif p.way == "dockerhub":
            block.update(dockerhub_user=p.dockerhub_user, image=p.image)
        else:
            block["static_target"] = p.static_target
            if p.static_target == "server":
                block.update(server=p.server, path=p.path or "/var/www/" + site["domain"])
        out["publish"] = block

    if not NAME_RE.match(str(site.get("theme"))):
        site["theme"] = "main"
    return out


LANG_TAIL = re.compile(r"^(?P<key>.+?)_(?P<lang>[a-z]{2}(?:-[a-z]{2})?)$")


def _tidy(block: dict[str, Any]) -> dict[str, Any]:
    """Перевод — сразу за своим ключом: `city`, `city_de`, затем `country`.

    Иначе каждое сохранение переставляло бы строки, и в git копились бы
    правки, в которых ничего не поменялось.
    """
    bases = [k for k in block if not (LANG_TAIL.match(k) and LANG_TAIL.match(k)["key"] in block)]
    out: dict[str, Any] = {}
    for key in bases:
        out[key] = block[key]
        for other in sorted(block):
            match = LANG_TAIL.match(other)
            if match and match["key"] == key:
                out[other] = block[other]
    out.update({k: v for k, v in block.items() if k not in out})
    return out


ORDER = (
    "heron",
    "site",
    "organization",
    "contact",
    "schema",
    "seo",
    "nav",
    "analytics",
    "publish",
    "build",
    "plugins",
)


def ordered(data: dict[str, Any]) -> dict[str, Any]:
    """Блоки в привычном порядке: сначала свои, затем незнакомые как были."""
    out = {key: data[key] for key in ORDER if key in data}
    out.update({key: value for key, value in data.items() if key not in out})
    return out
