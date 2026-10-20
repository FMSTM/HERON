"""Расхождения сайта и движка, закрытые в 0.1 beta.

- просмотр в контейнере слушает все интерфейсы;
- код в странице не просит движок искать файлы `media/`;
- шаги не теряют блоки кода;
- форма `tabs`;
- отчёт о неиспользуемых модулях видит вызовы из partials.
"""

from pathlib import Path

from heron.core import media, watch
from heron.core.parser import blocks, markdown, sections
from heron.core.report import unused_modules


def test_serve_listens_everywhere_only_in_container():
    assert watch.default_host(True) == "0.0.0.0"
    assert watch.default_host(False) == "127.0.0.1"
    assert watch.shown_url("0.0.0.0", 8000) == "http://localhost:8000/"
    assert watch.shown_url("::1", 8001) == "http://[::1]:8001/"


def test_without_code_keeps_lines_and_hides_code():
    text = (
        "Текст ![a](/media/a.jpg)\n"
        "| `![b](/media/b.jpg)` |\n"
        "```md\n![c](/media/c.jpg)\n```\n"
        "1. шаг\n\n   ```\n   ![d](/media/d.jpg)\n   ```\n"
    )
    masked = markdown.without_code(text)
    assert masked.count("\n") == text.count("\n")
    assert [len(x) for x in masked.split("\n")] == [len(x) for x in text.split("\n")]
    found = {m.group(1) for m in media.REFERENCE.finditer(masked)}
    assert found == {"/media/a.jpg"}


def _section(body: str):
    md = markdown.make()
    _, found = sections.split(md, body, "a.md")
    blocks.apply(md, found)
    return next(iter(found.values()))


def test_steps_keep_code_blocks():
    section = _section(
        "## A {#a}\n\n1. **Создайте.** Команда:\n\n   ```bash\n   heron new x -y\n   ```\n\n"
        "2. **Соберите.** Просто текст.\n"
    )
    first, second = section.data
    assert "heron new x -y" in first["more"]
    assert "heron new x -y" in first["html"]
    assert first["text"] == "Команда:"
    # шаг из одного абзаца — ровно как раньше
    assert second["more"] == ""
    assert second["html"] == second["text"] == "Просто текст."


def test_tabs_form():
    section = _section(
        "## A {#a .tabs}\n\n### Git {#git}\n\nТекст.\n\n"
        "```bash\ngit push\n```\n\n### Файлы\n\n- раз\n"
    )
    assert section.kind == "tabs"
    first, second = section.data
    assert (first["id"], first["title"]) == ("git", "Git")
    assert "git push" in first["html"]
    assert second["id"] == "tab-2"


def test_unused_modules_sees_partials(tmp_path: Path):
    theme = tmp_path
    (theme / "modules").mkdir()
    (theme / "partials").mkdir()
    (theme / "templates").mkdir()
    for name in ("faq", "steps", "lonely", "self"):
        (theme / "modules" / f"{name}.html").write_text("x", encoding="utf-8")
    (theme / "modules" / "self.html").write_text("{{ mod.self('a') }}", encoding="utf-8")
    (theme / "partials" / "sections.html").write_text("{{ mod.faq(s.id) }}", encoding="utf-8")
    (theme / "templates" / "page.html").write_text("{{ mod.steps('how') }}", encoding="utf-8")
    assert unused_modules(theme) == ["lonely", "self"]


def test_unused_modules_silent_on_dynamic_calls(tmp_path: Path):
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "faq.html").write_text("x", encoding="utf-8")
    (tmp_path / "base.html").write_text("{{ mod[section.kind](section.id) }}", encoding="utf-8")
    assert unused_modules(tmp_path) == []
