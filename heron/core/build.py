"""Конвейер сборки.

Восемь этапов строго по порядку, каждый может остановить сборку. Один проход,
никакого состояния между запусками: собрать дважды подряд — получить побайтово
одинаковый результат.

Спецификация: docs/spec/21-engine.md, раздел 4.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from heron import __version__
from heron.contracts import version as version_contract
from heron.contracts import wiring
from heron.contracts.site import SiteConfig, load_site
from heron.contracts.theme import ThemeConfig, load_theme
from heron.core import data as data_module
from heron.core import links, media, report, resolver, tree
from heron.core.errors import Collector, HeronError
from heron.core.hooks import Hooks
from heron.core.models import Site
from heron.core.parser import markdown
from heron.core.render import pages as renderer
from heron.modules import feed, llms, redirects, robots, sitemap

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
    report: report.Report | None = None
    written: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.collector.failed


def _page_path(url: str) -> str:
    trimmed = url.strip("/")
    return f"{trimmed}/index.html" if trimmed else "index.html"


def _write(dist: Path, name: str, text: str) -> None:
    path = dist / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_tree(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)


def prepare(site_root: Path, collector: Collector) -> tuple[SiteConfig, ThemeConfig, Path, Hooks]:
    """Этап 1: конфиги, версия движка, тема, плагины."""
    config = load_site(site_root / SITE_YAML)
    version_contract.check(config.heron, __version__, site_yaml=str(site_root / SITE_YAML))

    found = resolver.theme(site_root, config.site.theme)
    theme = load_theme(found.path / "theme.yaml")
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
) -> Result:
    """Собрать сайт целиком."""
    collector = Collector()
    site_root = site_root.resolve()
    dist = (dist or site_root / DIST).resolve()

    config, theme, theme_dir, hooks = prepare(site_root, collector)

    md = markdown.make(allow_raw_html=config.build.allow_raw_html)
    site, collector = tree.scan(site_root / "content", config, md, collector, drafts=drafts)
    site.data = data_module.load(site_root / "data", collector)
    hooks.call("on_tree_built", site)

    links.resolve(site, config, theme, collector)

    result = Result(config=config, theme=theme, theme_dir=theme_dir, site=site, collector=collector)
    if collector.failed:
        return result

    dist.mkdir(parents=True, exist_ok=True)
    manifest = (
        media.build(site, site_root, dist, theme.images, collector, cache_dir=site_root / CACHE)
        if with_media
        else media.Manifest()
    )
    if collector.failed:
        return result

    html = renderer.render_site(theme_dir, site, config, theme, collector, manifest)
    if collector.failed:
        return result

    files: dict[str, str] = {_page_path(url): text for url, text in html.items()}
    files.update(sitemap.generate(site, config))
    files.update(robots.generate(config))
    files.update(llms.generate(site, config))
    files.update(redirects.generate(site, collector))
    files.update(feed.generate(site, config))

    not_found = html.get("/404/")
    if not_found:
        files["404.html"] = not_found

    for extra in hooks.call("on_build_finished", site, config):
        if isinstance(extra, dict):
            files.update(extra)

    if collector.failed:
        return result

    for name, text in sorted(files.items()):
        _write(dist, name, text)
    _copy_tree(site_root / STATIC, dist)
    _copy_tree(theme_dir / ASSETS, dist / ASSETS)

    result.written = sorted(files)
    result.report = report.build(site, config, theme, theme_dir=theme_dir)
    return result


def check(site_root: Path, drafts: bool = False) -> Result:
    """Обойти и проверить, ничего не собирая."""
    collector = Collector()
    site_root = site_root.resolve()
    try:
        config, theme, theme_dir, hooks = prepare(site_root, collector)
    except HeronError as error:
        collector.errors.append(error)
        raise

    md = markdown.make(allow_raw_html=config.build.allow_raw_html)
    site, collector = tree.scan(site_root / "content", config, md, collector, drafts=drafts)
    site.data = data_module.load(site_root / "data", collector)
    links.resolve(site, config, theme, collector)
    redirects.generate(site, collector)

    return Result(
        config=config,
        theme=theme,
        theme_dir=theme_dir,
        site=site,
        collector=collector,
        report=report.build(site, config, theme, theme_dir=theme_dir),
    )
