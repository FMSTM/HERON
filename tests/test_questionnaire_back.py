"""Опросы терминала: `<` - шаг назад, основной язык не из списка, подпись «заменяет».

`heron new`/`init` (опрос сайта) и `page add`/`category add` (опросник страницы):
`<` возвращает к предыдущему вопросу с прежним ответом в скобках, на первом вопросе
говорит, что раньше ничего нет; ответы дальше не теряются; `\\<` - сам знак `<`;
до последнего «записать?» на диск ничего не пишется. Основной язык, которого нет в
языках сайта, - вопрос «добавить?», а не тупик.

Спецификация: docs/ru/spec/21-engine.md, §10 («Опрос в терминале: шаг назад»).
"""

from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron import cli
from heron.cli import main
from heron.edit import console
from heron.edit import entity as ops
from heron.scaffold import create
from heron.steps import Steps, literal, with_default


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.delenv("HERON_IN_CONTAINER", raising=False)
    monkeypatch.setattr(cli, "in_container", lambda: False)
    monkeypatch.setattr(cli, "can_ask", lambda: True)
    return tmp_path


def run(*args, input=None):
    return CliRunner().invoke(main, [str(a) for a in args], input=input)


def site_of(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))["site"]


def lines(*answers: str) -> str:
    return "\n".join(answers) + "\n"


# --- опрос сайта: подпись языков -------------------------------------------------


@pytest.mark.parametrize(
    ("notes", "words"),
    [
        ("en", "What you type replaces the list in brackets; Enter keeps it"),
        ("ru", "Введённое заменяет список в скобках; Enter - оставить"),
    ],
)
def test_languages_prompt_says_the_answer_replaces_the_brackets(here, notes, words):
    result = run("new", "s", "--notes", notes, input=lines("S", "", "en", "n"))
    assert result.exit_code == 0, result.output
    assert words in result.output
    intro = "< - back to the previous question" if notes == "en" else "< - назад к предыдущему"
    assert intro in result.output


# --- опрос сайта: основной язык не из списка ----------------------------------------


def test_owner_case_main_language_not_in_the_list_is_offered_to_add(here):
    """Ровно случай владельца: языки «ru, de», основной «en» - вопрос «добавить?», да."""
    result = run("init", ".", "--notes", "ru", input=lines("S", "", "ru, de", "en", "", ""))
    assert result.exit_code == 0, result.output
    assert "en нет в языках сайта. Добавить? [Y/n]" in result.output
    assert "языки сайта: ru, de, en" in result.output
    site = site_of(here)
    assert site["default_lang"] == "en"
    assert set(site["languages"]) == {"ru", "de", "en"}
    assert (here / "content" / "en" / "index.md").is_file()


def test_refusing_to_add_asks_for_the_main_language_again(here):
    result = run("new", "s", "--notes", "en", input=lines("S", "", "ru, de", "en", "n", "de", ""))
    assert result.exit_code == 0, result.output
    assert result.output.count("Main language") == 2
    site = site_of(here / "s")
    assert site["default_lang"] == "de" and site["languages"] == ["de", "ru"]


def test_flags_never_add_a_language_silently(here):
    """`-y` и `--answers` не спрашивают: основной язык не из списка - ошибка с подсказкой."""
    create(here / "s", name="S", languages=["ru", "de"], notes="en")
    answers = here / "a.yaml"
    answers.write_text("site:\n  languages: [ru, de]\n  default_lang: en\n", "utf-8")
    result = run("setup", "s", "--answers", answers)
    assert result.exit_code != 0
    assert "'en' is not among the site languages (ru, de)" in result.output
    assert "add it to site.languages or pick site.default_lang from them" in result.output
    assert site_of(here / "s")["languages"] == ["ru", "de"]


def test_setup_reads_a_site_yaml_whose_main_language_is_not_in_the_list(here):
    """Конфигуратор не начинает блок «Сайт» с нуля: имя и языки - как записаны."""
    from heron.setup import state

    create(here / "s", name="Keep me", languages=["ru", "de"], notes="en")
    path = here / "s" / "site.yaml"
    path.write_text(path.read_text("utf-8").replace("default_lang: ru", "default_lang: en"))
    site = state(here / "s")["answers"]["site"]
    assert (site["name"], site["languages"], site["default_lang"]) == (
        "Keep me",
        ["ru", "de"],
        "en",
    )


# --- опрос сайта: шаг назад ------------------------------------------------------


def test_back_on_the_first_question_says_there_is_nothing_before(here):
    result = run("new", "s", "--notes", "en", input=lines("<", "S", "", "en", ""))
    assert result.exit_code == 0, result.output
    assert "there is nothing before: this is the first question" in result.output
    assert site_of(here / "s")["name"] == "S"


def test_back_returns_with_the_answer_in_brackets_and_keeps_later_answers(here):
    answers = lines(
        "Shop",
        "shop.example",
        "en, de",
        "<",  # основной язык -> назад к языкам
        "<",  # языки -> назад к домену
        "",  # домен: в скобках shop.example, Enter - оставить
        "",  # языки: ответ, данный раньше, в скобках - Enter
        "de",
        "<",  # «создать?» -> назад к основному языку
        "",  # основной язык: в скобках de
        "y",
    )
    result = run("new", "s", "--notes", "en", input=answers)
    assert result.exit_code == 0, result.output
    out = result.output
    assert out.count("› [shop.example]") == 2, out
    assert out.count("› [en, de]") == 2, out
    assert "› [de]" in out
    site = site_of(here / "s")
    assert (site["domain"], site["languages"], site["default_lang"]) == (
        "shop.example",
        ["de", "en"],
        "de",
    )


def test_nothing_is_written_until_the_final_answer(here):
    answers = lines("Shop", "", "en", "<", "<", "", "", "n")
    result = run("new", "s", "--notes", "en", input=answers)
    assert result.exit_code == 0, result.output
    assert "nothing created" in result.output
    assert not (here / "s" / "site.yaml").exists()


def test_an_escaped_sign_is_the_value_itself(here):
    result = run("new", "s", "--notes", "en", input=lines("\\<", "", "en", ""))
    assert result.exit_code == 0, result.output
    assert site_of(here / "s")["name"] == "<"


def test_back_in_a_real_terminal(tmp_path):
    """Настоящий терминал (pty): `heron init .` - случай владельца с шагом назад."""
    leader, follower = pty.openpty()
    env = dict(os.environ, HERON_NOTES="en", TERM="xterm", COLUMNS="200")
    env.pop("HERON_IN_CONTAINER", None)
    code = "from heron.cli import main; main()"
    process = subprocess.Popen(
        [sys.executable, "-c", code, "init", "."],
        cwd=tmp_path,
        stdin=follower,
        stdout=follower,
        stderr=follower,
        env=env,
    )
    os.close(follower)
    answers = ["S", "", "ru, de", "en", "<", "<", "en, ru, de", "en", ""]
    out = b""
    deadline = time.monotonic() + 120
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([leader], [], [], 0.5)
            if ready:
                try:
                    chunk = os.read(leader, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
                # отвечаем, когда терминал ждёт ввода: подсказка «›» или «[Y/n]» в конце
                tail = out.decode("utf-8", "replace").rstrip(" ")
                if answers and (tail.endswith("]") or tail.endswith("›")):
                    os.write(leader, (answers.pop(0) + "\r").encode())
            elif process.poll() is not None:
                break
    finally:
        os.close(leader)
        process.wait(timeout=30)
    text = out.decode("utf-8", "replace")
    assert process.returncode == 0, text
    assert "en is not among the site languages. Add it? [Y/n]" in text, text
    assert "› [ru, de]" in text  # назад к языкам: ответ, данный раньше, в скобках
    site = site_of(tmp_path)
    assert site["default_lang"] == "en" and site["languages"] == ["en", "ru", "de"]


# --- опросник страницы ----------------------------------------------------------


@pytest.fixture
def one(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    monkeypatch.setattr(cli, "can_ask", lambda: True)
    root = tmp_path / "one"
    create(root, name="Demo", languages=["en"], notes="en")
    return root


def front(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


# новая страница сайта на одном языке: категория, title, h1, description, slug,
# четыре свёрнутые группы, eyebrow, вводный текст - и «записать?»
REST = ["", "", "", "", "", "", ""]


def test_page_add_back_across_questions_and_groups(one):
    answers = [
        "<",  # категория - первый вопрос
        "",
        "T1",
        "<",  # h1 -> назад к title: в скобках T1
        "",
        "H1",
        "D1",
        "<",  # slug (следующая группа) -> назад к description: в скобках D1
        "D2",
        *REST,
        "<",  # «записать?» -> назад к вводному тексту
        "",
        "",
    ]
    result = run("page", "add", "about", one, "--notes", "en", input=lines(*answers))
    assert result.exit_code == 0, result.output
    out = result.output
    assert "< - back to the previous question" in out
    assert "there is nothing before: this is the first question" in out
    assert "› [T1]" in out and "› [D1]" in out
    data = front(one / "content" / "en" / "about.md")
    assert (data["title"], data["h1"], data["description"]) == ("T1", "H1", "D2")


def test_page_add_keeps_later_answers_and_writes_nothing_before_the_end(one):
    answers = ["", "T1", "H1", "<", "<", "T2", "", "D1", *REST, "n"]
    result = run("page", "add", "about", one, "--notes", "en", input=lines(*answers))
    assert result.exit_code == 0, result.output
    # h1: назад с description и снова после нового title - ответ, данный раньше, в скобках
    assert result.output.count("› [H1]") == 2, result.output
    assert not (one / "content" / "en" / "about.md").exists()
    answers = ["", "T1", "H1", "<", "<", "T2", "", "D1", *REST, ""]
    result = run("page", "add", "about", one, "--notes", "en", input=lines(*answers))
    assert result.exit_code == 0, result.output
    data = front(one / "content" / "en" / "about.md")
    assert (data["title"], data["h1"], data["description"]) == ("T2", "H1", "D1")


class Script:
    def __init__(self, answers):
        self.answers = list(answers)
        self.out: list[str] = []

    def io(self):
        def ask(prompt):
            self.out.append(prompt)
            return self.answers.pop(0)

        def echo(text="", color=None, dim=False, bold=False):
            self.out.append(text)

        return console.Io(ask, echo)


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.delenv("HERON_NOTES", raising=False)
    root = tmp_path / "demo"
    create(root, name="Demo", languages=["en"], notes="en", demo=True)
    return root


def _ask_field(root: Path, path: str, answers: list[str]):
    entity = ops.open_entity(ops.context(root, "en"), "blocks")
    item = next(f for f in ops.fields_of(entity, "en") if f.path == path)
    script = Script(answers)
    session = console.Console(entity, script.io(), "en")
    start = dict(entity.pages)

    def reset() -> None:
        entity.pages = dict(start)

    changed = session.steps.run(lambda: session.field("en", item), reset)
    assert not script.answers, script.answers
    return changed, entity, script


def test_list_items_go_back_one_item_at_a_time(demo):
    answers = [
        "+",
        "Q1",
        "A1",
        "<",  # вопрос второго пункта, пустая строка -> назад к ответу первого
        "A1x",
        "Q2",
        "A2",
        "",  # конец списка
    ]
    changed, entity, script = _ask_field(demo, "sections.faq.items", answers)
    assert changed
    text = entity.pages["en"].text
    assert "Q1" in text and "A1x" in text and "Q2" in text and "A2" in text
    assert any(line.startswith("  item 1: a") and line.endswith("[A1] ›") for line in script.out)


def test_list_back_on_the_first_item_returns_to_the_list_question(demo):
    answers = ["+", "<", "+", "Q1", "A1", ""]
    changed, entity, script = _ask_field(demo, "sections.faq.items", answers)
    assert changed
    assert "  › [+]" in script.out  # первый вопрос списка - с прежним ответом в скобках
    assert "Q1" in entity.pages["en"].text


def test_an_escaped_sign_in_a_field_is_the_sign(demo):
    changed, entity, _ = _ask_field(demo, "sections.faq.items", ["+", "\\<", "A", ""])
    assert changed
    item = next(f for f in ops.fields_of(entity, "en") if f.path == "sections.faq.items")
    assert item.value == [{"q": "<", "a": "A"}]


# --- сам механизм ------------------------------------------------------------------


def test_literal_and_brackets():
    assert literal("\\<") == "<" and literal("\\\\<") == "\\<" and literal("<b>") == "<b>"
    assert with_default("  › [en]", "ru, de") == "  › [ru, de]"
    assert with_default("  item 2 ›", "x") == "  item 2 [x] ›"
    assert with_default("Add it? [Y/n]", "n") == "Add it? [n]"


def test_steps_replay_is_silent_and_retries_belong_to_their_question():
    out: list[str] = []
    feed = iter(["a", "bad", "b", "<", "", "c"])

    def body() -> list[str]:
        steps.echo("first")
        one = steps.ask("1 ›", key="one")
        steps.echo("second")
        again = False
        while True:
            two = steps.ask("2 ›", key="two", again=again)
            if two != "bad":
                break
            again = True
        steps.echo("third")
        three = steps.ask("3 ›", key="three")
        return [one, two, three]

    steps = Steps(lambda prompt: (out.append(prompt), next(feed))[1], out.append, "none")
    assert steps.run(body) == ["a", "b", "c"]
    # назад с третьего: повтор молчит до второго вопроса, его подсказка - снова на экране
    assert out == [
        "first",
        "1 ›",
        "second",
        "2 ›",
        "2 ›",
        "third",
        "3 ›",
        "second",
        "2 [b] ›",
        "third",
        "3 ›",
    ]
