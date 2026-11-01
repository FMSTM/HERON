"""Сообщения отчёта на ключах texts/report.py: ru прежний, en без кириллицы."""

import re

from heron.core import report
from heron.core.errors import Collector, HeronError
from heron.messages import Msg
from heron.texts import report as texts

CYR = re.compile("[а-яА-ЯёЁ]")


def test_keys_parity_and_en_clean():
    assert texts.TEXT["ru"].keys() == texts.TEXT["en"].keys()
    assert not any(CYR.search(x) for x in texts.TEXT["en"].values())
    assert not any("—" in x or "–" in x for x in texts.TEXT["en"].values())


def test_summary_renders_msg_by_language(tmp_path):
    c = Collector()
    c.error(
        "E030", Msg("report_old_not_utf8", byte=3), hint=Msg("report_old_not_utf8_hint")
    )
    c.warn(Msg("report_seo_no_cover", n=2), kind="seo")
    full = tmp_path / "w.txt"
    en = report.summary(c, full=full, lang="en")
    assert "E030 <unknown file>: the old URLs file is not UTF-8 (byte 3)" in en
    assert "re-save the file as UTF-8" in en
    assert "pages without a cover: 2" in en
    assert "pages without a cover: 2" in full.read_text(encoding="utf-8")
    ru = report.summary(c, lang="ru")
    assert "страниц без обложки: 2" in ru
    assert "пересохраните файл" in ru


def test_heron_error_str_stays_russian():
    err = HeronError("E001", "плохо", hint="поправьте")
    assert str(err) == "E001 <неизвестный файл>: плохо\n  что сделать: поправьте"
