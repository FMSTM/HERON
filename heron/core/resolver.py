"""Поиск темы и плагинов.

Один механизм на обе сущности — второго не заводим, иначе придётся помнить,
какой где, и через полгода никто не помнит.

Порядок: локальное в папке сайта, затем установленный пакет. Локальное всегда
сильнее: тема правится прямо в сайте, без публикации на каждую правку CSS.

Спецификация: docs/spec/23-distribution.md, раздел 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path

from heron.core import paths
from heron.core.errors import HeronError
from heron.core.hooks import Hooks
from heron.messages import Msg

THEME_GROUP = "heron.themes"
PLUGIN_GROUP = "heron.plugins"
LOCAL_THEME = "theme"
LOCAL_PLUGINS = "plugins"


@dataclass(slots=True)
class Found:
    name: str
    path: Path
    source: str


def theme(site_root: Path, name: str) -> Found:
    """Найти тему: локальная папка, затем установленный пакет."""
    local = site_root / LOCAL_THEME
    if (local / "theme.yaml").is_file():
        return Found(name=name, path=local, source=Msg("tree_theme_local"))

    for entry in entry_points(group=THEME_GROUP):
        if entry.name != name:
            continue
        try:
            path = Path(entry.load()())
        except Exception as exc:  # noqa: BLE001 — чужой код, причину показываем как есть
            raise HeronError(
                code="E013",
                message=Msg("tree_theme_load_failed", name=name, error=exc),
                path="site.yaml",
            ) from exc
        if (path / "theme.yaml").is_file():
            return Found(name=name, path=path, source=Msg("tree_package", value=entry.value))

    raise HeronError(
        code="E013",
        message=Msg("tree_theme_not_found", name=name),
        path="site.yaml",
        hint=Msg("tree_theme_not_found_hint", folder=LOCAL_THEME, name=name),
    )


def _escape(name: str, path: Path) -> HeronError:
    return HeronError(
        code=paths.CODE,
        message=Msg("tree_plugin_escape", name=name),
        path=str(path),
        hint=Msg("tree_plugin_escape_hint"),
    )


def _load_local(path: Path, name: str, hooks: Hooks) -> bool:
    entry = path / "__init__.py"
    if entry.is_symlink():
        raise _escape(name, entry)
    if not entry.is_file():
        return False
    import sys
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(f"heron_site_plugin_{name}", entry)
    if spec is None or spec.loader is None:
        return False
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    register = getattr(module, "register", None)
    if register is None:
        raise HeronError(
            code="E014",
            message=Msg("tree_plugin_no_register", name=name),
            path=str(path),
        )
    register(hooks)
    return True


def plugins(site_root: Path, names: list[str], hooks: Hooks) -> list[Found]:
    """Подключить плагины из списка `plugins` в site.yaml."""
    found: list[Found] = []
    installed = {entry.name: entry for entry in entry_points(group=PLUGIN_GROUP)}

    plugins_dir = site_root / LOCAL_PLUGINS
    if plugins_dir.exists() and (
        plugins_dir.is_symlink() or not paths.inside(site_root, plugins_dir)
    ):
        # Сама папка plugins/ ведёт наружу: до исполнения кода плагина.
        raise HeronError(
            code=paths.CODE,
            message=Msg("tree_plugins_dir_escape", folder=LOCAL_PLUGINS),
            path=str(plugins_dir),
            hint=Msg("tree_plugins_dir_escape_hint", folder=LOCAL_PLUGINS),
        )

    for name in names:
        if not paths.NAME_RE.match(name):
            raise HeronError(
                code="E014",
                message=Msg("tree_plugin_bad_name", name=name),
                path="site.yaml",
                hint=Msg("tree_plugin_bad_name_hint"),
            )
        local = plugins_dir / name
        if local.is_symlink() or (local.is_dir() and not paths.inside(plugins_dir, local)):
            raise _escape(name, local)
        try:
            if local.is_dir() and _load_local(local, name, hooks):
                found.append(Found(name=name, path=local, source=Msg("tree_plugin_local")))
                continue
        except HeronError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HeronError(
                code="E014",
                message=Msg("tree_plugin_load_failed", name=name, error=exc),
                path=str(local),
            ) from exc

        entry = installed.get(name)
        if entry is None:
            raise HeronError(
                code="E014",
                message=Msg("tree_plugin_not_installed", name=name, folder=LOCAL_PLUGINS),
                path="site.yaml",
                hint=Msg("tree_plugin_not_installed_hint", name=name),
            )
        try:
            register = entry.load()
            register(hooks)
        except Exception as exc:  # noqa: BLE001
            raise HeronError(
                code="E014",
                message=Msg("tree_plugin_load_failed", name=name, error=exc),
                path="site.yaml",
            ) from exc
        found.append(
            Found(
                name=name,
                path=Path(str(import_module(entry.module).__file__ or "")),
                source=Msg("tree_package", value=entry.value),
            )
        )

    return found
