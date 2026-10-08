"""Документация движка — внутри самого движка.

Агент сайта часто работает только с образом: клона репозитория рядом нет,
а документация в сети может быть новее или старее его образа. Поэтому
текст документации едет в образе (около 100 КБ, без картинок) и читается
командой `heron docs` — ровно той версии, что и движок.

В установленном пакете файлы лежат в `heron/_docs/` (их кладёт сборка
колеса, см. pyproject.toml). Из исходников — прямо из репозитория.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

PACKED = Path(__file__).parent / "_docs"
SOURCE = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Topic:
    name: str
    path: str
    about: str
    group: str


# Имя темы → файл. Порядок — порядок оглавления.
TOPICS: tuple[Topic, ...] = (
    Topic(
        "agents", "AGENTS.md", "с чего начинать агенту: роли, правила, карта документации", "start"
    ),
    Topic("readme", "README.md", "что такое HERON, быстрый старт, несколько сайтов", "start"),
    Topic(
        "architect", "docs/agents/architect.md", "роль: структура сайта по отчёту о старом", "roles"
    ),
    Topic(
        "content", "docs/agents/content.md", "роль: страницы, SEO-блок, переводы, переезд", "roles"
    ),
    Topic("designer", "docs/agents/designer.md", "роль: тема, шаблоны, модули", "roles"),
    Topic("builder", "docs/agents/builder.md", "роль: сборка, проверка, выкладка", "roles"),
    Topic(
        "capabilities", "docs/agents/capabilities.md", "что движок уже умеет — по задачам", "roles"
    ),
    Topic(
        "concepts",
        "docs/guide/01-concepts.md",
        "01 · понятия: страница, ключ, адрес, тема",
        "guide",
    ),
    Topic("first-site", "docs/guide/02-first-site.md", "02 · первый сайт от пустой папки", "guide"),
    Topic("pages", "docs/guide/03-content.md", "03 · страницы, секции, ссылки, картинки", "guide"),
    Topic("theme", "docs/guide/04-theme.md", "04 · тема: theme.yaml, шаблоны, модули", "guide"),
    Topic("seo", "docs/guide/05-seo.md", "05 · SEO и переезд со старого сайта", "guide"),
    Topic("deploy", "docs/guide/06-deploy.md", "06 · сборка, образ, несколько сайтов", "guide"),
    Topic(
        "contract",
        "docs/spec/20-data-contract.md",
        "20 · контракт: папка, URL, поля, ключи",
        "spec",
    ),
    Topic("engine", "docs/spec/21-engine.md", "21 · движок: конвейер, модель, CLI, ошибки", "spec"),
    Topic(
        "deploy-spec", "docs/spec/22-deploy.md", "22 · развёртывание: nginx, CI, переезд", "spec"
    ),
    Topic(
        "distribution",
        "docs/spec/23-distribution.md",
        "23 · поставка: образ, команды, теги",
        "spec",
    ),
    Topic("architecture", "docs/architecture.md", "архитектура одной страницей", "spec"),
)

TEMPLATES = "docs/agents/templates"

GROUPS = {
    "start": "Начало",
    "roles": "Роли агентов",
    "guide": "Гайды по порядку",
    "spec": "Справочник",
}


def root() -> Path:
    """Где лежит документация: в пакете или в репозитории рядом."""
    if (PACKED / "AGENTS.md").is_file():
        return PACKED
    return SOURCE


def topic(name: str) -> Topic | None:
    return next((t for t in TOPICS if t.name == name), None)


def templates() -> list[str]:
    folder = root() / TEMPLATES
    return sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []


def read(rel: str) -> str:
    return (root() / rel).read_text(encoding="utf-8")


def files() -> list[str]:
    """Все файлы документации, относительные пути."""
    out = [t.path for t in TOPICS]
    out += [f"{TEMPLATES}/{name}" for name in templates()]
    return out


def contents() -> str:
    """Оглавление: темы по группам с одной строкой описания."""
    lines = ["Документация HERON этой версии движка. Читать: heron docs <тема>", ""]
    for group, title in GROUPS.items():
        lines.append(f"{title}:")
        for item in (t for t in TOPICS if t.group == group):
            lines.append(f"  {item.name:<14} {item.about}")
        lines.append("")
    lines.append("Образцы: heron docs template <файл> — " + ", ".join(templates()))
    lines.append("Поиск:   heron docs --search <текст>")
    lines.append("Папкой:  heron docs --export <папка> — со ссылками между файлами")
    return "\n".join(lines) + "\n"


def search(text: str, context: int = 1) -> list[str]:
    """Строки документации с `text` (без учёта регистра) и соседние строки."""
    pattern = re.compile(re.escape(text), re.IGNORECASE)
    out: list[str] = []
    for rel in files():
        lines = read(rel).splitlines()
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            name = next((t.name for t in TOPICS if t.path == rel), rel)
            out.append(f"{name} · {rel}:{index + 1}")
            start, stop = max(0, index - context), min(len(lines), index + context + 1)
            for near in range(start, stop):
                mark = ">" if near == index else " "
                out.append(f"  {mark} {lines[near]}")
            out.append("")
    return out


def export(target: Path) -> list[str]:
    """Выложить документацию папкой, сохраняя пути: ссылки между файлами работают."""
    written = []
    for rel in files():
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root() / rel, destination)
        written.append(rel)
    return written
