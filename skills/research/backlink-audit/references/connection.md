# Ahrefs API

Use direct REST API v3, not MCP, for this user's Ahrefs integration.

## Credentials
Использовать `scripts/credentials.py` для чтения AHREFS_API_KEY из окружения или .env активного профиля. Не читать другой профиль и не копировать ключ в командную строку, Git, отчёт или чат. Секретный файл должен иметь права 0600 на POSIX.

## Requests
Base URL: https://api.ahrefs.com/v3/
Header: Authorization: Bearer <key>. Request JSON using output=json. Python urllib.request works without additional dependencies. Redact the key from any error body before printing. Do not send the key to any other origin.

Official docs: https://docs.ahrefs.com/en/api
Machine-readable endpoint and field schema: https://docs.ahrefs.com/openapi.json
Consult the current schema before building unfamiliar queries; do not invent field names.

## Verification and cost
- GET subscription-info/limits-and-usage?output=json is free. Inspect workspace usage, per-key cap, expiry, and plan before large jobs. null per-key limit means no individual cap, not unlimited workspace entitlement.
- Free smoke test: GET site-explorer/domain-rating?date=2023-05-18&target=firehose.com&output=json.
- Site Explorer test queries targeting ahrefs.com, yep.com, or firehose.com are free. See https://docs.ahrefs.com/en/api/docs/free-test-queries for exact restrictions.
- Free test success proves authentication but not paid endpoint entitlement for arbitrary targets.
- Normal queries may consume nonrefundable units, minimum 50 for charged endpoints. Select only needed fields; set small explicit limits. Do not launch bulk exports or enable paid overages without user approval.
- Do not assume REST API is Enterprise-only: consult current eligibility docs and actual responses.
- Distinguish stored credential + verified REST access from registered native MCP tools. This integration uses terminal HTTP requests; do not claim a native tool was installed.

## Защита запросов
Не следовать редиректам с Authorization, включая тот же origin; не повторять платный запрос автоматически. Запросы только к https://api.ahrefs.com/v3/. Ошибки выводить кодом/статусом без тела, заголовков и секретных URL. Сначала проверить актуальную документацию стоимости; исторически бесплатные примеры не считать гарантией текущих условий. Готового универсального API-клиента здесь нет: параметры запроса строятся по актуальной схеме при выполнении аудита.
