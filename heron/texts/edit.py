"""Сообщения heron/edit/: модель правки страницы и проверка полей."""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "edit_not_utf8": "файл страницы не в кодировке UTF-8",
        "edit_single_line": "значение этого поля - одна строка, без переводов строки",
        "edit_one_paragraph": "значение этого поля - один абзац, без пустых строк внутри",
        "edit_bad_path": "путь {value!r}: без пробелов и скобок, например media/team/photo.jpg",
        "edit_readonly": "поле только для чтения: {reason}",
        "edit_ro_setext": "заголовок подчёркнут строкой ниже, правьте его в файле",
        "edit_ro_anchor": "у заголовка нет якоря {{#…}}",
        "edit_ro_place": "место этого поля в markdown редактор не знает, правьте его в файле",
        "edit_ro_first_paragraph": "сначала заполните первый абзац",
        "edit_ro_lead_split": "подводка разделена цитатой, правьте её в файле",
        "edit_ro_form": "блок записан в другой форме, чем ждёт тема, правьте его в файле",
        "edit_ro_marker": "пункт списка записан необычно (табуляция после маркера), правьте его в файле",
        "edit_ro_bold_lines": "жирный зачин занимает несколько строк, правьте его в файле",
        "edit_ro_no_image": "в пункте нет картинки ![подпись](путь)",
        "edit_ro_table_new": "таблицы в блоке ещё нет: начните её в файле со строки шапки",
        "edit_ro_front": "SEO-блок не читается как YAML, сначала поправьте его в файле",
        "edit_ro_path": "категория - это папка файла; перенос делают команды страниц и категорий",
        "edit_ro_body": "текст страницы не разбирается: {reason}",
        "edit_front_broken": "SEO-блок не читается как YAML, сначала поправьте его в файле",
        "edit_front_flow": "значение записано в фигурных скобках {{…}}, правьте его в файле",
        "edit_front_not_mapping": "по этому пути в SEO-блоке не набор ключей",
        "edit_unknown_field": "нет такого поля: {path}",
        "edit_bad_index": "нет пункта с номером {index}",
        "edit_no_key": "у файла нет ключа страницы: он лежит не в content/<язык>/",
        "edit_no_section": "на странице нет секции {section!r}",
        "edit_bad_anchor": (
            "якорь {anchor!r}: латиница в нижнем регистре, цифры и дефис, например how-to-start"
        ),
        "edit_section_exists": "секция с якорем {section!r} на странице уже есть",
        "edit_heading_empty": "у блока должен быть заголовок",
        "edit_group_schema": "Разметка для поисковиков",
        "edit_schema_hint": "Уточнения разметки {kind} для этой страницы поверх site.yaml",
        "edit_schema_help": (
            "Поля разметки schema.org типа {kind}: их читают поисковики, на странице их не видно. "
            "То, что задано здесь, дополняет общий блок schema из site.yaml для этой страницы. "
            "Пишите только то, что правда и есть на странице; лишнее поисковик считает спамом."
        ),
        "edit_required": "поле {field} обязательно",
        "edit_too_long": "{field}: {length} знаков, больше {max}",
        "edit_too_short": "{field}: {length} знаков, меньше {min}",
        "edit_few_items": "{field}: пунктов {count}, нужно не меньше {min}",
        "edit_many_items": "{field}: пунктов {count}, можно не больше {max}",
        "edit_not_in_values": "{field}: {value!r} - нет среди допустимых: {values}",
        "edit_image_missing": "{field}: файла {src} нет в папке сайта",
        "edit_image_narrow": "{field}: {src} шириной {width} px, нужно от {min} px",
        "edit_image_ratio": "{field}: пропорции {src} - {actual}, тема ждёт {ratio}",
        "edit_image_unreadable": "{field}: {src} не читается как картинка",
        "edit_schema_type": "schema.{kind}: в словаре schema.org нет такого типа",
        "edit_schema_prop": "schema.{kind}.{prop}: у типа {kind} нет такого свойства",
        "edit_section_missing": "нет обязательной секции {section!r}",
        "edit_unknown_type": "тип {value!r} - в теме есть только: {known}",
        "edit_bad_key": (
            "ключ {key!r}: части через /, в каждой латиница в нижнем регистре, цифры и дефис"
        ),
        "edit_bad_key_hint": "например about-agency или services/roofing",
        "edit_type_hint": "без --type - тип страниц категории; все типы темы - `heron describe`",
        "edit_key_is_category": "под ключом {key} уже категория (папка с _index.md), а не страница",
        "edit_key_is_page": "под ключом {key} уже страница ({key}.md), а не категория",
        "edit_key_kind_hint": (
            "у страницы и категории с одним ключом был бы один адрес. Править категорию - "
            "`heron category add {key}`, страницу - `heron page add {key}`; или возьмите другой ключ"
        ),
        "edit_unknown_view": "вид {view!r} тип {type} не знает; его виды: {views}",
        "edit_field_failed": "поле {path} ({lang}): {reason}",
        "edit_move_home": "главную не переносят: её адрес - корень языка",
        "edit_move_inside": "категорию {key} нельзя перенести внутрь неё самой ({target})",
        "edit_move_taken": "{key} не перенести: ключ {target} уже занят",
        "edit_move_taken_hint": "выберите свободный ключ или сначала уберите то, что там лежит",
        "edit_answers_shape": (
            "файл ответов - набор ключей: key, type и поля по языкам (ru:, en: …); образец - --dump"
        ),
        "edit_answers_unknown": (
            "в ответах неизвестные ключи: {names}. Ждём key, kind, type и языки сайта: {langs}"
        ),
        "edit_answers_lang": "ответы языка {lang}: набор полей (title: …) или pending",
        "edit_con_yes_words": "y, yes, д, да",
        "edit_con_no_words": "n, no, н, нет",
        "edit_con_empty": "пусто",
        "edit_con_yes": "да",
        "edit_con_no": "нет",
        "edit_con_items": "пунктов: {count}",
        "edit_con_bad_flag": "ответ - да или нет (y или n)",
        "edit_con_bad_number": "нужно целое число",
        "edit_con_bad_date": "дата - ГГГГ-ММ-ДД, например 2026-11-08",
        "edit_con_bad_schema": "свойства - имя=значение через точку с запятой: name=…; url=…",
        "edit_con_required": "(обязательно)",
        "edit_con_no_help": "подробной справки у поля нет",
        "edit_con_example": "пример: {example}",
        "edit_con_readonly": "здесь не меняется: {reason}",
        "edit_con_in_file": "пункты с полями правят в файле или в студии",
        "edit_con_category": (
            "Категория - раздел сайта, в котором лежит страница; адрес страницы начинается с неё"
        ),
        "edit_con_root": "корень сайта, без категории",
        "edit_con_category_how": (
            "номер - выбрать; номер и + (например 1+) - новая категория внутри; "
            "+ - новая в корне; ? - справка"
        ),
        "edit_con_bad_choice": "нет такого варианта - выберите номер из списка",
        "edit_con_new_category": "имя новой категории внутри {parent} (латиница, цифры, дефис):",
        "edit_con_category_made": (
            "категория {key} будет создана на всех языках с заготовкой - заполните её потом: "
            "`heron category add {key}`"
        ),
        "edit_con_type": "Тип страницы - каким шаблоном темы она рисуется и какие блоки в ней ждут",
        "edit_con_open_group": "Изменить? [y/N]",
        "edit_con_translate_new": (
            "Перевод на {lang}. Введите перевод поля или нажмите Enter - пропустить: в файле "
            "останется текст {main}, страница получит пометку «перевод не готов» и не попадёт "
            "в боевую сборку, пока вы её не переведёте"
        ),
        "edit_con_translate": "Перевод на {lang}: Enter оставляет текущий текст",
        "edit_con_skip": "пропустить",
        "edit_con_ready": "Перевод на {lang} готов - снять пометку translation: pending? [y/N]",
        "edit_con_head_new": "Новая {kind} {key} - языки: {langs}",
        "edit_con_head_edit": "Правка: {kind} {key} уже есть. Языки: {langs}",
        "edit_con_keys": (
            "Enter - оставить значение в скобках, ? - справка по полю, - - очистить поле, "
            "Ctrl+C - выйти без записи"
        ),
        "edit_con_page_word": "страница",
        "edit_con_category_word": "категория",
        "edit_con_main": "основной",
        "edit_con_summary": "Итого:",
        "edit_con_new_file": "новый файл",
        "edit_con_changed": "изменён",
        "edit_con_same": "без изменений",
        "edit_con_pending": "перевод не готов (translation: pending)",
        "edit_con_move": "перенос {old} → {new}: файлы на всех языках, 301 со старых адресов",
        "edit_con_menu": "меню (nav)",
        "edit_con_save": "Записать?",
        "edit_answers_yaml": "файл ответов не читается как YAML: {problem}",
        "edit_web_soon": (
            "Студия в браузере появится в следующем шаге выпуска 0.3.0. Пока - опросник в "
            "терминале, он спрашивает те же поля."
        ),
        "edit_web_now": "Опросник: `heron {command}`",
        "edit_dump_head": (
            "# Ответы для heron page add и category add ({key}): поправьте и передайте "
            "через --answers. Пути полей - heron describe"
        ),
        "edit_cancelled": "Отменено, файлы не тронуты.",
        "edit_warning": "предупреждение: {text}",
        "edit_invalid": "запись остановлена, поля не проходят проверку:\n    {lines}",
        "edit_invalid_hint": (
            "поправьте эти поля в ответах или в опроснике; правила - те же, что у heron check"
        ),
        "edit_exists": "{kind} {key} уже есть, вопросов нет (нет терминала) - ничего не меняю:",
        "edit_state_missing": "нет файла",
        "edit_exists_next": (
            "Править: в терминале `heron {command}`; агенту - --dump, затем --answers файл"
        ),
        "edit_nothing": "{kind} {key}: изменений нет, файлы не тронуты.",
        "edit_saved_new": "Создана {kind} {key}:",
        "edit_saved_edit": "Сохранена {kind} {key}:",
        "edit_saved_category": "создана категория {key} (заготовка на всех языках)",
        "edit_saved_moved": "перенесено: {old} → {new}",
        "edit_saved_redirect": "301: {old} → {new} (redirect_from)",
        "edit_comments_lost": "комментарии не удалось сохранить, копия - в .heron-cache/setup/",
        "edit_saved_pending": (
            "Пометка translation: pending - эти языки боевая сборка не опубликует. "
            "Перевести: `heron {command}`"
        ),
        "edit_saved_next": "Посмотреть: `heron serve {path}` · список страниц: `heron page list {path}`",
        "edit_found_by_name": "нашлась страница {key} - открываю её",
    },
    "en": {
        "edit_not_utf8": "the page file is not in UTF-8",
        "edit_single_line": "the value of this field is one line, without line breaks",
        "edit_one_paragraph": "the value of this field is one paragraph, without empty lines inside",
        "edit_bad_path": "the path {value!r}: no spaces or brackets, like media/team/photo.jpg",
        "edit_readonly": "the field is read-only: {reason}",
        "edit_ro_setext": "the heading is underlined by the next line, edit it in the file",
        "edit_ro_anchor": "the heading has no {{#…}} anchor",
        "edit_ro_place": "the editor does not know where this field lives in markdown, edit it in the file",
        "edit_ro_first_paragraph": "fill in the first paragraph first",
        "edit_ro_lead_split": "the lead is split by a quote, edit it in the file",
        "edit_ro_form": "the block is written in another form than the theme expects, edit it in the file",
        "edit_ro_marker": "the list item is written unusually (a tab after the marker), edit it in the file",
        "edit_ro_bold_lines": "the bold start takes several lines, edit it in the file",
        "edit_ro_no_image": "the item has no ![caption](path) picture",
        "edit_ro_table_new": "the block has no table yet: start it in the file with the header row",
        "edit_ro_front": "the SEO block does not read as YAML, fix it in the file first",
        "edit_ro_path": "the category is the folder of the file; page and category commands move it",
        "edit_ro_body": "the text of the page does not parse: {reason}",
        "edit_front_broken": "the SEO block does not read as YAML, fix it in the file first",
        "edit_front_flow": "the value is written in curly braces {{…}}, edit it in the file",
        "edit_front_not_mapping": "this path in the SEO block is not a set of keys",
        "edit_unknown_field": "there is no such field: {path}",
        "edit_bad_index": "there is no item number {index}",
        "edit_no_key": "the file has no page key: it is not in content/<lang>/",
        "edit_no_section": "the page has no section {section!r}",
        "edit_bad_anchor": (
            "the anchor {anchor!r}: lowercase latin letters, digits and hyphens, like how-to-start"
        ),
        "edit_section_exists": "the page already has a section with the anchor {section!r}",
        "edit_heading_empty": "a block needs a heading",
        "edit_group_schema": "Markup for search engines",
        "edit_schema_hint": "Refinements of the {kind} markup for this page on top of site.yaml",
        "edit_schema_help": (
            "The fields of the schema.org {kind} markup: search engines read them, the page "
            "does not show them. What you set here adds to the common schema block of "
            "site.yaml for this page. Write only what is true and is on the page; search "
            "engines treat anything extra as spam."
        ),
        "edit_required": "the field {field} is required",
        "edit_too_long": "{field}: {length} characters, more than {max}",
        "edit_too_short": "{field}: {length} characters, fewer than {min}",
        "edit_few_items": "{field}: {count} items, needs at least {min}",
        "edit_many_items": "{field}: {count} items, at most {max} allowed",
        "edit_not_in_values": "{field}: {value!r} is not among the allowed values: {values}",
        "edit_image_missing": "{field}: there is no file {src} in the site folder",
        "edit_image_narrow": "{field}: {src} is {width} px wide, needs {min} px or more",
        "edit_image_ratio": "{field}: the proportions of {src} are {actual}, the theme expects {ratio}",
        "edit_image_unreadable": "{field}: {src} does not read as a picture",
        "edit_schema_type": "schema.{kind}: the schema.org vocabulary has no such type",
        "edit_schema_prop": "schema.{kind}.{prop}: the type {kind} has no such property",
        "edit_section_missing": "the required section {section!r} is missing",
        "edit_unknown_type": "the type {value!r} - the theme has only: {known}",
        "edit_bad_key": (
            "key {key!r}: parts separated by /, each of lowercase Latin letters, digits and hyphens"
        ),
        "edit_bad_key_hint": "for example about-agency or services/roofing",
        "edit_type_hint": (
            "without --type - the page type of the category; all types of the theme - "
            "`heron describe`"
        ),
        "edit_key_is_category": "the key {key} is already a category (a folder with _index.md)",
        "edit_key_is_page": "the key {key} is already a page ({key}.md), not a category",
        "edit_key_kind_hint": (
            "a page and a category with one key would share one address. To edit the category - "
            "`heron category add {key}`, the page - `heron page add {key}`; or take another key"
        ),
        "edit_unknown_view": "the type {type} does not know the view {view!r}; its views: {views}",
        "edit_field_failed": "field {path} ({lang}): {reason}",
        "edit_move_home": "the home page is not moved: its address is the root of the language",
        "edit_move_inside": "the category {key} cannot be moved inside itself ({target})",
        "edit_move_taken": "{key} cannot be moved: the key {target} is taken",
        "edit_move_taken_hint": "choose a free key or first remove what lies there",
        "edit_answers_shape": (
            "an answers file is a set of keys: key, type and fields per language (en:, ru: …); "
            "a sample - --dump"
        ),
        "edit_answers_unknown": (
            "unknown keys in the answers: {names}. Expected key, kind, type and the languages "
            "of the site: {langs}"
        ),
        "edit_answers_lang": "the answers of {lang}: a set of fields (title: …) or pending",
        "edit_con_yes_words": "y, yes",
        "edit_con_no_words": "n, no",
        "edit_con_empty": "empty",
        "edit_con_yes": "yes",
        "edit_con_no": "no",
        "edit_con_items": "items: {count}",
        "edit_con_bad_flag": "the answer is yes or no (y or n)",
        "edit_con_bad_number": "a whole number is needed",
        "edit_con_bad_date": "a date is YYYY-MM-DD, for example 2026-11-08",
        "edit_con_bad_schema": "properties are name=value separated by semicolons: name=…; url=…",
        "edit_con_required": "(required)",
        "edit_con_no_help": "the field has no detailed help",
        "edit_con_example": "example: {example}",
        "edit_con_readonly": "not changed here: {reason}",
        "edit_con_in_file": "items with fields are edited in the file or in the studio",
        "edit_con_category": (
            "Category - the section of the site the page lives in; the address of the page starts "
            "with it"
        ),
        "edit_con_root": "the root of the site, no category",
        "edit_con_category_how": (
            "a number - pick; a number and + (for example 1+) - a new category inside; "
            "+ - a new one at the top; ? - help"
        ),
        "edit_con_bad_choice": "no such choice - pick a number from the list",
        "edit_con_new_category": "the name of the new category inside {parent} (Latin, digits, hyphen):",
        "edit_con_category_made": (
            "the category {key} will be created in all languages from a stub - fill it in later: "
            "`heron category add {key}`"
        ),
        "edit_con_type": ("Page type - which theme template draws it and which blocks it expects"),
        "edit_con_open_group": "Change? [y/N]",
        "edit_con_translate_new": (
            "Translation into {lang}. Type the translation of a field or press Enter to skip it: "
            'the file keeps the {main} text, the page gets the "translation pending" mark and '
            "stays out of production until you translate it"
        ),
        "edit_con_translate": "Translation into {lang}: Enter keeps the current text",
        "edit_con_skip": "skip",
        "edit_con_ready": (
            "Is the {lang} translation ready - remove the mark translation: pending? [y/N]"
        ),
        "edit_con_head_new": "New {kind} {key} - languages: {langs}",
        "edit_con_head_edit": "Editing: the {kind} {key} already exists. Languages: {langs}",
        "edit_con_keys": (
            "Enter - keep the value in brackets, ? - help on the field, - - clear the field, "
            "Ctrl+C - quit without writing"
        ),
        "edit_con_page_word": "page",
        "edit_con_category_word": "category",
        "edit_con_main": "main",
        "edit_con_summary": "Summary:",
        "edit_con_new_file": "new file",
        "edit_con_changed": "changed",
        "edit_con_same": "unchanged",
        "edit_con_pending": "translation pending (translation: pending)",
        "edit_con_move": "move {old} → {new}: files in all languages, 301 from the old addresses",
        "edit_con_menu": "menu (nav)",
        "edit_con_save": "Write?",
        "edit_answers_yaml": "the answers file does not read as YAML: {problem}",
        "edit_web_soon": (
            "The studio in a browser arrives in the next step of release 0.3.0. For now - the "
            "questionnaire in the terminal, it asks the same fields."
        ),
        "edit_web_now": "The questionnaire: `heron {command}`",
        "edit_dump_head": (
            "# Answers for heron page add and category add ({key}): edit them and pass them "
            "with --answers. Field paths - heron describe"
        ),
        "edit_cancelled": "Cancelled, the files are untouched.",
        "edit_warning": "warning: {text}",
        "edit_invalid": "writing stopped, fields do not pass the check:\n    {lines}",
        "edit_invalid_hint": (
            "fix these fields in the answers or in the questionnaire; the rules are those of "
            "heron check"
        ),
        "edit_exists": (
            "the {kind} {key} already exists, no questions (no terminal) - nothing changed:"
        ),
        "edit_state_missing": "no file",
        "edit_exists_next": (
            "To edit: in a terminal `heron {command}`; an agent - --dump, then --answers file"
        ),
        "edit_nothing": "{kind} {key}: no changes, the files are untouched.",
        "edit_saved_new": "Created the {kind} {key}:",
        "edit_saved_edit": "Saved the {kind} {key}:",
        "edit_saved_category": "created the category {key} (a stub in all languages)",
        "edit_saved_moved": "moved: {old} → {new}",
        "edit_saved_redirect": "301: {old} → {new} (redirect_from)",
        "edit_comments_lost": "the comments could not be kept, a copy is in .heron-cache/setup/",
        "edit_saved_pending": (
            "Marked translation: pending - the production build will not publish these languages. "
            "To translate: `heron {command}`"
        ),
        "edit_saved_next": "Preview: `heron serve {path}` · the list of pages: `heron page list {path}`",
        "edit_found_by_name": "found the page {key} - opening it",
    },
}
