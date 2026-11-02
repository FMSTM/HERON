"""Паритет документации: docs/en повторяет docs/ru файл в файл.

Правило — docs/ru/spec/21-engine.md §14 («паритет документации») и
docs/ru/spec/23-distribution.md §10 («Два языка документации»):

- у каждого docs/ru/** есть docs/en/** с тем же путём и наоборот; исключения —
  docs/en/GLOSSARY.md (рабочий файл переводчиков, пары нет); статус ``missing``
  в docs/translation.yaml не допускается нигде: перевод закончен (E12.S7), beta
  и prod требуют ``current``; список читается из translation.yaml, а не
  хардкодится;
- у пары .md совпадают число строк, заголовки по уровням, последовательность
  явных якорей ``<a id="…"></a>`` в конце строки заголовка (``{#…}`` — разметка
  секций страницы сайта, не якорь документации: в заголовках образца страницы
  она сверяется как литерал, в блоках кода не считается), относительные ссылки
  (цели и порядок), таблицы и строки в каждой, пункты списков, блоки кода (язык
  и строки в каждом);
- побайтно сравниваются только литеральные токены блоков кода — флаги, коды
  ошибок, имена файлов, ключи YAML, начало команды, значения не-строковых
  полей; остальной текст блока (комментарии, плейсхолдеры, подписи, значения
  примеров) переводится и не сравнивается;
- у образцов .yaml и фронтматтера — те же ключи и значения не-строковых полей;
- page.md несёт восемь групп SEO-блока своего языка (heron/scaffold/text/<язык>/seo-block.md);
- в docs/en нет кириллицы вне разрешённых мест (ALLOWED_CYRILLIC): правило либо
  общее (имена второго языка примера), либо привязано к файлу и разделу, где
  русский литерал нужен по смыслу (адрес, строка интерфейса, строка отчёта).

Статус ``stale`` значит «ru уже изменился, перевод догоняет»: пара обязана
существовать, но структура не сверяется — расхождение тогда ожидаемо, а сам
stale ловит scripts/check_translation.py (ошибка на beta/prod).
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
RU = DOCS / "ru"
EN = DOCS / "en"
TRANSLATION = DOCS / "translation.yaml"
SEO_BLOCK = ROOT / "heron" / "scaffold" / "text"

# docs/en без пары в docs/ru: словарь терминов для переводчиков (23 §10, 20 §1).
EN_ONLY = frozenset({"GLOSSARY.md"})


@dataclass(frozen=True)
class Allowed:
    """Одно разрешение кириллицы: фрагмент строки, который можно оставить русским.

    ``file`` (путь от docs/en) и ``section`` сужают правило: без них оно действует во
    всех файлах и разделах. ``section`` — якорь ``<a id>`` заголовка или, если у
    заголовка якоря нет, его текст; правило действует во всём разделе, включая
    подзаголовки, но не за его пределами.
    """

    pattern: str
    reason: str
    file: str | None = None
    section: str | None = None


# Кириллица в docs/en допустима только здесь. Каждое правило вырезает из строки
# разрешённый фрагмент; если после этого кириллица осталась — это непереведённый
# текст. Значения для второго языка примера (llms_note.ru) многострочные и
# разрешаются отдельно — см. _llms_note_ru_lines. Каждое правило обязано где-то
# срабатывать в своём файле и разделе (test_allowed_cyrillic_rules_are_used).
# Правила 20 и 21 — дословные литералы, которые перевод оставляет как есть: адреса
# и строки интерфейса и отчёта, которые движок печатает по-русски (heron/messages.py).
ALLOWED_CYRILLIC: tuple[Allowed, ...] = (
    Allowed(
        r"\bname_ru:\s*[^#\n]*",
        "name_ru — имя сайта на втором языке примера, оно русское по смыслу (23 §10)",
    ),
    Allowed(
        r"\btitle_suffix_ru:\s*\"[^\"\n]*\"",
        "title_suffix_ru — суффикс <title> русских страниц примера (23 §10)",
    ),
    Allowed(
        r"\"Читать далее\"",
        "пример ru-строки интерфейса темы рядом с английской: roles/capabilities.md, guide/04-theme.md, "
        "spec/21-engine.md §7",
    ),
    Allowed(
        r"`/(?:новости|кредит)/?`",
        "20 §2, старые адреса: кириллические адреса-примеры в обратных кавычках",
        "spec/20-data-contract.md",
        "old-addresses-cyrillic",
    ),
    Allowed(
        r"^\s*- /новости-компании/",
        "20 §2, старые адреса: строка yaml-примера redirect_from с кириллическим адресом",
        "spec/20-data-contract.md",
        "old-addresses-cyrillic",
    ),
    Allowed(
        r"\"й\"",
        "20 §2, старые адреса: символ «й» — пример того, что нормализует NFC",
        "spec/20-data-contract.md",
        "old-addresses-cyrillic",
    ),
    Allowed(
        r"\"Записаться\"",
        "21 §7: ru-строка интерфейса темы рядом с английской",
        "spec/21-engine.md",
        "rendering",
    ),
    Allowed(
        r"`/кредит/(?:  /credits/;)?`",
        "21 §9: кириллический адрес-пример и строка карты редиректов",
        "spec/21-engine.md",
        "redirects",
    ),
    Allowed(
        r"\"(?:Страниц — N|Предупреждений — N|… и ещё N|что сделать|Использование|Ошибка)\"",
        "21 §10: ru-строки отчёта, рамки предупреждений и разбора флагов (heron/messages.py)",
        "spec/21-engine.md",
        "10. CLI",
    ),
    Allowed(
        r"`\[en: перевода на ru пока нет\]`|`\(откроется на en\)`",
        "21 §10: пометки `heron docs` на русском (docs_fallback, docs_toc_other)",
        "spec/21-engine.md",
        "10. CLI",
    ),
)
LLMS_NOTE_RU = "llms_note.ru — текст llms*.txt для русской версии сайта примера (23 §10)"

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
FENCE_OPEN = re.compile(r"^(\s*)(`{3,})\s*([^`\s]*)[^`]*$")
FENCE_CLOSE = re.compile(r"^\s*(`{3,})\s*$")  # CommonMark: закрывает только чистая ограда
HEADING = re.compile(r"^(#{1,6})\s")
ANCHOR = re.compile(r"^#{1,6} .*<a id=\"([^\"]+)\"></a>\s*$")
HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:<a id=\"([^\"]+)\"></a>)?\s*$")
SECTION_ID = re.compile(r"\{#([^}\s]+)")
LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
INLINE_CODE = re.compile(r"`[^`\n]*`")
PLACEHOLDER = re.compile(r"<[^<>\n]+>")
FLAG = re.compile(r"(?<![\w-])--[a-z][\w-]*")
ERROR_CODE = re.compile(r"\bE\d{3}\b")
FILE_NAME = re.compile(r"[\w.<>-]*\.(?:md|ya?ml|html|json|jsonl|txt|sh|py|css|js|toml|map|xml)\b")
YAML_KEY = re.compile(r"^\s*(?:-\s+)?([\w\"'@.-]+):(?:\s|$)", re.M)
YAML_SCALAR = re.compile(
    r"^\s*(?:-\s+)?([\w\"'@.-]+):[ \t]+(true|false|null|~|-?\d+(?:\.\d+)?)[ \t]*$", re.M
)
ENV_PREFIX = re.compile(r"^([A-Z_][A-Z0-9_]*)=\S*$")
HERON_CMD = frozenset({"$H", "heron"})
# Блоки, где «#» — не комментарий, а текст (заголовки Markdown, схемы, Jinja).
PROSE_BLOCKS = frozenset({"", "markdown", "md", "jinja", "text"})


def _translation() -> dict[str, dict[str, str]]:
    data = yaml.safe_load(TRANSLATION.read_text(encoding="utf-8"))
    return {entry["path"]: entry for entry in data["files"]}


def _files(base: Path) -> set[str]:
    return {
        path.relative_to(base).as_posix()
        for path in base.rglob("*")
        if path.is_file() and not any(p.startswith(".") for p in path.relative_to(base).parts)
    }


ENTRIES = _translation()
RU_FILES = _files(RU)
EN_FILES = _files(EN)
PAIRS = sorted(rel for rel in RU_FILES if ENTRIES.get(rel, {}).get("en_status") == "current")


# ---------------------------------------------------------------- разбор Markdown


@dataclass
class Block:
    lang: str
    lines: list[str]
    start: int  # номер строки открывающей ограды, с 1


@dataclass
class Doc:
    lines: list[str]
    prose: list[str] = field(default_factory=list)  # строки вне блоков кода
    blocks: list[Block] = field(default_factory=list)


def _closes(line: str, fence: str) -> bool:
    """Закрывает ли строка блок, открытый оградой fence: чистая ограда не короче открывающей."""
    match = FENCE_CLOSE.match(line)
    return bool(match) and len(match.group(1)) >= len(fence)


def _parse(text: str) -> Doc:
    """Делит Markdown на прозу и блоки кода (ограды ``` и длиннее, с отступом тоже)."""
    doc = Doc(lines=text.splitlines())
    current: Block | None = None
    fence = ""
    for number, line in enumerate(doc.lines, 1):
        if current is None:
            match = FENCE_OPEN.match(line)
            if match:
                fence = match.group(2)
                current = Block(lang=match.group(3), lines=[], start=number)
            else:
                doc.prose.append(line)
        elif _closes(line, fence):
            doc.blocks.append(current)
            current = None
        else:
            current.lines.append(line)
    if current is not None:
        doc.blocks.append(current)  # незакрытая ограда — блок до конца файла
    return doc


def _headings(doc: Doc) -> dict[int, int]:
    counts: Counter[int] = Counter()
    for line in doc.prose:
        match = HEADING.match(line)
        if match:
            counts[len(match.group(1))] += 1
    return dict(sorted(counts.items()))


def _anchors(doc: Doc) -> list[str]:
    """Явные якоря `<a id="…"></a>` в конце заголовков вне блоков кода (23 §10)."""
    return [m.group(1) for line in doc.prose if (m := ANCHOR.match(line))]


def _section_ids(doc: Doc) -> list[str]:
    """`{#id}` в заголовках вне блоков кода — секции образца страницы (templates/page.md).

    Это не якорь документации, а разметка, которую читает движок: литерал, он не переводится.
    """
    return [i for line in doc.prose if HEADING.match(line) for i in SECTION_ID.findall(line)]


def _links(doc: Doc) -> list[str]:
    text = INLINE_CODE.sub("", "\n".join(doc.prose))
    return [
        target
        for target in LINK.findall(text)
        if not target.startswith(("http://", "https://", "mailto:", "#"))
    ]


def _tables(doc: Doc) -> list[int]:
    rows, current = [], 0
    for line in [*doc.prose, ""]:
        if line.lstrip().startswith("|"):
            current += 1
        elif current:
            rows.append(current)
            current = 0
    return rows


def _list_items(doc: Doc) -> int:
    return sum(1 for line in doc.prose if LIST_ITEM.match(line))


# ---------------------------------------------------------------- литеральные токены


def _code(block: Block) -> list[str]:
    """Строки блока без комментариев (кроме блоков-прозы) и с плейсхолдерами «<>»."""
    out = []
    for line in block.lines:
        if block.lang not in PROSE_BLOCKS:
            if line.lstrip().startswith("#"):
                continue
            line = re.sub(r"\s+#(?:\s.*)?$", "", line)
        out.append(PLACEHOLDER.sub("<>", line.rstrip()))
    return out


def _command_start(line: str) -> list[str]:
    """Начало команды: программа, у `$H`/`heron` ещё и подкоманда; VAR= — имя переменной."""
    words = line.split()
    tokens = []
    while words and ENV_PREFIX.match(words[0]):
        tokens.append(ENV_PREFIX.match(words[0]).group(1) + "=")
        words.pop(0)
    if words:
        tokens.append(f"cmd:{words[0]}")
        if words[0] in HERON_CMD and len(words) > 1:
            tokens.append(f"cmd:{words[0]} {words[1]}")
    return tokens


def _tokens(block: Block) -> Counter[str]:
    """Мультимножество литеральных токенов блока — то, что не переводится (23 §10)."""
    lines = _code(block)
    code = "\n".join(lines)
    found: Counter[str] = Counter()
    found.update(f"flag:{t}" for t in FLAG.findall(code))
    found.update(f"code:{t}" for t in ERROR_CODE.findall(code))
    # Имя файла — последняя часть пути: папка примера (мой-сайт/ → my-site/) переводится.
    found.update(f"file:{t.rsplit('/', 1)[-1]}" for t in FILE_NAME.findall(code))
    if block.lang == "yaml":
        found.update(f"key:{k}" for k in YAML_KEY.findall(code))
        found.update(f"value:{k}={v}" for k, v in YAML_SCALAR.findall(code))
    if block.lang in ("bash", "sh", "shell"):
        continued = False
        for line in lines:
            if line.strip() and not continued:
                found.update(_command_start(line))
            continued = line.rstrip().endswith("\\")
    return found


def _diff(ru: Counter[str], en: Counter[str]) -> str:
    only_ru = sorted((ru - en).elements())
    only_en = sorted((en - ru).elements())
    return f"только в ru {only_ru}, только в en {only_en}"


# ---------------------------------------------------------------- YAML


def _flat(data: object, prefix: str = "") -> dict[str, object]:
    if isinstance(data, dict):
        out: dict[str, object] = {}
        for key, value in data.items():
            out.update(_flat(value, f"{prefix}{key}."))
        return out
    if isinstance(data, list):
        out = {}
        for index, value in enumerate(data):
            out.update(_flat(value, f"{prefix}{index}."))
        return out
    return {prefix.rstrip("."): data}


def _yaml_problems(ru_text: str, en_text: str, where: str) -> list[str]:
    ru, en = _flat(yaml.safe_load(ru_text)), _flat(yaml.safe_load(en_text))
    problems = []
    if set(ru) != set(en):
        problems.append(
            f"{where}: ключи расходятся: только в ru {sorted(set(ru) - set(en))}, "
            f"только в en {sorted(set(en) - set(ru))}"
        )
    for key in sorted(set(ru) & set(en)):
        if not isinstance(ru[key], str) and ru[key] != en[key]:
            problems.append(f"{where}: значение {key}: ru {ru[key]!r} != en {en[key]!r}")
    return problems


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    if text.startswith("---\n"):
        _, front, body = text.split("---\n", 2)
        return front, body
    return None, text


# ---------------------------------------------------------------- сравнение пары


def _md_problems(ru_text: str, en_text: str) -> list[str]:
    problems = []
    ru_front, ru_body = _split_frontmatter(ru_text)
    en_front, en_body = _split_frontmatter(en_text)
    if (ru_front is None) != (en_front is None):
        problems.append("фронтматтер есть только в одном языке")
    elif ru_front is not None and en_front is not None:
        problems += _yaml_problems(ru_front, en_front, "фронтматтер")
    ru, en = _parse(ru_body), _parse(en_body)
    for name, measure in (
        ("заголовки по уровням", _headings),
        ("якоря <a id> заголовков по порядку", _anchors),
        ("id секций {#…} в заголовках по порядку", _section_ids),
        ("относительные ссылки по порядку", _links),
        ("строки в каждой таблице", _tables),
        ("пункты списков", _list_items),
    ):
        if measure(ru) != measure(en):
            problems.append(f"{name}: ru {measure(ru)} != en {measure(en)}")
    if len(ru.blocks) != len(en.blocks):
        problems.append(f"блоков кода: ru {len(ru.blocks)} != en {len(en.blocks)}")
    for index, (a, b) in enumerate(zip(ru.blocks, en.blocks, strict=False), 1):
        where = f"блок кода №{index} (ru строка {a.start}, en строка {b.start})"
        if a.lang != b.lang:
            problems.append(f"{where}: язык ru {a.lang!r} != en {b.lang!r}")
        if len(a.lines) != len(b.lines):
            problems.append(f"{where}: строк ru {len(a.lines)} != en {len(b.lines)}")
        ru_tokens, en_tokens = _tokens(a), _tokens(b)
        if ru_tokens != en_tokens:
            problems.append(f"{where}: литеральные токены: {_diff(ru_tokens, en_tokens)}")
    return problems


def _problems(rel: str) -> list[str]:
    ru_text = (RU / rel).read_text(encoding="utf-8")
    en_text = (EN / rel).read_text(encoding="utf-8")
    problems = []
    ru_lines, en_lines = len(ru_text.splitlines()), len(en_text.splitlines())
    if ru_lines != en_lines:
        problems.append(f"число строк: ru {ru_lines} != en {en_lines}")
    if rel.endswith((".yaml", ".yml")):
        problems += _yaml_problems(ru_text, en_text, "образец")
    elif rel.endswith(".md"):
        problems += _md_problems(ru_text, en_text)
    return problems


def _report(rel: str, problems: list[str]) -> str:
    return f"docs/en/{rel} расходится с docs/ru/{rel}:\n  - " + "\n  - ".join(problems)


# ---------------------------------------------------------------- кириллица


def _llms_note_ru_lines(lines: list[str]) -> set[int]:
    """Номера строк (с 0) внутри значения llms_note.ru: русский текст второго языка."""
    allowed: set[int] = set()
    note_indent: int | None = None
    ru_indent: int | None = None
    for number, line in enumerate(lines):
        if not line.strip():
            if ru_indent is not None:
                allowed.add(number)
            continue
        indent = len(line) - len(line.lstrip())
        bare = line.strip()
        if ru_indent is not None and indent > ru_indent:
            allowed.add(number)
            continue
        ru_indent = None
        if note_indent is not None and indent <= note_indent:
            note_indent = None
        if re.match(r"llms_note:\s*(?:#.*)?$", bare):
            note_indent = indent
        elif note_indent is not None and re.match(r"ru:\s*[|>]", bare):
            ru_indent = indent
        elif note_indent is not None and re.match(r"ru:\s*\S", bare):
            allowed.add(number)
    return allowed


def _sections(lines: list[str]) -> list[frozenset[str]]:
    """Для каждой строки — разделы, в которых она лежит: якорь или текст каждого заголовка выше.

    Раздел охватывает свои подзаголовки: строка под `### Old addresses` лежит и в нём,
    и в объемлющем `## 2. …`. Заголовки в блоках кода не в счёт (там «#» — комментарий).
    """
    stack: list[tuple[int, str]] = []
    out: list[frozenset[str]] = []
    fence = ""
    for line in lines:
        match = FENCE_OPEN.match(line)
        if not fence and match:
            fence = match.group(2)
        elif fence and _closes(line, fence):
            fence = ""
        heading = None if fence else HEADING_LINE.match(line)
        if heading:
            level = len(heading.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading.group(3) or heading.group(2)))
        out.append(frozenset(name for _, name in stack))
    return out


def _applies(rule: Allowed, rel: str, sections: frozenset[str]) -> bool:
    if rule.file is not None and rule.file != rel:
        return False
    return rule.section is None or rule.section in sections


def _cyrillic_problems(
    rel: str, text: str | None = None, rules: tuple[Allowed, ...] | None = None
) -> list[str]:
    """Строки docs/en/<rel> с кириллицей вне разрешённых мест; text и rules — для проверки."""
    if text is None:
        text = (EN / rel).read_text(encoding="utf-8")
    rules = ALLOWED_CYRILLIC if rules is None else rules
    lines = text.splitlines()
    note = _llms_note_ru_lines(lines)
    sections = _sections(lines)
    problems = []
    for number, line in enumerate(lines):
        if number in note or not CYRILLIC.search(line):
            continue
        rest = line
        for rule in rules:
            if _applies(rule, rel, sections[number]):
                rest = re.sub(rule.pattern, "", rest)
        if CYRILLIC.search(rest):
            problems.append(f"docs/en/{rel}:{number + 1}: {line.strip()}")
    return problems


# ---------------------------------------------------------------- тесты


def test_translation_lists_every_ru_file() -> None:
    """translation.yaml — полный перечень docs/ru: из него тест берёт, что переведено."""
    assert set(ENTRIES) == RU_FILES, (
        f"docs/ru без записи: {sorted(RU_FILES - set(ENTRIES))}; "
        f"запись без файла: {sorted(set(ENTRIES) - RU_FILES)}"
    )


def test_ru_sha256_matches() -> None:
    """ru_sha256 записи — хеш нынешнего русского файла (кроме stale, 23 §10)."""
    wrong = [
        f"docs/ru/{rel}: ru_sha256 {entry['ru_sha256'][:12]}…, на деле "
        f"{hashlib.sha256((RU / rel).read_bytes()).hexdigest()[:12]}…"
        for rel, entry in sorted(ENTRIES.items())
        if entry["en_status"] != "stale"
        and (RU / rel).is_file()
        and hashlib.sha256((RU / rel).read_bytes()).hexdigest() != entry["ru_sha256"]
    ]
    assert not wrong, "хеш не совпадает:\n" + "\n".join(wrong)


def test_every_ru_file_has_en_pair() -> None:
    problems = []
    for rel in sorted(RU_FILES):
        status = ENTRIES.get(rel, {}).get("en_status")
        if status == "missing":
            problems.append(
                f"docs/ru/{rel}: en_status missing — перевод закончен, beta и prod требуют "
                f"current; переведите файл и поставьте current"
            )
        elif rel not in EN_FILES:
            problems.append(f"docs/ru/{rel} ({status}): нет перевода docs/en/{rel}")
    assert not problems, "\n".join(problems)


def test_no_en_file_without_ru_pair() -> None:
    orphans = [f"docs/en/{rel}" for rel in sorted(EN_FILES - RU_FILES - EN_ONLY)]
    assert not orphans, (
        f"в docs/en без пары в docs/ru (разрешён только {sorted(EN_ONLY)}): {orphans}"
    )


def test_there_is_something_to_compare() -> None:
    """Защита от пустого параметра: переведённые пары есть и все они сверяются ниже."""
    assert PAIRS, "translation.yaml не даёт ни одной пары current"
    assert set(PAIRS) <= EN_FILES


@pytest.mark.parametrize("rel", PAIRS)
def test_structure_parity(rel: str) -> None:
    if rel not in EN_FILES:
        pytest.fail(f"docs/en/{rel} нет (см. test_every_ru_file_has_en_pair)")
    problems = _problems(rel)
    assert not problems, _report(rel, problems)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_page_template_has_seo_groups(lang: str) -> None:
    """templates/page.md — те же 8 групп SEO-блока, что кладёт `heron page`."""
    if not (DOCS / lang / "templates" / "page.md").is_file():
        pytest.skip(f"docs/{lang}/templates/page.md ещё нет")
    group = re.compile(r"^# =+ (\d+)\. .+ =+$", re.M)

    def groups(path: Path) -> list[str]:
        front, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        return [m.group(0) for m in group.finditer(front or "")]

    expected = groups(SEO_BLOCK / lang / "seo-block.md")
    assert [g.split(".")[0] for g in expected] == [f"# {'=' * 17} {n}" for n in range(1, 9)]
    actual = groups(DOCS / lang / "templates" / "page.md")
    assert actual == expected, (
        f"docs/{lang}/templates/page.md: группы SEO-блока {actual} "
        f"не совпадают с heron/scaffold/text/{lang}/seo-block.md {expected}"
    )


def test_no_cyrillic_in_en_outside_allowed() -> None:
    problems = [line for rel in sorted(EN_FILES - EN_ONLY) for line in _cyrillic_problems(rel)]
    allowed = "; ".join([*(rule.reason for rule in ALLOWED_CYRILLIC), LLMS_NOTE_RU])
    assert not problems, (
        f"русский текст в docs/en вне разрешённых мест (разрешено: {allowed}):\n"
        + "\n".join(problems)
    )


def test_allowed_cyrillic_rules_are_used() -> None:
    """Каждое разрешение кому-то нужно в своём файле и разделе: лишнее — дыра в проверке."""
    unused = []
    for rule in ALLOWED_CYRILLIC:
        names = [rule.file] if rule.file else sorted(EN_FILES - EN_ONLY)
        hit = False
        for rel in names:
            lines = (EN / rel).read_text(encoding="utf-8").splitlines()
            sections = _sections(lines)
            hit = hit or any(
                _applies(rule, rel, sections[n])
                and any(CYRILLIC.search(m.group(0)) for m in re.finditer(rule.pattern, line))
                for n, line in enumerate(lines)
            )
        if not hit:
            unused.append(rule.reason)
    assert not unused, f"разрешения кириллицы, которые нигде не применяются: {unused}"


# --- сами правила кириллицы: узкие по файлу и разделу ---------------------------

SPEC20 = "spec/20-data-contract.md"
SPEC21 = "spec/21-engine.md"


def _scoped_rules() -> list[Allowed]:
    return [rule for rule in ALLOWED_CYRILLIC if rule.file is not None]


def test_scoped_rules_name_a_file_and_a_section() -> None:
    """Узкое правило задаёт и файл, и раздел; файл и раздел существуют в docs/en."""
    for rule in _scoped_rules():
        assert rule.section, rule.reason
        assert rule.file in EN_FILES, rule.reason
        lines = (EN / rule.file).read_text(encoding="utf-8").splitlines()
        assert any(rule.section in names for names in _sections(lines)), rule.reason


def test_sections_nest_by_heading_level_and_skip_code() -> None:
    lines = [
        '## 2. Tree <a id="tree"></a>',
        '### Old <a id="old"></a>',
        "text",
        "```bash",
        "# comment in code",
        "```",
        "### Next",
        "after",
        "## 3. Other",
        "last",
    ]
    names = _sections(lines)
    assert names[2] == {"tree", "old"}
    assert names[4] == {"tree", "old"}  # «#» в блоке кода — не заголовок
    assert names[7] == {"tree", "Next"}
    assert names[9] == {"3. Other"}


OLD = '## Old <a id="old-addresses-cyrillic"></a>'
SEO05 = "guide/05-seo.md"
FIRST02 = "guide/02-first-site.md"
MIGRATE = '## Moving <a id="migrate-from-old-site"></a>'
CREATE = "## 1. Create a site"
PROMPT_RU = "На каком языке вам удобнее работать: подсказки, сообщения, комментарии в файлах"
RENDERING = '## 7. R <a id="rendering"></a>'
REDIRECTS = '### redirects <a id="redirects"></a>'


@pytest.mark.parametrize(
    ("rel", "text"),
    [
        (SPEC20, f'{OLD}\nThe address `/кредит/` and "й".\n'),
        (SPEC20, f"{OLD}\n```yaml\n  - /новости-компании/\n```\n"),
        (SPEC21, f'{RENDERING}\n("Book now" / "Записаться")\n'),
        (SPEC21, f"{REDIRECTS}\nmap `/кредит/  /credits/;`\n"),
        (SPEC21, '## 10. CLI\n- "Pages — N" / "Страниц — N", `Error`/"Ошибка"\n'),
        (SPEC21, "## 10. CLI\n`[en: перевода на ru пока нет]`, `(откроется на en)`\n"),
    ],
)
def test_scoped_rules_allow_their_literals(rel: str, text: str) -> None:
    assert _cyrillic_problems(rel, text) == []


@pytest.mark.parametrize(
    ("rel", "text"),
    [
        # тот же литерал в другом разделе того же файла
        (SPEC20, '## 3. Languages <a id="languages"></a>\nThe address `/кредит/`.\n'),
        (SPEC21, f"{RENDERING}\n`/кредит/  /credits/;`\n"),
        (SPEC21, f'{REDIRECTS}\n"Записаться"\n'),
        (SPEC21, '## 11. Errors\n"Страниц — N" and `(откроется на en)`\n'),
        # тот же литерал в другом файле, но под тем же якорем
        ("guide/03-content.md", f"{OLD}\n`/кредит/`\n"),
        ("roles/builder.md", f'{RENDERING}\n"Записаться"\n'),
        # соседняя кириллица в разрешённом разделе остаётся ошибкой
        (SPEC20, f"{OLD}\nThe address `/скидки/`.\n"),
        (SPEC21, '## 10. CLI\n"Страниц — N" and "Готово"\n'),
        (SPEC21, "## 10. CLI\nПереведите это слово.\n"),
        # guide/05: адрес только в migrate-from-old-site и только строкой списка yaml
        (SEO05, "## Languages\n  - /старая-страница/\n"),
        (SEO05, f"{MIGRATE}\nThe address /старая-страница/ moved.\n"),
        (SEO05, f"{MIGRATE}\n  - /новая-страница/\n"),
        ("guide/03-content.md", f"{MIGRATE}\n  - /старая-страница/\n"),
        # guide/02: строка подсказки только целиком, только в разделе 1 и только в 02
        (FIRST02, f"## 2. Describe the site\n{PROMPT_RU}\n"),
        (FIRST02, f"{CREATE}\n{PROMPT_RU} и ещё\n"),
        (FIRST02, f"{CREATE}\nНа каком языке вам удобнее работать\n"),
        ("guide/01-install.md", f"{CREATE}\n{PROMPT_RU}\n"),
    ],
)
def test_scoped_rules_do_not_open_cyrillic_wider(rel: str, text: str) -> None:
    assert _cyrillic_problems(rel, text), (rel, text)


# --- закрытие блока кода по CommonMark ---------------------------------------------


def test_fence_closes_only_with_clean_fence() -> None:
    """Строка с текстом после фенса блок не закрывает; короткая ограда тоже."""
    text = "````md\nline\n```` текст\n```\n````\nprose\n"
    doc = _parse(text)
    assert len(doc.blocks) == 1
    assert doc.blocks[0].lines == ["line", "```` текст", "```"]
    assert doc.prose == ["prose"]


def test_fence_text_after_fence_does_not_hide_heading_section() -> None:
    lines = ["## A", "```", "x", "``` text", "# not heading", "```", "## B", "y"]
    names = _sections(lines)
    assert names[4] == {"A"}  # блок ещё открыт: «#» в нём не заголовок
    assert names[7] == {"B"}


# --- пара README.ru.md / README.md --------------------------------------------------


def _readme_pairs() -> list[tuple[str, str]]:
    data = yaml.safe_load(TRANSLATION.read_text(encoding="utf-8"))
    return [(e["ru"], e["en"]) for e in data.get("root_files", [])]


def test_readme_pair_is_listed() -> None:
    assert ("README.ru.md", "README.md") in _readme_pairs()


def test_readme_pair_has_same_structure() -> None:
    ru_text = (ROOT / "README.ru.md").read_text(encoding="utf-8")
    en_text = (ROOT / "README.md").read_text(encoding="utf-8")
    problems = _md_problems(ru_text, en_text)
    assert not problems, "README.ru.md и README.md расходятся:\n" + "\n".join(problems)


def test_readme_pair_structure_catches_missing_heading() -> None:
    ru_text = (ROOT / "README.ru.md").read_text(encoding="utf-8")
    en_text = (ROOT / "README.md").read_text(encoding="utf-8")
    lines = en_text.splitlines()
    index = next(i for i, line in enumerate(lines) if HEADING.match(line) and not line.startswith("# "))
    mutated = "\n".join(lines[:index] + lines[index + 1 :])
    assert _md_problems(ru_text, mutated)
