# {name} — для агентов

Это сайт на движке HERON. Всё, что агенту нужно для работы с ним, лежит в `agents/`; код движка читать не нужно.

- **О проекте:** {about}
- **Языки сайта:** {languages}, основной — {default_lang}; домен — {domain}.
- **Язык комплекта:** {notes} (`build.notes`); результаты работы — в `agents/work/`.
- **Движок:** HERON {version}, канал {channel}; версия и хеши комплекта — `agents/heron-kit.yaml`.
- **Документация этой версии:** {docs_url} и `docker run --rm ghcr.io/fmstm/heron:{channel} docs --lang {notes} <тема>`.
- **Проверка «готово»:** `heron check --strict --json` отвечает кодом 0.

Читай сначала [agents/README.md](agents/README.md) — ниже его текст; ссылки в нём ведут в `agents/`.

---
