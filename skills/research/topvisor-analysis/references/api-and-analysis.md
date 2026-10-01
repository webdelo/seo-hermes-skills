# API и методика

Документация: https://topvisor.com/ru/api/v2/first-call/ ; https://topvisor.com/ru/api/projects-2/projects/get/ ; https://topvisor.com/ru/api/positions-2/get-history/ ; https://topvisor.com/ru/api/v2/basic-params/paging/ . Визуальный источник https://webdelo.com/ .

Base: https://api.topvisor.com/v2/json/ . POST JSON, headers Content-Type application/json, User-Id, Authorization bearer. Запрет redirects. Только get/projects_2/projects и get/positions_2/history.

Projects params: {"fields":["id","name","url","status_positions_percent"],"show_searchers_and_regions":2,"limit":1000,"offset":0}. result список проектов; searchers[].regions[].index это region_index, не key. Сохранять metadata, не передавать весь аккаунт критику.

History params: project_id, regions_indexes, dates (type_range=100) ИЛИ date1/date2 (type_range=0 для полного периода), fields=["id","name","group_id"], positions_fields=["position","relevant_url"], show_headers=true, show_exists_dates=true. Объём ограничить нужным периодом.
result.keywords[].positionsData["YYYY-MM-DD:project_id:region_index"] = {"position":"6","relevant_url":"https://..."}. Позиция числовой строкой допустима. Даты анализа headers.dates; existsDates может охватывать всю историю. headers.projects[].searchers[].regions[] может содержать device_name="PC"; не угадывать названия по кодам.
Пагинация nextOffset на верхнем уровне. total обязательно сверять; нельзя остановиться по короткой странице при наличии nextOffset. Повтор ID, смена total/заголовков или несходящийся count = блокировка достоверного отчёта.

Sentinel -- документирован, но причина отсутствия и глубина не доказаны. Исторический набор удалённых ключей и настройки глубины не восстанавливать догадками. Агрегаты numeric-only сопровождаются покрытием, иначе они скрывают выпадения. Текущий status_positions_percent<100 нельзя игнорировать; прошлые даты также не объявлять сертифицированно завершёнными.

Минимальные результаты: report.html, changes.csv, raw responses, evidence.json с параметрами без ключей, UTC, hashes и счётчиками. Клиентские каталоги 0700, файлы 0600. Существующие результаты не перетирать. Ссылки HTML должны иметь полный видимый URL; проверка href не означает проверенную доступность сайта.

Клиент read_api.py ограничен выгрузкой и сохранением доказательств. Интерпретацию и дизайн делать по конкретной задаче с тестами, это не автономный мониторинг. Старый незавершённый draft topvisor-readonly-monitor не использовать.
