"""Сообщения ресурсов на ключах texts/media.py: ru прежний, en без кириллицы."""

import re

import pytest

from heron.core import media
from heron.core.errors import Collector, HeronError
from heron.messages import Msg

CYR = re.compile("[а-яА-ЯёЁ]")


def _en_ok(item) -> str:
    for part in (item.message, getattr(item, "hint", None)):
        if part is None:
            continue
        assert isinstance(part, Msg)
        assert not CYR.search(part.text("en"))
    return item.message.text("en")


def test_both_folders(tmp_path):
    (tmp_path / "media").mkdir()
    (tmp_path / "img").mkdir()
    with pytest.raises(HeronError) as raised:
        media.folder(tmp_path, Collector())
    err = raised.value
    assert err.message == "в сайте есть и media/, и img/ - движок не знает, какая настоящая"
    assert err.hint == "перенесите файлы в media/ и удалите img/"
    assert _en_ok(err) == "the site has both media/ and img/: the engine cannot tell which one is real"


def test_same_address_clash(tmp_path):
    for d in ("media", "static/media"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "a.png").write_bytes(b"x")
    with pytest.raises(HeronError) as raised:
        media.folder(tmp_path, Collector())
    assert raised.value.message == "static/media и media/ дают один адрес: a.png"
    assert _en_ok(raised.value) == "static/media and media/ give the same address: a.png"


def test_two_folders_and_legacy_warnings(tmp_path):
    (tmp_path / "media").mkdir()
    (tmp_path / "static/media").mkdir(parents=True)
    collector = Collector()
    media.folder(tmp_path, collector)
    warning = collector.warnings[0]
    assert warning.message.startswith("в /media/ отдаются две папки сразу")
    assert "Move the contents" in _en_ok(warning)
    assert warning.kind == "картинки"

    legacy = tmp_path / "other"
    (legacy / "img").mkdir(parents=True)
    collector = Collector()
    assert media.folder(legacy, collector) == "img"
    assert collector.warnings[0].message.startswith("папка ресурсов называется img/")
    assert _en_ok(collector.warnings[0]).startswith("the assets folder is called img/")


def test_small_cover_text():
    msg = media.small_cover(1200, "media/a.png")
    assert isinstance(msg, Msg)
    assert msg == "обложка меньше 1200 px: media/a.png"
    assert msg.text("en") == "the cover is narrower than 1200 px: media/a.png"


def test_owner_with_more_pages():
    owner = media._owner({"media/a.png": ["p1.md", "p2.md", "p3.md"]}, "media/a.png")
    assert owner == "p1.md и ещё 2"
    assert owner.text("en") == "p1.md and 2 more"
    assert media._owner({"media/a.png": ["p1.md"]}, "media/a.png") == "p1.md"
    assert media._owner({}, "media/a.png") == "media/a.png"


def test_locate_escape(tmp_path):
    (tmp_path / "media").mkdir()
    collector = Collector()
    assert media.locate(tmp_path, "other/x.png", {}, collector) is None
    err = collector.errors[0]
    assert err.message == "путь 'other/x.png' выходит за пределы media/"
    assert not CYR.search(err.hint.text("en"))
    assert _en_ok(err).startswith("path 'other/x.png' goes outside media/")


def test_cache_link_guard(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    cache = tmp_path / "cache"
    cache.symlink_to(real)
    with pytest.raises(HeronError) as raised:
        media.guard(cache)
    assert raised.value.message.startswith("кэш - ссылка, а не папка")
    assert _en_ok(raised.value).startswith("the cache is a link, not a folder")
    assert raised.value.hint == "удалите эту ссылку - папка кэша пересоздастся при сборке"


def test_slice_is_dir(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    with pytest.raises(HeronError) as raised:
        media._reusable(folder)
    assert raised.value.message == f"на месте нарезки в кэше - папка: {folder}"
    assert _en_ok(raised.value).startswith("a folder sits where a rendition")


def test_msg_survives_pickle():
    import pickle

    msg = media.small_cover(800, "media/x.png")
    again = pickle.loads(pickle.dumps(msg))
    assert again == msg and again.text("en") == msg.text("en")
