"""SVG: обходы санитайзера через SMIL-анимации и относительные ссылки (аудит SEC-03).

Значения анимации (`from`, `to`, `by`, `values`) сверяются и как CSS, и как
ссылка; анимация не меняет ссылку и стиль; `#` годится только как чистый
фрагмент; `<image>` и `<feImage>` берут только `#id` или растр внутри файла.
"""

from __future__ import annotations

import pytest

from heron.core import svg

NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'


def wrap(inner: str) -> bytes:
    return f"<svg {NS}>{inner}</svg>".encode()


BAD = [
    # из отчёта аудита
    '<rect><set attributeName="fill" to="url(https://evil.example/track)"/></rect>',
    '<rect><animate attributeName="fill" values="#ok;url(https://evil.example/leak)"/></rect>',
    '<image href="/leak.svg"/>',
    '<image href="evil.svg"/>',
    '<image xlink:href="../evil.png"/>',
    '<filter id="f"><feImage href="evil.svg"/></filter>',
    '<filter id="f"><feImage xlink:href="/leak.svg"/></filter>',
    '<filter id="f"><feImage href="https://evil.example/x.png"/></filter>',
    # остальные значения анимации и экранирование
    '<rect><animate attributeName="fill" from="url(//evil.example/x)"/></rect>',
    '<rect><animate attributeName="fill" by="url(other.svg#g)"/></rect>',
    '<rect><animate attributeName="fill" values="red; u\\72l(https://evil.example/x)"/></rect>',
    '<rect><animate attributeName="x" values="0;https://evil.example/x"/></rect>',
    # анимация не меняет ссылку и стиль
    '<a href="#a"><set attributeName="href" to="#b"/></a>',
    '<a href="#a"><set attributeName="xlink:href" to="#b"/></a>',
    '<rect><set attributeName="style" to="fill:red"/></rect>',
    '<rect><animate attributeName="src" values="#a;#b"/></rect>',
    # `#` - только чистый фрагмент
    '<use href="#a;url(https://evil.example/x)"/>',
    '<use href="#a)url(https://evil.example/x"/>',
    # url() на чужое - ни в каком атрибуте
    '<a href="url(https://evil.example/x)"><text>x</text></a>',
]

GOOD = [
    '<rect><animate attributeName="opacity" values="0;1;0" dur="2s"/></rect>',
    '<rect><animate attributeName="fill" values="url(#a);url(#b)" dur="1s"/></rect>',
    '<rect><set attributeName="fill" to="red"/></rect>',
    '<rect><animateTransform attributeName="transform" type="rotate"'
    ' from="0 5 5" to="360 5 5"/></rect>',
    '<circle><animateMotion path="M0,0 L10,10" values="0,0;10,10"/></circle>',
    '<filter id="f"><feColorMatrix values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0"/></filter>',
    '<filter id="f"><feImage href="#shape"/></filter>',
    '<image href="data:image/png;base64,iVBORw0KGgo=" width="1" height="1"/>',
    '<use href="#a"/><use xlink:href="#a"/>',
]


@pytest.mark.parametrize("inner", BAD)
def test_smil_and_relative_bypasses_are_refused(inner):
    assert svg.problem(wrap(inner)) is not None


@pytest.mark.parametrize("inner", GOOD)
def test_ordinary_animation_and_fragments_pass(inner):
    assert svg.problem(wrap(inner)) is None


def test_rules_version_drops_old_cache():
    # кэш годных файлов прежних правил не годится: в нём могут быть обходы выше
    assert svg.RULES >= 5
