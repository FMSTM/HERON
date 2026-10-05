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
GUIDE = ROOT / "docs" / "guide"


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
    assert meta.redirect_from == ["/старый-адрес/"]
    md = markdown.make()
    intro, found = sections.split(md, body, "page.md", offset=line)
    blocks.apply(md, found)
    assert {k: s.kind for k, s in found.items()} == {
        "includes": "list",
        "how": "steps",
        "faq": "faq",
    }


def test_links_between_agent_docs_resolve():
    docs = [ROOT / "AGENTS.md", ROOT / "README.md", *AGENTS.glob("*.md"), *GUIDE.glob("*.md")]
    for doc in docs:
        text = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"\]\(([^)#\s]+)\)", text):
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
    create(root, name="demo", languages=["en"])
    shutil.copy(TEMPLATES / "site.yaml", root / "site.yaml")
    create(root, name="demo", languages=["en", "ru"])  # то, что делает init
    shutil.copy(TEMPLATES / "theme.yaml", root / "theme" / "theme.yaml")

    templates = root / "theme" / "templates"
    page_tpl = (templates / "page.html").read_text(encoding="utf-8")
    for kind in ("service", "category", "article"):
        (templates / f"{kind}.html").write_text(page_tpl, encoding="utf-8")
    for name in ("default.png", "default-ru.png"):
        _png(root / "media" / "og" / name)

    head = "---\ntitle: {t}\nh1: {h}\ndescription: Description\n{x}---\n\nText.\n"
    service = (TEMPLATES / "page.md").read_text(encoding="utf-8")
    files = {
        "en/index.md": head.format(t="Site home", h="Home", x=""),
        "ru/index.md": head.format(t="Главная сайта", h="Главная", x=""),
        "en/404.md": head.format(t="Not found", h="No such page", x=""),
        "ru/404.md": head.format(t="Не найдено", h="Страницы нет", x=""),
        "en/services/_index.md": head.format(
            t="Catalog", h="Our catalog", x="children_type: service\n"
        ),
        "en/services/design.md": service,
        "en/services/planning.md": head.format(t="Planning", h="Space planning", x=""),
    }
    for rel, text in files.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    assert (dist / "services" / "design" / "index.html").is_file()
    assert "/старый-адрес/  /services/design/;" in (dist / "redirects.map").read_text(
        encoding="utf-8"
    )
    assert "/wp-*  1;" in (dist / "gone.map").read_text(encoding="utf-8")
    design = result.site.page("services/design", "en")
    assert [p.url for p in design.related["related"]] == ["/services/planning/"]


def test_page_template_has_the_same_seo_groups_as_scaffold():
    """Образец страницы и блок, который кладёт движок, — одни и те же восемь групп."""
    group = re.compile(r"^# =+ (.+?) =+$", re.M)
    template = (TEMPLATES / "page.md").read_text(encoding="utf-8")
    scaffold = (ROOT / "heron" / "scaffold" / "text" / "ru" / "seo-block.md").read_text(
        encoding="utf-8"
    )
    assert group.findall(template) == group.findall(scaffold)
    assert len(group.findall(template)) == 8


def test_agents_prompt_names_every_role_document():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for role in ("architect", "content", "designer", "builder"):
        assert f"docs/agents/{role}.md" in text
        assert (AGENTS / f"{role}.md").is_file()
