"""Окружение сборки: что отличает прод от всего остального."""

from __future__ import annotations

from heron.core.environment import BuildEnv
from heron.scaffold import create


def test_prod_opens_index_and_counters():
    env = BuildEnv.named("prod")
    assert env.indexable and env.analytics and env.is_prod


def test_anything_but_prod_is_closed():
    for name in ("dev", "stage", "preview", ""):
        env = BuildEnv.named(name)
        assert not env.indexable, name
        assert not env.analytics, name


def test_default_is_closed():
    """Забыть указать окружение — не повод открыть сайт поисковикам."""
    assert not BuildEnv().indexable


def test_env_var_picks_environment(monkeypatch):
    monkeypatch.setenv("HERON_ENV", "prod")
    assert BuildEnv.resolve().indexable


def test_flag_wins_over_env_var(monkeypatch):
    monkeypatch.setenv("HERON_ENV", "prod")
    assert not BuildEnv.resolve("dev").indexable


def test_keys_override_environment_default(monkeypatch):
    """Прод-подобное превью: собрано как прод, но закрыто от индексации."""
    monkeypatch.setenv("HERON_INDEXABLE", "false")
    env = BuildEnv.resolve("prod")
    assert not env.indexable
    assert env.analytics


def test_new_site_holds_content_only(tmp_path):
    """Папка сайта — это контент. Сборка живёт в HERON, не здесь."""
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")
    forbidden = {
        "Dockerfile",
        "compose.yml",
        "docker-compose.yml",
        "build.sh",
        ".env",
        ".env.example",
        "deploy.sh",
        "Makefile",
    }
    present = {p.name for p in root.rglob("*") if p.is_file()}
    assert not (forbidden & present), sorted(forbidden & present)
    assert (root / "site.yaml").is_file()
    assert (root / "content").is_dir()


def test_new_site_has_no_content_pages(tmp_path):
    """Контента при старте может не быть: сначала конфиг, потом страницы."""
    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")
    assert not list((root / "content").rglob("*.md"))
    assert (root / "content" / "uk").is_dir()


def test_init_takes_languages_from_site_yaml(tmp_path):
    """Языки объявляет site.yaml, а не то, какие папки уже завелись."""
    from heron.scaffold import adopt

    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")

    config = root / "site.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "  default_lang: uk\n  languages: [uk]",
            "  default_lang: ru\n  languages: [ru, uk, en]",
        ),
        encoding="utf-8",
    )
    adopt(root)

    for lang in ("ru", "uk", "en"):
        assert (root / "content" / lang).is_dir(), lang
        assert (root / "theme" / "i18n" / f"{lang}.yaml").is_file(), lang


def test_init_survives_broken_site_yaml(tmp_path):
    """`init` зовут именно тогда, когда конфиг ещё сырой. Падать нельзя."""
    from heron.scaffold import adopt

    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")
    (root / "site.yaml").write_text("site: [это не словарь\n", encoding="utf-8")
    adopt(root)
    assert (root / "content").is_dir()


def test_empty_site_builds_in_dev(tmp_path):
    """Тему доводят раньше, чем пишут контент — на деве это норма."""
    from heron.core import build as pipeline

    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")
    result = pipeline.run(root, env=BuildEnv.named("dev"))
    assert not result.failed
    assert "robots.txt" in result.written


def test_empty_site_refuses_to_build_in_prod(tmp_path):
    """А наружу пустой сайт не выкладывают: это всегда чья-то ошибка."""
    from heron.core import build as pipeline

    root = tmp_path / "demo"
    root.mkdir()
    create(root, name="demo")
    result = pipeline.run(root, env=BuildEnv.named("prod"))
    assert result.failed
    assert [e.code for e in result.collector.errors] == ["E017"]
