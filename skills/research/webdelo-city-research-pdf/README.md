# PDF-отчёты для локальных SEO-страниц Webdelo

Установка:

```bash
hermes skills install webdelo/seo-hermes-skills/skills/research/webdelo-city-research-pdf
```

После установки попросите Hermes: «Загрузи навык webdelo-city-research-pdf».

Навык строит PDF из двух итоговых RU-таблиц страницы и сохранённых ответов XMLRiver. Для работы нужны Python 3.11+, `reportlab` и `pypdf`, установленные в виртуальном окружении. API-ключи для сборки PDF не требуются: рендер использует уже проверенные локальные данные.
