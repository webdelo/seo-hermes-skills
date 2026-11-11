# DataForSEO — промты и Query fan-out

Навык получает дословные пользовательские промты и Query fan-out через DataForSEO AI Optimization API. Он не генерирует, не переводит и не редактирует формулировки.

## Установка

```bash
hermes skills install webdelo/seo-hermes-skills/skills/research/dataforseo-ai-optimization
```

После установки попросите Hermes загрузить `dataforseo-ai-optimization`.

## Доступ

Нужны персональные `DFS_LOGIN` и `DFS_PASSWORD`, выданные владельцем команды. Не отправляйте их в чат и не сохраняйте в папку навыка. Live-запросы платные.

## Режимы

- `history` — ищет наблюдаемые пользовательские промты и Query fan-out в LLM Mentions.
- `scrape` — отправляет точный промт пользователя в ChatGPT LLM Scraper и возвращает текущий Query fan-out.

ChatGPT LLM Mentions DataForSEO ограничен рынком United States / English. Результаты этого режима нельзя выдавать за российский или русскоязычный спрос.