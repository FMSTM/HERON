"""Инструкция для агентов не расходится с движком.

Шаблоны из docs/agents/templates проходят валидацию, ссылки между
документами ведут на существующие файлы, а сайт, собранный по шаблонам,
собирается в прод без ошибок.
"""

from __future__ import annotations

import io
import re
import shutil
from pathlib import Path

import yaml
from PIL import Image

from heron.contracts.site import SiteConfig
from heron.contracts.theme import ThemeConfig
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.core.parser import blocks, frontmatter, markdown, sections
from heron.scaffold import create

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "docs" / "agents"
TEMPLATES = AGENTS / "templates"


def test_site_template_is_valid():
    data = yaml.safe_load((TEMPLATES / "site.yaml").read_text(encoding="utf-8"))
    config = SiteConfig.model_validate(data)
    assert config.for_lang("ru").site.name != config.site.name
    assert config.gone


def test_theme_template_is_valid():
    data = yaml.safe_load((TEMPLATES / "theme.yaml").read_text(encoding="utf-8"))
    theme = ThemeConfig.model_validate(data)
    assert {"home", "service", "article", "404"} <= set(theme.types)


def test_page_template_parses_into_expected_forms():
    text = (TEMPLATES / "page.md").read_text(encoding="utf-8")
    data, body, line = frontmatter.split(text, "page.md")
    meta = frontmatter.parse_meta(data, "page.md")
    assert meta.redirect_from == ["/старий-адрес/"]
    md = markdown.make()
    intro, found = sections.split(md, body, "page.md", offset=line)
    blocks.apply(md, found)
    assert {k: s.kind for k, s in found.items()} == {
        "includes": "list",
        "how": "steps",
        "faq": "faq",
    }


def test_links_between_agent_docs_resolve():
    docs = [ROOT / "AGENTS.md", *AGENTS.glob("*.md")]
    for doc in docs:
        for target in re.findall(r"\]\(([^)#\s]+)\)", doc.read_text(encoding="utf-8")):
            if target.startswith(("http", "/")):
                continue  # внешние адреса и ссылки сайта в примерах
            assert (doc.parent / target).exists(), f"{doc.name}: битая ссылка {target}"


def _png(path: Path) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (1200, 630), (20, 40, 60)).save(buf, "PNG")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


def test_site_built_from_templates_passes_prod_strict_checks(tmp_path):
    """Сценарий А на шаблонах: new → site.yaml → init → тема → контент → prod."""
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["uk"])
    shutil.copy(TEMPLATES / "site.yaml", root / "site.yaml")
    create(root, name="demo", languages=["uk", "ru"])  # то, что делает init
    shutil.copy(TEMPLATES / "theme.yaml", root / "theme" / "theme.yaml")

    templates = root / "theme" / "templates"
    page_tpl = (templates / "page.html").read_text(encoding="utf-8")
    for kind in ("service", "category", "article"):
        (templates / f"{kind}.html").write_text(page_tpl, encoding="utf-8")
    for name in ("default.png", "default-ru.png"):
        _png(root / "media" / "og" / name)

    head = "---\ntitle: {t}\nh1: {h}\ndescription: Опис\n{x}---\n\nТекст.\n"
    service = (TEMPLATES / "page.md").read_text(encoding="utf-8")
    files = {
        "uk/index.md": head.format(t="Головна сайту", h="Головна", x=""),
        "ru/index.md": head.format(t="Главная сайта", h="Главная", x=""),
        "uk/404.md": head.format(t="Не знайдено", h="Сторінки немає", x=""),
        "ru/404.md": head.format(t="Не найдено", h="Страницы нет", x=""),
        "uk/services/_index.md": head.format(
            t="Каталог", h="Наш каталог", x="children_type: service\n"
        ),
        "uk/services/design.md": service,
        "uk/services/planning.md": head.format(t="Планування", h="Планування простору", x=""),
    }
    for rel, text in files.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    assert (dist / "services" / "design" / "index.html").is_file()
    assert "/старий-адрес/  /services/design/;" in (dist / "redirects.map").read_text(
        encoding="utf-8"
    )
    assert "/wp-*  1;" in (dist / "gone.map").read_text(encoding="utf-8")
    design = result.site.page("services/design", "uk")
    assert [p.url for p in design.related["related"]] == ["/services/planning/"]
