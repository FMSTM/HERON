"""Одно правило домена: опрос `heron new` и site.yaml согласны всегда.

Раньше в CLI и в контракте были разные регулярки: `a-.com` CLI отвергал,
а site.yaml принимал; `https://shop.com/` site.yaml приводил к домену,
а CLI отвергал.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from heron.contracts.site import SiteBlock


def contract_accepts(text: str) -> bool:
    try:
        SiteBlock(domain=text, theme="main")
    except ValidationError:
        return False
    return True


def cli_accepts(text: str) -> bool:
    from heron import cli

    return cli._check_domain("en")(text) is None


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("example.com", True),
        ("Example.COM", True),
        ("https://example.com/", True),
        ("sub.example.co.uk", True),
        ("xn--80ak6aa92e.com", True),
        ("a-.com", False),
        ("-a.com", False),
        ("a.-b.com", False),
        ("example", False),
        ("exa mple.com", False),
        ("example.com/path", False),
        ("a" * 64 + ".com", False),
    ],
)
def test_cli_and_site_yaml_agree(text, ok):
    assert contract_accepts(text) is ok
    assert cli_accepts(text) is ok
