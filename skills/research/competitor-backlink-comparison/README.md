# Сравнение сайтов с конкурентами — DataForSEO + Ahrefs

Установка:

```bash
hermes skills install webdelo/seo-hermes-skills/skills/research/competitor-backlink-comparison
```

После установки попросите Hermes: «Загрузи навык competitor-backlink-comparison». Недостающие обязательные доступы запрашиваются защищённо; значения выдаёт владелец команды лично.

## Spec JSON

Минимальная форма:

```json
{
  "focal_domain": "example.com",
  "clusters": {
    "category-a": [
      "http://example.com/category-a",
      "https://competitor-one.example/category-a?view=all"
    ],
    "category-b": [
      "https://example.com/category-b",
      "https://competitor-two.example/category-b"
    ]
  }
}
```

- `focal_domain` — основной hostname без схемы, пути, query, порта и пробелов. Значение приводится к нижнему регистру; один начальный `www.` снимается для сопоставления.
- `clusters` — объект «имя кластера → непустой массив точных абсолютных HTTP/HTTPS URL».
- Один URL может входить только в один кластер.
- Опциональный `row_limit` — число строк каждого backlink-запроса, от 1 до 1000; по умолчанию 1000. Лимит согласовать до платного сбора.
- Один spec может содержать не более 1000 целевых URL и 100 уникальных канонических target-доменов (`www.` и регистр не создают отдельный домен). Превышение отклоняется до сетевых и платных запросов; автоматического chunking нет.
- Скрипт сохраняет URL дословно. HTTP/HTTPS, path и query не нормализуются.

## Команды

```bash
python3 scripts/compare_backlinks.py --spec /path/spec.json --out /path/new-result
python3 scripts/compare_backlinks.py --spec /path/spec.json --out /path/new-result --from-cache /path/prior-result
python3 -m unittest scripts/test_compare_backlinks.py -v
```

Live-режим читает `AHREFS_API_KEY`, `DFS_LOGIN`, `DFS_PASSWORD` из окружения или `.env` активного `HERMES_HOME`. `--from-cache` читает `api-cache.json`, не требует credentials и не делает API-запросов. Непустой `--out` отклоняется. На POSIX новый выходной каталог получает права `0700`, а live `api-cache.json` — `0600`.

Выходные файлы: `summary.json`, `ahrefs_backlinks_raw.csv`, `dataforseo_backlinks_raw.csv`, один русский `report.ru.md`; live-сбор также сохраняет `api-cache.json`. Summary помечает цели через `is_focal`, считает Ahrefs `dofollow_rows` и сохраняет DataForSEO `page_summary`. Русский отчёт содержит сравнительную Markdown-таблицу для каждого кластера, явно отмечает основной сайт и показывает `page_summary.backlinks`/`referring_domains` отдельно от ограниченной выгрузки строк.

Live-сбор отклоняет DataForSEO-ответы с ошибочным верхнеуровневым или task-level `status_code`, даже если HTTP-статус равен 200. Ошибка сообщает только уровень и числовой код; provider `status_message` не выводится.

Python 3.11+, только стандартная библиотека. Тесты синтетические и не подтверждают live-доступ, тариф или стоимость API.
