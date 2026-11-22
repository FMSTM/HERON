"""Dockerfile.site (0.3.2): статика сайта - ровно в одном слое итогового образа.

`COPY .` и следом `RUN chmod -R` в одном этапе кладут каждый файл дважды:
chmod трогает файл нижнего слоя, overlayfs копирует его наверх. Дерево
готовится в этапе `tree`, в итоговый образ оно приезжает одним COPY.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "Dockerfile.site").read_text(encoding="utf-8")
DIGEST = "sha256:782bb89768cc87b7f95c18b95baa1af250e5d451f26794f59363540161147c01"
HTML = "/usr/share/nginx/html"


def _instructions(text: str) -> list[str]:
    joined = re.sub(r"\\\n", " ", text)
    return [
        line.strip() for line in joined.splitlines() if line.strip() and not line.startswith("#")
    ]


def _stages() -> list[list[str]]:
    stages: list[list[str]] = []
    for line in _instructions(TEXT):
        if line.upper().startswith("FROM "):
            stages.append([])
        if stages:
            stages[-1].append(line)
    return stages


def test_both_stages_use_the_pinned_nginx():
    froms = [s[0] for s in _stages()]
    assert len(froms) == 2
    assert all(DIGEST in line and "nginx-unprivileged:1.30.6-alpine" in line for line in froms)


def test_final_stage_has_the_site_in_exactly_one_copy_and_no_run_touches_it():
    final = _stages()[-1]
    copies = [line for line in final if line.startswith("COPY") and HTML in line]
    assert len(copies) == 1 and "--from=tree" in copies[0]
    runs = [line for line in final if line.startswith("RUN")]
    assert runs and not any(HTML in line or "chmod" in line or "chown" in line for line in runs)
    # конфиг nginx - своим COPY с владельцем nginx, мимо дерева сайта
    assert any(
        line.startswith("COPY")
        and "--chown=nginx:nginx" in line
        and "/etc/nginx/conf.d/default.conf" in line
        for line in final
    )


def test_user_check_and_port_are_kept():
    final = _stages()[-1]
    assert "USER nginx" in final
    assert any(line.startswith("RUN nginx -t") for line in final)
    assert final[-1] == "EXPOSE 8080"
    # nginx -t - после USER nginx: под тем же пользователем, что и сервер
    assert final.index("USER nginx") < next(
        i for i, line in enumerate(final) if line.startswith("RUN nginx -t")
    )


def test_tree_stage_moves_the_config_out_of_the_site_and_fixes_permissions():
    tree = _stages()[0]
    run = next(line for line in tree if line.startswith("RUN"))
    assert ".heron-nginx.conf" in run and "chmod -R a+rX" in run
    assert "exit 1" in run  # без конфига - внятная ошибка, а не пустой сайт
