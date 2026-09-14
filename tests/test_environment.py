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
