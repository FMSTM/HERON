"""Шаблоны темы — недоверенный код: собираются в песочнице.

Каждый тест кладёт в тему один «вредный» шаблон страницы и проверяет, что
сборка отказывает с E033, а побочного эффекта нет. Последний — что обычная
белая тема собирается как раньше.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heron.core import build as pipeline
from heron.scaffold import create

PAGE = '{{% extends "base.html" %}}{{% block content %}}{payload}{{% endblock %}}'


def _site(tmp_path: Path) -> Path:
    root = tmp_path / "s"
    create(root, name="S", languages=["en"], demo=True)
    return root


def _with(root: Path, payload: str) -> None:
    (root / "theme" / "templates" / "page.html").write_text(
        PAGE.format(payload=payload), encoding="utf-8"
    )


def _codes(result) -> set[str]:
    return {error.code for error in result.collector.errors}


@pytest.mark.parametrize(
    "payload",
    [
        # исполнение кода через служебные атрибуты функций
        '{{ lipsum.__globals__["os"].popen("touch {marker}").read() }}',
        '{{ cycler.__init__.__globals__.os.popen("touch {marker}").read() }}',
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        # методы самого BaseModel: parse_file читает любой файл
        '{{ site.parse_file("{secret}") }}',
        '{{ site.__class__.parse_file("{secret}") }}',
        "{{ theme.model_construct() }}",
        # окружение сборки заново — это git в чужой папке
        '{{ env.stamped("/") }}',
        # изменение данных сайта из шаблона
        "{{ languages.append('xx') }}",
        "{{ data.update({'x': 1}) }}",
    ],
)
def test_harmful_template_is_refused(tmp_path, payload):
    root = _site(tmp_path)
    marker = tmp_path / "MARKER"
    secret = tmp_path / "secret.json"
    secret.write_text('{"name": "SECRET-MARKER"}', encoding="utf-8")
    _with(root, payload.replace("{marker}", str(marker)).replace("{secret}", str(secret)))
    result = pipeline.run(root)
    assert result.failed
    assert "E033" in _codes(result), [e.message for e in result.collector.errors]
    assert not marker.exists()
    for page in (root / "dist").rglob("*.html") if (root / "dist").exists() else []:
        assert "SECRET-MARKER" not in page.read_text(encoding="utf-8")


def test_path_objects_are_closed(tmp_path):
    """Путь, если он однажды попадёт в контекст, не даёт ни читать, ни писать."""
    from jinja2.exceptions import SecurityError

    from heron.core.render.env import ThemeSandbox

    target = tmp_path / "out.txt"
    env = ThemeSandbox()
    with pytest.raises(SecurityError):
        env.from_string("{{ p.write_text('x') }}").render(p=target)
    with pytest.raises(SecurityError):
        env.from_string("{{ p.read_text() }}").render(p=target)
    assert not target.exists()


def test_white_theme_builds_unchanged(tmp_path):
    root = _site(tmp_path)
    result = pipeline.run(root)
    assert not result.failed, [e.message for e in result.collector.errors]
    assert (root / "dist" / "index.html").is_file()
