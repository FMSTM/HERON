def test_author_comments_never_reach_the_page():
    """Пояснения, которые автор пишет себе, — не текст страницы.

    Сырой HTML в контенте выключен, поэтому незачищенный комментарий не
    исчезает, а экранируется и выезжает на страницу видимой строкой.
    """
    from heron.core.parser import markdown as md_mod
    from heron.core.parser.sections import split

    md = md_mod.make()
    intro, sections = split(md, "<!-- заметка для себя -->\n\nТекст абзаца.\n", "x.md")
    assert "заметка" not in intro.html
    assert "Текст абзаца" in intro.html


def test_comments_inside_code_blocks_survive():
    from heron.core.parser import markdown as md_mod
    from heron.core.parser.sections import split

    md = md_mod.make()
    intro, _ = split(md, "```html\n<!-- это содержимое -->\n```\n", "x.md")
    assert "это содержимое" in intro.html
