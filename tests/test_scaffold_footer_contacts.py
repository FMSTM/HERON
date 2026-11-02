"""Подвал стартовой темы: ссылка на каждый канал так же, как её строит анкета (E15.S1.T21)."""

from __future__ import annotations

import html
import re

import pytest
import yaml

from heron.core import build as pipeline
from heron.scaffold import create
from heron.setup.answers import CONTACT_TYPES, contact_url

VALUES = {
    "phone": "+380 00 000 00 00",
    "email": "info@example.com",
    "website": "example.com",
    "whatsapp": "+380 00 000 00 00",
    "viber": "+380 00 000 00 00",
}


def _value(kind):
    return VALUES.get(kind, "@demo_name")


def _footer(tmp_path, channels):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["en"], notes="en")
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("contact", {})["channels"] = channels
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    page = (root / "dist" / "index.html").read_text(encoding="utf-8")
    return page[page.index('<footer class="site-footer">') :]


def _hrefs(footer):
    return [html.unescape(h) for h in re.findall(r'<a href="([^"]*)"', footer)]


@pytest.mark.parametrize("kind", CONTACT_TYPES)
def test_each_channel_links_like_the_questionnaire(tmp_path, kind):
    value = _value(kind)
    footer = _footer(tmp_path, [{"type": kind, "value": value}])
    expected = contact_url(kind, value)
    if kind == "phone":
        expected = "tel:+380000000000"
    elif kind == "email":
        expected = "mailto:" + value
    if expected is None:
        assert f"contact-{kind}" in footer
        assert value in footer
        assert value not in "".join(_hrefs(footer))
    else:
        assert expected in _hrefs(footer)


def test_viber_without_digits_is_plain_text(tmp_path):
    footer = _footer(tmp_path, [{"type": "viber", "value": "abc"}])
    assert "contact-viber" in footer
    assert "abc" in footer
    assert not [h for h in _hrefs(footer) if h.startswith("viber:")]


def test_whatsapp_without_digits_is_plain_text(tmp_path):
    footer = _footer(tmp_path, [{"type": "whatsapp", "value": "abc"}])
    assert "abc" in footer
    assert not [h for h in _hrefs(footer) if "wa.me" in h]


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("telegram", "my name"),
        ("tiktok", "a"),
        ("instagram", "a" * 65),
        ("x", "@@demo"),
        ("youtube", "@@demo"),
        ("website", "localhost"),
        ("website", "my site"),
        ("viber", "https://example.com/v"),
        ("whatsapp", "https://example.com/w"),
        ("x", "https://x.com/demo"),
        ("telegram", "  @demo_name  "),
    ],
)
def test_channel_link_agrees_with_contact_url(tmp_path, kind, value):
    footer = _footer(tmp_path, [{"type": kind, "value": value}])
    item = re.search(r'<li class="contact contact-[^"]*">(.*?)</li>', footer, re.S).group(1)
    expected = contact_url(kind, value)
    assert _hrefs(item) == ([expected] if expected else [])
