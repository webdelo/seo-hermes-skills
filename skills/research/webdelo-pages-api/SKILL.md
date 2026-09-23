---
name: webdelo-pages-api
description: Connect to and update Webdelo pages through signed API.
version: 0.1.0
author: Spara Daniil, Hermes Agent
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [webdelo, pages, markdown, publishing, api]
    related_skills: [webdelo-city-json-rebuild]
---

# Webdelo Pages API

Use this skill to connect to Webdelo Page API, export existing pages, update approved envelopes, and verify the result. For rebuilding legacy city-page JSON against page 96, use `webdelo-city-json-rebuild`. Publish the skill only to a repository explicitly approved by the user. The supplied API secret is a credential: never place it in `SKILL.md`, source files, chat output, git, or an API payload.

## When to Use

- Create or update a Webdelo page from Markdown.
- Convert reviewed editorial content to the Markdown format shown in the supplied reference.
- Validate an API response after a page publication.
- Do not use for public GitHub publishing, static-site deployment, or unauthorised content changes.

## Prerequisites

- Page API base path: `https://<target-host>/api/v1/pages` (for example `.com` or `.de`); use the installation explicitly selected by the user.
- Store the secret only as `WEBDELO_PAGES_SECRET` in the active process environment or the active Hermes profile's `.env`; never put it in `config.yaml`.
- The local reference `~/Downloads/page-api-integration-guide.md` documents the request contract when available; otherwise obtain the vendor guide. The base path has no list route; signed `GET /api/v1/pages/{id}` exports a page.
- Get explicit user approval for every create, update, or overwrite. Drafting and validation do not require approval.

## City-page export workflow

When given a `webdelo.page.export` JSON plus city copy, treat the export as a layout/media template and the city copy as the authority for city-specific text. Inspect the actual JSON recursively: text may live in `content` HTML, `data.expert_block`, nested `blocks`, metadata, and FAQ items; pictures may be HTML `<img>`, `[asset ...]`, `[image id=... lazy]`, `images[]`, or iframe embeds. Keep reusable company assets, CSS classes, layout, template references and valid links. Replace city-specific strings across **all** nested fields, breadcrumbs, alt text, map embeds and metadata; do not carry city-specific hero photos, Keyword Planner screenshots or unrelated geographic mockups into the new page. If new city imagery is not supplied, leave an explicit non-rendering TODO comment rather than a fake URL or mismatched image. Rebuild only locales for which translated copy is supplied; never relabel old locales with new city names. Remove or null original page/block IDs to avoid overwriting the source, and label the result a **draft** until an import contract is confirmed. Validate JSON parsing, block and FAQ counts, all target headings and paragraphs, image references, and absence of old-city residue before delivery. Do not publish without a separate explicit request and API contract.

## Markdown Contract

Use standard Markdown unless the API contract says otherwise:

```md
# H1

## H2

1. Ordered item
2. Ordered item

Paragraph text.

**Bold and italic emphasis.**

[Link label](https://example.com)
```

Preserve the exact approved wording, heading hierarchy, ordered-list numbering, links, and UTF-8 characters. Do not insert HTML, tracking code, credentials, or unpublished personal data.

## Procedure

1. Create the Markdown in a local draft file with `write_file`. Completion: H1 is unique, heading levels are sequential, and all links use absolute HTTPS URLs unless deliberately relative.
2. Review the draft with `read_file` and check links using the appropriate retrieval tool. Completion: the reviewed text is exactly the text intended for publication.
3. Confirm target installation hostname (the same API may exist on `.com` and `.de`), slug, and moderation/public choice with the user; the export's `source.installation_host` is not overridden by the earlier API example hostname.
4. Read the API contract: HMAC-SHA256 lowercase hex over `{unix_seconds}:{locale}:{slug}` keyed by the dedicated Page API secret. For GET export, put `timestamp, signature, locale, slug` in query parameters; for POST/PUT import, these are **top-level JSON** fields. Clock skew tolerance defaults to 60 seconds. Read the secret from environment or a local private credential file; never echo it or save a signed request to disk.
5. For create, send exactly one `POST /api/v1/pages` with `{timestamp, signature, locale, slug, sections:["base_info","blocks","meta"], update_mode:"full", auto_publish:false, envelope:<validated export JSON>}`. Use `auto_publish:true` only with explicit public-release approval. `POST` reads the new slug from `envelope.source.page_slug`, not just top-level `slug`; ensure both match. Never automatically retry a timed-out POST because it may have created a duplicate, and never use `PUT` against the template page ID.
6. Check `status`, `page_id`, `created`, `imported`, `skipped`, `warnings`, and `moderation` from the response. A non-empty `warnings` list needs investigation.
7. Signed `GET /api/v1/pages/{page_id}` using the new slug and locale, then verify returned ID, slug, locale, title, SEO meta, blocks, FAQ, and absence of the old city. In moderation the public URL may return 404; don't claim it is publicly live.

## Pitfalls

- `POST /api/v1/pages` without JSON-level timestamp/signature returns `401 UNAUTHORIZED`; bare `GET /api/v1/pages` is not a list endpoint (404). Authentication is **not** in headers and does **not** sign the raw body.
- The API secret may be present in a local `webdelo-key.txt` supplied by the user; read it in process memory without printing, and prefer the active profile secret environment when configured. Never commit request helpers together with credentials.
- Media referenced in `images[]` are re-downloaded server-side. Missing city-specific hero or Keyplanner images should remain omitted with a private TODO, never be replaced by assets for another city.
- **Domain isolation is not provided by this Page API.** The guide says locale status changes apply across every configured domain, and a page created against `.de` was subsequently exportable with the same ID from `.com`. If the user says content must exist *only* on `.de`, do not `PUT`/`auto_publish` multilingual content until a verified domain-scoped admin workflow or endpoint is available. Calling the `.de` host alone is not isolation.
- When the user supplies separate locale manuscripts, bind the actual paragraphs, headings and FAQ answers from those files to each HTML block. Do not commission new translations. Check user-provided links before publishing: a manuscript may contain unrelated `claude.ai` URLs where Webdelo service links were intended.
- For processed city pages, normalize the English hero to `IT Agency in <Toponym>` and SEO/OG title to `IT Agency in <Toponym>, Webdelo GmbH`. Normalize the German hero to `IT Agentur in <Toponym>` and SEO/OG title to `IT Agentur in <Toponym>, Webdelo GMBH` (preserve this exact capitalization). In the English contact block, use `In-person meeting in your city` without a trailing hyphen. Preserve the supplied wording in other fields and locales.
- For reuse of an existing page export as the **layout/media template**, match blocks by logical order/type but preserve the template's `images[]`, CSS/layout, `template-ref` IDs, and inline icons; source-page JSON contributes localized copy and metadata only. Remove any inherited city-specific iframe/photo/placeholder (even if embedded in HTML) rather than showing the template city on the target page. A source may have 21–23 blocks: insert a textless alignment slot when the old page omits Expert View, and exclude an extra chat widget while retaining the template's 22-block structure. Nested text lists may contain 0–7 rows or paragraphs; clone/remove only the template row shell so every supplied source text survives without importing source media. Before `PUT`, compare every media record against the template and scan the whole JSON for old-city references not present in the source. `PUT full` re-downloads media and rewrites selected sections, so take a signed GET backup of the exact target first.
- Do not trust old breadcrumb hrefs: some exports have wrong locale prefixes or missing parent links. Preserve page-96 breadcrumb markup, copy source labels, and rebuild home/locations/parent hrefs from the locale plus the German parent label slug (`ä→ae`, `ö→oe`, `ü→ue`, `ß→ss`).
- Domain-specific states cannot be implemented with Page API `auto_publish`: `true` marks all configured domains public and `false` marks all moderation for each imported locale. If requested statuses differ by domain, keep the prepared envelope local until an authenticated domain-scoped workflow is available. If the user explicitly permits hiding across *all* domains, `auto_publish:false` is a non-public substitute. Verify both a plain public URL and a cache-busted/no-cache URL: the origin may return 404 while a CDN still serves stale pre-moderation content on the plain URL. Report the exact API status as **Moderation** and disclose every stale-cache URL until it clears; never claim a plain cached URL is hidden.
- Treat a 2xx response as insufficient: always read back the exact target before reporting publication.
- Never perform bulk writes or overwrites from this skill without a separately enumerated, user-approved target list.

## Verification

- Draft formatting is reviewed locally.
- The API request is verified against current vendor documentation rather than inferred conventions.
- The returned page ID/URL is read back and matches the approved content.
- `git status` for every nearby repository remains free of this skill, secret, drafts, and generated request files.
