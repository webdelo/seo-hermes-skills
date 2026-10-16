---
name: webdelo-local-seo-pages
description: Use when creating multilingual Webdelo local SEO city pages.
version: 1.1.1
author: Spara Daniil, Hermes Agent
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [webdelo, local-seo, city-pages, multilingual, qa]
    related_skills: [webdelo-pages-api, google-ads-keyplanner, xmlriver-semantics]
---

# Webdelo Local SEO City Pages

Create or revise a multilingual Webdelo city landing page from a fresh page export, user-approved editorial instructions, and live local-search evidence. This skill governs city-specific copy, localization, rotation, and pre-upload QA; use `webdelo-pages-api` for signing, upload, and readback.

## When to Use

- A user asks to create, replace, or localize copy for an existing city SEO page.
- A user requires Google Ads Keyword Planner and organic-SERP/XMLRiver evidence inside the page.
- A user asks for Russian source copy plus German and English localizations.
- Do not use for a purely structural migration to a template with unchanged copy; use `webdelo-city-json-rebuild` instead.

## Procedure

1. Read the city-page instructions first. For an existing page, export the exact target with the signed Page API and save the untouched response. For a new local SEO page, download page ID `100` immediately before drafting and use that fresh export as the canonical structural authority. Do not rely on an older local copy. A fresh download is not proof that page 100 itself was updated: describe it as a fresh export unless a before/after comparison or explicit user statement confirms a revision. Record whether identity comes from a target export or must be created (`page_id: null`, requested slug, and locales).
2. Inspect the selected structural envelope programmatically. Record block count/order, shared versus city-specific blocks, FAQ positions, table/card schemas, metadata fields, image URLs, template references, and publication status. Build against that actual schema; do not assume a neighboring city page has the same block count.
3. Deep-copy the fresh approved reference for a new page. Preserve its block order, CSS/layout markup, SVG, template references, and media relations; clear inherited `block_id` values recursively. Copy shared conversion blocks verbatim and completely—including nested blocks and images—and replace text only in blocks the brief explicitly designates as city-specific. This prevents accidental shortening of case, team, testimonial, or consultation content.
4. Collect local evidence before writing copy. Query an explicit, city-qualified German keyword list through Keyword Planner with the locale, geography, and search network requested for the page. Capture average monthly searches, competition, and low/high top-of-page bid values from the saved raw response. Derive the stated 12-month coverage from the returned `monthlySearchVolumes`, rather than assuming a calendar period from the run date. Resolve returned terms to the submitted list by normalized punctuation/case and `closeVariants` before treating a requested metric as absent; Google can normalize a hyphenated toponym such as `Baden-Baden` to `Baden Baden`. Retrieve the specified organic results separately and preserve the query, country/language/device assumptions, collection period, and actual returned rank/count. Describe SERP composition from the received result set; when an endpoint returns fewer than the requested depth, say “up to N” only if true or state the actual count, rather than claiming a full top-N.
5. Choose a fresh keyword set and FAQ set by checking the instruction file's rotation log before drafting. Append only the actually used terms/questions after the page has passed QA. Never reuse an already logged city key or FAQ when unused alternatives exist.
6. Generate the Russian source as structured HTML/JSON text for the existing blocks with a language model, using the editorial instructions and verified evidence as inputs. Do not use scripts or templated string substitution to author the prose; reserve code for deterministic assembly, structural copying, metric placement, and QA. Use exact B2B terminology, preserve layout markup and approved links, and use `<b>` rather than `<strong>`. Place the verified search-demand and CPC range in all three required contexts when requested: the sources/methodology subheading, the Google Search block, and the Google Ads block. Label figures as historical estimates, state geography/language/network, and never imply a bid range guarantees traffic, clicks, or ranking.
7. Generate and semantically review native German and English localizations of the completed RU source, block for block. Localize metadata, titles, URLs, FAQs, alt text, and internal links for each locale; do not mechanically translate city names, website paths, or service links. Keep the numerical values, units, evidence limitations, and block semantics consistent across locales. Apply native number formatting per locale (for example, RU `1 300` and comma decimals, DE `1.300` and comma decimals, EN `1,300` and dot decimals).
8. Assemble the final three-locale envelope from the latest reviewed locale drafts, then validate that assembled file. If any locale draft is corrected after an earlier assembly, rebuild the envelope before validation and upload; do not upload an earlier aggregate.
9. Run a recursive validation before upload. Assert valid JSON; expected locales; no stale city name outside allowed shared assets; no `<strong>`; required data figures in all three mandated blocks in each locale using that locale's formatted volume/CPC values; expected table/FAQ/image counts; unique FAQ prompts; valid locale-specific metadata; and an HTTP `200` probe for every distinct absolute `images[].url` in the assembled envelope. A plausible storage filename is not evidence that a localized rendition exists. Traverse every user-visible string recursively—including nested card `title`, `content`, CTA, FAQ, table and metadata fields—and flag text in the wrong writing system or source language, excluding explicitly approved names and immutable image metadata. Extract and review rendered-text snippets for hero, Search, Ads, sources/methodology and every FAQ—not only raw JSON or counters. Assert that Search and Ads are non-identical substantive copy, FAQs have five distinct prompts and answers, the hero includes every required trust marker, and metadata values are stored under the target locale key rather than a copied `ru` key.
10. Perform an independent critic pass after structural validation and before creating PDFs or calling the Page API. Keep the critic separate from the drafting context and require it to inspect all 21 locale payloads for factual/evidence mismatches, nested source-language residue, malformed local grammar, claims beyond returned SERP depth, missing or duplicated FAQ prompts, forbidden generic B2B terms, and incorrect regional routes. Correct every P0/P1 finding, reassemble the envelope, and rerun the full validator; do not treat a drafting agent's self-report or a sidecar QA file as proof.
11. If the deliverable includes a city research PDF, build it from the final RU payload's two page tables and the saved XMLRiver SERP result sets rather than retyping evidence. Make city, regional comparison scope, query set, and source-methodology wording explicit per-report configuration; never reuse a neighboring city's scope string. Programmatically assert extracted PDF text contains the city, the correct regional scope, the query-volume and CPC ranges, and every named SERP query; check page count and raster-review a title page and a content page for Cyrillic glyphs, overlaps, clipping, and a white background.
12. When user approval covers the update, hand the validated envelope to `webdelo-pages-api`. Upload with the explicitly requested moderation/public status, then signed-readback the exact page and re-run the content assertions against the response. Report moderation accurately; do not claim a moderated page is public.

## Canonical Page-100 Layout Rules

Use a fresh signed export of page ID `100` as the final layout template for new Webdelo local SEO pages. Preserve its block order, HTML shells, media relations, and current `template-ref` structure. The canonical template mapping is:

- `data.template_id: 8` — Cases for local pages;
- `data.template_id: 9` — the reusable block immediately after Hero;
- `data.template_id: 10` — Service Card Grids / SEO services;
- `data.template_id: 11` — Consultation.

For every `en`, `ru`, and `de` locale, enforce the following spacing in the assembled envelope:

- each of the two `audit-table` blocks: `data.spacing.padding_bottom` must be the exact string `"!pb-22"`;
- the single advice block (`type: "services-2-col-grid"` with a non-empty `data.expert_block`): `data.spacing.padding_top` must be the exact string `"!pt-22"`;
- preserve the advice block's existing `data.spacing.padding_bottom`, normally `"!pb-0"`;
- do not put the service-to-advice gap into template `10`; the accepted implementation places it above the following advice block.

Never substitute `22rem`, numeric `22`, `"!pb-[22rem]"`, `"!pt-[22rem]"`, or inline CSS for these class strings. Before upload, recursively assert exactly two target audit tables and one target advice block per locale: six `!pb-22` values and three `!pt-22` values in total. After upload, perform a fresh signed readback and require the same counts and values; then check every public locale URL with a cache-busted direct HTTP request and confirm the rendered HTML contains both class strings.

For a narrow spacing correction on an existing page, begin from a fresh signed export, use a partial `blocks` update, preserve every other `data` key, and restrict the recursive diff to the named `padding_bottom` or `padding_top` leaf paths. Page ID `100` is the reference, not a write target unless the user explicitly includes it.

## Editorial Rules

- Treat Google Ads values as evidence for the named keyword set and collection settings, not citywide market totals. Use the original currency and distinguish search volume from clicks, impressions, and forecasts.
- In the methodology/source block, name the data source, geography, language, search network, period, and what each metric means. Cite source URLs in a visible source subsection when the page's design permits it.
- In the Google Search block, explain the organic result composition for the actual query; in the Google Ads block, connect the observed CPC range and competition to paid-search pressure without promising outcomes.
- Keep RU as the editorial source unless the user supplies another canonical manuscript. Do not publish machine-like translations; perform a semantic review of DE and EN before upload.
- Preserve user-approved city facts and claims exactly. New numerical claims need a source, metric type, geography, and period.

## Pitfalls

- Export the target immediately before edits, or download the designated reference immediately before creating a new page, and map its real blocks first — city pages may differ in block count and nesting, so copying a neighboring page or a stale template can silently drop current content.
- Do not call a reference page “updated” merely because it was downloaded again — a retrieval timestamp establishes freshness of the export, not a content change; verify a revision before making that claim.
- Preserve a reference page’s shared blocks verbatim unless the brief explicitly marks them for localization — abbreviated hand-copies lose nested copy, media relations, and conversion structure.
- Match requested Keyword Planner terms against both returned `text` and `closeVariants` after normalizing hyphens and case — treating Google’s normalized spelling as a missing result falsely erases usable metrics.
- Use only returned Keyword Planner bid fields and label unavailable values — absent fields are not zero and invented ranges undermine the evidence block.
- Insert a requested statistic in every named placement during source drafting, then assert it in every locale with locale-specific display values — a shared validator literal rejects correct localized separators or lets an unlocalized variant through.
- Rebuild the multilingual envelope after every late locale-level correction or media replacement, then rerun the recursive media probe — assembled JSON is a snapshot and otherwise uploads stale copy or the superseded asset URL.
- Validate required content counts from the target brief explicitly: total blocks, table rows, FAQ items, conclusions, and referenced image arrays — visually complete copy can still omit a CMS sub-block.
- Do not accept localization from structural counters alone — recursively inspect every visible nested string for source-language residue as well as FAQ duplication, Search/Ads collapse, hero trust omissions, and metadata under the wrong locale key; block schemas can pass while a nested card title or body remains untranslated.
- Describe XMLRiver depth from the actual returned set in page tables and reports — a request for top 10 can return nine organic results, so calling it a complete top 10 contradicts the displayed category totals.
- Parameterize PDF methodology and comparison geography by target city, then assert that the rendered title/source page contains the intended scope and no neighboring-city scope — a reused report template can retain factually wrong geography while all numeric checks pass.
- Preserve HTML table/card shells while replacing only text nodes — freehand reconstruction changes responsive layout and can break the CMS renderer.
- Generate editorial copy and translations with a model rather than string-generation scripts — programmatic prose produces rigid, repetitive localization; scripts belong to envelope assembly and repeatable QA.
- Require a second-pass critical review after deterministic assertions — fluent copy can still contain locality, grammar, or evidence defects.
- Inspect nested fields recursively for old toponyms — stale city names persist in breadcrumbs, metadata, FAQ, image alt text, iframe URLs, and cards even when headings are correct.
- Treat a successful import as provisional until signed readback confirms the exact locales, blocks, metadata, and moderation grid.
- Read back localized `images[].custom_properties.alt` values as well as image URLs — content-addressed media can be deduplicated to an existing record whose global metadata is retained, so a page import may not update alt text for every locale. Treat retained wrong-locale alt values as unresolved accessibility/SEO work and update the media record through the media-library workflow rather than claiming the page import fixed them.

## Verification

Completion requires a saved raw evidence response, final multilingual JSON, successful API readback with no unresolved warnings, and per-locale assertions for data placement, city identity, links, assets, and metadata. When a PDF was requested, completion also requires text extraction checks and at least one rendered-page visual review. Keep publication state separate from content correctness in the final report.
