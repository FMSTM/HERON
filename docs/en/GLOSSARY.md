# Glossary ru → en

Terms of the HERON documentation and their English equivalents. The source is `docs/ru/`, the translation is `docs/en/` (`spec/23-distribution.md` §10). Every translation uses these terms; a new term gets a row here first, then it is used. This is a working file for translators of the documentation, not an instruction for a site author: it has no Russian pair and is not part of the agent kit `agents/` (`spec/20-data-contract.md` §1), while the repository, the wheel and the image carry it.

## Rules

- **One language throughout.** A human who chose `en` reads every file in English: instructions, comments, hints. No Russian text is left in `docs/en/` except literal tokens and values for the other language of an example.
- **Structure 1:1.** The same file names, the same number of lines, the same number of headings of each level, the same sequence of explicit anchors `<a id="…"></a>`, the same set of relative links and their targets, the same number of tables and rows, the same lists, the same number of code blocks and lines in each.
- **Not translated:** commands, flags, YAML keys, values of non-string fields, error codes (`E024`), file and folder names, paths, environment variables, template and macro names, `heron docs` topic names, role names in file names, addresses (`sitebuilder.heron.software`, `FMSTM/HERON`).
- **Only literal tokens are byte-equal**, in code blocks too: commands, flags, keys, error codes, paths, file names, values of non-string fields. Everything else in a block is translated: diagrams and forms in blocks without a language and in `markdown` blocks, placeholders, comments and captions, example values (`мой-сайт` → `my-site`, `"Название"` → `"Site name"`). The kit language in ready commands equals the file language (`--notes en`, `heron docs --lang en`); site languages in examples (`--lang en,ru`, a translation with `--lang ru`) stay.
- **Samples** (`templates/*.yaml`, `templates/page.md`): comments and hints are translated; string placeholder values are translated by meaning; values for the `ru` language (`name_ru`, `*_ru`, `llms_note.ru`) stay Russian because they are the Russian variant of the site. `build.notes` equals the language of the kit.
- **Explicit anchors.** A heading that other files link to (`file.md#anchor`) carries an explicit anchor `<a id="anchor"></a>` at the end of the heading line, ASCII kebab-case, the same in both languages; links use it. The anchor is copied byte for byte, the heading text is translated.
- **Placeholders in inline code** are translated: `<язык>` → `<lang>`, `<канал>` → `<channel>`, `<тема>` → `<topic>`, `<сайт>` → `<site>`, `<папка>` → `<folder>`, `<тип>` → `<type>`, `<ключ>` → `<key>`, `<имя>` → `<name>`, `<текст>` → `<text>`, `<якорь>` → `<anchor>`, `<модуль>` → `<module>`, `<файл>` → `<file>`.
- **Neutrality.** Tool names appear only where the Russian text has them (the "Who reads which file" list of the kit `README.md`, the root pointers in `spec/20-data-contract.md` §1). Company names appear nowhere.
- **Typography and tone.** Short sentences, "you" for instructions to the agent, no marketing. A plain hyphen is preferred to a long dash. American spelling throughout (behavior, catalog, license, organization), as in the engine messages.

## Terms

| ru | en | First use |
|---|---|---|
| агент | agent | `README.md` |
| комплект (для агентов) | kit (agent kit) | `README.md` |
| роль | role | `README.md` |
| архитектор | architect | `README.md` |
| контент и SEO | content and SEO | `README.md` |
| дизайнер | designer | `README.md` |
| сборщик | builder | `README.md` |
| образец | sample | `README.md` |
| гайд | guide | `README.md` |
| спецификация | spec | `README.md` |
| движок | engine | `README.md` |
| образ (Docker) | image | `README.md` |
| канал (`prod`, `beta`) | channel | `README.md` |
| ветка | branch | `README.md` |
| папка сайта | site folder | `README.md` |
| страница | page | `README.md` |
| ключ (страницы) | key | `README.md` |
| адрес | address | `README.md` |
| слаг | slug | `README.md` |
| секция (`## Заголовок {#якорь}`) | section | `README.md` |
| форма секции (`kind`) | section form | `README.md` |
| якорь | anchor | `README.md` |
| вступление | intro | `README.md` |
| тип страницы | page type | `README.md` |
| тема (оформление) | theme | `README.md` |
| тема (`heron docs <тема>`) | topic | `README.md` |
| шаблон | template | `README.md` |
| модуль | module | `README.md` |
| SEO-блок | SEO block | `README.md` |
| анкета (`heron setup`) | questionnaire | `README.md` |
| сборка | build | `README.md` |
| дев-сборка | dev build | `roles/architect.md` |
| прод, прод-сборка | production, production build | `README.md` |
| выкладка | deploy | `README.md` |
| публикация | publication | `README.md` |
| отчёт | report | `README.md` |
| вопросы человеку | questions for the human | `README.md` |
| человек (тот, кто дал задачу) | the human | `README.md` |
| заказчик | client | `README.md` |
| источник (заказчика) | source | `README.md` |
| факт | fact | `README.md` |
| долг контента | content debt | `README.md` |
| сводка «Не заполнено» | the "Not filled" summary | `roles/content.md` |
| предупреждение | warning | `README.md` |
| ошибка | error | `README.md` |
| код выхода | exit code | `README.md` |
| «готово, когда» | done when | `README.md` |
| останов | stop rule | `README.md` |
| круг «исправить → `check`» | round "fix → `check`" | `README.md` |
| единственная точка правды | single source of truth | `README.md` |
| строка атрибуции | attribution line | `README.md` |
| зарезервированное имя | reserved name | `README.md` |
| манифест | manifest | `README.md` |
| корневые указатели | root pointers | `architecture.md` |
| записка (`heron-readme.md`) | note | `architecture.md` |
| фолбэк (на другой язык) | fallback | `architecture.md` |
| состояние перевода | translation state | `architecture.md` |
| тест паритета | parity test | `architecture.md` |
| резолв | resolve | `architecture.md` |
| генераторы | generators | `architecture.md` |
| служебное (группа 7 SEO-блока) | service (as in the engine SEO block; not the `service` page type) | `templates/page.md` |
| сведение (в отчёте `check`) | info line | `spec/21-engine.md` |
| раздел (папка с `_index.md`) | section (a folder with `_index.md`) | `roles/architect.md` |
| раздел (документа) | section | `README.md` |
| каталог | catalog | `roles/architect.md` |
| справочник (`data/`) | reference data | `roles/content.md` |
| связь, поле связи | relation, relation field | `templates/structure.md` |
| обратный список (`back`) | reverse list | `templates/theme.yaml` |
| разметка (schema.org) | markup | `templates/site.yaml` |
| разметка (markdown секции) | markup | `roles/content.md` |
| сквозной узел (`schema.entity`) | site-wide node | `templates/site.yaml` |
| счётчики | analytics counters | `README.md` |
| нейросети | AI models | `templates/site.yaml` |
| строки интерфейса | interface strings | `roles/designer.md` |
| стартовая тема, заготовка темы | starter theme | `roles/designer.md` |
| белая тема | the white starter theme | `roles/designer.md` |
| заготовка (страницы, секции) | stub | `roles/content.md` |
| нарезка (картинок) | renditions | `templates/site.yaml` |
| метка сборки | build stamp | `roles/designer.md` |
| хлебные крошки | breadcrumbs | `templates/page.md` |
| выдача (поисковая) | search results | `templates/page.md` |
| ключевые запросы | search queries | `templates/page.md` |
| интент | intent | `templates/page.md` |
| старый адрес | old address | `templates/structure.md` |
| перенос адресов, таблица переноса | address migration, migration table | `templates/structure.md` |
| переезд (со старого сайта) | migration | `roles/content.md` |
| дорвеи | doorway pages | `roles/architect.md` |
| задача на движок | engine task | `templates/structure.md` |
| ДЫРА (метка в структуре) | GAP | `templates/structure.md` |
| мой-сайт (папка в примерах команд) | my-site | `roles/content.md` |
| «Название» (в примерах команд) | "Site name" | `roles/builder.md` |
| граница публикации | publication boundary | `roles/builder.md` |
| группы предупреждений (`картинки`, `связи`, …) | as the engine prints them in English: `images`, `relations`, `links`, `menu`, `translations`, `languages`, `content`, `other` | `roles/builder.md` |
| перевод | translation | `README.md` |
