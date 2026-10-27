"""Папка темы и файлы в static/ и теме - ссылки наружу: E024 и в check, и в build (F30).

21 §4 «Границы файлов»: символическая ссылка наружу из content/, data/, media/,
static/ и темы - E024. Раньше целая `theme/` ссылкой наружу читалась молча и
попадала в dist, а файл-ссылка в static/ и шаблон-ссылка в теме давали у check
«Ошибок нет», а у build E024. Проверка одна на обе команды (`build.rooted`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from heron.cli import main
from heron.core import build as pipeline
from heron.core.errors import HeronError
from heron.scaffold import create

MARK = "SECRET-OUTSIDE-THEME"


@pytest.fixture
def site(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["en"], agents="false")
    return root


def _theme_outside(root: Path) -> Path:
    """Тема переезжает за пределы сайта, на её месте - ссылка; в шаблоне чужой маркер."""
    outside = root.parent / "outside-theme"
    shutil.move(root / "theme", outside)
    page = outside / "templates" / "page.html"
    page.write_text(page.read_text(encoding="utf-8") + f"\n<!-- {MARK} -->\n", encoding="utf-8")
    (root / "theme").symlink_to(outside, target_is_directory=True)
    return outside


def _template_link_out(root: Path) -> None:
    outside = root.parent / "page.html"
    outside.write_text(f"<p>{MARK}</p>", encoding="utf-8")
    (root / "theme" / "templates" / "page.html").unlink()
    (root / "theme" / "templates" / "page.html").symlink_to(outside)


def _asset_link_out(root: Path) -> None:
    outside = root.parent / "evil.css"
    outside.write_text(f"/* {MARK} */", encoding="utf-8")
    (root / "theme" / "assets" / "evil.css").symlink_to(outside)


def _i18n_link_out(root: Path) -> None:
    outside = root.parent / "en.yaml"
    outside.write_text(f"x: {MARK}\n", encoding="utf-8")
    (root / "theme" / "i18n" / "en.yaml").unlink()
    (root / "theme" / "i18n" / "en.yaml").symlink_to(outside)


def _static_file_link_out(root: Path) -> None:
    outside = root.parent / "passwd.txt"
    outside.write_text(MARK, encoding="utf-8")
    (root / "static").mkdir(exist_ok=True)
    (root / "static" / "leak.txt").symlink_to(outside)


def _static_folder_link_out(root: Path) -> None:
    outside = root.parent / "shared"
    outside.mkdir()
    (outside / "x.txt").write_text(MARK, encoding="utf-8")
    (root / "static").mkdir(exist_ok=True)
    (root / "static" / "shared").symlink_to(outside, target_is_directory=True)


CASES = {
    "theme-folder": _theme_outside,
    "template-file": _template_link_out,
    "asset-file": _asset_link_out,
    "i18n-file": _i18n_link_out,
    "static-file": _static_file_link_out,
    "static-folder": _static_folder_link_out,
}


def _leaks(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return [p for p in folder.rglob("*") if p.is_file() and MARK.encode() in p.read_bytes()]


@pytest.mark.parametrize("case", sorted(CASES))
def test_check_and_build_both_say_e024(site: Path, case: str) -> None:
    CASES[case](site)
    with pytest.raises(HeronError) as checked:
        pipeline.check(site)
    with pytest.raises(HeronError) as built:
        pipeline.run(site)
    assert checked.value.code == built.value.code == "E024"
    assert _leaks(site / "dist") == []  # ничего чужого в сборку не попало


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("command", ["check", "build"])
def test_cli_stops_with_e024(site: Path, case: str, command: str) -> None:
    CASES[case](site)
    args = [command, str(site)] + (["--env", "prod", "--strict"] if command == "build" else [])
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 1, result.output
    assert "E024" in result.output
    assert "unexpected error" not in result.output and "engine bug" not in result.output
    assert _leaks(site / "dist") == []


def test_theme_folder_message_names_the_folder(site: Path) -> None:
    _theme_outside(site)
    with pytest.raises(HeronError) as raised:
        pipeline.check(site)
    assert "theme/" in raised.value.message
    assert raised.value.path == str(site / "theme")


def test_theme_symlink_inside_the_site_is_fine(site: Path) -> None:
    """`theme/` - ссылка на другую папку того же сайта: так делают общие темы."""
    shutil.move(site / "theme", site / "theme-real")
    (site / "theme").symlink_to("theme-real", target_is_directory=True)
    assert not pipeline.check(site).failed
    result = pipeline.run(site)
    assert not result.failed, [str(e) for e in result.collector.errors]


def test_links_inside_theme_and_static_are_fine(site: Path) -> None:
    (site / "static").mkdir(exist_ok=True)
    (site / "static" / "real.txt").write_text("ok", encoding="utf-8")
    (site / "static" / "alias.txt").symlink_to(site / "static" / "real.txt")
    css = site / "theme" / "assets" / "site.css"
    (site / "theme" / "assets" / "alias.css").symlink_to(css)
    assert not pipeline.check(site).failed
    result = pipeline.run(site)
    assert not result.failed, [str(e) for e in result.collector.errors]
    assert (site / "dist" / "alias.txt").read_text(encoding="utf-8") == "ok"


def test_site_folder_itself_may_be_a_link(tmp_path: Path) -> None:
    """Сама папка сайта - ссылка на папку: её назвал человек, это не выход наружу."""
    real = tmp_path / "real"
    real.mkdir()
    create(real, name="demo", languages=["en"], agents="false")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert not pipeline.check(alias).failed
    assert not pipeline.run(alias).failed


def test_theme_of_an_installed_package_lives_outside_legally(site: Path, tmp_path: Path) -> None:
    """Тема из пакета лежит вне сайта: корень сверяется только у локальной `theme/`."""
    package = tmp_path / "package" / "theme"
    shutil.copytree(site / "theme", package)
    pipeline.rooted(site, package)  # не бросает
    # а такая же папка с именем theme/ в чужом месте, но не рядом с сайтом - тоже
    other = tmp_path / "other"
    other.mkdir()
    shutil.copytree(site / "theme", other / "theme")
    pipeline.rooted(site, other / "theme")


def test_folder_link_outside_theme_inside_a_package_theme_is_still_e024(
    site: Path, tmp_path: Path
) -> None:
    """Файл-ссылка наружу внутри темы пакета - тоже E024 (проверка файлов общая)."""
    package = tmp_path / "package" / "mytheme"
    shutil.copytree(site / "theme", package)
    outside = tmp_path / "x.css"
    outside.write_text("a{}", encoding="utf-8")
    (package / "assets" / "x.css").symlink_to(outside)
    with pytest.raises(HeronError) as raised:
        pipeline.rooted(site, package)
    assert raised.value.code == "E024"
