"""Сообщения отчёта check: SEO-замечания, старые адреса (core/report.py)."""

TEXT: dict[str, dict[str, str]] = {
    "ru": {
        "report_seo_nav_empty": "навигация nav.main пуста: поисковик не увидит разделов сайта",
        "report_seo_nav_html": "ссылок навигации нет в HTML главной ({lang}): меню строится скриптом, краулер его не видит",
        "report_seo_titles": "одинаковый title у {n} страниц ({lang}): {pages}",
        "report_seo_no_cover": "страниц без обложки: {n} (нет og:image в разметке и primaryImageOfPage)",
        "report_old_lost": "старый адрес {url} никуда не ведёт; вероятно, поставить 301 на {target}: redirect_from: [{url}] во фронтматтере {file}",
        "report_old_summary": "старых адресов: {total}, без пути: {lost}",
        "report_old_not_utf8": "файл старых адресов не в UTF-8 (байт {byte})",
        "report_old_not_utf8_hint": "пересохраните файл в UTF-8 и запустите check снова",
    },
    "en": {
        "report_seo_nav_empty": "nav.main is empty: search engines will not see the site sections",
        "report_seo_nav_html": "the home page HTML ({lang}) has no navigation links: the menu is built by a script, crawlers do not see it",
        "report_seo_titles": "{n} pages share the same title ({lang}): {pages}",
        "report_seo_no_cover": "pages without a cover: {n} (no og:image and no primaryImageOfPage)",
        "report_old_lost": "old URL {url} leads nowhere; probably set a 301 to {target}: redirect_from: [{url}] in the front matter of {file}",
        "report_old_summary": "old URLs: {total}, without a path: {lost}",
        "report_old_not_utf8": "the old URLs file is not UTF-8 (byte {byte})",
        "report_old_not_utf8_hint": "re-save the file as UTF-8 and run check again",
    },
}
