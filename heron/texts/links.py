"""Сообщения связей, дат и страницы 404 (core/links.py, core/dates.py, core/notfound.py)."""

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "links_unresolved": "ссылка {href} никуда не ведёт",
        "links_fallback": "ссылка {path}: на {lang!r} этой страницы нет, ведёт на версию {found!r}",
        "links_no_default": "страница есть на {lang!r}, но нет на языке по умолчанию {default!r}",
        "links_field_empty": "поле {field!r} не заполнено, а тема ждёт минимум {required}",
        "links_missing_page": "{field}: страницы {name!r} не существует{of_type}",
        "links_of_type": " среди страниц типа {type!r}",
        "links_missing_page_hint": (
            "страница называется именем своего файла без расширения, "
            "а не адресом: slug на неё ничего здесь не меняет"
        ),
        "links_ambiguous": "{field}: имя {name!r} неоднозначно — {sources}",
        "links_ambiguous_hint": "уточните тип связи в theme.yaml или переименуйте файл",
        "links_self": "{field}: страница ссылается на саму себя ({name!r}), пропущено",
        "links_too_few": "{field}: ссылок {count}, тема ждёт минимум {required}",
        "links_menu_untranslated": "меню {group!r}: {key!r} ещё не переведено на {lang!r}",
        "links_menu_missing": "меню {group!r}: нет страницы {key!r} на языке {lang!r}",
        "links_dates_no_history": "истории нет — даты взяты из времени файлов, страниц {count}",
        "links_dates_dirty": "файл изменён, но не закоммичен — дата взята из времени файла",
        "links_dates_not_in_history": "файла нет в истории — дата взята из времени файла",
        "links_dates_same_time": (
            "у всех файлов одно время — так выглядит копирование, а не правка; "
            "дата обновления не проставлена"
        ),
        "links_dates_unreadable": "файл не читается — даты нет",
        "links_dates_future": "{name}: {moment} — позже сборки; поисковик сочтёт дату ошибкой",
        "links_dates_backwards": "обновление {updated} раньше публикации {date}",
        "links_notfound_no_template": (
            "нет content/{lang}/404.md и шаблона темы templates/404.html: "
            "на несуществующий адрес сервер отдаст свою заглушку"
        ),
        "links_notfound_from_theme": (
            "нет content/{lang}/404.md: страница 404 собрана из шаблона темы без текста"
        ),
        "links_notfound_source": "content/{lang}/404.md (нет файла)",
    },
    "en": {
        "links_unresolved": "link {href} leads nowhere",
        "links_fallback": "link {path}: this page does not exist in {lang!r}, it leads to the {found!r} version",
        "links_no_default": "the page exists in {lang!r} but not in the default language {default!r}",
        "links_field_empty": "field {field!r} is empty, but the theme expects at least {required}",
        "links_missing_page": "{field}: page {name!r} does not exist{of_type}",
        "links_of_type": " among pages of type {type!r}",
        "links_missing_page_hint": (
            "a page is named by its file name without the extension, "
            "not by its address: a slug changes nothing here"
        ),
        "links_ambiguous": "{field}: name {name!r} is ambiguous: {sources}",
        "links_ambiguous_hint": "specify the relation type in theme.yaml or rename the file",
        "links_self": "{field}: the page links to itself ({name!r}), skipped",
        "links_too_few": "{field}: {count} links, the theme expects at least {required}",
        "links_menu_untranslated": "menu {group!r}: {key!r} is not translated into {lang!r} yet",
        "links_menu_missing": "menu {group!r}: no page {key!r} in language {lang!r}",
        "links_dates_no_history": "no history: dates are taken from file times, pages: {count}",
        "links_dates_dirty": "the file is changed but not committed: the date is taken from the file time",
        "links_dates_not_in_history": "the file is not in the history: the date is taken from the file time",
        "links_dates_same_time": (
            "all files have the same time: this looks like a copy, not an edit; "
            "the update date is not set"
        ),
        "links_dates_unreadable": "the file cannot be read: no date",
        "links_dates_future": "{name}: {moment} is later than the build; a search engine will treat the date as an error",
        "links_dates_backwards": "update {updated} is earlier than publication {date}",
        "links_notfound_no_template": (
            "no content/{lang}/404.md and no theme template templates/404.html: "
            "the server will serve its own placeholder for a missing address"
        ),
        "links_notfound_from_theme": (
            "no content/{lang}/404.md: the 404 page is built from the theme template without text"
        ),
        "links_notfound_source": "content/{lang}/404.md (no file)",
    },
}
