"""Конвейер сборки.

Восемь этапов строго по порядку, каждый может остановить сборку. Один проход,
никакого состояния между запусками: собрать дважды подряд — получить побайтово
одинаковый результат.

Спецификация: docs/spec/21-engine.md, раздел 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from heron import __version__
from heron.contracts import version as version_contract
from heron.contracts import wiring
from heron.contracts.site import SiteConfig, load_site
from heron.contracts.theme import ThemeConfig, load_theme
from heron.core import data as data_module
from heron.core import (
    dates,
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
from heron.core.errors import Collector, HeronError
from heron.core.hooks import Hooks
from heron.core.models import Site
from heron.core.parser import markdown
from heron.core.progress import Progress, Silent
from heron.core.render import pages as renderer
from heron.modules import feed, jsonld, llms, nginx, redirects, robots, sitemap

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
    label: str,
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
            output.Entry(owner=f"{label}/{rel}", kind=kind, source=path),
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
    version_contract.check(config.heron, __version__, site_yaml=str(site_root / SITE_YAML))

    found = resolver.theme(site_root, config.site.theme)
    theme = load_theme(found.path / "theme.yaml")
    wiring.verify_engine(theme, str(found.path / "theme.yaml"))
    collector.warnings.extend(wiring.verify(theme, config, str(site_root / SITE_YAML)))

    hooks = Hooks()
    resolver.plugins(site_root, config.plugins, hooks)
    hooks.call("on_config", config, theme)
    return config, theme, found.path, hooks


def run(
    site_root: Path,
    dist: Path | None = None,
    drafts: bool = False,
    with_media: bool = True,
    strict: bool = False,
    env: BuildEnv | None = None,
    progress: Progress | None = None,
) -> Result:
    """Собрать сайт целиком.

    Кэш нарезанных картинок кладётся рядом с результатом, а не рядом с
    контентом: папка сайта монтируется только на чтение, и пачкать её
    служебными файлами сборка не имеет права.
    """
    collector = Collector()
    env = env or BuildEnv()
    say = progress or Silent()
    site_root = site_root.resolve()
    env = env.stamped(site_root)
    dist = (dist or site_root / DIST).resolve()

    say.step("step_config")
    config, theme, theme_dir, hooks = prepare(site_root, collector)
    paths.layout(site_root, dist, dist.parent / CACHE, sources(site_root, theme_dir))
    rooted(site_root, theme_dir)
    strict = strict or config.build.fail_on_warning
    for_env(config, env)
    say.done("done_config", theme=config.site.theme, langs=len(config.site.languages))

    say.step("step_content")
    site = content(site_root, config, theme, theme_dir, hooks, collector, drafts)
    say.done("done_pages", count=len(site.pages))

    # Сайт без страниц — нормальное состояние на деве: тему доводят раньше,
    # чем пишут контент. В проде это всегда чья-то ошибка — пустой конвейер,
    # не тот путь, забытый язык, — и выкладывать её наружу нельзя.
    if env.is_prod and not [p for p in site.pages if not p.generated]:
        collector.error(
            "E017",
            "в проде нечего собирать: ни одной страницы",
            path=str(site_root / "content"),
            hint="проверьте путь к контенту и языки в site.yaml; "
            "пустую сборку можно делать только в деве",
        )
    # Язык по умолчанию отдаётся из корня. Пуст он — корень сайта отвечает
    # 404, даже если другие языки заполнены целиком. На деве это стадия
    # работы, в проде — витрина без входа.
    elif env.is_prod and not [p for p in site.of_lang(config.site.default_lang) if not p.generated]:
        default = config.site.default_lang
        collector.error(
            "E021",
            f"в проде пуст язык по умолчанию {default!r}: корень сайта ответил бы 404",
            path=str(site_root / "content" / default),
            hint=f"заполните content/{default}/ или назначьте default_lang "
            "языком, на котором контент уже есть",
        )

    _roots(site, config, collector, prod=env.is_prod)

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
        say.done("done_masters", count=len(manifest.items))
        if collector.failed:
            return result

        say.step("step_templates")
        html = renderer.render_site(
            theme_dir, site, config, theme, collector, manifest, env, progress=say, hooks=hooks
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
            owner = (
                f"страница {page.source}" if page is not None and page.source else f"страница {url}"
            )
            outputs.add(
                _page_path(url), output.Entry(owner=owner, kind="page", text=text), collector
            )
        not_found = html.get("/404/")
        if not_found:
            claim({"404.html": not_found}, "page", "страница 404")
        claim(sitemap.generate(site, config), "generator", "генератор sitemap")
        claim(robots.generate(config, env), "generator", "генератор robots.txt")
        claim(llms.generate(site, config), "generator", "генератор llms.txt")
        moves = redirects.collect(site, collector, config)
        claim(redirects.files(moves), "generator", "генератор карт 301/410")
        claim(nginx.generate(config, moves), "generator", "генератор конфига nginx")
        claim(feed.generate(site, config), "generator", "генератор ленты")
        say.done()

        for extra in hooks.call("on_generate", site, config):
            if isinstance(extra, dict):
                claim(extra, "plugin", "плагин (on_generate)")

        _claim_tree(outputs, site_root / STATIC, "", "static", "static", collector)
        _claim_tree(outputs, theme_dir / ASSETS, f"{ASSETS}/", "asset", "тема assets", collector)
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
                workers=config.build.workers,
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
        result.report = report.build(site, config, theme, theme_dir=theme_dir, site_root=site_root)
        # Проверяется то, что действительно ляжет в сборку: конфиг, подменённый
        # статикой через build.overrides, — его байты, а не сгенерированный.
        result.report.nginx_test = nginx.check(outputs.text_of(nginx.NAME), collector)
        _schema(site, config, theme, collector, result.report)
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
            name = getattr(handler, "__module__", "") or "плагин"
            result.finish_errors.append(f"{name}: {type(error).__name__}: {error}")
            continue
        if isinstance(returned, dict) and returned:
            result.notices.append(
                "плагин вернул файлы из on_build_finished — они не записаны: "
                "файлы сборки объявляются в on_generate(site, config)"
            )
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
) -> Site:
    """Этапы 2–4, общие для `build` и `check`: обход, разбор, даты, связи.

    Расширения применяются одинаково в обоих: свои типы секций, правка
    страницы после разбора, свои связи после обхода. Иначе `check`
    проверял бы не тот сайт, который соберёт `build`.
    """
    md = markdown.make(allow_raw_html=config.build.allow_raw_html)
    site, _ = tree.scan(
        site_root / "content", config, md, collector, drafts=drafts, custom=hooks.blocks()
    )
    for page in site.pages:
        hooks.call("on_page_parsed", page)
    site.data = data_module.load(site_root / "data", collector)
    dates.resolve(site, site_root, config.build.updated_from, collector)
    dates.check(site, collector)
    hooks.call("on_tree_built", site)
    notfound.ensure(site, config, theme_dir, collector)
    links.resolve(site, config, theme, collector)
    return site


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
        message = f"у языка {lang!r} нет главной страницы: {home} ответит 404"
        where = f"content/{lang}/index.md"
        if prod:
            collector.error("E028", message, path=where, hint="создайте index.md в корне языка")
        else:
            collector.warn(message, path=where, kind="языки")


TEXT_SUFFIXES = {".css", ".js", ".html", ".svg", ".json", ".xml", ".txt", ".webmanifest"}


def rooted(site_root: Path, theme_dir: Path) -> None:
    """Папки исходников и папки темы — не ссылки наружу (E024)."""
    names = ("content", "data", media.MEDIA, media.LEGACY, STATIC, "plugins")
    paths.rooted(site_root, [site_root / name for name in names])
    paths.rooted(theme_dir, [theme_dir / name for name in (ASSETS, "i18n", "templates", "modules")])
    paths.readable([*(site_root / name for name in names), theme_dir])


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


def _schema(site, config, theme, collector, built) -> None:
    """Проверить разметку каждой страницы и посчитать узлы для отчёта.

    Разметку не видно глазами: она либо есть и верна, либо её нет, и узнают
    об этом из чужой панели вебмастера через месяц.
    """
    for page in site.pages:
        for kind in jsonld.verify(page, config, theme, collector, site):
            built.schema_nodes[kind] += 1


def check(site_root: Path, drafts: bool = False, strict: bool = False) -> Result:
    """Обойти и проверить, ничего не собирая.

    Строгий режим тот же, что у сборки: `strict` или `build.fail_on_warning`.
    """
    collector = Collector()
    site_root = site_root.resolve()
    try:
        config, theme, theme_dir, hooks = prepare(site_root, collector)
    except HeronError as error:
        collector.errors.append(error)
        raise

    rooted(site_root, theme_dir)
    site = content(site_root, config, theme, theme_dir, hooks, collector, drafts)
    _roots(site, config, collector, prod=False)
    media.folder(site_root, collector)
    media.check_video(site, collector)
    media.verify(site, site_root, collector, config)
    redirects.generate(site, collector, config)

    built = report.build(site, config, theme, theme_dir=theme_dir, site_root=site_root)
    _schema(site, config, theme, collector, built)
    return Result(
        config=config,
        theme=theme,
        theme_dir=theme_dir,
        site=site,
        collector=collector,
        report=built,
        strict=strict or config.build.fail_on_warning,
    )
