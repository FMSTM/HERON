"""Перекрёстные ссылки между краткой и полной версией файлов для нейросетей."""

from heron.core import links, tree
from heron.modules import llms
from tests import sites

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/bio.md": sites.page("Біографія"),
    "ru/index.md": sites.page("Главная"),
    "ru/bio.md": sites.page("Биография"),
}

BASE = "https://example.com"


def built(tmp_path, files=None, **over):
    content = sites.build(tmp_path, files or FILES)
    config = sites.config(**over)
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return llms.generate(site, config)


def test_short_file_points_at_its_full_version(tmp_path):
    files = built(tmp_path, seo={"llms_txt": True})
    assert f"{BASE}/llms-full-uk.txt" in files["llms-uk.txt"]
    assert f"{BASE}/llms-full-ru.txt" in files["llms-ru.txt"]


def test_full_file_points_back_at_the_short_one(tmp_path):
    files = built(tmp_path, seo={"llms_txt": True})
    assert f"{BASE}/llms-uk.txt" in files["llms-full-uk.txt"]
    assert f"{BASE}/llms-ru.txt" in files["llms-full-ru.txt"]


def test_link_stands_in_the_head_before_the_title(tmp_path):
    text = built(tmp_path, seo={"llms_txt": True})["llms-uk.txt"]
    assert text.index("/llms-full-uk.txt") < text.index("# Головна")


def test_root_file_lists_full_versions_too(tmp_path):
    text = built(tmp_path, seo={"llms_txt": True})["llms.txt"]
    for lang in ("uk", "ru"):
        assert f"{BASE}/llms-{lang}.txt" in text
        assert f"{BASE}/llms-full-{lang}.txt" in text
    assert text.index("## Языковые версии") < text.index("## Повні тексти")


def test_without_full_files_nothing_points_at_them(tmp_path):
    files = built(tmp_path, seo={"llms_txt": False})
    assert [name for name in files if "full" in name] == []
    assert not any("llms-full" in text for text in files.values())


def test_single_language_still_gets_the_link_to_full_texts(tmp_path):
    only = {"uk/index.md": sites.page("Головна"), "uk/bio.md": sites.page("Біографія")}
    files = built(
        tmp_path,
        only,
        site={
            "domain": "example.com",
            "theme": "demo",
            "default_lang": "uk",
            "languages": ["uk"],
        },
        seo={"llms_txt": True},
    )
    # Один язык: языковых файлов нет, корневой и есть перечень.
    assert "llms-uk.txt" not in files
    text = files["llms.txt"]
    assert f"{BASE}/llms-full.txt" in text
    assert "Все языковые версии" not in text
    assert f"{BASE}/llms.txt" in files["llms-full.txt"]


def test_no_file_of_the_set_is_a_dead_end(tmp_path):
    files = built(tmp_path, seo={"llms_txt": True})
    names = set(files)
    for name, text in files.items():
        reachable = {other for other in names if other != name and other in text}
        assert reachable, f"{name} — тупик"
