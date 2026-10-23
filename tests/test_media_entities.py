"""Имя картинки с символом, который HTML экранирует: нарезки на месте."""

from __future__ import annotations

import re

from PIL import Image

from heron.core import build as pipeline
from heron.core.media import used_in
from heron.scaffold import create


def test_escaped_name_gets_its_renditions(tmp_path):
    name = "a&b"
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True)
    Image.new("RGB", (640, 480), (20, 120, 30)).save(root / "media" / f"{name}.png")
    index = root / "content" / "en" / "index.md"
    index.write_text(
        index.read_text("utf-8") + f"\n\n## Pic {{#pic}}\n\n![A picture](media/{name}.png)\n",
        encoding="utf-8",
    )
    home = root / "theme" / "templates" / "home.html"
    home.write_text(
        home.read_text("utf-8").replace(
            "{% block content %}",
            "{% block content %}{{ picture('media/" + name + ".png', '16:9', alt='x') }}",
            1,
        ),
        encoding="utf-8",
    )
    result = pipeline.run(root, strict=True)
    problems = [e.message for e in result.collector.errors]
    problems += [w.message for w in result.collector.warnings]
    assert not result.failed, problems
    html = (root / "dist" / "index.html").read_text("utf-8")
    assert "a&amp;b-16x9-400.webp" in html and "a&b-16x9" not in html  # экранировано
    found = re.findall(r'(?:src|srcset)="([^"]+)"', html)
    refs = {part.split()[0] for item in found for part in item.split(",") if "16x9" in part}
    assert refs
    import html as htmllib
    import urllib.parse

    for ref in refs:
        rel = urllib.parse.unquote(htmllib.unescape(ref)).lstrip("/")
        assert (root / "dist" / rel).is_file(), rel


def test_used_in_decodes_entities_and_percent():
    found = used_in(['<img src="/media/a&amp;b-1.png">', '<img src="/media/a%20b-1.png">'])
    assert "media/a&b-1.png" in found and "media/a b-1.png" in found
    assert "media/a&amp;b-1.png" in found  # сырой вид тоже остаётся
