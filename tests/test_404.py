"""Страница 404 на каждом языке: из контента, из шаблона темы, без ничего.

Спецификация: docs/spec/20-data-contract.md, раздел 2, «Страница 404».
"""

from __future__ import annotations

from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.scaffold import create
from tests import sites
from tests.nginx_server import needs_nginx, serve

NF = "---\ntitle: {t}\nh1: {h}\ndescription: Сторінки немає\n---\n\n{body}\n"


def make(tmp_path, with_files=True):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk", "ru"])
    sites.clear_content(root)
    for lang, title in (("uk", "Головна"), ("ru", "Главная")):
        (root / "content" / lang / "index.md").write_text(
            f"---\ntitle: {title} сайту\nh1: {title}\ndescription: О\n---\n\nТекст.\n",
            encoding="utf-8",
        )
    if with_files:
        (root / "content" / "uk" / "404.md").write_text(
            NF.format(t="Не знайдено", h="Такої сторінки немає", body="Спробуйте головну."),
            encoding="utf-8",
        )
        (root / "content" / "ru" / "404.md").write_text(
            NF.format(t="Не найдено", h="Такой страницы нет", body="Попробуйте главную."),
            encoding="utf-8",
        )
    return root


def test_404_from_content_without_declaring_type(tmp_path):
    root = make(tmp_path)
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert not result.failed, [str(e) for e in result.collector.errors]
    dist = root / "dist"
    assert "Такої сторінки немає" in (dist / "404.html").read_text(encoding="utf-8")
    assert "Такой страницы нет" in (dist / "ru" / "404" / "index.html").read_text(encoding="utf-8")
    assert result.site.page("404", "ru").type == "404"
    for name in ("sitemap-uk.xml", "sitemap-ru.xml", "llms-uk.txt", "llms-ru.txt"):
        path = dist / name
        if path.exists():
            assert "/404/" not in path.read_text(encoding="utf-8"), name


def test_without_file_theme_template_is_used_with_warning(tmp_path):
    root = make(tmp_path, with_files=False)
    result = pipeline.run(root)
    assert not result.failed
    assert (root / "dist" / "404.html").is_file()
    assert (root / "dist" / "ru" / "404" / "index.html").is_file()
    said = [w for w in result.collector.warnings if "404.md" in w.message]
    assert len(said) == 2


def test_without_file_and_template_only_warning(tmp_path):
    root = make(tmp_path, with_files=False)
    (root / "theme" / "templates" / "404.html").unlink()
    result = pipeline.run(root)
    assert not result.failed
    assert not (root / "dist" / "404.html").exists()
    assert any("заглушку" in w.message for w in result.collector.warnings)


def test_empty_language_gets_no_generated_404(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    create(root, name="demo", languages=["uk", "ru"])
    sites.clear_content(root)
    (root / "content" / "ru" / "index.md").write_text(
        "---\ntitle: Главная сайта\nh1: Главная\ndescription: О\n---\n\nТекст.\n",
        encoding="utf-8",
    )
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    # основной язык пуст: E021, а не тихая сборка из одной 404
    assert [e.code for e in result.collector.errors] == ["E021"]


@needs_nginx
def test_nginx_serves_404_of_the_language(tmp_path):
    root = make(tmp_path)
    assert not pipeline.run(root).failed
    with serve(root / "dist", tmp_path / "nginx") as get:
        assert get("/nope/")[0] == 404
        assert "Такої сторінки немає" in get.body
        assert get("/ru/nope/")[0] == 404
        assert "Такой страницы нет" in get.body
        assert get("/404.html")[0] == 404  # internal: напрямую не открыть
