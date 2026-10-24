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
        return Found(name=name, path=local, source="локальная")

    for entry in entry_points(group=THEME_GROUP):
        if entry.name != name:
            continue
        try:
            path = Path(entry.load()())
        except Exception as exc:  # noqa: BLE001 — чужой код, причину показываем как есть
            raise HeronError(
                code="E013",
                message=f"тема {name!r} установлена, но не загружается: {exc}",
                path="site.yaml",
            ) from exc
        if (path / "theme.yaml").is_file():
            return Found(name=name, path=path, source=f"пакет {entry.value}")

    raise HeronError(
        code="E013",
        message=f"тема {name!r} не найдена ни локально, ни среди установленных",
        path="site.yaml",
        hint=f"положите её в {LOCAL_THEME}/ или установите пакет heron-theme-{name}",
    )


def _escape(name: str, path: Path) -> HeronError:
    return HeronError(
        code=paths.CODE,
        message=f"плагин {name!r} ведёт за пределы plugins/ через ссылку",
        path=str(path),
        hint="положите папку плагина в plugins/ вместо ссылки",
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
            message=f"в плагине {name!r} нет функции register(hooks)",
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
            message=f"папка {LOCAL_PLUGINS}/ ведёт за пределы сайта через ссылку",
            path=str(plugins_dir),
            hint=f"сделайте {LOCAL_PLUGINS}/ настоящей папкой внутри сайта вместо ссылки",
        )

    for name in names:
        if not paths.NAME_RE.match(name):
            raise HeronError(
                code="E014",
                message=f"плагин {name!r}: недопустимое имя",
                path="site.yaml",
                hint="имя плагина — латиница, цифры, _ и -, не с дефиса",
            )
        local = plugins_dir / name
        if local.is_symlink() or (local.is_dir() and not paths.inside(plugins_dir, local)):
            raise _escape(name, local)
        try:
            if local.is_dir() and _load_local(local, name, hooks):
                found.append(Found(name=name, path=local, source="локальный"))
                continue
        except HeronError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HeronError(
                code="E014",
                message=f"плагин {name!r} упал при загрузке: {exc}",
                path=str(local),
            ) from exc

        entry = installed.get(name)
        if entry is None:
            raise HeronError(
                code="E014",
                message=f"плагин {name!r} не установлен и не найден в {LOCAL_PLUGINS}/",
                path="site.yaml",
                hint=f"уберите из plugins или установите пакет, дающий {name!r}",
            )
        try:
            register = entry.load()
            register(hooks)
        except Exception as exc:  # noqa: BLE001
            raise HeronError(
                code="E014",
                message=f"плагин {name!r} упал при загрузке: {exc}",
                path="site.yaml",
            ) from exc
        found.append(
            Found(
                name=name,
                path=Path(str(import_module(entry.module).__file__ or "")),
                source=f"пакет {entry.value}",
            )
        )

    return found
