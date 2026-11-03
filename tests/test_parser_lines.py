"""Номера строк и комментарии автора: ошибка указывает на настоящую строку файла."""

from heron.core import tree
from heron.core.parser import markdown
from tests import sites

HEAD = "---\ntitle: T\nh1: T\ndescription: D\n---\n"


def scan(tmp_path, text: str, **over):
    content = sites.build(tmp_path, {"uk/index.md": text})
    return tree.scan(content, sites.config(**over))


def codes(collector) -> list[str]:
    return [e.code for e in collector.errors]


def test_bad_id_points_to_real_file_line(tmp_path):
    text = "---\ntitle: T\nh1: T\ndescription: D\n---\n\n## X {#Bad_Id}\n"
    _, collector = scan(tmp_path, text)
    errors = [e for e in collector.errors if e.code == "E016"]
    assert errors and errors[0].line == 7


def test_multiline_comment_keeps_line_numbers(tmp_path):
    text = HEAD + "\n<!-- заметка\nв три\nстроки -->\n\n## X {#Bad_Id}\n"
    _, collector = scan(tmp_path, text)
    errors = [e for e in collector.errors if e.code == "E016"]
    assert errors and errors[0].line == 11


def test_raw_html_line_number(tmp_path):
    text = HEAD + "\nТекст.\n\n<div>x</div>\n"
    _, collector = scan(tmp_path, text)
    errors = [e for e in collector.errors if e.code == "E015"]
    assert errors and errors[0].line == 9


def test_comment_removed_and_newlines_kept():
    out = markdown.strip_comments("a <!-- x\ny\nz --> b\nc")
    assert "<!--" not in out
    assert out.count("\n") == 3
    assert out.startswith("a ") and out.endswith(" b\nc")


def test_comments_in_code_survive():
    inline = "Пример `<!-- заметка -->` тут.\n"
    indented = "Текст.\n\n    <!-- заметка -->\n"
    fenced = "- пункт\n\n  ```html\n  <!-- заметка -->\n  ```\n"
    for src in (inline, indented, fenced):
        assert "<!-- заметка -->" in markdown.strip_comments(src)


def test_comment_in_prose_removed_but_code_kept():
    out = markdown.strip_comments("Текст <!-- убрать --> и `<!-- оставить -->`.\n")
    assert "убрать" not in out
    assert "<!-- оставить -->" in out


def test_commented_heading_attr_not_checked(tmp_path):
    text = HEAD + "\n## Тема {#ok}\n\nТекст.\n\n<!--\n## Старое {#old onclick=x}\n-->\n"
    _, collector = scan(tmp_path, text)
    assert "E025" not in codes(collector)


def test_forbidden_attr_outside_comment_still_fails(tmp_path):
    text = HEAD + "\n## Тема {#ok onclick=x}\n\nТекст.\n"
    _, collector = scan(tmp_path, text)
    errors = [e for e in collector.errors if e.code == "E025"]
    assert errors and errors[0].line == 7


def test_link_in_comment_not_collected(tmp_path):
    text = HEAD + "\nТекст.\n\n<!-- см. [там](/uk/nowhere/) -->\n\n[тут](/uk/other/)\n"
    site, _ = scan(tmp_path, text)
    hrefs = [href for _, href in site.by_key[("uk", "")].links]
    assert "/uk/nowhere/" not in hrefs
    assert "/uk/other/" in hrefs


def test_u2028_does_not_shift_section_raw(tmp_path):
    text = HEAD + "\n## Первая {#first}\n\nодин два\n\n## Вторая {#second}\n\nконец\n"
    site, collector = scan(tmp_path, text)
    assert not collector.errors
    first = site.by_key[("uk", "")].sections["first"]
    assert first.raw.startswith("один")
    assert "два" in first.raw
    assert "## Вторая" not in first.raw
    second = site.by_key[("uk", "")].sections["second"]
    assert second.raw.strip() == "конец"


def test_split_lines_only_on_newlines():
    assert markdown.split_lines("a b\fc\r\nd\re\n") == ["a b\fc", "d", "e", ""]
