"""Отчёт `check` и сводка долгов по контенту.

Замена схемы валидации, от которой отказались ради простоты входа: контроль
остаётся, но не требует писать и поддерживать схемы.

Сводка долгов — тот самый список к заказчику, который иначе теряется. Он
печатается после каждой сборки, а не вспоминается раз в квартал.

Спецификация: docs/spec/21-engine.md, раздел 12.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

import heron
from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core import links as links_module
from heron.core import media, notes
from heron.core.errors import Collector, HeronError, Warning_
from heron.core.models import Site
from heron.messages import Msg, rendered
from heron.modules.sitemap import indexable

LINK = re.compile(r'href="(/[^"#?]*)')
MODULE_CALL = re.compile(r"mod\.([a-z_][a-z0-9_]*)\s*\(")
# Вызов модуля по имени из переменной: `mod[name](…)`, `mod|attr(name)`.
# Какие модули так зовутся, по тексту шаблона не узнать — и тогда честнее
# промолчать, чем объявить половину темы лишней.
DYNAMIC_CALL = re.compile(r"\bmod\s*(?:\[|\|\s*attr\b)")


def unused_modules(theme_dir: Path) -> list[str]:
    """Модули темы, которые не зовёт ни один шаблон.

    Смотрим все шаблоны темы на любой глубине: типы, базу, partials и сами
    модули — модуль вправе позвать другой. Вызов модулем самого себя не
    считается: такой модуль всё равно никто не рисует.
    """
    modules = theme_dir / "modules"
    available = {path.stem for path in modules.glob("*.html")} if modules.is_dir() else set()
    if not available:
        return []
    called: set[str] = set()
    for template in sorted(theme_dir.rglob("*.html")):
        try:
            text = template.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if DYNAMIC_CALL.search(text):
            return []
        own = template.stem if template.parent == modules else None
        called.update(
            name.replace("_", "-")
            for name in MODULE_CALL.findall(text)
            if name.replace("_", "-") != own
        )
    return sorted(available - called)


@dataclass
class KitStatus:
    """Что известно о комплекте для агентов в папке сайта (20 §1)."""

    present: bool = False
    engine: str | None = None
    lang: str | None = None
    current: bool | None = None
    disabled: bool = False

    def as_json(self) -> dict[str, object]:
        """Поле `kit` из `check --json` (21 §10)."""
        return {
            "present": self.present,
            "engine": self.engine,
            "lang": self.lang,
            "current": self.current,
        }


# Манифест комплекта — несколько сотен строк; больше — не манифест.
KIT_MANIFEST_LIMIT = 64 * 1024
# re.ASCII: \d без него — любые цифры Юникода («٠.١»), версия движка — только ASCII
_ENGINE = re.compile(r"\d+(\.\d+){1,3}([.+-]?[0-9A-Za-z.+-]*)?\Z", re.ASCII)
_LANGS = ("ru", "en")

# Метки в данных отчёта, которые переводятся при печати: список без имени
# (`uneven_keys`) и корень сайта (`notes_missing`).
LIST = "список"
ROOT = "корень"


def kit_status(site_root: Path | None, config: SiteConfig) -> KitStatus:
    """Прочитать манифест комплекта мягко: любой сбой — одна строка-сведение.

    Вызывается только из `check`: сборка и просмотр манифест не читают.
    """
    disabled = getattr(config.build, "agents", None) is False
    if site_root is None:
        return KitStatus(disabled=disabled)
    folder = Path(site_root) / "agents"
    if not folder.is_dir():
        return KitStatus(disabled=disabled)
    status = KitStatus(present=True, disabled=disabled)
    manifest = folder / "heron-kit.yaml"
    try:
        # is_file до открытия: FIFO и каталог не читаем (чтение FIFO зависает)
        if not manifest.is_file() or manifest.stat().st_size > KIT_MANIFEST_LIMIT:
            return status
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — битый манифест не ошибка (21 §4), в т. ч. RecursionError
        return status
    if not isinstance(data, dict):
        return status
    engine, lang = data.get("engine"), data.get("lang")
    if isinstance(engine, (str, int, float)) and not isinstance(engine, bool):
        text = str(engine)
        if len(text) <= 32 and _ENGINE.match(text):
            status.engine = text
            status.current = text == heron.__version__
    if isinstance(lang, str) and lang in _LANGS:
        status.lang = lang
    return status


def schema_lines(section, lang: str) -> list[str]:
    """Строки раздела проверки разметки: находки, исключения, лишние, pending."""
    from heron.messages import say

    if not (section.nodes or section.findings or section.excepted or section.unused):
        return []
    count = len(section.findings)
    prod = section.env_prod
    lines = [
        say(
            lang,
            "schema_head",
            release=section.release,
            nodes=section.nodes,
            n=count,
            errors=count if prod else 0,
            warnings=0 if prod else count,
        )
    ]
    for entry in section.findings:
        lines.append(
            say(
                lang,
                "schema_finding",
                code=entry.code,
                file=entry.file,
                path=entry.path,
                detail=entry.detail(lang),
                pages=entry.pages,
            )
        )
        lines.append(say(lang, "schema_key", finding=entry.key))
    if section.excepted:
        lines.append(say(lang, "schema_exceptions_head", n=len(section.excepted)))
        for entry in section.excepted:
            if entry.source == "flag":
                lines.append("  " + say(lang, "schema_exception_flag", finding=entry.key))
            else:
                until = entry.until.isoformat() if entry.until else "-"
                lines.append(
                    say(
                        lang,
                        "schema_exception_site",
                        finding=entry.key,
                        reason=entry.reason,
                        until=until,
                        source="site.yaml",
                    )
                )
    lines.extend(say(lang, "schema_unused", finding=key) for key in section.unused)
    lines.extend(say(lang, "schema_expired", finding=e.key, until=e.until) for e in section.expired)
    if section.pending:
        lines.append(say(lang, "schema_pending", props=", ".join(section.pending)))
    return lines


@dataclass(slots=True)
class Report:
    """Что движок знает о сайте после обхода."""

    pages_by_lang: Counter = field(default_factory=Counter)
    pages_by_type: Counter = field(default_factory=Counter)
    missing_sections: dict[str, list[str]] = field(default_factory=dict)
    format_mismatch: list[tuple[str, str, str, str]] = field(default_factory=list)
    unused_sections: list[tuple[str, str]] = field(default_factory=list)
    unused_modules: list[str] = field(default_factory=list)
    broken_links: list[tuple[str, int, str]] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    nameless_in_nav: list[str] = field(default_factory=list)
    untranslated: dict[str, list[str]] = field(default_factory=dict)
    unused_media: list[str] = field(default_factory=list)
    static_media: list[str] = field(default_factory=list)
    notes_missing: list[str] = field(default_factory=list)
    uneven_keys: list[tuple[str, str, str, int, int]] = field(default_factory=list)
    schema_nodes: Counter = field(default_factory=Counter)
    # итог проверки разметки по словарю schema.org (heron.schemaorg.policy.SchemaSection)
    schema: Any = None
    # (страниц с ручной датой, всего страниц, источник дат из site.yaml)
    manual_dates: tuple[int, int, str] | None = None
    # размеры хэшей карт nginx и кто их задаёт: движок (auto) или хост (off)
    # результат `nginx -t` на собранном конфиге: (прошёл, вывод) или None
    nginx_test: tuple[bool, str] | None = None
    # None — сведение о комплекте не собиралось (build/serve); считает только check
    kit: KitStatus | None = None
    # язык запуска, а без него язык сайта: для render() и kit_line() без аргумента
    notes_lang: str = "en"

    def kit_line(self, lang: str | None = None) -> str:
        """Одна строка-сведение о комплекте для агентов."""
        from heron.messages import say

        lang = lang or self.notes_lang
        kit = self.kit or KitStatus()
        if kit.disabled:
            return say(lang, "kit_disabled")
        if not kit.present:
            return say(lang, "kit_missing")
        if kit.engine is None:
            return say(lang, "kit_unreadable")
        if kit.current is False:
            return say(lang, "kit_outdated", kit=kit.engine, engine=heron.__version__)
        return say(lang, "kit_found", engine=kit.engine, code=kit.lang or "?")

    def render(self, lang: str | None = None) -> str:
        """Отчёт текстом — то, что печатается после сборки.

        Язык — язык сообщений (`build.notes`, флаг `--notes` или
        `HERON_NOTES` сильнее); не задан — язык пояснений сайта.
        """
        from heron.messages import say

        lang = lang or self.notes_lang
        lines: list[str] = []

        by_lang = ", ".join(
            f"{code}: {count}" for code, count in sorted(self.pages_by_lang.items())
        )
        lines.append(
            say(lang, "report_pages", count=sum(self.pages_by_lang.values()), by_lang=by_lang)
        )
        by_type = ", ".join(
            f"{name}: {count}" for name, count in sorted(self.pages_by_type.items())
        )
        lines.append(say(lang, "report_types", by_type=by_type))

        if self.untranslated:
            lines.append("")
            lines.append(say(lang, "report_untranslated"))
            for code, pages in sorted(self.untranslated.items()):
                shown = ", ".join(pages[:5]) + (" …" if len(pages) > 5 else "")
                lines.append(f"  {code} — {len(pages)}: {shown}")

        if self.missing_sections:
            lines.append("")
            lines.append(say(lang, "report_missing"))
            for section, pages in sorted(self.missing_sections.items()):
                shown = ", ".join(pages[:5]) + (" …" if len(pages) > 5 else "")
                lines.append(
                    say(lang, "report_missing_line", section=section, count=len(pages), shown=shown)
                )

        if self.format_mismatch:
            lines.append("")
            lines.append(say(lang, "report_format"))
            for source, section, want, got in self.format_mismatch[:20]:
                lines.append(
                    say(
                        lang,
                        "report_format_line",
                        source=source,
                        section=section,
                        want=want,
                        got=got,
                    )
                )
            lines.append(say(lang, "report_format_fix"))

        if self.nameless_in_nav:
            lines.append("")
            lines.append(say(lang, "report_nameless"))
            for source in self.nameless_in_nav[:20]:
                lines.append(f"  {source}")

        if self.unused_sections:
            lines.append("")
            lines.append(say(lang, "report_unused_sections"))
            for source, section in self.unused_sections[:20]:
                lines.append(f"  {source}: {section}")

        if self.unused_modules:
            lines.append("")
            lines.append(say(lang, "report_unused_modules", names=", ".join(self.unused_modules)))

        if self.broken_links:
            lines.append("")
            lines.append(say(lang, "report_broken"))
            for source, line, href in self.broken_links[:20]:
                lines.append(f"  {source}:{line} -> {href}")

        if self.orphans:
            lines.append("")
            lines.append(say(lang, "report_orphans", urls=", ".join(self.orphans[:10])))

        if self.schema_nodes:
            by_kind = ", ".join(
                f"{kind}: {count}" for kind, count in sorted(self.schema_nodes.items())
            )
            lines.append("")
            lines.append(say(lang, "report_schema", by_kind=by_kind))
        if self.schema is not None:
            lines.extend(schema_lines(self.schema, lang))

        if self.unused_media:
            lines.append("")
            lines.append(say(lang, "report_unused_media", count=len(self.unused_media)))
            for path in self.unused_media[:20]:
                lines.append(f"  {path}")

        if self.static_media:
            lines.append("")
            lines.append(say(lang, "report_static_media"))
            for path in self.static_media[:20]:
                lines.append(f"  {path}")

        if self.uneven_keys:
            lines.append("")
            lines.append(say(lang, "report_uneven"))
            for owner, where, key, have, total in self.uneven_keys[:20]:
                if where == LIST:
                    where = say(lang, "report_list")
                lines.append(
                    say(
                        lang,
                        "report_uneven_line",
                        owner=owner,
                        where=where,
                        field=key,
                        have=have,
                        total=total,
                    )
                )

        if self.nginx_test is not None:
            passed, output = self.nginx_test
            if passed:
                lines.append(say(lang, "report_nginx_ok"))

        if self.manual_dates:
            manual, total, mode = self.manual_dates
            lines.append("")
            lines.append(say(lang, "report_manual_dates", manual=manual, total=total, mode=mode))

        if self.notes_missing:
            lines.append("")
            folders = [say(lang, "report_root") if f == ROOT else f for f in self.notes_missing]
            lines.append(say(lang, "report_notes_missing", folders=", ".join(folders)))

        if self.kit is not None:
            lines.append("")
            lines.append(self.kit_line(lang))

        return "\n".join(lines) + "\n"


def build(
    site: Site,
    config: SiteConfig,
    theme: ThemeConfig,
    theme_dir=None,
    site_root=None,
    lang: str | None = None,
) -> Report:
    """Собрать отчёт по обойдённому сайту.

    `lang` - язык запуска от вызывающего. Без него (прямой вызов мимо CLI) отчёт
    помнит язык сайта только как умолчание для `render()` и `kit_line()`.
    """
    report = Report()
    report.notes_lang = lang or config.build.notes

    for page in site.pages:
        report.pages_by_lang[page.lang] += 1
        report.pages_by_type[page.type] += 1

    mode = config.build.updated_from
    manual = sum(1 for page in site.pages if page.meta.updated is not None)
    if mode != "manual" and manual:
        report.manual_dates = (manual, len(site.pages), mode)

    # чего не хватает по типам, по мнению темы
    missing: dict[str, list[str]] = defaultdict(list)
    for page in site.pages:
        wanted = theme.sections_of(page.type)
        formats = theme.formats_of(page.type)
        for section_id in wanted:
            if not page.has(section_id):
                missing[section_id].append(page.source)
                continue
            want = formats.get(section_id)
            section = page.section(section_id)
            if want and section is not None and section.kind != want:
                report.format_mismatch.append((page.source, section_id, want, section.kind))
        if wanted and not theme.any_sections(page.type):
            for section_id in page.sections:
                if section_id not in wanted:
                    report.unused_sections.append((page.source, section_id))
    report.missing_sections = dict(missing)

    # страницы меню без короткого имени: в меню уедет латинский слаг
    for groups in site.nav.values():
        for pages in groups.values():
            for page in pages:
                if not page.meta.nav_title and page.source not in report.nameless_in_nav:
                    report.nameless_in_nav.append(page.source)
    report.nameless_in_nav.sort()

    # переводы
    default = config.site.default_lang
    for lang in config.site.languages:
        if lang == default:
            continue
        absent = [p.key or "/" for p in site.of_lang(default) if lang not in p.translations]
        if absent:
            report.untranslated[lang] = sorted(absent)

    # поля, которые есть не у всех элементов списка
    for page in site.pages:
        for section_id, section in page.sections.items():
            report.uneven_keys.extend(_uneven(page.source, section_id, section.data))
    for name, node in (site.data or {}).items():
        report.uneven_keys.extend(_uneven(f"data/{name}", "", node))

    # внутренние ссылки: куда ведут — из готового HTML, потому что язык
    # подставлен уже там; куда не ведут — из исходника, потому что человеку
    # нужен номер строки, а в HTML строк исходника нет
    report.broken_links = links_module.unresolved(site, config)
    linked: set[str] = set()
    for page in site.pages:
        chunks = [page.intro.html if page.intro else "", *(s.html for s in page.sections.values())]
        for chunk in chunks:
            for raw in LINK.findall(chunk):
                # markdown-it процентно кодирует нелатинские адреса,
                # а человеку в отчёте нужно видеть то, что он написал
                href = unquote(raw)
                target = href if href.endswith("/") else href + "/"
                if target in site.by_url:
                    linked.add(target)

    for page in site.pages:
        # Главная языка — не сирота: на неё ведёт переключатель языков,
        # а он живёт в теме, а не в тексте страниц.
        if page.url in ("/", f"/{page.lang}/") or page.parent is not None or page.url in linked:
            continue
        in_nav = any(page in group for groups in site.nav.values() for group in groups.values())
        if not in_nav:
            report.orphans.append(page.url)

    # модули темы, которые никто не зовёт
    if theme_dir is not None:
        report.unused_modules = unused_modules(theme_dir)

    if site_root is not None:
        report.unused_media = media.unused(site, site_root, config)
        report.static_media = _content_in_static(site_root)
        report.notes_missing = _without_notes(site_root)

    return report


_HREF = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


def _seo_text(config: SiteConfig, key: str, **values) -> Msg:
    return Msg(f"report_seo_{key}", **values)


def _norm_href(href: str, domain: str = "") -> str | None:
    """Путь ссылки для сравнения с пунктом меню; чужой хост - None.

    Снимается только свой домен (`domain` - хост окружения): ссылка
    https://other.site/bio/ пунктом меню /bio/ не считается.
    """
    href = unquote(href.strip()).split("#", 1)[0].split("?", 1)[0]
    host = re.match(r"^(?:https?:)?//([^/]+)", href, re.IGNORECASE)
    if host:
        if host.group(1).lower() != domain.lower():
            return None
        href = href[host.end() :]
    if not href.startswith("/"):
        href = "/" + href
    return href.rstrip("/") + "/" if href != "/" else "/"


def nav_empty(site: Site, config: SiteConfig) -> list[Warning_]:
    """nav.main пуст: поисковик не увидит разделов сайта."""
    if config.nav.main:
        return []
    return [Warning_(_seo_text(config, "nav_empty"), path="site.yaml", kind="seo")]


def pages_without_cover(site: Site, config: SiteConfig) -> list[Warning_]:
    """Индексируемые страницы без обложки: предупреждение, не ошибка."""
    missing = [
        page
        for lang in config.site.languages
        for page in site.of_lang(lang)
        if indexable(page) and page.cover_source(config) is None
    ]
    if not missing:
        return []
    return [Warning_(_seo_text(config, "no_cover", n=len(missing)), kind="seo")]


def duplicate_titles(site: Site, config: SiteConfig) -> list[Warning_]:
    """Одинаковый title (заголовок + суффикс) у индексируемых страниц одного языка."""
    result: list[Warning_] = []
    for lang in config.site.languages:
        # суффикс по языкам: title_suffix_ru -> seo.i18n["title_suffix"]["ru"]
        suffix = config.seo.i18n.get("title_suffix", {}).get(lang, config.seo.title_suffix)
        groups: dict[str, list[str]] = defaultdict(list)
        for page in site.of_lang(lang):
            # то же правило, что у карты сайта: 404 и неопубликованные не в счёт
            if not indexable(page):
                continue
            groups[f"{page.title}{suffix}".strip()].append(page.source)
        for pages in groups.values():
            if len(pages) > 1:
                shown = ", ".join(sorted(pages))
                result.append(
                    Warning_(
                        _seo_text(config, "titles", n=len(pages), lang=lang, pages=shown),
                        kind="seo",
                    )
                )
    return result


def nav_in_html(out: dict[str, str], site: Site, config: SiteConfig) -> list[Warning_]:
    """Ссылки nav.main есть в HTML главной каждого языка.

    `out` - путь файла сборки -> HTML. Меню, вставленное скриптом, в HTML
    главной не видно, и краулер его не получает.
    """
    result: list[Warning_] = []
    default = config.site.default_lang
    for lang in config.site.languages:
        pages = site.nav.get(lang, {}).get("main", [])
        if not pages:
            continue
        home = "index.html" if lang == default else f"{lang}/index.html"
        html = out.get(home)
        if html is None:
            continue
        found = {_norm_href(h, config.site.domain) for h in _HREF.findall(html)}
        if not any(_norm_href(page.url) in found for page in pages):
            result.append(Warning_(_seo_text(config, "nav_html", lang=lang), path=home, kind="seo"))
    return result


def _uneven(owner: str, where: str, node) -> list[tuple[str, str, str, int, int]]:
    """Поля, которые есть у части элементов списка, но не у всех.

    Шаблон пишут по первому элементу, а падает он на шестом: у движка
    строгий режим неопределённых значений, и обращение к отсутствующему
    ключу роняет сборку целиком. Сказать об этом заранее дешевле, чем
    ловить на выкате, и честнее, чем молча подставлять пустоту.

    Это не ошибка контента: у половины документов действительно нет места
    выдачи. Это предупреждение автору шаблона — писать `d.get("place")`.
    """
    if isinstance(node, dict):
        out: list[tuple[str, str, str, int, int]] = []
        for key, value in node.items():
            out.extend(_uneven(owner, f"{where}.{key}" if where else str(key), value))
        return out
    items = [item for item in node if isinstance(item, dict)] if isinstance(node, list) else []
    if len(items) < 2:
        return []
    counts: Counter = Counter()
    for item in items:
        counts.update(item.keys())
    return [
        (owner, where or LIST, str(key), have, len(items))
        for key, have in sorted(counts.items())
        if have < len(items)
    ]


def _without_notes(site_root) -> list[str]:
    """Папки сайта без пояснительной записки.

    Не ошибка и даже не предупреждение: у сайтов, заведённых раньше, записок
    нет вовсе, и это их право. Но сказать об этом стоит — решение «куда
    положить файл» принимается через месяц и в другом окне, а не в момент
    чтения спецификации.
    """
    folders = ["content", "media", "theme", "data", "static", "plugins"]
    missing = [] if (site_root / notes.NOTE).is_file() else [ROOT]
    for name in folders:
        folder = site_root / name
        if folder.is_dir() and not (folder / notes.NOTE).is_file():
            missing.append(f"{name}/")
    return missing


def _content_in_static(site_root) -> list[str]:
    """Картинки и видео в static/ — почти всегда обход обработки.

    Класть файл мимо контента быстрее, чем объявить его, поэтому static/
    зарастает сама собой. Движок там ничего не режет и не проверяет, так что
    молчать об этом нельзя: сайт тихо теряет варианты под брейкпоинты.
    """
    root = site_root / "static"
    if not root.is_dir():
        return []
    suffixes = media.IMAGE_SUFFIXES | {".mp4", ".webm", ".mov", ".m4v", ".ogv"}
    found = [
        path.relative_to(site_root).as_posix()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in suffixes
        and not _belongs_in_static(path.relative_to(root))
    ]
    return found


# Картинки, которым место именно в static/: браузер и поисковики ищут их
# по точному адресу в корне сайта, нарезка им только вредит.
STATIC_IMAGES = (
    "favicon*",
    "apple-touch-icon*",
    "android-chrome-*",
    "mstile-*",
    "safari-pinned-tab*",
    "icon-*.png",
    "icon.svg",
)


def _belongs_in_static(rel) -> bool:
    """Иконка сайта или служебный файл — не контент, не повод для замечания."""
    from fnmatch import fnmatch

    if rel.parts and rel.parts[0] == ".well-known":
        return True
    name = rel.name.lower()
    return any(fnmatch(name, pattern) for pattern in STATIC_IMAGES)


# Порядок видов в сводке: сверху то, что ломает страницу для посетителя,
# снизу то, что заметит только редактор.
ORDER = [
    "картинки",
    "связи",
    "ссылки",
    "меню",
    "переводы",
    "языки",
    "прочее",
    # Ниже — не поломка, а работа, которая ещё не сделана: перевод.
    "нет перевода",
]

# Сколько примеров показывать в каждой группе. Остальное — в файле.
EXAMPLES = 6


def summary(collector: Collector, full: Path | None = None, lang: str = "en") -> str:
    """Короткая сводка ошибок и предупреждений.

    Предупреждения группируются по виду. Сто однотипных замечаний про
    переводы не должны прятать десяток важных про картинки, которых нет
    на диске: раньше сводка резалась на тридцатом по порядку появления,
    и важное просто не доходило до глаз.

    Сводка и тексты замечаний — на языке сообщений (`lang`). Файл `full` —
    для разбора, в нём виды как в коде.
    """
    from heron.messages import kind as kind_label
    from heron.messages import say

    lines: list[str] = []
    for error in collector.errors:
        lines.append(_error_text(error, lang))
    if not collector.warnings:
        return "\n".join(lines)

    groups: dict[str, list] = {}
    for warning in collector.warnings:
        groups.setdefault(getattr(warning, "kind", "прочее") or "прочее", []).append(warning)

    lines.append("")
    lines.append(say(lang, "summary_warnings", count=len(collector.warnings)))
    for kind in [*ORDER, *sorted(set(groups) - set(ORDER))]:
        batch = groups.get(kind)
        if not batch:
            continue
        lines.append(f"  {kind_label(lang, kind)} — {len(batch)}:")
        for warning in batch[:EXAMPLES]:
            where = warning.path or ""
            if where and warning.line:
                where = f"{where}:{warning.line}"
            where = f"{where}: " if where else ""
            lines.append(f"    {where}{rendered(warning.message, lang)}")
        if len(batch) > EXAMPLES:
            lines.append(say(lang, "summary_more", count=len(batch) - EXAMPLES))

    if full is not None:
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(
                "\n".join(
                    f"{getattr(w, 'kind', '') or 'прочее'}\t"
                    f"{w.path or ''}{f':{w.line}' if w.path and w.line else ''}\t"
                    f"{rendered(w.message, lang)}"
                    for w in collector.warnings
                )
                + "\n",
                encoding="utf-8",
            )
            lines.append(say(lang, "summary_full", path=full))
        except OSError:
            pass
    return "\n".join(lines)


def _error_text(error, lang: str) -> str:
    """Ошибка одной строкой, как `str(HeronError)`, но рамка — на языке сообщений."""
    from heron.messages import say

    where = error.path or say(lang, "summary_unknown_file")
    if error.line is not None:
        where = f"{where}:{error.line}"
    text = f"{error.code} {where}: {rendered(error.message, lang)}"
    if error.hint:
        text = f"{text}\n" + say(lang, "error_hint", hint=rendered(error.hint, lang))
    return text


# --- старые адреса: heron check --old-urls ------------------------------------------


def read_old_urls(path: Path) -> list[str]:
    """Адреса из файла: по строке на адрес или выгрузка Search Console (CSV).

    Пустые строки и строки с # пропускаются. В строке с запятой или табом
    берётся первый столбец, похожий на URL (начинается с / или со схемы);
    строка без такого столбца (заголовок CSV) пропускается.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise HeronError(
            "E030",
            Msg("report_old_not_utf8", byte=error.start),
            path=str(path),
            hint=Msg("report_old_not_utf8_hint"),
        ) from error
    urls: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cells = next(csv.reader([line.replace("\t", ",")]))
        pick = [c.strip() for c in cells if c.strip().startswith(("/", "http://", "https://"))]
        if _looks_like_url(line):
            urls.append(line)
        elif pick:
            urls.append(pick[0])
    return urls


def _looks_like_url(line: str) -> bool:
    return line.startswith(("/", "http://", "https://")) and "," not in line and "\t" not in line


def old_urls(urls: list[str], site: Site, config: SiteConfig) -> tuple[list[Warning_], str]:
    """Предупреждения по адресам без пути и строка сводки (Msg, язык при показе)."""
    warnings: list[Warning_] = []
    seen: set[str] = set()
    for url in urls:
        # повторы - как их видит nginx: без схемы и хоста, слеш не важен
        key = links_module.old_key(url)
        if key in seen:
            continue
        seen.add(key)
        if links_module.resolve_old(url, site, config) is not None:
            continue
        if links_module.is_old_gone(url, config):
            continue
        target = links_module.suggest_target(url, site, config)
        shown = urlsplit(url).path or url
        warnings.append(
            Warning_(
                Msg("report_old_lost", url=shown, target=target.url, file=target.source),
                path="old-urls",
                kind="редиректы",
            )
        )
    summary = Msg("report_old_summary", total=len(seen), lost=len(warnings))
    return warnings, summary
