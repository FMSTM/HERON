"""Отчёт `check` и сводка долгов по контенту.

Замена схемы валидации, от которой отказались ради простоты входа: контроль
остаётся, но не требует писать и поддерживать схемы.

Сводка долгов — тот самый список к заказчику, который иначе теряется. Он
печатается после каждой сборки, а не вспоминается раз в квартал.

Спецификация: docs/spec/21-engine.md, раздел 12.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import unquote

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core.errors import Collector
from heron.core.models import Site

LINK = re.compile(r'href="(/[^"#?]*)')
MODULE_CALL = re.compile(r"mod\.([a-z_][a-z0-9_]*)\s*\(")


@dataclass(slots=True)
class Report:
    """Что движок знает о сайте после обхода."""

    pages_by_lang: Counter = field(default_factory=Counter)
    pages_by_type: Counter = field(default_factory=Counter)
    missing_sections: dict[str, list[str]] = field(default_factory=dict)
    unused_sections: list[tuple[str, str]] = field(default_factory=list)
    unused_modules: list[str] = field(default_factory=list)
    broken_links: list[tuple[str, str]] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    nameless_in_nav: list[str] = field(default_factory=list)
    untranslated: dict[str, list[str]] = field(default_factory=dict)

    def render(self) -> str:
        """Отчёт текстом — то, что печатается после сборки."""
        lines: list[str] = []

        by_lang = ", ".join(
            f"{lang}: {count}" for lang, count in sorted(self.pages_by_lang.items())
        )
        lines.append(f"Страниц — {sum(self.pages_by_lang.values())} ({by_lang})")
        by_type = ", ".join(
            f"{name}: {count}" for name, count in sorted(self.pages_by_type.items())
        )
        lines.append(f"Типы — {by_type}")

        if self.untranslated:
            lines.append("")
            lines.append("Не переведено:")
            for lang, pages in sorted(self.untranslated.items()):
                shown = ", ".join(pages[:5]) + (" …" if len(pages) > 5 else "")
                lines.append(f"  {lang} — {len(pages)}: {shown}")

        if self.missing_sections:
            lines.append("")
            lines.append("Не заполнено:")
            for section, pages in sorted(self.missing_sections.items()):
                shown = ", ".join(pages[:5]) + (" …" if len(pages) > 5 else "")
                lines.append(f"  {section:12} — {len(pages)} страниц: {shown}")

        if self.nameless_in_nav:
            lines.append("")
            lines.append("В меню, но без короткого имени — покажется имя файла:")
            for source in self.nameless_in_nav[:20]:
                lines.append(f"  {source}")

        if self.unused_sections:
            lines.append("")
            lines.append("Секции, которых тема не использует (опечатка в якоре?):")
            for source, section in self.unused_sections[:20]:
                lines.append(f"  {source}: {section}")

        if self.unused_modules:
            lines.append("")
            lines.append(
                "Модули темы, которые не зовёт ни один шаблон: " + ", ".join(self.unused_modules)
            )

        if self.broken_links:
            lines.append("")
            lines.append("Ссылки в никуда:")
            for source, href in self.broken_links[:20]:
                lines.append(f"  {source} -> {href}")

        if self.orphans:
            lines.append("")
            lines.append("На эти страницы никто не ссылается: " + ", ".join(self.orphans[:10]))

        return "\n".join(lines) + "\n"


def build(site: Site, config: SiteConfig, theme: ThemeConfig, theme_dir=None) -> Report:
    """Собрать отчёт по обойдённому сайту."""
    report = Report()

    for page in site.pages:
        report.pages_by_lang[page.lang] += 1
        report.pages_by_type[page.type] += 1

    # чего не хватает по типам, по мнению темы
    missing: dict[str, list[str]] = defaultdict(list)
    for page in site.pages:
        wanted = theme.sections_of(page.type)
        for section_id in wanted:
            if not page.has(section_id):
                missing[section_id].append(page.source)
        if wanted:
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

    # внутренние ссылки
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
                elif not href.startswith(("/img/", "/static/", "/assets/")):
                    report.broken_links.append((page.source, href))

    for page in site.pages:
        if page.url == "/" or page.parent is not None or page.url in linked:
            continue
        in_nav = any(page in group for groups in site.nav.values() for group in groups.values())
        if not in_nav:
            report.orphans.append(page.url)

    # модули темы, которые никто не зовёт
    if theme_dir is not None:
        called: set[str] = set()
        for template in (theme_dir / "templates").glob("*.html"):
            called.update(MODULE_CALL.findall(template.read_text(encoding="utf-8")))
        for template in theme_dir.glob("*.html"):
            called.update(MODULE_CALL.findall(template.read_text(encoding="utf-8")))
        available = {path.stem for path in (theme_dir / "modules").glob("*.html")}
        report.unused_modules = sorted(available - {name.replace("_", "-") for name in called})

    return report


def summary(collector: Collector) -> str:
    """Короткая сводка ошибок и предупреждений."""
    lines: list[str] = []
    for error in collector.errors:
        lines.append(str(error))
    if collector.warnings:
        lines.append("")
        lines.append(f"Предупреждений — {len(collector.warnings)}:")
        for warning in collector.warnings[:30]:
            where = f"{warning.path}: " if warning.path else ""
            lines.append(f"  {where}{warning.message}")
        if len(collector.warnings) > 30:
            lines.append(f"  … и ещё {len(collector.warnings) - 30}")
    return "\n".join(lines)
