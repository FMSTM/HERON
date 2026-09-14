"""Адреса: единственное место, где к пути приклеивается домен."""

from __future__ import annotations

from heron.contracts.site import SiteConfig


def absolute(config: SiteConfig, url: str) -> str:
    return f"https://{config.site.domain}{url}"


def home_url(config: SiteConfig, lang: str) -> str:
    return "/" if lang == config.site.default_lang else f"/{lang}/"
