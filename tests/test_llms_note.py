"""Блок сведений о сайте в файлах для нейросетей."""

from heron.core import links, tree
from heron.modules import llms
from tests import sites

FILES = {
    "uk/index.md": sites.page("Головна"),
    "uk/bio.md": sites.page("Біографія"),
    "ru/index.md": sites.page("Главная"),
    "ru/bio.md": sites.page("Биография"),
}

NOTE_UK = "### Про сайт\n\nТелефон: +00 000 000 00 00. Приймаємо з 9 до 18."
NOTE_RU = "### О сайте\n\nТелефон: +00 000 000 00 00. Принимаем с 9 до 18."


def built(tmp_path, **over):
    content = sites.build(tmp_path, FILES)
    config = sites.config(**over)
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return llms.generate(site, config), config


def seo(**over):
    return {"seo": {"llms_txt": True, **over}}


def test_without_the_field_files_are_unchanged(tmp_path):
    plain, _ = built(tmp_path, **seo())
    noted, _ = built(tmp_path, **seo(llms_note={}))
    assert plain == noted


def test_note_lands_in_both_files_of_its_language(tmp_path):
    files, _ = built(tmp_path, **seo(llms_note={"ru": NOTE_RU}))
    assert NOTE_RU in files["llms-ru.txt"]
    assert NOTE_RU in files["llms-full-ru.txt"]
    assert NOTE_RU not in files["llms-uk.txt"]
    assert NOTE_RU not in files["llms-full-uk.txt"]
    # русский не основной — корневой файл его не показывает
    assert NOTE_RU not in files["llms.txt"]


def test_note_of_the_default_language_reaches_the_root_file(tmp_path):
    files, _ = built(tmp_path, **seo(llms_note={"uk": NOTE_UK}))
    assert NOTE_UK in files["llms.txt"]
    assert NOTE_UK in files["llms-uk.txt"]


def test_note_stands_after_the_description_and_before_the_listing(tmp_path):
    files, _ = built(tmp_path, **seo(llms_note={"uk": NOTE_UK}))
    text = files["llms-uk.txt"]
    assert text.index("> Описание") < text.index(NOTE_UK) < text.index("## ")
    full = files["llms-full-uk.txt"]
    assert full.index("# Головна") < full.index(NOTE_UK) < full.index("URL: ")


def test_page_text_looking_like_a_description_does_not_move_the_note(tmp_path):
    files = {
        **FILES,
        "uk/bio.md": (
            "---\ntitle: Біографія\nh1: Біографія\ndescription: Опис\n---\n\n"
            "> Описание\n\n## Що це {#what}\n\n> Описание\n\nТекст.\n"
        ),
    }
    content = sites.build(tmp_path, files)
    config = sites.config(**seo(llms_note={"uk": NOTE_UK}))
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    out = llms.generate(site, config)
    assert out["llms-full-uk.txt"].count(NOTE_UK) == 1
    assert out["llms-full-uk.txt"].index(NOTE_UK) < out["llms-full-uk.txt"].index("URL: ")
