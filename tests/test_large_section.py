"""Раздел со 120 детьми: одна страница каталога, все дети в карте сайта.

Спецификация: docs/spec/21-engine.md, раздел 4, «Большие разделы».
"""

from __future__ import annotations

from heron.core import build as pipeline
from heron.scaffold import create

N = 120


def test_section_with_120_children_builds_as_one_page(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    content = root / "content" / "uk"
    (content / "index.md").write_text(
        "---\ntitle: Г\nh1: Головна\ndescription: О\n---\n\nТекст.\n", encoding="utf-8"
    )
    faq = content / "faq"
    faq.mkdir()
    (faq / "_index.md").write_text(
        "---\ntitle: Питання\nh1: Питання та відповіді\ndescription: О\n---\n\nТекст.\n",
        encoding="utf-8",
    )
    for n in range(N):
        (faq / f"q-{n:03d}.md").write_text(
            f"---\ntitle: Питання {n}\nh1: Питання номер {n}\ndescription: О\norder: {n}\n---\n\n"
            "Відповідь.\n",
            encoding="utf-8",
        )
    templates = root / "theme" / "templates"
    (templates / "page.html").write_text(
        '{% extends "base.html" %}{% block content %}<h1>{{ page.h1 }}</h1>'
        '<ul class="kids">{% for c in page.children %}<li><a href="{{ c.url }}">{{ c.h1 }}</a></li>'
        "{% endfor %}</ul>{% endblock %}",
        encoding="utf-8",
    )
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]

    catalog = result.site.page("faq", "uk")
    assert len(catalog.children) == N
    assert [c.meta.order for c in catalog.children] == list(range(N))

    html = (root / "dist" / "faq" / "index.html").read_text(encoding="utf-8")
    assert html.count("<li><a href=") == N
    assert not (root / "dist" / "faq" / "page").exists()  # пагинации нет

    sitemap = (root / "dist" / "sitemap.xml").read_text(encoding="utf-8")
    assert sitemap.count("<loc>") == N + 2  # дети, раздел и главная
