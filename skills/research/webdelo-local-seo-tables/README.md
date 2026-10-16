# Две таблицы частотности для локальных страниц Webdelo

Установка:

```bash
hermes skills install webdelo/seo-hermes-skills/skills/research/webdelo-local-seo-tables
```

После установки попросите Hermes: «Загрузи навык `webdelo-local-seo-tables` и сформируй две таблицы для локальной SEO-страницы».

Навык собирает первую таблицу из сохранённой сырой выгрузки Google Ads Keyword Planner, вторую — из проверенного межгородского набора Google Ads/XMLRiver, а затем валидирует строки RU/DE/EN и класс `!pb-22`.

Для запуска скопируйте `references/spec-example.json`, укажите пути к источникам относительно spec-файла и выполните команду из `SKILL.md`. Полные обязательные структуры Google Ads, comparison JSON и результата описаны в `references/input-schema.md`.
