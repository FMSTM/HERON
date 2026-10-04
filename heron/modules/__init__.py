"""Модули-генераторы: то, что движок дописывает к собранным страницам.

Поставляются в ядре, но пишутся против тех же хуков, что и внешние плагины.
"""

from heron.modules import feed, jsonld, llms, redirects, robots, sitemap

__all__ = ["feed", "jsonld", "llms", "redirects", "robots", "sitemap"]
