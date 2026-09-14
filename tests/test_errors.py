"""Формат сообщения об ошибке: адрес обязателен, подсказка выводится."""

from heron.core.errors import ERRORS, Collector, HeronError


def test_message_has_address():
    err = HeronError("E002", "нет title", path="content/uk/bio.md", line=3)
    assert "content/uk/bio.md:3" in str(err)
    assert "E002" in str(err)


def test_hint_rendered():
    err = HeronError("E005", "недопустимый слаг", path="a.md", hint="только латиница")
    assert "что сделать" in str(err)


def test_codes_are_continuous():
    assert list(ERRORS) == [f"E{n:03d}" for n in range(1, len(ERRORS) + 1)]


def test_collector_collects_without_raising():
    c = Collector()
    c.warn("title длиннее 60 знаков", path="a.md")
    assert not c.failed
    c.error("E001", "битый YAML", path="a.md", line=1)
    assert c.failed
