"""Подпись движка в каждой HTML-странице.

Две вещи, обе — при сборке, ни в контенте, ни в `site.yaml` их нет:

- `<meta name="generator" content="HERON">` в `<head>` — по нему движок
  сайта узнают детекторы (Wappalyzer, BuiltWith). Без номера версии: он
  подсказывает, какую уязвимость искать, а пользы не даёт;
- HTML-комментарий с подписью сразу после `<!doctype html>`.

На поисковую выдачу не влияет: комментарии поисковики не читают,
`generator` в ранжировании не участвует. Отключается в `site.yaml` одной
строкой: `build.generator: false`. Тема, которая уже поставила свой
`generator`, его сохраняет: второй тег не добавляется.
"""

from __future__ import annotations

import re

GENERATOR = "HERON"
COMMENT = (
    "<!--\n"
    "\tBuilt with HERON — a fast static site generator by FAMOUS.TEAM\n"
    "\tHERON: https://github.com/FMSTM/HERON\n"
    "\tFAMOUS.TEAM: https://famous.team\n"
    "-->\n"
)
META = f'<meta name="generator" content="{GENERATOR}">'

DOCTYPE = re.compile(r"^\s*<!doctype[^>]*>[ \t]*\r?\n?", re.I)
HEAD = re.compile(r"<head\b[^>]*>", re.I)
HAS_GENERATOR = re.compile(r"<meta\b[^>]*\bname\s*=\s*[\"']?generator\b", re.I)


def sign(html: str) -> str:
    """Поставить подпись. Повторный вызов ничего не меняет."""
    if COMMENT not in html:
        match = DOCTYPE.match(html)
        if match:
            head = match.group(0)
            if not head.endswith("\n"):
                head += "\n"
            html = head + COMMENT + html[match.end() :]
        else:
            html = COMMENT + html
    if not HAS_GENERATOR.search(html):
        match = HEAD.search(html)
        if match:
            html = html[: match.end()] + "\n" + META + html[match.end() :]
    return html
