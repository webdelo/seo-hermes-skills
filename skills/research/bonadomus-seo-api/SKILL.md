---
name: bonadomus-seo-api
description: Read and update Bonadomus catalog SEO via its API.
version: 0.1.0
author: Spara Daniil, Hermes Agent
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [bonadomus, seo, api, idx, catalog]
---

# Bonadomus SEO API

Use this skill to read and update the SEO content of Bonadomus catalog pages through the production SEO API. It covers page meta, editorial HTML, editorial blocks, and shape templates; MLS listing pages are read-only. Never commit a token, paste it into chat, or include it in command output.

## When to Use

- Inspect the effective or own SEO data of a Bonadomus catalog URL.
- Create or update a catalog page's meta, `seo_text`, or editorial block after explicit approval.
- Inspect or update an approved shape-wide meta template.
- Do not use for listing-page changes: listing metadata is read-only.

## Credentials

1. In Bonadomus admin, an administrator opens **IDX → SEO API → Tokens** and creates a personal access token with the required ability.
2. Use `seo:read` for all GET requests, `seo:write` for page metadata and blocks, and `seo:templates` for template changes.
3. Store the token only in the active process environment:

```sh
export BONADOMUS_SEO_API_TOKEN='…'
export BONADOMUS_SEO_API_URL='https://bonadomus.com/api/v1/seo'
```

Do not add the token to this repository, a skill, source code, shell profile, request log, or generated JSON. The API limit is 60 requests per minute per token.

## Read Procedure

1. For a public catalog path, call `GET /pages/resolve?path=<path>` first. Completion: `id`, `version`, `path`, `shape`, `reachable`, own `meta`, effective values, and blocks are known.
2. Use `GET /pages?per_page=50` only to list addresses that already have their own records. Completion: do not infer that a missing list item has no generated page.
3. Use `GET /pages/{id}` to inspect a known record before any update. Completion: the current `version` is recorded.
4. Use `GET /templates` or `GET /templates/{id}` to inspect templates. Completion: shape, filters, priority, and published state are known before a template change.

```sh
curl --silent --show-error \
  -H "Authorization: Bearer $BONADOMUS_SEO_API_TOKEN" \
  --get --data-urlencode 'path=/dania-beach' \
  "$BONADOMUS_SEO_API_URL/pages/resolve"
```

## Editorial Layout Standard

The approved reference is the catalog page `/dania-beach` (record `id: 101`, shape `city`). Its editorial content is stored in `meta.seo_text`; it is rendered inside `.idx-catalog__editorial.idx-catalog__editorial--seo-text`.

Use this HTML shell for new city-page editorial content unless the user supplies another approved reference:

```html
<div class="page-article" style="padding-bottom:0;">
  <section style="margin-bottom:32px;">
    <h2 style="margin-bottom:20px;">Primary editorial heading</h2>
    <p style="margin-bottom:16px;">Opening paragraph.</p>
    <p style="margin-bottom:0;">Closing paragraph.</p>
  </section>
  <section style="margin-bottom:32px;">
    <h3 style="margin-bottom:20px;">Supporting question or topic</h3>
    <p style="margin-bottom:16px;">Supporting copy.</p>
    <ul style="margin-bottom:16px;"><li>Factual item</li></ul>
    <p style="margin-bottom:0;">Closing paragraph.</p>
  </section>
</div>
```

Rules derived from the approved page:

- Use one `h2` for the editorial introduction, then `h3` for subsequent topical sections.
- Place each topic in its own `section` with `margin-bottom:32px`.
- Set heading spacing to `margin-bottom:20px`; use `margin-bottom:16px` on paragraphs except the final paragraph of a section, which uses `margin-bottom:0`.
- Use semantic `p`, `ul`, and `li`; use `b` only for factual emphasis. Do not add custom page-grid, sidebar, card, or typography classes.
- Keep the text in `meta.seo_text`. Do not use `below` blocks as a substitute unless the user explicitly requests a separate block; `PUT /pages/{id}/blocks` replaces the complete selected zone and locale.
- Provide each requested locale separately (`en`, `ru`, `es`). Never overwrite a locale not approved by the user.

## Write Procedure

1. Show the user the exact path or ID, locale, current own value, effective value, and proposed payload. Completion: approval explicitly covers every field and locale.
2. Re-read `GET /pages/{id}` immediately before the write and include its `version` in the request. Completion: the change is protected from stale overwrites.
3. Use the narrowest endpoint:
   - `PATCH /pages/{id}/meta` for a partial meta or `seo_text` update;
   - `PUT /pages/{id}/blocks` for one complete zone and locale;
   - `PUT /pages` only when a path must create or upsert a record;
   - `PUT /templates/{id}` only for an approved shape-wide template change.
4. Read `applied` in the response. Completion: every requested field has the expected stored `new` value.
5. Re-read the same target after the write. Completion: own and effective values match the approved result.

Example partial write:

```json
{
  "version": 6,
  "seo_text": {
    "en": "<div class=\"page-article\" style=\"padding-bottom:0;\">…</div>"
  }
}
```

Omitted fields and locales remain unchanged. `null` or an empty string clears an own value and restores template/generator fallback. Titles, descriptions, and H1s are limited to 70, 170, and 120 characters per locale respectively. The server sanitizes HTML: scripts, iframes, event handlers, objects, and `javascript:` URLs are removed.

## Conflict and Safety Rules

- A `409` means the page version changed. Re-read the record, compare the current values, and obtain fresh approval if the intervening change affects the proposal.
- A `403` means the token lacks the required ability; do not retry as a write.
- Template changes can affect every page matching the shape. Treat them as bulk production changes and require separate explicit approval.
- The server logs every request, including rejected requests and request bodies. Send only the approved payload.

## Verification

- A read is successful only when it returns HTTP 200 with the expected JSON structure.
- A write is successful only when `applied` reports the expected stored values and a fresh GET confirms the exact field, locale, and effective result.
- Before reporting completion, verify that no unapproved locale, block zone, or template was changed.
