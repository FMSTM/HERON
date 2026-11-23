"""Встраиваемые сервисы HERON 0.3.3: `services.chat` - HERON Chat.

- тег `<script async src="<host>/chat/l.js" data-widget data-lang>` перед `</body>`
  на каждой странице сборки, где чат включён (`env`), не на 404;
- CSP nginx: хост - в script-src и connect-src, `api` - только в connect-src;
  без чата и в выключенном окружении политика прежняя; ни `*`, ни схем целиком;
- E047 на кривой ключ, host/api не https или с путём, ui, имя окружения, `shop`;
- хост по умолчанию - один, в определении сервиса;
- тема видит `services.chat.enabled` и `services.chat.ui`;
- конфигуратор: `chat` в ответах пишет `services.chat`, формат проверяется;
- просмотр студии получает те же origin в своей CSP;
- чат на непроизводственной сборке - сведение про разрешённые адреса.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from heron.cli import main
from heron.contracts.site import SiteConfig
from heron.core import build as pipeline
from heron.core.environment import BuildEnv
from heron.core.errors import Collector
from heron.modules import nginx, services
from heron.setup import answers as setup_answers
from heron.setup.server import preview_policy

KEY = "hcw_DTTQXXFWX2X8F6XHB1RQXBRN8G"
DEV_HUB = "https://dev-hub.heron.software"
BASE = {
    "heron": ">=0.3,<0.4",
    "site": {"domain": "site.example", "theme": "main", "default_lang": "en", "languages": ["en"]},
}
TAG = re.compile(r'<script async src="([^"]+)"([^>]*)></script>')


def _config(chat=None, **extra) -> SiteConfig:
    data = {**BASE, **extra}
    if chat is not None:
        data["services"] = {"chat": chat}
    return SiteConfig.model_validate(data)


def _errors(config: SiteConfig) -> list:
    collector = Collector()
    services.verify(config, collector)
    return collector.errors


def _csp(conf: str) -> str:
    return re.search(r'Content-Security-Policy "([^"]+)"', conf).group(1)


# --- проверка --------------------------------------------------------------------------


def test_good_chat_has_no_errors():
    assert _errors(_config({"widget": KEY, "host": DEV_HUB, "env": ["dev"]})) == []


@pytest.mark.parametrize(
    "chat",
    [
        {"widget": "hcw_short"},
        {"widget": "hcw_DTTQXXFWX2X8F6XHB1RQXBRN8I"},  # I не из base32 Крокфорда
        {},
        {"widget": KEY, "host": "http://dev-hub.heron.software"},
        {"widget": KEY, "host": "https://dev-hub.heron.software/chat"},
        {"widget": KEY, "host": "https://*.heron.software"},
        {"widget": KEY, "host": "https:"},
        {"widget": KEY, "api": "https://api.example/v1"},
        {"widget": KEY, "ui": "half"},
        {"widget": KEY, "env": ["Dev"]},
        {"widget": KEY, "env": {"prod": {"widget": "nope"}}},
    ],
)
def test_bad_chat_is_e047_with_hint(chat):
    errors = _errors(_config(chat))
    assert errors and {e.code for e in errors} == {"E047"}
    assert all(e.hint and e.path == "site.yaml" for e in errors)


def test_shop_is_reserved():
    config = SiteConfig.model_validate({**BASE, "services": {"shop": {"x": 1}}})
    assert [e.code for e in _errors(config)] == ["E047"]


def test_unknown_service_key_is_e011():
    with pytest.raises(Exception) as caught:
        SiteConfig.model_validate({**BASE, "services": {"chat": {"widget": KEY, "colour": 1}}})
    assert "colour" in str(caught.value)


# --- окружения и хост ------------------------------------------------------------------


def test_default_host_lives_in_one_place():
    active = services.active(_config({"widget": KEY}), "prod")
    assert active[0].csp["script-src"] == (services.CHAT_HOST,)
    assert services.CHAT_HOST == "https://hub.heron.software"
    assert services.CHAT_HOST + "/chat/l.js" in active[0].tag("en")


def test_env_list_and_per_env_values():
    other = "hcw_0123456789ABCDEFGHJKMNPQRS"
    config = _config(
        {
            "widget": KEY,
            "host": DEV_HUB,
            "env": {"dev": None, "prod": {"widget": other, "host": "https://hub.heron.software"}},
        }
    )
    dev, prod = services.active(config, "dev"), services.active(config, "prod")
    assert KEY in dev[0].tag("en") and DEV_HUB in dev[0].tag("en")
    assert other in prod[0].tag("en") and "https://hub.heron.software/chat/l.js" in prod[0].tag(
        "en"
    )
    assert services.active(config, "stage") == []
    assert services.active(_config({"widget": KEY, "env": ["dev"]}), "prod") == []


def test_tag_attributes():
    config = _config({"widget": KEY, "host": DEV_HUB, "api": "https://api.example", "ui": "none"})
    tag = services.active(config, "dev")[0].tag("de")
    assert tag == (
        f'<script async src="{DEV_HUB}/chat/l.js" data-widget="{KEY}" data-lang="de" '
        'data-api="https://api.example" data-ui="none"></script>'
    )


# --- CSP -------------------------------------------------------------------------------


def test_csp_without_chat_is_unchanged():
    plain = _csp(nginx.generate(_config())[nginx.NAME])
    assert plain == _csp(nginx.generate(_config(), env="dev")[nginx.NAME])
    off = _config({"widget": KEY, "host": DEV_HUB, "env": ["dev"]})
    assert _csp(nginx.generate(off, env="prod")[nginx.NAME]) == plain
    assert "connect-src" not in plain


def test_csp_with_chat_and_separate_api():
    config = _config({"widget": KEY, "host": DEV_HUB, "api": "https://api.example", "env": ["dev"]})
    csp = _csp(nginx.generate(config, env="dev")[nginx.NAME])
    assert f"script-src 'self' {DEV_HUB};" in csp
    assert f"connect-src 'self' {DEV_HUB} https://api.example;" in csp
    assert "img-src 'self' data:;" in csp and "frame-src" not in csp
    for bad in ("*", "'unsafe-eval'", " https: ", " http:"):
        assert bad not in csp


def test_csp_merges_counters_and_chat():
    config = _config({"widget": KEY, "host": DEV_HUB}, analytics={"metrika": "123"})
    csp = _csp(nginx.generate(config, env="prod")[nginx.NAME])
    assert f"script-src 'self' https://mc.yandex.ru {DEV_HUB};" in csp
    assert f"connect-src 'self' https://mc.yandex.ru {DEV_HUB};" in csp


@pytest.mark.skipif(shutil.which("nginx") is None, reason="нет nginx")
def test_nginx_t_passes_with_chat():
    config = _config({"widget": KEY, "host": DEV_HUB, "api": "https://api.example"})
    result = nginx.check(nginx.generate(config, env="dev")[nginx.NAME])
    assert result is not None and result[0], result


def test_preview_policy_gets_the_same_origins():
    sources = services.csp(_config({"widget": KEY, "host": DEV_HUB}), "dev")
    policy = preview_policy("http://localhost:8000", sources)
    assert f"script-src 'self' {DEV_HUB};" in policy
    assert f"connect-src 'self' {DEV_HUB};" in policy
    assert "frame-ancestors http://localhost:8000" in policy
    assert preview_policy("http://localhost:8000", {}) == preview_policy("http://localhost:8000")


# --- сборка ----------------------------------------------------------------------------


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SITE_ENV", raising=False)
    assert CliRunner().invoke(main, ["new", "demo", "--no-agents", "-y"]).exit_code == 0
    root = tmp_path / "demo"
    data = yaml.safe_load((root / "site.yaml").read_text(encoding="utf-8"))
    data["site"]["languages"] = ["en", "de"]
    (root / "site.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert CliRunner().invoke(main, ["init", str(root), "-y"]).exit_code == 0
    # второй язык - «переведён»: боевая сборка публикует его как обычный
    for page in (root / "content" / "de").rglob("*.md"):
        text = page.read_text(encoding="utf-8")
        page.write_text(re.sub(r"(?m)^translation: pending.*\n", "", text), encoding="utf-8")
    return root


def _add_chat(root: Path, chat: dict) -> None:
    path = root / "site.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["services"] = {"chat": chat}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _tags(dist: Path) -> dict[str, list[str]]:
    out = {}
    for page in dist.rglob("*.html"):
        rel = page.relative_to(dist).as_posix()
        if rel.startswith("_heron"):
            continue
        out[rel] = TAG.findall(page.read_text(encoding="utf-8"))
    return out


def test_tag_on_every_page_of_the_enabled_env_only(site, tmp_path):
    _add_chat(site, {"widget": KEY, "host": DEV_HUB, "env": ["dev"]})
    dev = pipeline.run(site, dist=tmp_path / "dev", env=BuildEnv.resolve("dev"))
    prod = pipeline.run(site, dist=tmp_path / "prod", env=BuildEnv.resolve("prod"))
    assert not dev.failed, [str(e) for e in dev.collector.errors]
    assert not prod.failed, [str(e) for e in prod.collector.errors]
    tags = _tags(tmp_path / "dev")
    pages = {rel: found for rel, found in tags.items() if not rel.startswith(("404", "de/404"))}
    assert pages and all(len(found) == 1 for found in pages.values()), pages
    assert all(not found for rel, found in tags.items() if rel not in pages), tags
    html = (tmp_path / "dev" / "de" / "index.html").read_text(encoding="utf-8")
    assert f'data-widget="{KEY}" data-lang="de"></script>\n</body>' in html
    assert all(not found for found in _tags(tmp_path / "prod").values())
    dev_csp = _csp((tmp_path / "dev" / ".heron-nginx.conf").read_text(encoding="utf-8"))
    prod_csp = _csp((tmp_path / "prod" / ".heron-nginx.conf").read_text(encoding="utf-8"))
    assert DEV_HUB in dev_csp and DEV_HUB not in prod_csp
    # чат на дев-сборке - сведение про разрешённые адреса, не предупреждение
    assert any(n.message.key == "services_chat_cors" for n in dev.collector.notes)
    assert not any(n.message.key == "services_chat_cors" for n in prod.collector.notes)


def test_bad_key_stops_check_and_build(site, tmp_path):
    _add_chat(site, {"widget": "hcw_nope", "host": "https://hub.example/chat"})
    result = CliRunner().invoke(main, ["check", str(site), "--notes", "en"])
    assert result.exit_code == 1 and "E047" in result.output
    built = pipeline.run(site, dist=tmp_path / "x")
    assert built.failed and {e.code for e in built.collector.errors} == {"E047"}


def test_theme_sees_the_flags(site, tmp_path):
    base = site / "theme" / "base.html"
    text = base.read_text(encoding="utf-8")
    marker = "<!--chat:{{ services.chat.enabled }}:{{ services.chat.ui }}-->"
    base.write_text(text.replace("</body>", marker + "</body>"), encoding="utf-8")
    off = pipeline.run(site, dist=tmp_path / "off")
    assert not off.failed, [str(e) for e in off.collector.errors]
    assert "<!--chat:False:None-->" in (tmp_path / "off" / "index.html").read_text("utf-8")
    _add_chat(site, {"widget": KEY, "ui": "none"})
    on = pipeline.run(site, dist=tmp_path / "on")
    assert not on.failed, [str(e) for e in on.collector.errors]
    assert "<!--chat:True:none-->" in (tmp_path / "on" / "index.html").read_text("utf-8")


# --- конфигуратор ----------------------------------------------------------------------


def test_configurator_writes_and_reads_services_chat():
    answers = setup_answers.Answers.model_validate(
        {"chat": {"widget": KEY, "host": DEV_HUB + "/", "envs": ["dev"]}}
    )
    out = setup_answers.merge(dict(BASE), answers, ">=0.3,<0.4")
    assert out["services"] == {"chat": {"widget": KEY, "host": DEV_HUB, "env": ["dev"]}}
    back = setup_answers.read(out)
    assert back.chat.widget == KEY and back.chat.envs == ["dev"]
    # пустой ключ - блока чата нет
    empty = setup_answers.merge(out, setup_answers.Answers(), ">=0.3,<0.4")
    assert "services" not in empty


def test_configurator_keeps_other_envs_and_values():
    data = {
        **BASE,
        "services": {"chat": {"widget": KEY, "env": {"stage": None, "prod": {"host": DEV_HUB}}}},
    }
    answers = setup_answers.read(data)
    assert set(answers.chat.envs) == {"stage", "prod"}
    out = setup_answers.merge(data, answers, ">=0.3,<0.4")
    assert out["services"]["chat"]["env"] == {"stage": None, "prod": {"host": DEV_HUB}}


@pytest.mark.parametrize(
    "chat",
    [
        {"widget": "hcw_bad"},
        {"widget": KEY, "host": "http://x.example"},
        {"widget": KEY, "ui": "x"},
    ],
)
def test_configurator_rejects_bad_values(chat):
    with pytest.raises(ValueError):
        setup_answers.Answers.model_validate({"chat": chat})
