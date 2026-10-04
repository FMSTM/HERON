"""Картинки во вложенных полях фронтматтера и в справочниках data/.

Тема вправе объявить поле любой формы — карту с подписью, список карт,
карту со списками. Разбор только строк и плоских списков терял такую
картинку молча: ни ошибки, ни предупреждения, просто пустое место.
"""

from __future__ import annotations

import yaml

from heron.core import data as data_module
from heron.core import media, tree
from heron.core.errors import Collector
from tests import sites


def _page(**fields) -> str:
    meta = {"title": "Сторінка", "h1": "Сторінка", "description": "Опис", **fields}
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{head}\n---\n\nТекст.\n"


def _scan(tmp_path, files):
    content = sites.build(tmp_path, files)
    site, collector = tree.scan(content, sites.config())
    return site, collector


def test_image_inside_nested_map(tmp_path):
    files = {
        "uk/index.md": _page(photos={"hero": {"src": "img/foto/x.jpg", "alt": "Підпис"}}),
    }
    site, _ = _scan(tmp_path, files)
    assert "img/foto/x.jpg" in media.references(site)


def test_list_of_maps_is_read_whole(tmp_path):
    files = {
        "uk/index.md": _page(
            photos={
                "work": [
                    {"src": "img/foto/a.jpg", "alt": "А"},
                    {"src": "img/foto/b.jpg", "alt": "Б"},
                ]
            }
        ),
    }
    site, _ = _scan(tmp_path, files)
    assert {"img/foto/a.jpg", "img/foto/b.jpg"} <= media.references(site)


def test_typo_in_nested_path_is_e007_with_page_name(tmp_path):
    files = {"uk/index.md": _page(photos={"hero": {"src": "img/foto/нет.jpg"}})}
    site, collector = _scan(tmp_path, files)
    media.verify(site, tmp_path, collector)
    errors = [e for e in collector.errors if e.code == "E007"]
    assert errors and "uk/index.md" in errors[0].path


def test_prose_field_is_not_an_image(tmp_path):
    """Картинку узнаём по значению целиком, а не по вхождению подстроки."""
    files = {"uk/index.md": _page(promise="Смотрите img/foto/x.jpg в конце страницы")}
    site, _ = _scan(tmp_path, files)
    assert media.references(site) == set()


def test_external_link_is_not_ours(tmp_path):
    files = {"uk/index.md": _page(cover="https://example.com/img/foto/x.jpg")}
    site, _ = _scan(tmp_path, files)
    assert media.references(site) == set()


def test_image_declared_in_data(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "booking.yaml").write_text(
        "panel:\n  photo:\n    src: img/foto/room.jpg\n    alt: Кабінет\n", encoding="utf-8"
    )
    site, collector = _scan(tmp_path, {"uk/index.md": _page()})
    site.data = data_module.load(tmp_path / "data", collector)
    assert "img/foto/room.jpg" in media.references(site)
    assert media.declared_by(site)["img/foto/room.jpg"] == ["data/booking"]


def test_cycle_in_data_does_not_hang(tmp_path):
    """YAML-якорь даёт общий объект: предел глубины дешевле разбирательств."""
    node: dict = {"src": "img/foto/deep.jpg"}
    box: dict = {"node": node}
    node["self"] = box
    found: set[str] = set()
    media.walk(box, found)
    assert found == {"img/foto/deep.jpg"}


def test_collector_is_untouched_by_walk():
    found: set[str] = set()
    media.walk({"a": [{"b": {"c": "img/x.png"}}]}, found)
    assert found == {"img/x.png"}
    assert not Collector().errors
