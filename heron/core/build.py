"""Конвейер сборки.

Восемь этапов строго по порядку, каждый может остановить сборку. Один проход,
никакого состояния между запусками: собрать дважды подряд — получить побайтово
одинаковый результат.

Спецификация: docs/spec/21-engine.md, раздел 4.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from heron.contracts import wiring
from heron.contracts.site import SiteConfig, load_site
from heron.contracts.theme import ThemeConfig, load_theme, missing_hints
from heron.core import check as templates_check
from heron.core import data as data_module
from heron.core import (
    dates,
    demo,
    links,
    media,
    notes,
    notfound,
    output,
    paths,
    report,
    resolver,
    tree,
    urls,
)
from heron.core.environment import BuildEnv
from heron.core.errors import Collector, HeronError, Warning_
from heron.core.hooks import Hooks
from heron.core.models import Page, Site
from heron.core.parser import markdown
from heron.core.progress import Progress, Silent
from heron.core.render import env as render_env
from heron.core.render import pages as renderer
from heron.core.render import themeref
from heron.messages import Msg
from heron.modules import feed, jsonld, llms, nginx, redirects, robots, sitemap
from heron.schemaorg import policy
from heron.schemaorg.images import source_exists

SITE_YAML = "site.yaml"
CACHE = ".heron-cache"
DIST = "dist"
STATIC = "static"
ASSETS = "assets"


@dataclass(slots=True)
class Result:
    """Что получилось: где лежит, что внутри, на что жаловался движок."""

    config: SiteConfig
    theme: ThemeConfig
    theme_dir: Path
    site: Site
    collector: Collector
    env: BuildEnv = field(default_factory=BuildEnv)
    report: report.Report | None = None
    written: list[str] = field(default_factory=list)
    # строгий режим, с которым шла сборка: --strict или build.fail_on_warning
    strict: bool = False
    applied: output.Applied | None = None
    # сказанное после записи: на удачу сборки уже не влияет
    notices: list[str] = field(default_factory=list)
    # упавшие завершающие действия (on_build_finished): сайт записан, но
    # то, что плагин делал после записи, не сделано
    finish_errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """Сборка не удалась: ошибки, а в строгом режиме — и предупреждения."""
        return self.collector.failed or (self.strict and bool(self.collector.warnings))


def _page_path(url: str) -> str:
    trimmed = url.strip("/")
    return f"{trimmed}/index.html" if trimmed else "index.html"


def _claim_tree(
    outputs: output.Outputs,
    source: Path,
    prefix: str,
    kind: str,
    owner: Callable[[str], str],
    collector: Collector,
) -> None:
    """Заявить папку как есть, кроме того, чего в сети быть не должно.

    `static/` уезжает байт в байт — вместе со служебной запиской и с тем,
    что насыпал файловый менеджер. И то и другое оказалось бы опубликовано
    по своему адресу.

    Символическая ссылка наружу — E024, а не копия чужого файла в
    публичную сборку (`paths.files`).
    """
    for rel, path in paths.files(source, where=str(source)):
        if any(notes.skip(part) for part in rel.split("/")):
            continue
        outputs.add(
            f"{prefix}{rel}",
            output.Entry(owner=owner(rel), kind=kind, source=path),
            collector,
        )


def for_env(config: SiteConfig, env: BuildEnv) -> None:
    """Подставить домен окружения. Нет такого ключа — остаётся основной.

    Домен выбирается тем же именем окружения, что управляет индексацией:
    иначе появляется второй рычаг, который однажды забудут переключить, и
    прод уезжает в сеть с дев-доменом в каноникле.
    """
    chosen = config.site.domains.get(env.name)
    if chosen:
        config.site.domain = chosen


def prepare(site_root: Path, collector: Collector) -> tuple[SiteConfig, ThemeConfig, Path, Hooks]:
    """Этап 1: конфиги, версия движка, тема, плагины."""
    config = load_site(site_root / SITE_YAML)

    found = resolver.theme(site_root, config.site.theme)
    theme = load_theme(found.path / "theme.yaml")
    wiring.verify_engine(theme, str(found.path / "theme.yaml"))
    collector.warnings.extend(wiring.verify(theme, config, str(site_root / SITE_YAML)))

    hooks = Hooks()
    resolver.plugins(site_root, config.plugins, hooks)
    hooks.call("on_config", config, theme)
    return config, theme, found.path, hooks


WORKERS_ENV = "HERON_WORKERS"


def env_workers() -> int | None:
    """Число процессов из `HERON_WORKERS`: пусто — не задано, иначе 0–64 или ошибка."""
    raw = os.environ.get(WORKERS_ENV, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if not 0 <= value <= 64:
        raise HeronError(
            code="E011",
            message=Msg("build_bad_workers", env=WORKERS_ENV, raw=raw),
            path=WORKERS_ENV,
            hint=Msg("build_bad_workers_hint"),
        )
    return value


SITEMAP_IMAGES = 20


def sitemap_images(config: SiteConfig, manifest: media.Manifest) -> Callable[[Page], list[str]]:
    """Картинки страницы для карты сайта: обложка первой, затем картинки текста.

    Только абсолютные адреса домена окружения, без дублей, не больше
    `SITEMAP_IMAGES` на страницу.
    """
    cover_url = render_env.cover_url(manifest, config)
    prefix = urls.absolute(config, "/")

    def collect(page: Page) -> list[str]:
        found: list[str] = []
        candidates = [cover_url(page)]
        chunks = [page.intro.raw if page.intro else "", *(s.raw for s in page.sections.values())]
        for chunk in chunks:
            for match in media.REFERENCE.finditer(markdown.without_code(chunk)):
                src = paths.normalize(match.group(1))
                if src.lower().endswith(tuple(media.KEEP)):
                    candidates.append(urls.absolute(config, f"/{src}"))
        for href in candidates:
            if href.startswith(prefix) and href not in found:
                found.append(href)
        return found[:SITEMAP_IMAGES]

    return collect


def _homes(outputs: output.Outputs, config: SiteConfig) -> dict[str, str]:
    """HTML главных страниц языков - только то, что смотрит nav_in_html.

    Остальные index.html сборки не читаются: статика вроде static/old/index.html
    в cp1251 этой проверке не нужна и ронять сборку не должна. Главная, которую
    нельзя прочитать (E034), просто не проверяется: это предупреждение, а не
    повод забраковать сборку.
    """
    homes: dict[str, str] = {}
    for lang in config.site.languages:
        rel = urls.home_url(config, lang).lstrip("/") + "index.html"
        try:
            html = outputs.text_of(rel)
        except HeronError:
            continue
        if html is not None:
            homes[rel] = html
    return homes


def run(
    site_root: Path,
    dist: Path | None = None,
    drafts: bool = False,
    with_media: bool = True,
    strict: bool = False,
    env: BuildEnv | None = None,
    progress: Progress | None = None,
    workers: int | None = None,
    allow_schema: Sequence[str] = (),
    notes_lang: str | None = None,
) -> Result:
    """Собрать сайт целиком.

    `notes_lang` - язык запуска: на нём пишутся находки разметки schema.org.

    Процессов на нарезку: аргумент `workers` (флаг `--workers`), затем
    переменная `HERON_WORKERS`, затем `build.workers` из `site.yaml`.

    Кэш нарезанных картинок кладётся рядом с результатом, а не рядом с
    контентом: папка сайта монтируется только на чтение, и пачкать её
    служебными файлами сборка не имеет права.
    """
    collector = Collector()
    env = env or BuildEnv()
    say = progress or Silent()
    if workers is None:
        workers = env_workers()
    site_root = site_root.resolve()
    env = env.stamped(site_root)
    dist = (dist or site_root / DIST).resolve()

    say.step("step_config")
    config, theme, theme_dir, hooks = prepare(site_root, collector)
    # Корень кэша проверяется первым: в него пишет и отчёт о предупреждениях,
    # даже когда сборка упала на контенте.
    media.guard(dist.parent / CACHE)
    paths.layout(site_root, dist, dist.parent / CACHE, sources(site_root, theme_dir))
    rooted(site_root, theme_dir)
    strict = strict or config.build.fail_on_warning
    for_env(config, env)
    say.done("done_config", theme=config.site.theme, langs=len(config.site.languages))

    say.step("step_content")
    site = content(site_root, config, theme, theme_dir, hooks, collector, drafts, env.is_prod)
    say.done("done_pages", count=len(site.pages))

    # Сайт без страниц — нормальное состояние на деве: тему доводят раньше,
    # чем пишут контент. В проде это всегда чья-то ошибка — пустой конвейер,
    # не тот путь, забытый язык, — и выкладывать её наружу нельзя.
    if env.is_prod and not [p for p in site.pages if not p.generated]:
        collector.error(
            "E017",
            Msg("build_prod_no_pages"),
            path=str(site_root / "content"),
            hint=Msg("build_prod_no_pages_hint"),
        )
    # Язык по умолчанию отдаётся из корня. Пуст он — корень сайта отвечает
    # 404, даже если другие языки заполнены целиком. На деве это стадия
    # работы, в проде — витрина без входа.
    elif env.is_prod and not [p for p in site.of_lang(config.site.default_lang) if not p.generated]:
        default = config.site.default_lang
        collector.error(
            "E021",
            Msg("build_prod_empty_default_lang", default=default),
            path=str(site_root / "content" / default),
            hint=Msg("build_prod_empty_default_lang_hint", default=default),
        )

    _roots(site, config, collector, prod=env.is_prod)
    # исполняемый SVG в прод не уходит; на деве и в serve - предупреждение
    svg_files(site_root, theme_dir, collector, error=env.is_prod, cache=dist.parent / CACHE)

    result = Result(
        config=config,
        theme=theme,
        theme_dir=theme_dir,
        site=site,
        collector=collector,
        env=env,
        strict=strict,
    )
    if collector.failed:
        return result

    # Кэш нарезок общий для сборок в одну папку: от плана до записи сборка
    # держит разделяемую блокировку, чтобы уборка не удалила нужное ей.
    cache = dist.parent / CACHE
    output.make_dir(cache / media.SLICES)  # папка над --out недоступна — E035, не «denied»
    with media.using(cache):
        say.step("step_images")
        media.folder(site_root, collector)
        media.check_video(site, collector)
        # План, а не нарезка: шаблонам нужны имена и размеры, а кодировать стоит
        # только то, на что после рендера найдётся ссылка (этап «нарезка» ниже).
        manifest = (
            media.plan(
                site,
                site_root,
                theme.images,
                collector,
                cache_dir=cache,
                strict=strict,
                config=config,
            )
            if with_media
            else media.Manifest()
        )
        if with_media:
            # Мастер, на который ссылается только разметка, едет в сборку целиком:
            # план его не знает, а краулер просит именно этот адрес.
            for src in sorted(media.schema_references(site, config)):
                source = paths.source(site_root, src)
                if src not in manifest.masters and source.is_file():
                    manifest.copies.setdefault(src, source)
        say.done("done_masters", count=len(manifest.items))
        if collector.failed:
            return result

        say.step("step_templates")
        # Черновая сборка пишет, что нарисовал каждый модуль: из этого и из
        # контракта темы собирается служебная справка темы /_heron/theme/.
        seen: demo.Seen | None = None if env.is_prod else set()
        html = renderer.render_site(
            theme_dir,
            site,
            config,
            theme,
            collector,
            manifest,
            env,
            progress=say,
            hooks=hooks,
            seen=seen,
        )
        say.done("done_pages", count=len(html))
        if collector.failed:
            return result

        say.step("step_generators")
        outputs = output.Outputs(overrides={paths.normalize(o) for o in config.build.overrides})

        def claim(files: dict[str, str], kind: str, owner: str) -> None:
            for name, text in files.items():
                outputs.add(name, output.Entry(owner=owner, kind=kind, text=text), collector)

        by_url = {page.url: page for page in site.pages}
        for url, text in html.items():
            page = by_url.get(url)
            owner = Msg(
                "build_owner_page",
                where=page.source if page is not None and page.source else url,
            )
            outputs.add(
                _page_path(url), output.Entry(owner=owner, kind="page", text=text), collector
            )
        not_found = html.get("/404/")
        if not_found:
            claim({"404.html": not_found}, "page", Msg("build_owner_page_404"))
        claim(
            sitemap.generate(
                site, config, sitemap_images(config, manifest) if env.indexable else None
            ),
            "generator",
            Msg("build_owner_sitemap"),
        )
        claim(robots.generate(config, env), "generator", Msg("build_owner_robots"))
        claim(llms.generate(site, config), "generator", Msg("build_owner_llms"))
        moves = redirects.collect(site, collector, config)
        claim(redirects.files(moves), "generator", Msg("build_owner_redirects"))
        claim(nginx.generate(config, moves), "generator", Msg("build_owner_nginx"))
        claim(feed.generate(site, config), "generator", Msg("build_owner_feed"))
        if seen is not None:
            # Справка темы - только в черновой сборке: в боевую, в карту сайта
            # и в llms.txt она не попадает, у неё noindex (21 §7 «Справка темы»).
            found = demo.shown(site, theme, seen)
            claim(
                themeref.pages(
                    theme_dir, site, config, theme, found, manifest, env, hooks, notes_lang
                ),
                "generator",
                Msg("build_owner_theme_ref"),
            )
        say.done()

        for extra in hooks.call("on_generate", site, config):
            if isinstance(extra, dict):
                claim(extra, "plugin", Msg("build_owner_plugin_generate"))

        _claim_tree(
            outputs, site_root / STATIC, "", "static", lambda rel: f"static/{rel}", collector
        )
        _claim_tree(
            outputs,
            theme_dir / ASSETS,
            f"{ASSETS}/",
            "asset",
            lambda rel: Msg("build_owner_theme_asset", rel=rel),
            collector,
        )
        if collector.failed:
            return result

        if with_media:
            # Режем только то, на что ссылается собранный сайт: страницы, карты,
            # разметка, файлы плагинов, стили темы и статика. Всё прочее из плана
            # остаётся в кэше и в сборку не едет.
            say.step("step_slices")
            texts = outputs.texts()
            texts += _texts(theme_dir / ASSETS)
            texts += _texts(site_root / STATIC)
            placed = media.finish(
                manifest,
                site_root,
                theme.images,
                used=media.used_in(texts),
                workers=config.build.workers if workers is None else workers,
                progress=say,
            )
            for item in placed:
                outputs.add(
                    item.rel,
                    output.Entry(
                        owner=item.owner or item.rel,
                        kind="media",
                        source=item.source,
                        link=item.link,
                    ),
                    collector,
                )
            say.done("done_files", count=len(placed))

        outputs.check_tree(collector)
        outputs.check_overrides(collector)

        # Всё, что может забраковать сборку, — до записи: отчёт, разметка,
        # nginx -t. Строгая сборка с предупреждением не трогает прошлую версию.
        result.report = report.build(
            site, config, theme, theme_dir=theme_dir, site_root=site_root, lang=notes_lang
        )
        collector.warnings.extend(report.nav_empty(site, config))
        collector.warnings.extend(report.duplicate_titles(site, config))
        collector.warnings.extend(report.nav_in_html(_homes(outputs, config), site, config))
        # Проверяется то, что действительно ляжет в сборку: конфиг, подменённый
        # статикой через build.overrides, — его байты, а не сгенерированный.
        # Конфиг, который нельзя прочитать или который пуст, — ошибка до записи:
        # nginx -t иначе пропускался, и непроверенный файл уходил в dist.
        try:
            conf = outputs.text_of(nginx.NAME)
        except HeronError as error:
            collector.errors.append(error)
            conf = None
        else:
            if conf is not None and not conf.strip():
                collector.error(
                    "E034",
                    Msg("build_nginx_empty", name=nginx.NAME),
                    path=nginx.NAME,
                    hint=Msg("build_nginx_empty_hint"),
                )
                conf = None
        result.report.nginx_test = nginx.check(conf, collector)
        _schema(
            site,
            config,
            theme,
            collector,
            result.report,
            env,
            allow_schema,
            exists=(lambda rel: rel in outputs.entries) if with_media else None,
        )
        if result.failed:
            return result

        say.step("step_write")
        result.applied = output.commit(dist, outputs)
        say.done("done_files", count=len(outputs.entries))
        result.written = sorted(outputs.entries)

    # После записи: результат уже на месте, хук его видит, но изменить
    # сборку не может. Файлы отсюда больше не принимаются — для них
    # on_generate; вернувший файлы старый плагин получает объяснение.
    # Падение завершающего действия — не падение сборки: сайт уже записан и
    # цел. Это отдельный статус (`finish_errors`), CLI выходит с кодом 3.
    for handler in hooks.handlers.get("on_build_finished", []):
        try:
            returned = handler(site, config, dist)
        except Exception as error:  # noqa: BLE001 — чужой код, любой отказ
            name = getattr(handler, "__module__", "") or Msg("build_plugin_word")
            result.finish_errors.append(
                Msg("build_finish_failed", name=name, kind=type(error).__name__, error=str(error))
            )
            continue
        if isinstance(returned, dict) and returned:
            result.notices.append(Msg("build_finished_returned_files"))
    media.sweep_daily(cache)
    return result


def content(
    site_root: Path,
    config: SiteConfig,
    theme: ThemeConfig,
    theme_dir: Path,
    hooks: Hooks,
    collector: Collector,
    drafts: bool,
    prod: bool = False,
) -> Site:
    """Этапы 2–4, общие для `build` и `check`: обход, разбор, даты, связи.

    `prod` - боевая сборка: страницы с пометкой `translation: pending` не
    публикуются на своём языке (`site.held`), черновая показывает их с плашкой.
    Обе говорят о каждой такой странице предупреждением: с `--strict` это ошибка.

    Расширения применяются одинаково в обоих: свои типы секций, правка
    страницы после разбора, свои связи после обхода. Иначе `check`
    проверял бы не тот сайт, который соберёт `build`.
    """
    md = markdown.make(allow_raw_html=config.build.allow_raw_html)
    site, _ = tree.scan(
        site_root / "content",
        config,
        md,
        collector,
        drafts=drafts,
        custom=hooks.blocks(),
        hold_pending=prod,
    )
    pending_warnings(site, collector)
    placeholders(site, collector, prod)
    anchors_mismatch(site, collector)
    type_fields(site, theme, collector)
    for page in site.pages:
        hooks.call("on_page_parsed", page)
    site.data = data_module.load(site_root / "data", collector)
    dates.resolve(site, site_root, config.build.updated_from, collector)
    dates.check(site, collector)
    hooks.call("on_tree_built", site)
    notfound.ensure(site, config, theme_dir, collector)
    links.resolve(site, config, theme, collector)
    return site


def pending_warnings(site: Site, collector: Collector) -> None:
    """Предупреждение о каждой странице с непереведённым текстом (`translation: pending`)."""
    for page in site.held:
        if page.held_by is not None:
            message = Msg("build_pending_category", lang=page.lang, category=page.held_by)
        else:
            message = Msg("build_pending_held", lang=page.lang)
        collector.warn(message, path=page.source, kind="переводы")
    for page in site.pages:
        if page.meta.pending:
            collector.warn(
                Msg("build_pending_shown", lang=page.lang), path=page.source, kind="переводы"
            )


# Поля SEO-блока, в которых заготовка оставляет метку TODO.
STUB_FIELDS = ("title", "h1", "description", "nav_title", "og_title", "og_description")


def placeholders(site: Site, collector: Collector, prod: bool) -> None:
    """Текст заготовки `page add` / `category add`, который так и не заменили (E040).

    Метка `TODO` в начале поля SEO-блока или заголовка секции, строки-заготовки
    тела на любом языке пояснений (на странице другого языка - тоже заготовка).
    Боевая сборка с ними не публикуется - ошибка с файлом и полем; черновая
    и `check` без `--env prod` - предупреждение.
    """
    from heron.scaffold.page import BODY

    lines = {words[name] for words in BODY.values() for name in ("intro", "content")}
    for page in site.pages:
        found: list[tuple[str, str]] = []
        for name in STUB_FIELDS:
            value = getattr(page.meta, name, None)
            if value is None:
                value = page.meta.extra.get(name)
            if isinstance(value, str) and value.strip().startswith("TODO"):
                found.append((name, value.strip()))
        blocks = [("intro", page.intro)] if page.intro is not None else []
        blocks += list(page.sections.items())
        for section_id, section in blocks:
            if section_id != "intro" and section.title.strip().startswith("TODO"):
                found.append((f"sections.{section_id}.heading", section.title.strip()))
            for line in section.raw.splitlines():
                if line.strip() in lines:
                    found.append((f"sections.{section_id}", line.strip()))
                    break
        for where, text in found:
            message = Msg("build_placeholder", field=where, text=text[:60])
            if prod:
                collector.error(
                    "E040", message, path=page.source, hint=Msg("build_placeholder_hint")
                )
            else:
                collector.warn(message, path=page.source, kind="прочее")


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str | list | dict) and not value)


TYPE_CHECKS = {
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "flag": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, list),
    "date": lambda v: isinstance(v, dt.date | str),
}


def type_fields(site: Site, theme: ThemeConfig, collector: Collector) -> None:
    """Свои поля фронтматтера типа (`types.<тип>.fields`): те же правила, что у редактора.

    Обязательное пустое, значение не из `values`, значение не того типа - E042;
    длина и число пунктов вне пределов - предупреждение.
    """
    for page in site.pages:
        spec = theme.types.get(page.type)
        if spec is None or not spec.fields:
            continue
        for item in spec.fields:
            value = page.meta.get(item.name)
            where = f"{item.name} ({page.type})"
            if _blank(value):
                if item.required:
                    collector.error(
                        "E042",
                        Msg("build_type_field_required", field=item.name, type=page.type),
                        path=page.source,
                        hint=Msg("build_type_field_hint", field=item.name),
                    )
                continue
            check = TYPE_CHECKS.get(item.type)
            if check is not None and not check(value):
                collector.error(
                    "E042",
                    Msg("build_type_field_type", field=where, kind=item.type, value=str(value)),
                    path=page.source,
                    hint=Msg("build_type_field_hint", field=item.name),
                )
                continue
            if item.type == "enum" and str(value) not in item.values:
                collector.error(
                    "E042",
                    Msg(
                        "build_type_field_value",
                        field=where,
                        value=str(value),
                        values=", ".join(item.values),
                    ),
                    path=page.source,
                    hint=Msg("build_type_field_hint", field=item.name),
                )
                continue
            if isinstance(value, str):
                size = len(value.strip())
                if (item.max_length and size > item.max_length) or (
                    item.min_length and size < item.min_length
                ):
                    collector.warn(
                        Msg(
                            "build_type_field_length",
                            field=where,
                            length=size,
                            min=item.min_length or 0,
                            max=item.max_length or "-",
                        ),
                        path=page.source,
                        kind="прочее",
                    )
            if isinstance(value, list):
                count = len(value)
                if (item.max_items and count > item.max_items) or (
                    item.min_items and count < item.min_items
                ):
                    collector.warn(
                        Msg(
                            "build_type_field_items",
                            field=where,
                            count=count,
                            min=item.min_items or 0,
                            max=item.max_items or "-",
                        ),
                        path=page.source,
                        kind="прочее",
                    )


def anchors_mismatch(site: Site, collector: Collector) -> None:
    """Якоря секций - структура страницы: на всех языках одни и те же (предупреждение).

    Студия и `page add` меняют якорь сразу на всех языках; расхождение - след
    ручной правки одного файла: ссылки `#якорь` с других языков ведут в никуда.
    """
    by_key: dict[str, list] = {}
    for page in site.pages:
        by_key.setdefault(page.key, []).append(page)
    for _key, pages in sorted(by_key.items()):
        if len(pages) < 2:
            continue
        base = pages[0]
        anchors = list(base.sections)
        for page in pages[1:]:
            mine = list(page.sections)
            if set(mine) != set(anchors):
                collector.warn(
                    Msg(
                        "build_anchors_differ",
                        lang=page.lang,
                        other=base.lang,
                        missing=", ".join(a for a in anchors if a not in mine) or "-",
                        extra=", ".join(a for a in mine if a not in anchors) or "-",
                    ),
                    path=page.source,
                    kind="переводы",
                )


# Поля SEO-блока, одни на все языки страницы (опросник и студия правят их только на
# основном языке и пишут во все файлы, 21 §10): тип, порядок, обложка, флаги, дата.
SHARED_FIELDS = ("order", "image", "og_image", "noindex", "date", "children_type")
# Свои поля типа без текста - тоже одни на все языки (21 §7, `types.<тип>.fields`).
TEXT_FIELD_TYPES = ("text", "markdown", "list", "link")


def shared_mismatch(site: Site, theme: ThemeConfig, default: str, collector: Collector) -> None:
    """Общие поля страницы расходятся между языками (`heron check`, предупреждение).

    Тип, порядок, обложка, флаги, дата, вид раздела и свои поля темы без текста -
    одни на все языки: расхождение - след ручной правки одного файла (или 0.2,
    где языки правили по отдельности). Сверка - с основным языком.
    """
    by_key: dict[str, list] = {}
    for page in [*site.pages, *site.held]:
        by_key.setdefault(page.key, []).append(page)
    for _key, pages in sorted(by_key.items()):
        if len(pages) < 2:
            continue
        base = next((page for page in pages if page.lang == default), pages[0])
        for page in pages:
            if page is base:
                continue
            names = ["type", *SHARED_FIELDS, *_theme_shared(theme, base.type)]
            differ = [
                name for name in names if _shared_value(page, name) != _shared_value(base, name)
            ]
            if differ:
                collector.warn(
                    Msg(
                        "build_shared_differ",
                        lang=page.lang,
                        other=base.lang,
                        fields=", ".join(differ),
                    ),
                    path=page.source,
                    kind="переводы",
                )


def _theme_shared(theme: ThemeConfig, page_type: str) -> list[str]:
    spec = theme.types.get(page_type)
    if spec is None:
        return []
    out = [spec.views.key] if spec.views is not None else []
    out += [f.name for f in spec.fields or [] if f.type not in TEXT_FIELD_TYPES]
    return out


def _shared_value(page: Page, name: str) -> Any:
    if name == "type":
        return page.type
    if name in SHARED_FIELDS:
        return getattr(page.meta, name, None)
    return page.meta.get(name)


def implicit_folders(site: Site, site_root: Path, langs: list[str], collector: Collector) -> None:
    """Папка со страницами без `_index.md` ни на одном языке (так было в 0.2): предупреждение.

    Сборка считает такую папку разделом, как раньше; опросник и студия её не
    трогают при правке страниц. Сделать категорией явно - `heron category add`.
    """
    content_root = site_root / "content"
    seen: set[str] = set()
    for page in sorted([*site.pages, *site.held], key=lambda p: p.source):
        parts = page.source.split("/")[1:-1]
        for depth in range(1, len(parts) + 1):
            folder = "/".join(parts[:depth])
            if folder in seen:
                continue
            seen.add(folder)
            if any((content_root / lang / folder / INDEX_FILE).is_file() for lang in langs):
                continue
            collector.warn(
                Msg("build_implicit_folder", folder=folder),
                path=f"{page.lang}/{folder}/",
                kind="прочее",
            )


INDEX_FILE = "_index.md"


SVG_CACHE = "svg-safe.json"  # в .heron-cache рядом со сборкой: sha256 файла -> находка


def svg_files(
    site_root: Path,
    theme_dir: Path,
    collector: Collector,
    error: bool = True,
    cache: Path | None = None,
) -> None:
    """SVG из `media/` и темы сайт отдаёт как есть: исполняемое в нём - `E043`.

    Та же проверка, что у загрузки в студии (`heron.core.svg`): файлы, положенные
    мимо студии (руками, темой, скриптом), ловят `heron check` и сборка. `error` -
    ошибка (`check`, боевая сборка: такой файл в прод не уходит), иначе
    предупреждение (черновая сборка, `serve`). `cache` - папка `.heron-cache`:
    итог по sha256 файла, чтобы не разбирать одни и те же SVG на каждой сборке.
    """
    import hashlib
    import json

    from heron.core import svg

    known: dict[str, str | None] = {}
    store = cache / SVG_CACHE if cache is not None else None
    if store is not None:
        try:
            loaded = json.loads(store.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                known = {str(k): v for k, v in loaded.items() if v is None or isinstance(v, str)}
        except (OSError, ValueError):
            known = {}
    seen: dict[str, str | None] = {}
    for path in svg.files(site_root / "media", theme_dir):
        try:
            data = path.read_bytes()
        except OSError as failure:
            reason: str | None = failure.strerror or str(failure)
        else:
            digest = hashlib.sha256(data).hexdigest()
            reason = known[digest] if digest in known else svg.problem(data)
            seen[digest] = reason
        if reason is None:
            continue
        try:
            shown = path.relative_to(site_root).as_posix()
        except ValueError:
            shown = str(path)
        if error:
            collector.error(
                "E043",
                Msg("build_svg_unsafe", reason=reason),
                path=shown,
                hint=Msg("build_svg_unsafe_hint"),
            )
        else:
            collector.warn(Msg("build_svg_unsafe", reason=reason), path=shown, kind="прочее")
    if store is not None and seen != known:
        try:
            store.parent.mkdir(parents=True, exist_ok=True)
            temp = store.with_suffix(".tmp")
            temp.write_text(json.dumps(seen, sort_keys=True), encoding="utf-8")
            temp.replace(store)
        except OSError:
            pass  # кэш - ускорение, не условие сборки


def _roots(site: Site, config: SiteConfig, collector: Collector, prod: bool) -> None:
    """У каждого языка сайта есть главная: `content/<язык>/index.md`.

    Без неё корень языка (`/` или `/ru/`) отвечает 404, хотя переключатель
    языков и hreflang ведут именно туда. В проде это ошибка `E028`, на деве
    и в `check` — предупреждение: главную часто пишут последней. Пустой язык
    по умолчанию — отдельная, более ранняя ошибка `E021`.
    """
    said = {e.code for e in collector.errors}
    if "E017" in said:
        return  # страниц нет вовсе — об этом уже сказано
    for lang in config.site.languages:
        home = urls.home_url(config, lang)
        if any(p.url == home and not p.generated for p in site.pages):
            continue
        if lang == config.site.default_lang and "E021" in said:
            continue  # об этом уже сказано
        message = Msg("build_no_home_page", lang=lang, home=home)
        hint = Msg("build_no_home_page_hint")
        if any(p.url == home for p in site.held):
            # главная есть, но не переведена: боевая сборка её не публикует
            message = Msg("build_home_pending", lang=lang, home=home)
            hint = Msg("build_home_pending_hint", lang=lang)
        where = f"content/{lang}/index.md"
        if prod:
            collector.error("E028", message, path=where, hint=hint)
        else:
            collector.warn(message, path=where, kind="языки")


TEXT_SUFFIXES = {".css", ".js", ".html", ".svg", ".json", ".xml", ".txt", ".webmanifest"}


def _local_theme(site_root: Path, theme_dir: Path) -> bool:
    """Тема лежит в папке сайта (`theme/`), а не в установленном пакете."""
    return theme_dir.name == resolver.LOCAL_THEME and (
        theme_dir.parent.resolve() == site_root.resolve()
    )


def rooted(site_root: Path, theme_dir: Path) -> None:
    """Папки исходников и папки темы — не ссылки наружу (E024).

    Одна проверка и для `check`, и для `build`: они не расходятся. Сама `theme/`
    сверяется с корнем сайта, как `content/` и `static/`; файл-ссылка наружу в
    `static/` и в теме (шаблон, стиль, строки) — E024 до сборки, а не только при
    копировании или рендере. Тема из установленного пакета лежит вне сайта
    законно, поэтому корень сверяется только у локальной.
    """
    names = ("content", "data", media.MEDIA, media.LEGACY, STATIC, "plugins")
    paths.rooted(site_root, [site_root / name for name in names])
    if _local_theme(site_root, theme_dir):
        paths.rooted(site_root, [theme_dir])
    paths.rooted(theme_dir, [theme_dir / name for name in (ASSETS, "i18n", "templates", "modules")])
    paths.readable([*(site_root / name for name in names), theme_dir])
    for folder in (site_root / STATIC, theme_dir):
        for _ in paths.files(folder, where=str(folder)):
            pass  # ссылка наружу внутри папки - E024


def sources(site_root: Path, theme_dir: Path) -> list[Path]:
    """Папки исходников: в них сборка не пишет и с ними не пересекается."""
    names = ("content", "data", media.MEDIA, media.LEGACY, STATIC)
    return [*(site_root / name for name in names), theme_dir]


def _texts(folder: Path) -> list[str]:
    """Текстовые файлы папки: в них тоже бывают ссылки на /media/."""
    out = []
    for _, path in paths.files(folder, where=str(folder)):
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                out.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return out


def _schema(site, config, theme, collector, built, env, allow=(), exists=None) -> None:
    """Проверить разметку каждой страницы и посчитать узлы для отчёта.

    Разметку не видно глазами: она либо есть и верна, либо её нет, и узнают
    об этом из чужой панели вебмастера через месяц.
    """
    check_ = policy.SchemaCheck(
        env_prod=env.is_prod,
        allow=list(allow),
        exceptions=list(config.schema_exceptions),
        today=policy.today_for_build(),
    )
    for page in site.pages:
        for kind in jsonld.verify(page, config, theme, collector, site, check_):
            built.schema_nodes[kind] += 1
    if exists is not None:
        for page, graph in check_.graphs:
            check_.images(page, graph, config, exists, theme)
    built.schema = check_.finish(collector, built.notes_lang)


def theme_controls(site_root: Path, theme_dir: Path, collector: Collector) -> None:
    """Управляющие символы терминала в тексте темы - `E044` (`heron check --theme`).

    Подсказки и справка `theme.yaml`, строки `theme/i18n/*.yaml` и SEO-блок
    демо-страниц печатают `page add`, `describe`, `page list`: `ESC ] 52` в них
    писал бы в буфер обмена, `ESC [ 2 J` стирал бы экран. Терминал движок
    защищает сам (`heron.term`), а тема с такими символами в каталог не идёт.
    """
    import yaml

    from heron import term
    from heron.core.parser.frontmatter import FRONTMATTER

    def walk(value, path: str, out: list[tuple[str, list[str]]]) -> None:
        if isinstance(value, str):
            found = term.controls(value)
            if found:
                out.append((path or "-", found))
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(key, path, out)
                walk(item, f"{path}.{key}" if path else str(key), out)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}.{index}", out)

    sources = [theme_dir / "theme.yaml", *sorted((theme_dir / "i18n").glob("*.yaml"))]
    content = site_root / "content"
    demo = sorted(content.rglob("*.md")) if content.is_dir() else []
    for path in [*sources, *demo]:
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".md":
                match = FRONTMATTER.match(text)
                text = match.group("body") if match else ""
            data = yaml.safe_load(text)
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue  # негодный файл - забота своей проверки
        found: list[tuple[str, list[str]]] = []
        walk(data, "", found)
        try:
            shown = path.relative_to(site_root).as_posix()
        except ValueError:
            shown = str(path)
        for where, chars in found:
            collector.error(
                "E044",
                Msg("build_theme_control", field=where, chars=" ".join(chars)),
                path=shown,
                hint=Msg("build_theme_control_hint"),
            )


def theme_contract(theme: ThemeConfig, theme_dir: Path, collector: Collector) -> None:
    """Контракт темы для опросника и студии: описан ли и с подсказками ли.

    Тема без `fields` собирается как раньше - одно предупреждение на проверку,
    что опросник покажет только служебные поля. Тема с `fields`, у которой нет
    `hint` на каком-то из её языков, - ошибка: подсказка - половина контракта,
    без неё новичок в студии видит голое имя поля.
    """
    where = str(theme_dir / "theme.yaml")
    if not theme.described:
        collector.warnings.append(
            Warning_(Msg("build_theme_no_fields", theme=theme.name), path=where)
        )
        return
    missing = missing_hints(theme)
    if missing:
        collector.errors.append(
            HeronError(
                code="E041",
                message=Msg(
                    "build_theme_hints",
                    theme=theme.name,
                    langs=", ".join(theme.hint_langs()) or "-",
                    missing=missing,
                ),
                path=where,
                hint=Msg("build_theme_hints_hint"),
            )
        )


def check(
    site_root: Path,
    drafts: bool = False,
    strict: bool = False,
    env: BuildEnv | None = None,
    allow_schema: Sequence[str] = (),
    notes_lang: str | None = None,
    theme_demo: bool = False,
) -> Result:
    """Обойти и проверить, ничего не собирая.

    Строгий режим тот же, что у сборки: `strict` или `build.fail_on_warning`.
    `theme_demo` (`check --theme`) - сайт ещё и демо своей темы: страницы
    собираются шаблонами темы, и каждый тип, блок и вид раздела должен быть
    показан (`core/demo.py`, E037).
    """
    collector = Collector()
    site_root = site_root.resolve()
    try:
        config, theme, theme_dir, hooks = prepare(site_root, collector)
    except HeronError as error:
        collector.errors.append(error)
        raise

    rooted(site_root, theme_dir)
    theme_contract(theme, theme_dir, collector)
    for lang in config.site.languages:
        try:
            render_env.load_strings(theme_dir, lang, Collector())
        except HeronError as error:
            collector.errors.append(error)
    # check шаблоны не рендерит; изменение данных, на котором песочница
    # уронит сборку (E033), видно и по разбору шаблона — говорим заранее
    templates_check.mutations(site_root, theme_dir, config, collector, hooks)
    env = env or BuildEnv.resolve(None)
    site = content(site_root, config, theme, theme_dir, hooks, collector, drafts, env.is_prod)
    templates_check.missing_templates(site, theme, theme_dir, config, collector, hooks)
    templates_check.inline_scripts(theme_dir, site_root, collector)
    svg_files(site_root, theme_dir, collector)
    implicit_folders(site, site_root, config.site.languages, collector)
    shared_mismatch(site, theme, config.site.default_lang, collector)
    _roots(site, config, collector, prod=False)
    media.folder(site_root, collector)
    media.check_video(site, collector)
    media.verify(site, site_root, collector, config)
    media.verify_covers(site, site_root, collector, theme.images, config)
    redirects.generate(site, collector, config)
    if theme_demo:
        theme_controls(site_root, theme_dir, collector)
    if theme_demo and not collector.failed:
        demo.verify(theme, theme_dir, site, config, collector, hooks)

    built = report.build(
        site, config, theme, theme_dir=theme_dir, site_root=site_root, lang=notes_lang
    )
    collector.warnings.extend(report.nav_empty(site, config))
    collector.warnings.extend(report.duplicate_titles(site, config))
    collector.warnings.extend(report.pages_without_cover(site, config))
    built.kit = report.kit_status(site_root, config)
    _schema(
        site,
        config,
        theme,
        collector,
        built,
        env,
        allow_schema,
        exists=lambda rel: source_exists(site_root, rel, theme_dir),
    )
    return Result(
        config=config,
        theme=theme,
        theme_dir=theme_dir,
        site=site,
        collector=collector,
        report=built,
        strict=strict or config.build.fail_on_warning,
    )
