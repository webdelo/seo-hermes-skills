---
name: webdelo-city-json-rebuild
description: Rebuild Webdelo city-page JSON from the approved template.
version: 0.1.0
author: Spara Daniil, Hermes Agent
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [webdelo, json, city-pages, localization, qa]
    related_skills: [webdelo-pages-api]
---

# Webdelo City JSON Rebuild

Use this skill to modernize an existing Webdelo city or regional page export. The approved reference page supplies structure, Templates, styling, and media; the target page supplies its existing EN/RU/DE copy and page identity. Publish the skill only to a repository explicitly approved by the user; never publish working exports or credentials.

## When to Use

- Rebuild an old `webdelo.page.export` JSON to match the approved page-96 layout.
- Preserve supplied localized copy while normalizing selected H1 and metadata fields.
- Prepare and validate an update for an existing page ID.
- Do not use for writing new translations, inventing city copy, or creating duplicate pages.

## Inputs

- Approved template export: page 96, containing 22 blocks per locale and two Template blocks.
- Fresh signed export of the target page.
- Target page ID and slug.
- Locales: `en`, `ru`, and `de`.

Treat the template as authority for layout and media. Treat the target export as authority for page identity, localized text, metadata descriptions, FAQ content, and geographic labels.

## Rebuild Procedure

1. Read both JSON files and assert the template page ID is 96 and the target ID is the requested existing page. Completion: source ID and slug are known and unchanged.
2. Deep-copy page 96, then replace `source`, `sections.base_info`, and textual metadata with values from the target export. Never copy template-page identity into the result.
3. For every locale, map the old logical content into page 96's 22-block shell. Old exports may contain 21–23 blocks: insert a textless alignment slot when Expert View is absent and discard an extra obsolete chat widget.
4. Preserve from page 96:
   - block types, order, positions, and CSS/layout HTML;
   - `images[]` and reusable media;
   - both `template-ref` blocks and their template IDs;
   - icons and other presentation-only markup.
5. Copy from the target page only its supplied textual material: headings, paragraphs, lists, nested cards, expert copy, FAQ, breadcrumb labels, geographic copy, and localized metadata. Adapt row counts by cloning or removing only the template row shell; do not drop target text.
6. Rebuild breadcrumb hrefs instead of trusting old links. Use `/` for German home and `/en` or `/ru` for localized roots. Build parent slugs from the German parent label with `ä→ae`, `ö→oe`, `ü→ue`, `ß→ss` and ASCII hyphenation. Preserve a three-level breadcrumb when the source is regional; do not invent a city level.
7. Remove inherited template-city residue, city-specific iframe maps, photos, screenshots, and placeholders unless the same text legitimately exists in the target source. Never substitute imagery from another city when the correct image is absent.
8. Normalize only the approved fields:
   - EN H1: `IT Agency in <Toponym>`;
   - EN SEO and OG title: `IT Agency in <Toponym>, Webdelo GmbH`;
   - DE H1: `IT Agentur in <Toponym>`;
   - DE SEO and OG title: `IT Agentur in <Toponym>, Webdelo GMBH`;
   - remove the hyphen immediately after `In-person meeting in your city`, preserving any following explanation.
9. Determine the localized toponym from hero or breadcrumb text when `base_info.title` has a bad prefix or wrong-language value. Remove only known prefixes such as `State of`, `Land`, or `Земля`; do not rewrite the supplied copy elsewhere.
10. Remove imported `block_id` values recursively so template block IDs cannot target the wrong record. Keep the target page ID and slug.
11. Write a UTF-8 JSON file with `ensure_ascii=false` and indentation. Completion: the file parses and retains the exact target identity.

## Validation

Before any API write, prove all of the following:

- Result has exactly 22 blocks for EN/RU/DE.
- Block types and positions equal page 96.
- Template IDs are exactly the two expected IDs in the same order.
- Template media arrays equal page 96 where media must be preserved.
- Variable-length technology, marketing, SLA, and geographic lists contain every source item and no leftover template item.
- Target page ID and slug equal the fresh target export.
- EN/DE H1, SEO title, and OG title match the approved patterns exactly.
- The English contact phrase has no immediate trailing hyphen.
- Mentions of Stuttgart/Штутгарт do not exceed those already present in the target source.
- No source locale was replaced by generated or independently translated text.

Abort before upload on any failed assertion. Fix the mapping rule, rebuild from the fresh source export, and rerun the full validator rather than editing the generated result manually.

## API Handoff

Use the separate `webdelo-pages-api` skill for authentication, backup, `PUT`, moderation status, signed readback, and public/cache checks. Update the existing page by ID; never create a duplicate. Use `auto_publish:false` when the user approved a non-public update and report the resulting status precisely as **Moderation**.

## Pitfalls

- A successful JSON parse does not prove text completeness; compare nested row and paragraph counts with the source.
- A 2xx import response is not verification; signed readback is mandatory.
- CDN cache may temporarily serve an old public response after moderation. Check both plain and cache-busted URLs and report stale URLs explicitly.
- The Page API cannot assign different publication states per domain through `auto_publish`.
- Credentials never belong in this skill, JSON, scripts, logs, reports, or GitHub.

## Verification

The workflow is complete only when local validation passes, the API readback matches the rebuilt page, all three locales report Moderation when requested, and public/cache checks have been recorded. For a batch, process pages sequentially and stop at the first failed page.
