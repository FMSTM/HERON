"""Анкета сохраняет комментарии автора в site.yaml и не трогает чужие ключи."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from heron import setup
from heron.scaffold import create
from heron.setup import comments
from heron.setup.answers import read

KEY = re.compile(r"^(\s*)(?:- )?(\"[^\"]*\"|'[^']*'|[^\s#:\"'\-][^:#]*?):(?:\s|$)")

# Ручной файл автора: комментарии над ключами, в конце строки, в конце блока,
# пустые разделы и ключи, которыми конфигуратор не управляет.
MANUAL = """\
# Мой сайт: правлю руками, не удалять.
heron: ">=0.1"

# --- сайт ---
site:
  name: Dr. Example   # имя в шапке
  domain: example.test
  # язык по умолчанию
  default_lang: en
  languages: [en]
  # конец блока site

organization:
  name: Dr. Example

# контакты врача
contact:
  phone: "+00 000 000 00 00"
  # адрес приёма
  street: Main street 1

# пустой раздел, наполню позже
custom:

# адреса, которых больше нет
gone:
  # старые страницы
  - /sample-page/   # снята
  - /wp-*

# формы: правлю руками
forms:
  # заявка с главной
  callback:
    # поля формы
    fields: [name, phone]   # без почты

# свой блок темы
my_block:
  # подпись в подвале
  footer_note: "Работаем по записи"   # короткая
  links:
    # первая ссылка
    - /about/
  # конец своего блока

# разметка, конфигуратор её не трогает
schema:
  entity:
    "@type": IndividualPhysician
    # телефон из контактов
    telephone: "{{ contact.phone }}"
    sameAs:
      # основной профиль
      - https://profile.example.test/x  # профиль

# финальный комментарий файла
"""

# Те же разделы контактов, но каналы уже записаны и прокомментированы автором.
CHANNELS = """\
contact:
  phone: "+00 000 000 00 00"
  channels:
    # основной телефон
    - type: phone   # звонки
      # только будни
      purpose: support
      value: "+00 000 000 00 00"   # основной
    # почта для документов
    - type: email
      value: hello@example.test   # ответ за день
"""

CONTACT = """\
contact:
  phone: "+00 000 000 00 00"
  # адрес приёма
  street: Main street 1
"""

LONG_NAME = " ".join(["Studio of Example and Partners"] * 4)

DOMAINS = """\
  domain: example.test
  domains:
    prod: example.test
    # превью для правок
    dev: preview.example.test   # временно
    # конец блока доменов
"""


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _comments(text: str) -> list[tuple[str, str]]:
    """Множество комментариев: (текст, путь ключа, к которому привязаны)."""
    found: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    pending: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            pending.append(stripped)
            continue
        match = KEY.match(line)
        if not match and stripped.startswith("- "):
            indent = _indent(line)
            owner = ".".join(n for i, n in stack if i < indent)
            path = f"{owner}[-]"
            found += [(c, path) for c in pending]
            pending = []
            inline = re.search(r"\s#\s.*$", line)
            if inline:
                found.append((inline.group(0).strip(), path))
            continue
        if not match:
            continue
        indent = len(match.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, match.group(2)))
        path = ".".join(name for _, name in stack)
        found += [(c, path) for c in pending]
        pending = []
        inline = re.search(r"\s#\s.*$", line)
        if inline:
            found.append((inline.group(0).strip(), path))
    found += [(c, "<end>") for c in pending]
    return sorted(found)


def _config(root: Path) -> dict:
    return yaml.safe_load((root / "site.yaml").read_text("utf-8"))


def _text(root: Path) -> str:
    return (root / "site.yaml").read_text("utf-8")


def _resave(root: Path, change=None) -> str:
    data = read(setup.raw_config(root)).model_dump()
    if change:
        change(data)
    setup.apply(root, setup.Answers.model_validate(data))
    return _text(root)


def _rename(data: dict) -> None:
    data["site"]["name"] = "Renamed Example"


def _scaffold(tmp_path: Path, notes: str) -> Path:
    root = tmp_path / notes
    create(root, name="S", languages=["en"], demo=True, notes=notes)
    return root


def _manual(tmp_path: Path, text: str = MANUAL) -> Path:
    root = _scaffold(tmp_path, "en")
    (root / "site.yaml").write_text(text, encoding="utf-8")
    return root


def _with_channels(tmp_path: Path) -> Path:
    assert CONTACT in MANUAL
    return _manual(tmp_path, MANUAL.replace(CONTACT, CHANNELS))


def _with_domains(tmp_path: Path, block: str = DOMAINS) -> Path:
    assert "  domain: example.test\n" in MANUAL
    return _manual(tmp_path, MANUAL.replace("  domain: example.test\n", block))


def _set_preview(data: dict, value: str = "") -> None:
    data["site"]["preview_domain"] = value


def _section(start: str, end: str) -> str:
    """Кусок MANUAL от начала ключа до конца строки с `end` включительно."""
    return MANUAL[MANUAL.index(start) : MANUAL.index(end) + len(end)]


@pytest.mark.parametrize("notes", ["ru", "en"])
def test_scaffold_comments_survive_save(tmp_path, notes):
    root = _scaffold(tmp_path, notes)
    before = _text(root)
    assert _comments(before), "фикстура heron new должна содержать комментарии"
    after = _resave(root, _rename)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert _comments(after) == _comments(before)


def test_manual_file_comments_survive_save(tmp_path):
    root = _manual(tmp_path)
    before = _text(root)
    assert len(_comments(before)) >= 8
    after = _resave(root, _rename)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert _comments(after) == _comments(before)
    for needle in ("# Мой сайт: правлю руками", "# конец блока site", "# пустой раздел"):
        assert needle in after


def test_unmanaged_keys_untouched(tmp_path):
    root = _manual(tmp_path)
    before = _config(root)
    after_text = _resave(root, _rename)
    after = yaml.safe_load(after_text)
    assert after["schema"] == before["schema"]
    assert "custom" in after and after["custom"] is None
    # блок schema остаётся в тексте как был, байт в байт
    block = MANUAL[MANUAL.index("schema:\n") : MANUAL.index("# профиль\n") + len("# профиль\n")]
    assert block in after_text


@pytest.mark.parametrize("notes", ["ru", "en", "manual"])
def test_repeat_save_is_idempotent(tmp_path, notes):
    root = _manual(tmp_path) if notes == "manual" else _scaffold(tmp_path, notes)
    first = _resave(root, _rename)
    second = _resave(root, _rename)
    assert second == first
    assert _resave(root) == first


def test_file_without_comments_saved_as_before(tmp_path):
    root = _scaffold(tmp_path, "en")
    data = _config(root)
    (root / "site.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    assert not _comments(_text(root))
    after = _resave(root, _rename)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert after.startswith(setup.HEADER["en"])
    assert _resave(root) == after


@pytest.mark.parametrize(
    "block",
    [
        pytest.param(("gone:\n", "  - /wp-*\n"), id="gone"),
        pytest.param(("forms:\n", "# без почты\n"), id="forms"),
        pytest.param(("my_block:\n", "    - /about/\n"), id="own"),
    ],
)
def test_unmanaged_blocks_byte_for_byte(tmp_path, block):
    root = _manual(tmp_path)
    section = _section(*block)
    before = _config(root)
    after = _resave(root, _rename)
    assert section in after
    name = block[0].rstrip(":\n")
    assert yaml.safe_load(after)[name] == before[name]


def test_end_of_block_comment_follows_neighbour_when_blocks_reorder(tmp_path):
    # ordered ставит свой блок после schema; комментарий в конце блока по устройству
    # carry привязан к следующему ключу: остаётся в файле над ним, не теряется
    root = _manual(tmp_path)
    after = _resave(root, _rename)
    assert after.index("# конец своего блока") < after.index("schema:\n")
    assert after.index("schema:\n") < after.index("my_block:\n")
    assert after.count("# конец своего блока") == 1


def test_own_block_in_place_keeps_end_comment_byte_for_byte(tmp_path):
    section = _section("# свой блок темы\n", "# конец своего блока\n")
    text = MANUAL.replace(section + "\n", "").replace(
        "# финальный комментарий", section + "\n# финальный комментарий"
    )
    root = _manual(tmp_path, text)
    after = _resave(root, _rename)
    assert section in after
    assert after.endswith(section + "\n# финальный комментарий файла\n")


def test_changed_channel_keeps_comments_inside_item(tmp_path):
    root = _with_channels(tmp_path)
    before = _text(root)

    def change(data: dict) -> None:
        data["about"]["contacts"][0]["value"] = "+00 000 000 00 99"

    after = _resave(root, change)
    channels = yaml.safe_load(after)["contact"]["channels"]
    assert channels[0]["value"] == "+00 000 000 00 99"
    assert channels[1]["value"] == "hello@example.test"
    assert _comments(after) == _comments(before)
    assert re.search(r'value: "?\+00 000 000 00 99"?\s+# основной', after)
    assert re.search(r"- type: phone\s+# звонки", after)
    assert _resave(root) == after


def test_channel_unchanged_item_stays_byte_for_byte(tmp_path):
    root = _with_channels(tmp_path)

    def change(data: dict) -> None:
        data["about"]["contacts"][0]["value"] = "+00 000 000 00 99"

    after = _resave(root, change)
    assert (
        "    # почта для документов\n"
        "    - type: email\n"
        "      value: hello@example.test   # ответ за день\n"
    ) in after


def test_long_value_with_inline_comment_changed(tmp_path):
    text = MANUAL.replace("name: Dr. Example   # имя в шапке", f"name: {LONG_NAME}   # имя в шапке")
    assert len(LONG_NAME) > 100
    root = _manual(tmp_path, text)
    before = _text(root)
    new_name = LONG_NAME.replace("Partners", "Colleagues")

    def change(data: dict) -> None:
        data["site"]["name"] = new_name

    after = _resave(root, change)
    assert _config(root)["site"]["name"] == new_name
    assert _comments(after) == _comments(before)
    assert _resave(root) == after


def test_long_value_with_inline_comment_unchanged(tmp_path):
    line = f"name: {LONG_NAME}   # имя в шапке"
    root = _manual(tmp_path, MANUAL.replace("name: Dr. Example   # имя в шапке", line))
    after = _resave(root)
    assert f"  {line}\n" in after


def test_normal_save_has_no_lost_flag(tmp_path):
    root = _manual(tmp_path)
    answers = setup.Answers.model_validate(read(setup.raw_config(root)).model_dump())
    result = setup.apply(root, answers)
    assert "comments_lost" not in result.warnings


def _diverge(_old: list[str], _new: list[str], _top: bool) -> tuple[list[str], list[str]]:
    return ["broken: true"], []


def _explode(_old: list[str], _new: list[str], _top: bool) -> tuple[list[str], list[str]]:
    raise ValueError("отступ не совпал")


@pytest.mark.parametrize("broken", [_diverge, _explode], ids=["diverged", "parse_error"])
def test_lost_flag_when_merge_fails(tmp_path, monkeypatch, broken):
    root = _manual(tmp_path)
    data = read(setup.raw_config(root)).model_dump()
    _rename(data)
    monkeypatch.setattr(comments, "_merge", broken)
    result = setup.apply(root, setup.Answers.model_validate(data))
    assert "comments_lost" in result.warnings
    # данные важнее комментариев: файл без них, но верный, прежний текст в резервной копии
    after = _text(root)
    assert after.startswith(setup.HEADER["en"])
    assert "# Мой сайт" not in after
    assert "broken" not in _config(root)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert _config(root)["schema"]["entity"]["sameAs"]
    assert result.backup
    assert (root / result.backup).read_text("utf-8") == MANUAL


def test_carry_reports_lost_when_data_differ():
    body = "site:\n  name: A\n"
    old = "# мой\nsite:\n  name: A\n"
    text, lost = comments.carry(old, body, "# шапка\n", {"site": {"name": "B"}})
    assert lost is True
    assert text == "# шапка\n" + body


def test_carry_not_lost_when_data_match():
    body = "site:\n  name: A\n"
    old = "# мой\nsite:\n  name: A\n"
    text, lost = comments.carry(old, body, "# шапка\n", {"site": {"name": "A"}})
    assert lost is False
    assert text == "# мой\n" + body


def test_removing_last_key_of_nested_block(tmp_path):
    root = _with_domains(tmp_path)
    before = _text(root)
    assert _config(root)["site"]["domains"]["dev"] == "preview.example.test"
    after = _resave(root, _set_preview)
    domains = yaml.safe_load(after)["site"]["domains"]
    assert domains == {"prod": "example.test"}
    assert "preview.example.test" not in after
    # комментарии над ключом и в его строке уходят вместе с ним, остальные остаются
    assert "# превью для правок" not in after
    assert "# временно" not in after
    assert "# конец блока доменов" in after
    gone = {"# превью для правок", "# временно"}
    kept = [item for item in _comments(before) if item[0] not in gone]
    assert sorted(c for c, _ in _comments(after)) == sorted(c for c, _ in kept)
    assert _resave(root) == after


def test_removing_only_key_removes_block_keeps_neighbours(tmp_path):
    block = (
        "  domain: example.test\n"
        "  domains:\n"
        "    # превью для правок\n"
        "    dev: preview.example.test\n"
        "  # после доменов\n"
    )
    root = _with_domains(tmp_path, block)
    after = _resave(root, _set_preview)
    assert "domains" not in yaml.safe_load(after)["site"]
    assert "# превью для правок" not in after
    assert "# после доменов" in after
    assert "# конец блока site" in after
    assert _resave(root) == after


def test_removing_first_channel_keeps_comments_of_second(tmp_path):
    root = _with_channels(tmp_path)

    def change(data: dict) -> None:
        del data["about"]["contacts"][0]

    after = _resave(root, change)
    channels = yaml.safe_load(after)["contact"]["channels"]
    assert [item["type"] for item in channels] == ["email"]
    # комментарии второго канала остаются при нём, а не на месте удалённого по индексу
    assert (
        "    # почта для документов\n"
        "    - type: email\n"
        "      value: hello@example.test   # ответ за день\n"
    ) in after
    # комментарии удалённого канала не переезжают к соседу
    found = [text for text, _ in _comments(after)]
    for gone in ("# основной телефон", "# звонки", "# только будни", "# основной"):
        assert gone not in found
    assert _resave(root) == after


def test_removing_key_keeps_detached_section_drops_adjacent_comment(tmp_path):
    block = (
        "  domain: example.test\n"
        "  domains:\n"
        "    prod: example.test\n"
        "    # раздел превью\n"
        "\n"
        "    # превью для правок\n"
        "    dev: preview.example.test   # временно\n"
    )
    root = _with_domains(tmp_path, block)
    after = _resave(root, _set_preview)
    assert yaml.safe_load(after)["site"]["domains"] == {"prod": "example.test"}
    assert "preview.example.test" not in after
    # отдалённый пустой строкой раздел остаётся вместе с пустой строкой
    assert "    prod: example.test\n    # раздел превью\n\n" in after
    # комментарий вплотную к ключу и в его строке уходит вместе с ним
    assert "# превью для правок" not in after
    assert "# временно" not in after
    assert _resave(root) == after


def test_inline_only_comments_survive_save_without_lost_flag(tmp_path):
    # ни одной строки-комментария: только комментарии в конце строк
    text = "".join(x for x in MANUAL.splitlines(keepends=True) if not x.lstrip().startswith("#"))
    root = _manual(tmp_path, text)
    before = _comments(text)
    assert before
    assert comments._has_comment(text.splitlines())
    data = read(setup.raw_config(root)).model_dump()
    _rename(data)
    result = setup.apply(root, setup.Answers.model_validate(data))
    assert "comments_lost" not in result.warnings
    after = _text(root)
    assert _config(root)["site"]["name"] == "Renamed Example"
    assert _comments(after.removeprefix(setup.HEADER["en"])) == before
    assert "  name: Renamed Example   # имя в шапке\n" in after
    assert _resave(root) == after


def test_apostrophe_value_with_inline_comment_survives_save(tmp_path):
    line = "name: It's ours   # слоган"
    root = _manual(tmp_path, MANUAL.replace("name: Dr. Example   # имя в шапке", line))
    assert yaml.safe_load(_text(root))["site"]["name"] == "It's ours"
    before = _comments(_text(root))
    after = _resave(root, lambda data: data["site"].update(default_lang="en", name="It's ours"))
    assert f"  {line}\n" in after
    assert ("# слоган", "site.name") in _comments(after)
    assert _comments(after) == before
    # смена значения с апострофом: комментарий остаётся при ключе
    changed = _resave(root, lambda data: data["site"].update(name="It's theirs"))
    assert yaml.safe_load(changed)["site"]["name"] == "It's theirs"
    assert ("# слоган", "site.name") in _comments(changed)
    assert _resave(root) == changed


def test_split_comment_respects_quotes():
    assert comments._split_comment("name: It's ours   # слоган") == (
        "name: It's ours",
        "   # слоган",
    )
    assert comments._split_comment("name: 'a # b'   # c") == ("name: 'a # b'", "   # c")


def test_file_without_comments_output_equals_header_plus_dump(tmp_path):
    root = _scaffold(tmp_path, "en")
    data = _config(root)
    (root / "site.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    assert not _comments(_text(root))
    after = _resave(root, _rename)
    expected = yaml.safe_load(after)
    assert after == setup.HEADER["en"] + setup.dump(expected)
    assert expected["site"]["name"] == "Renamed Example"
    assert _resave(root) == after
