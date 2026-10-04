"""Ссылки в тексте при разных слагах языков: сначала ключ, потом адрес.

Спецификация: docs/spec/20-data-contract.md, раздел 2.
"""

from heron.core import links, tree
from tests import sites


def page(title: str, body: str, **fields) -> str:
    head = "\n".join(f"{k}: {v}" for k, v in fields.items())
    head = f"\n{head}" if head else ""
    return (
        f"---\ntitle: {title}\nh1: {title}\ndescription: Опис{head}\n---\n\n"
        f"## Текст {{#what}}\n\n{body}\n"
    )


FILES = {
    "uk/index.md": sites.page("Головна"),
    "ru/index.md": sites.page("Главная"),
    # раздел: у uk адрес из имени папки, у ru — свой слаг
    "uk/guides/_index.md": sites.page("Посібники"),
    "ru/guides/_index.md": sites.page("Руководства", slug="rukovodstva"),
    "uk/guides/x.md": sites.page("Посібник"),
    "ru/guides/x.md": sites.page("Руководство"),
    # только на основном языке
    "uk/guides/only.md": sites.page("Лише uk"),
    "uk/a.md": page(
        "Посилання",
        "[x](/guides/x/) [x#](/guides/x/?a=1#faq) [дім](/) [only](/guides/only/)",
    ),
    "ru/a.md": page(
        "Ссылки",
        "[x](/guides/x/) [x#](/guides/x/?a=1#faq) [дом](/) [only](/guides/only/) "
        "[адрес](/rukovodstva/x/) [полный](/ru/rukovodstva/x/) [uk-адрес](/guides/) "
        "[файл](/media/a.pdf) [txt](/llms.txt) [cdn](//cdn.example.org/x/) "
        "[нет](/nowhere/)",
    ),
}


def built(tmp_path, files=None):
    content = sites.build(tmp_path, files or FILES)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site, collector


def html(site, url: str) -> str:
    return site.by_url[url].sections["what"].html


def test_key_link_gets_page_address_in_the_page_language(tmp_path):
    site, _ = built(tmp_path)
    assert 'href="/ru/rukovodstva/x/"' in html(site, "/ru/a/")
    assert 'href="/guides/x/"' in html(site, "/a/")


def test_anchor_and_query_survive(tmp_path):
    site, _ = built(tmp_path)
    assert 'href="/ru/rukovodstva/x/?a=1#faq"' in html(site, "/ru/a/")
    assert 'href="/guides/x/?a=1#faq"' in html(site, "/a/")


def test_home_key_is_slash(tmp_path):
    site, _ = built(tmp_path)
    assert 'href="/ru/"' in html(site, "/ru/a/")
    assert 'href="/"' in html(site, "/a/")


def test_address_in_page_language_and_full_address(tmp_path):
    site, _ = built(tmp_path)
    text = html(site, "/ru/a/")
    # /rukovodstva/x/ не ключ — ищется как адрес в языке страницы
    assert text.count('href="/ru/rukovodstva/x/"') >= 3
    # /guides/ — ключ раздела: русская версия
    assert 'href="/ru/rukovodstva/"' in text


def test_missing_translation_falls_back_to_default_with_warning(tmp_path):
    site, collector = built(tmp_path)
    assert 'href="/guides/only/"' in html(site, "/ru/a/")
    said = [w for w in collector.warnings if w.kind == "ссылки" and "only" in w.message]
    assert len(said) == 1
    assert said[0].path == "ru/a.md"
    assert "'uk'" in said[0].message


def test_resources_and_files_are_untouched(tmp_path):
    site, collector = built(tmp_path)
    text = html(site, "/ru/a/")
    assert 'href="/media/a.pdf"' in text
    assert 'href="/llms.txt"' in text
    assert 'href="//cdn.example.org/x/"' in text
    messages = [w.message for w in collector.warnings if w.kind == "ссылки"]
    assert not any("llms.txt" in m or "cdn" in m or "media" in m for m in messages)


def test_nothing_found_warns_with_file_line_and_link(tmp_path):
    site, collector = built(tmp_path)
    assert 'href="/nowhere/"' in html(site, "/ru/a/")
    broken = [w for w in collector.warnings if "никуда не ведёт" in w.message]
    assert [(w.path, w.message) for w in broken] == [
        ("ru/a.md", "ссылка /nowhere/ никуда не ведёт")
    ]
    assert broken[0].line == 9


def test_key_wins_over_address(tmp_path):
    """Строка — одновременно ключ одной страницы и адрес другой: берётся ключ."""
    files = {
        "uk/index.md": sites.page("Головна"),
        "ru/index.md": sites.page("Главная"),
        # ключ old, адрес /new/
        "uk/old.md": sites.page("Стара", slug="new"),
        # ключ other, адрес /old/
        "uk/other.md": sites.page("Інша", slug="old"),
        "uk/a.md": page("Посилання", "[x](/old/)"),
    }
    site, _ = built(tmp_path, files)
    assert 'href="/new/"' in html(site, "/a/")
