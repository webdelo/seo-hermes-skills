---
name: local-pages-plus-templates-de
description: Use when aligning Webdelo.de local-page templates.
version: 0.1.0
author: Spara Daniil, Hermes Agent
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [webdelo, locations, templates, localization, layout]
    related_skills: [webdelo-pages-api]
---

# Local Pages Plus Templates — DE

Align existing Webdelo.de IT/location pages to the user-approved German layout while preserving localized content and page identity. This is not the SEO city-research workflow: do not introduce Keyword Planner tables, SEO-only service templates, or a different page type during a layout correction.

## When to Use

- Repair RU/EN block order, spacing, template references and broken wrappers against the same page's approved DE version.
- Migrate an explicitly approved list of old location pages to a fresh approved location-page master.
- Do not use for other domains, inventing new city copy, or editing shared templates without separate permission.

## Prerequisites

- Load `webdelo-pages-api` for the signed API contract and credential handling.
- Use only `https://webdelo.de` for API requests and publication-status cells. Never use `auto_publish`, because it changes statuses across installations/domains.
- Receive an explicit target ID, approved reference ID/locale, target locales and permission to update. If the reference is unclear, export both candidates before asking.
- Use CLI/direct HTTP and an HTML5 parser, not browser automation. Keep raw backups, corrections, response evidence and readback in a dedicated work directory.
- Resolve `WEBDELO_PAGES_SECRET` in process memory; never include credentials or signed URLs in skills, logs, exports or Git.

## Reference Selection

A page number is not a layout specification. Verify its identity and actual block inventory first. Page 89 (`hessen`) is a general IT/location page; page 98 has been a Stuttgart SEO page with a different structure. Do not replace a 28-block IT page with a 20-block SEO shell merely because an earlier message named 98. A later user clarification overrides the earlier reference.

For same-page localization repairs, the current German version is the layout authority; RU/EN remain the authorities for their own wording and media. Read fresh exports every time: counts and template IDs below are observations, not permanent constants.

## Procedure

1. Signed-GET the exact target and the approved reference. Save immutable backups. Assert `source.installation_host`, `page_id`, slug and locale coverage. Inventory top-level and nested types, positions, IDs, template IDs, hidden flags, spacing, content and media.
2. Fetch plain and cache-busted public URLs on `.de` for each relevant locale. Parse with an HTML5 tree builder, such as BeautifulSoup plus html5lib. Record section order/classes, ancestor wrappers, nesting depth, review component types, headings and repeated components. Use the interpreter that actually has these dependencies.
3. Map blocks by semantic purpose, not just their names or numeric positions. Review blocks can have the same parent type while their children are `reviews-slider` versus `google-reviews`; preserve each complete localized block and move its existing locale-specific ID to the correct position.
4. Diagnose page HTML and expanded Templates together. A raw fragment may intentionally leave wrappers open for the next template. Do not auto-close it or copy a complete DE block into RU/EN before checking whether a localized template already supplies the remainder.
5. Preserve identity, unrequested locales, base information, metadata and media. For a layout correction, edit only the necessary block fields. Copy CMS spacing dictionaries from the approved DE counterpart, not guessed HTML margins. Preserve localized links and visible wording unless a missing label or fallback needs translation.
6. Match Hero's second-part template to the reference. In the observed IT layout, DE used template 12 whereas RU/EN incorrectly used SEO template 9. Preserve the DE opening wrappers and add the translated company-introduction label with its exact classes. Do not apply template 12 blindly to SEO pages.
7. Handle incomplete localized templates without changing shared assets: inspect the rendered result first. If only a fragment is missing, a page-local complete HTML fallback may be needed. Keep it in the same semantic slot and record why the raw representation differs. Never assume `template-ref.content` will render when the template locale is empty; it can be ignored.
8. Build a narrow partial envelope using each locale's actual `block_id`. Omit `images` and nested `blocks` unless those relations really need changing. Generate a recursive diff and assert every changed path is within the approved locales and fields. Assert all media by block ID, DE and metadata are unchanged.
9. Validate before writing: expected CMS block count; semantic type/order/positions; template IDs with individually documented fallback exceptions; nested review types; exact spacing; text/link preservation; no copied German body text; no duplicated template content. Use `<b>` for newly edited emphasis instead of introducing `<strong>`.
10. Fresh signed-GET immediately before PUT and abort if the source changed since the backup. Send `PUT /api/v1/pages/{target}` with `sections:["blocks"]`, `update_mode:"partial"` and explicit `status:{"webdelo.de":{"en":"public","ru":"public"}}` only for user-approved live corrections. Include only locales actually changed. Use their approved alternative statuses when not public.
11. Before first use of a deployment, confirm explicit status-map validation with a deliberately invalid status value AND an invalid envelope; require 422 with the expected status detail. Never use a valid envelope as a capability probe.
12. Save the write response; require no warnings and inspect the exact `moderation.applied` map. Signed-GET again and compare all intended sections against the expected result, including unchanged DE, metadata and media. Do not retry a write blindly after a timeout or failed readback.
13. Re-fetch plain and cache-busted public pages. Require HTTP 200 for public pages, matching DE section order/classes/parent wrappers, correct review order, and equal component counts. Detect the common defect where an unclosed SLA section captures every later section. Confirm each expected section belongs at the same nesting depth as DE.
14. Run an independent critic, resolve P0/P1, then deliver final JSON and a concise report. State that HTTP/HTML5 verification is not screenshot/pixel verification. Keep legacy unrelated content issues separate from the layout task.

## Known Template Integration Pitfalls

- Match the expanded page, not just raw JSON. Template 16 has supplied the standards timeline/cards for EN/RU while DE supplied those inline. Copying the complete DE standards HTML into the other locales would duplicate the component.
- Template 18 has had no EN output, leaving the EN SLA wrappers open. A localized complete SLA block matching the already-complete RU shell restores cards and closes the wrappers while keeping the reference slot. Recheck current template output before using this fallback again.
- Template 7 has had no RU output. Setting `content` on a `template-ref` did not render its fallback. Rendering the same localized grid as `type:"html"` in the existing slot worked without modifying the shared template. Retained `data.template_id:7` is provenance only, NOT an active template reference; disclose this exception.
- Page-local fallbacks do not receive later template updates. Record them and re-evaluate them on the next migration; remove a fallback only after the localized template actually renders correctly.
- Preserve link versus non-link states in copied region grids. Do not turn an unavailable city link into a fake published route.
- Do not reproduce accidentally duplicated DE paragraphs merely to equalize text-node counts. Preserve equivalent containers/classes and the distinct localized content; document the exception.
- Copy malformed inline SVG geometry from the trusted reference, not translated markup. Numeric SVG path data must never be localized.
- Domain status isolation is not independent per-domain content storage. The API shares block content; an explicit `.de` status map prevents other status changes, but cannot promise a separately published domain copy is unaffected. Do not call or change other-domain endpoints.

## Verification and Delivery

Save at minimum:
- Fresh source export and final multilingual readback JSON.
- Narrow partial envelope and recursive change manifest.
- Local assertions for unchanged DE/identity/meta/media and permitted changes.
- Write response showing only approved `.de` status cells.
- Plain/cache-busted public HTML and HTML5 layout report.
- Explicit fallback/representation exceptions and independent critic result.

Completion requires successful signed readback AND public expanded-layout checks. For a batch, process only the enumerated approved pages, sequentially, stopping at the first failure. Never migrate other pages merely because this skill was created.
