"""Данные структурированных секций совпадают с их html: метки ссылок, шаги, ссылки на втором языке."""

from heron.core import links, tree
from tests import sites


def _scan(tmp_path, body: str):
    files = {"uk/index.md": sites.page("Головна"), "uk/doc.md": _doc(body)}
    content = sites.build(tmp_path, files)
    site, _ = tree.scan(content, sites.config())
    return site.by_url["/doc/"].sections


def _doc(body: str) -> str:
    return f"---\ntitle: Док\nh1: Док\ndescription: Опис\n---\n\n{body}"


def test_reference_label_in_list_resolves_to_address(tmp_path):
    sections = _scan(
        tmp_path,
        "## Список {#items}\n\n- [текст][метка]\n- второй\n\n[метка]: /adres/\n",
    )
    data = str(sections["items"].data)
    assert "/adres/" in data
    assert "[текст][метка]" not in data


def test_reference_label_in_lead_resolves_to_address(tmp_path):
    sections = _scan(
        tmp_path,
        "## Раздел {#sec}\n\nПодводка [текст][метка] здесь.\n\n- пункт\n- второй\n\n[метка]: /adres/\n",
    )
    section = sections["sec"]
    assert "/adres/" in section.lead
    assert "[текст][метка]" not in section.lead


def test_bullet_list_with_nested_ordered_is_not_steps(tmp_path):
    sections = _scan(tmp_path, "## Список {#sec}\n\n- пункт\n  1. вложенный\n  2. второй\n")
    assert sections["sec"].kind != "steps"


def test_quote_with_ordered_list_is_not_steps(tmp_path):
    sections = _scan(tmp_path, "## Цитата {#sec}\n\n> 1. раз\n> 2. два\n")
    assert sections["sec"].kind != "steps"


def test_plain_ordered_list_is_still_steps(tmp_path):
    sections = _scan(tmp_path, "## Как {#sec}\n\n1. **Первый.** Текст\n2. **Второй.** Текст\n")
    assert sections["sec"].kind == "steps"
    assert len(sections["sec"].data) == 2


def _resolved(tmp_path, ru_body: str):
    files = {
        "uk/index.md": sites.page("Головна"),
        "uk/services/_index.md": sites.page("Послуги", type="category", children_type="service"),
        "uk/services/design.md": sites.page("Дизайн"),
        "ru/index.md": sites.page("Главная"),
        "ru/services/_index.md": sites.page("Услуги", type="category", children_type="service"),
        "ru/services/design.md": sites.page("Оформление"),
        "ru/about.md": _doc(ru_body),
    }
    content = sites.build(tmp_path, files)
    config = sites.config()
    site, collector = tree.scan(content, config)
    links.resolve(site, config, sites.theme(), collector)
    return site.by_url["/ru/about/"]


def test_step_more_links_are_localized_in_links(tmp_path):
    page = _resolved(
        tmp_path,
        "## Как {#how}\n\n1. **Шаг.** Первый абзац.\n\n   Продолжение [дизайн](/services/design/).\n"
        "2. **Второй.** Текст\n",
    )
    step = page.sections["how"].data[0]
    assert "/ru/services/design/" in step["html"]
    assert [item["href"] for item in step["links"]] == ["/ru/services/design/"]


def test_tabs_links_match_tabs_html_in_second_language(tmp_path):
    page = _resolved(
        tmp_path,
        "## Вкладки {#t .tabs}\n\n### Первая\n\nСм. [дизайн](/services/design/).\n\n### Вторая\n\nТекст\n",
    )
    tab = page.sections["t"].data[0]
    assert "/ru/services/design/" in tab["html"]
    assert [item["href"] for item in tab["links"]] == ["/ru/services/design/"]
