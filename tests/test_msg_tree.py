"""Сообщения tree и resolver: ru прежний байт в байт, en без кириллицы (E15.S2.T14)."""

import re
from pathlib import Path

import pytest

from heron.core import resolver, tree
from heron.core.errors import Collector, HeronError
from heron.core.hooks import Hooks
from heron.messages import Msg, rendered
from tests import sites

CYR = re.compile(r"[А-Яа-яЁё]")


def _scan(tmp_path: Path, files: dict[str, str], **over):
    content = sites.build(tmp_path, files)
    return tree.scan(content, sites.config(**over), collector=Collector())


def _check(msg, ru: str) -> None:
    assert isinstance(msg, Msg)
    assert msg.text("ru") == ru
    assert str(msg) == ru
    assert not CYR.search(msg.text("en"))


def test_scan_errors_ru_and_en(tmp_path):
    files = {
        "uk/index.md": sites.page("Главная"),
        "uk/Bad_Name.md": sites.page("X"),
        "uk/one.md": sites.page("A", slug="same"),
        "uk/two.md": sites.page("B", slug="same"),
        "uk/Bad Dir/page.md": sites.page("C"),
    }
    _, collector = _scan(tmp_path, files)
    by_code = {}
    for err in collector.errors:
        by_code.setdefault(err.code, []).append(err)

    name = [e for e in by_code["E005"] if "имя файла" in e.message][0]
    assert name.message.text("en") == "invalid file name 'Bad_Name.md'"
    _check(name.message, "недопустимое имя файла 'Bad_Name.md'")
    _check(name.hint, "слаг - латиница, цифры и дефис: getting-started.md")
    assert not CYR.search(name.hint.text("en"))

    segment = [e for e in by_code["E005"] if "сегмент" in e.message][0]
    _check(segment.message, "недопустимый сегмент адреса 'Bad Dir' (имя папки или slug раздела)")
    _check(segment.hint, "папки - латиница, цифры и дефис; или задайте slug в _index.md раздела")

    clash = by_code["E004"][0]
    assert clash.message.text("en").startswith("address /same/ is already taken by file")
    assert "уже занят файлом" in clash.message.text("ru")
    _check(clash.hint, "переименуйте файл или задайте другой slug во фронтматтере")


def test_missing_and_empty_language_warnings(tmp_path):
    _, collector = _scan(tmp_path, {"uk/index.md": sites.page("Главная")})
    warning = [w for w in collector.warnings if "нет дерева" in w.message][0]
    _check(warning.message, "нет дерева контента для языка 'ru'")
    assert warning.message.text("en") == "no content tree for language 'ru'"
    assert warning.kind == "языки"

    (tmp_path / "content" / "ru").mkdir()
    _, collector = tree.scan(tmp_path / "content", sites.config(), collector=Collector())
    empty = [w for w in collector.warnings if "нет ни одной" in w.message][0]
    _check(empty.message, "в языке 'ru' нет ни одной страницы")
    assert empty.message.text("en") == "language 'ru' has no pages"


def test_key_clash_and_home_key(tmp_path):
    files = {
        "uk/index.md": sites.page("Главная"),
        "uk/a.md": sites.page("A", slug="other"),
        "uk/a/_index.md": sites.page("B"),
        "uk/home/_index.md": sites.page("H"),
    }
    _, collector = _scan(tmp_path, files)
    errs = [e for e in collector.errors if e.code == "E029"]
    assert errs, collector.errors
    _check(errs[0].message, errs[0].message.text("ru"))
    assert "already belongs to file" in errs[0].message.text("en")
    _check(
        errs[0].hint,
        "у страницы и раздела одного уровня не может быть одного имени; переименуйте файл",
    )
    home = [w for w in collector.warnings if "pages.home" in w.message][0]
    _check(home.message, home.message.text("ru"))
    assert "pages.home" in home.message.text("en")
    assert home.kind == "прочее"


def test_symlink_escape(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text(sites.page("Чужой"), encoding="utf-8")
    root = tmp_path / "site"
    content = sites.build(root, {"uk/index.md": sites.page("Главная")})
    (content / "uk" / "link.md").symlink_to(outside)
    _, collector = tree.scan(content, sites.config(), collector=Collector())
    err = [e for e in collector.errors if e.path == "uk/link.md"][0]
    _check(err.message, "символическая ссылка ведёт за пределы content/")
    _check(err.hint, "положите сам файл в content/ вместо ссылки на него")


def test_theme_not_found(tmp_path):
    with pytest.raises(HeronError) as exc:
        resolver.theme(tmp_path, "nope")
    err = exc.value
    _check(err.message, "тема 'nope' не найдена ни локально, ни среди установленных")
    assert err.message.text("en") == "theme 'nope' is found neither locally nor among installed packages"
    _check(err.hint, f"положите её в {resolver.LOCAL_THEME}/ или установите пакет heron-theme-nope")


def test_theme_local_source(tmp_path):
    (tmp_path / resolver.LOCAL_THEME).mkdir()
    (tmp_path / resolver.LOCAL_THEME / "theme.yaml").write_text("name: x\n", encoding="utf-8")
    found = resolver.theme(tmp_path, "x")
    _check(found.source, "локальная")
    assert found.source.text("en") == "local"


def test_plugin_bad_name_and_not_installed(tmp_path):
    with pytest.raises(HeronError) as exc:
        resolver.plugins(tmp_path, ["-bad"], Hooks())
    _check(exc.value.message, "плагин '-bad': недопустимое имя")
    _check(exc.value.hint, "имя плагина - латиница, цифры, _ и -, не с дефиса")
    assert exc.value.message.text("en") == "plugin '-bad': invalid name"

    with pytest.raises(HeronError) as exc:
        resolver.plugins(tmp_path, ["ghost"], Hooks())
    _check(exc.value.message, f"плагин 'ghost' не установлен и не найден в {resolver.LOCAL_PLUGINS}/")
    _check(exc.value.hint, "уберите из plugins или установите пакет, дающий 'ghost'")


def test_local_plugin_failures(tmp_path):
    base = tmp_path / resolver.LOCAL_PLUGINS
    (base / "noreg").mkdir(parents=True)
    (base / "noreg" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(HeronError) as exc:
        resolver.plugins(tmp_path, ["noreg"], Hooks())
    _check(exc.value.message, "в плагине 'noreg' нет функции register(hooks)")
    assert exc.value.message.text("en") == "plugin 'noreg' has no register(hooks) function"

    (base / "boom").mkdir()
    (base / "boom" / "__init__.py").write_text("raise RuntimeError('oops')\n", encoding="utf-8")
    with pytest.raises(HeronError) as exc:
        resolver.plugins(tmp_path, ["boom"], Hooks())
    _check(exc.value.message, "плагин 'boom' упал при загрузке: oops")
    assert exc.value.message.text("en") == "plugin 'boom' failed to load: oops"


def test_plugin_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    site = tmp_path / "site"
    (site / resolver.LOCAL_PLUGINS).mkdir(parents=True)
    (site / resolver.LOCAL_PLUGINS / "evil").symlink_to(outside)
    with pytest.raises(HeronError) as exc:
        resolver.plugins(site, ["evil"], Hooks())
    _check(exc.value.message, "плагин 'evil' ведёт за пределы plugins/ через ссылку")
    _check(exc.value.hint, "положите папку плагина в plugins/ вместо ссылки")


def test_plugins_dir_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    site = tmp_path / "site"
    site.mkdir()
    (site / resolver.LOCAL_PLUGINS).symlink_to(outside)
    with pytest.raises(HeronError) as exc:
        resolver.plugins(site, ["any"], Hooks())
    _check(exc.value.message, f"папка {resolver.LOCAL_PLUGINS}/ ведёт за пределы сайта через ссылку")
    assert rendered(exc.value.hint, "en") == (
        f"make {resolver.LOCAL_PLUGINS}/ a real folder inside the site instead of a link"
    )
