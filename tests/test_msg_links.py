"""Сообщения связей, дат и 404 на ключах texts/links.py: ru прежний, en без кириллицы."""

import re
from datetime import UTC, date, datetime
from types import SimpleNamespace

from heron.core import dates, notfound
from heron.core.errors import Collector
from heron.messages import Msg  # noqa: F401

CYR = re.compile("[а-яА-ЯёЁ]")


def _en_ok(item) -> str:
    for part in (item.message, getattr(item, "hint", None)):
        if part is None:
            continue
        assert isinstance(part, Msg)
        assert not CYR.search(part.text("en"))
    return item.message.text("en")


def test_dates_future_and_backwards():
    now = datetime(2025, 1, 1, tzinfo=UTC)
    page = SimpleNamespace(
        generated=False,
        source="a.md",
        date_at=None,
        updated_at=datetime(2030, 1, 1, tzinfo=UTC),
        date=date(2024, 5, 1),
        updated=date(2024, 4, 1),
    )
    collector = Collector()
    dates.check(SimpleNamespace(pages=[page]), collector, now=now)
    msgs = [_en_ok(w) for w in collector.warnings]
    assert collector.warnings[0].message == (
        "updated: 2030-01-01T00:00:00+00:00 - позже сборки; поисковик сочтёт дату ошибкой"
    )
    assert msgs[0].startswith("updated: 2030-01-01T00:00:00+00:00 is later than the build")
    assert collector.warnings[1].message.text("ru").startswith("обновление 2024-04-01")
    assert msgs[1] == "update 2024-04-01 is earlier than publication 2024-05-01"


def test_dates_by_file_same_time(tmp_path):
    for n in ("a.md", "b.md"):
        (tmp_path / n).write_text("x")
    pages = [SimpleNamespace(source=n) for n in ("a.md", "b.md")]
    collector = Collector()
    dates._by_file(pages, tmp_path, collector, loud=True)
    (w,) = collector.warnings
    assert w.message.key == "links_dates_same_time"
    assert w.message.text("ru").startswith("у всех файлов одно время")
    assert "same time" in _en_ok(w)


def test_dates_unreadable_file(tmp_path):
    pages = [SimpleNamespace(source="gone.md")]
    collector = Collector()
    dates._by_file(pages, tmp_path, collector, loud=True)
    (w,) = collector.warnings
    assert w.message == "файл не читается - даты нет"
    assert _en_ok(w) == "the file cannot be read: no date"


def test_notfound_without_template(tmp_path):
    site = SimpleNamespace(
        of_lang=lambda lang: [SimpleNamespace(generated=False, type="page")], pages=[]
    )
    config = SimpleNamespace(site=SimpleNamespace(languages=["en"]))
    collector = Collector()
    notfound.ensure(site, config, tmp_path, collector)
    (w,) = collector.warnings
    assert w.message.text("ru").startswith("нет content/en/404.md и шаблона темы")
    assert _en_ok(w).startswith("no content/en/404.md and no theme template")


def test_msg_keys_ru_en_parity():
    from heron.texts import links

    assert links.TEXT["ru"].keys() == links.TEXT["en"].keys()
    assert not any(CYR.search(v) for v in links.TEXT["en"].values())
    msg = Msg("links_missing_page", field="f", name="x", of_type=Msg("links_of_type", type="t"))
    assert msg == "f: страницы 'x' не существует среди страниц типа 't'"
    assert msg.text("en") == "f: page 'x' does not exist among pages of type 't'"
