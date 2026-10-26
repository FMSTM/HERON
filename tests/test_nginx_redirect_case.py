"""301 и 410 срабатывают только при точном совпадении регистра.

Это задуманное поведение, а не случайность: адреса в вебе различают регистр,
страницы сайта тоже (`/Contacts/` не отдаёт `/contacts/`). Старый прод
отвечал 301 на адрес в другом регистре только наполовину: строковые ключи
`map` nginx сравнивал без учёта регистра лишь для латиницы, кириллица и
префиксы давали 404. Движок так не делает: адрес в другом регистре даёт 404,
в точном — 301 или 410, латиница и кириллица одинаково. Нужен второй вариант
регистра — он пишется в `redirect_from` (или `gone`) отдельной записью.

Тест падает, если конфиг начнёт сравнивать регистр иначе: вернётся
строковая `map` или регулярка с `~*`, пропадёт `location =`.

Спецификация: docs/ru/spec/21-engine.md, модуль redirects;
docs/ru/guide/06-deploy.md, «301 и 410 различают регистр».
"""

from __future__ import annotations

import re
from urllib.parse import quote as pct

import yaml

from heron.core import build as pipeline
from heron.scaffold import create
from tests.nginx_server import needs_nginx, serve

PAGE = "---\ntitle: {t}\nh1: {t}\ndescription: Опис\n{extra}---\n\nТекст.\n"

LAT = "/Old-Section/"
CYR = "/Старая-Страница/"
BOTH = "/Old-Page/"  # записан в двух регистрах — оба дают 301
GONE_LAT = "/Sample-Page/"
GONE_CYR = "/Старый-Архив/"
GONE_PREFIX = "/Wp-Admin/"


def make(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    create(root, name="demo", languages=["ru"])
    conf = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    conf["gone"] = [GONE_LAT, GONE_CYR, GONE_PREFIX + "*", "/?p=*"]
    (root / "site.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True), encoding="utf-8")
    moved = f"redirect_from: ['{LAT}', '{CYR}', '{BOTH}', '{BOTH.lower()}']\n"
    pages = {
        "ru/index.md": PAGE.format(t="Главная", extra=""),
        "ru/about.md": PAGE.format(t="О компании", extra=moved),
        "ru/contacts.md": PAGE.format(t="Контакты", extra=""),
    }
    for rel, text in pages.items():
        path = root / "content" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def build(tmp_path):
    root = make(tmp_path)
    result = pipeline.run(root)
    assert not result.failed, [str(e) for e in result.collector.errors]
    return root


def test_config_matches_case_exactly(tmp_path):
    conf = (build(tmp_path) / "dist" / ".heron-nginx.conf").read_text(encoding="utf-8")
    # точные location в том регистре, в каком записаны, и вариант без слеша
    for old in (LAT, CYR, BOTH, BOTH.lower()):
        assert f'location = "{old}" {{ return 301 "/about/"; }}' in conf, old
        assert f'location = "{old[:-1]}" {{ return 301 "/about/"; }}' in conf, old
    for old in (GONE_LAT, GONE_CYR):
        assert f'location = "{old}" {{ return 410; }}' in conf, old
    assert f'location ^~ "{GONE_PREFIX}" {{ return 410; }}' in conf
    # ни одного варианта в другом регистре
    for old in (LAT, CYR, GONE_LAT, GONE_CYR, GONE_PREFIX):
        assert f'"{old.lower()}"' not in conf, old
        assert f'"{old.upper()}"' not in conf, old
    # нет строковых карт (nginx сравнивает их без учёта регистра)
    # и нет регулярок без учёта регистра
    for head in re.findall(r"^map (.+?) \{$", conf, flags=re.M):
        block = conf.split(f"map {head} {{", 1)[1].split("\n}", 1)[0]
        for row in block.strip().splitlines():
            key = row.strip().split()[0]
            if key == "default":
                continue
            assert key.startswith('"~^'), (head, row)
    assert "~*" not in conf


@needs_nginx
def test_nginx_answers_only_exact_case(tmp_path):
    root = build(tmp_path)
    with serve(root / "dist", tmp_path / "nginx") as get:
        # точный регистр: 301, со слешем и без, кириллица и в percent-форме
        for old in (LAT, CYR, BOTH, BOTH.lower()):
            assert get(old) == (301, "/about/"), old
            assert get(old[:-1]) == (301, "/about/"), old
        assert get(pct(CYR)) == (301, "/about/")
        assert get(pct(CYR).lower()) == (301, "/about/")  # регистр %xx не важен

        # другой регистр: 404, а не 301 — и для латиницы, и для кириллицы
        for other in (LAT.lower(), LAT.upper(), CYR.lower(), CYR.upper(), BOTH.upper()):
            assert get(other)[0] == 404, other
            assert get(other[:-1])[0] == 404, other
        assert get(pct(CYR.lower()))[0] == 404

        # 410: точный регистр
        for old in (GONE_LAT, GONE_CYR):
            assert get(old)[0] == 410, old
            assert get(old[:-1])[0] == 410, old
        assert get(GONE_PREFIX + "x")[0] == 410
        assert get("/?p=5")[0] == 410

        # 410: другой регистр — 404
        for other in (GONE_LAT.lower(), GONE_LAT.upper(), GONE_CYR.lower(), GONE_CYR.upper()):
            assert get(other)[0] == 404, other
        assert get(GONE_PREFIX.lower() + "x")[0] == 404
        assert get(GONE_PREFIX.upper() + "x")[0] == 404
        assert get("/?P=5")[0] != 410

        # свои страницы сайта регистр тоже различают
        assert get("/contacts/")[0] == 200
        assert get("/Contacts/")[0] == 404
        assert get("/about/")[0] == 200
