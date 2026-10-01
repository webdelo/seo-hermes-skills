# Контракт проектных артефактов

CSV в UTF-8, с заголовками и стандартным CSV-экранированием. Массивы в ячейках сериализовать JSON. Исходные фразы и URL не исправлять; ID сохранять при сортировке. Это внутренний формат, не заявленный формат неизвестного внешнего сервиса.

| Файл | Поля / содержание |
|---|---|
| brief.md | сайт, тематика, реальные услуги, язык, регион, поисковая система, разрешения |
| queries.csv | query_id, query_raw, frequency, frequency_source |
| pages.csv | page_id, url_original, url_final, title, h1, h2_json, content_evidence, source_file, page_type, intent, geo, language, http_status, canonical, indexability, eligibility, reason |
| seeds.csv | seed_id, page_id, seed_phrase, evidence, approval_status |
| integration.md | сервис, документация, seed-семантика, маппинг колонок, настройки, разрешённый объём, получение статуса |
| seeded_input.json | версия входа, query_id, seed_id → page_id, параметры |
| seeded_raw.* | неизменённый реальный ответ первого прохода |
| seeded_memberships.csv | cluster_id, query_id, seed_ids_json, source_file |
| decisions.csv | query_id, cluster_id, previous_page_id, decision, target_page_id, reason, evidence |
| residual.csv | query_id, query_raw, reason |
| residual_raw.* | неизменённый реальный ответ второго прохода |
| residual_memberships.csv | cluster_id, query_id, source_file |
| mapping.csv | query_id, status, page_id, proposed_page_id, cluster_id, pass, reason, evidence |
| new_pages.csv | proposed_page_id, topic, main_query, intent, page_type, section, suggested_url, query_ids_json, relevance_reason, duplicate_check, priority, priority_evidence |
| rejected.csv | query_id, cluster_id, reason, evidence |
| review.csv | query_id, candidate_page_ids_json, reason, required_evidence |
| validation.json | проверки покрытия/ссылок, счётчики, ошибки, версии/хеши входов и выходов |
| progress.md | выполнено, файлы, проверки, блокировки, следующий шаг |
| review.md | независимый PASS/FAIL, проверенная версия, доказательства |
| report.md | сводка, ready/partial/blocked, результаты, ограничения, ссылки на файлы |

mapping.status: existing, new_page, rejected, needs_review, unresolved. Для existing обязателен page_id, для new_page обязателен proposed_page_id. У остальных целевые ID пустые; варианты находятся в review.csv. mapping.pass: seeded, residual, not_processed. Для cluster_id использовать разные префиксы проходов, сохраняя внешний ID в raw.

Неизвестные частотности оставлять пустыми. Дубли исходных строк сохранять с отдельными ID и обратным соответствием дедупликации. Seeds не включать в счётчик исходных запросов. При отсутствии интеграции записать blocked_external_clusterer; не создавать фиктивные raw-ответы.
