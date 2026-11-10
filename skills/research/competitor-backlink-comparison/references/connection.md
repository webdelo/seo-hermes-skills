# Подключение Ahrefs и DataForSEO

## Credentials

Скрипт читает `AHREFS_API_KEY`, `DFS_LOGIN`, `DFS_PASSWORD` сначала из окружения процесса, затем из `.env` активного `HERMES_HOME`. Другие профили не просматриваются. На POSIX файл `.env` должен иметь права `0600`.

Не передавать секреты аргументами CLI, не печатать заголовки Authorization, не сохранять их в spec, output, Git или чат. При отсутствии значения live-режим завершается до сети. `--from-cache` credentials не читает.

## Ahrefs API v3

Base URL: `https://api.ahrefs.com/v3/`. Авторизация: Bearer token только к этому origin. Скрипт отказывается следовать редиректам и не выводит тело ошибки.

Используемые endpoints:

- `site-explorer/domain-rating`: отдельный запрос для каждого домена; DR не складывается.
- `site-explorer/all-backlinks`: отдельный запрос для каждого исходного landing URL с `mode=exact`, `history=live`, `aggregation=all`, явным `limit` и ограниченным `select`.

Актуальные поля, тариф и units проверить перед live-запуском по официальной документации и OpenAPI: `https://docs.ahrefs.com/en/api`, `https://docs.ahrefs.com/openapi.json`. Не считать исторически бесплатный пример гарантией текущей цены.

## DataForSEO Backlinks API

Base URL: `https://api.dataforseo.com/v3/`. Авторизация: HTTP Basic из `DFS_LOGIN` и `DFS_PASSWORD` только к этому origin.

Используемые endpoints:

- `backlinks/bulk_pages_summary/live`: сводка по переданным точным страницам.
- `backlinks/backlinks/live`: строки ссылок отдельно для каждого точного target URL с явным `limit`.

Summary-счётчики и выгруженные строки имеют разный охват. Не заменять один другим. Ahrefs и DataForSEO могут иметь разные индексы, даты обхода и правила учёта, поэтому их результаты нельзя объединять в один count.

## Стоимость и сбои

Live endpoints могут быть платными. До запуска согласовать число доменов, URL и `row_limit`. Автоматического повтора нет: таймаут после платного запроса не доказывает, что списания не было. 401/403/429 и недоступный endpoint фиксировать как blocked без обхода или смены credentials.

Сохранённый `api-cache.json` предназначен для бесплатной повторной агрегации через `--from-cache`. Не публиковать cache, если в нём есть клиентские данные.
