---
name: webdelo-local-seo-tables
description: Build two verified frequency tables for Webdelo city pages.
version: 0.1.0
author: Spara Daniil, Hermes Agent
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [webdelo, local-seo, keyword-frequency, google-ads, xmlriver]
    related_skills: [webdelo-local-seo-pages, google-ads-keyplanner, xmlriver-semantics]
---

# Webdelo Local SEO Tables

Build the two `audit-table` datasets used by Webdelo local SEO pages from saved Google Ads Keyword Planner metrics and a verified city-comparison dataset. Code performs deterministic metric mapping and formatting; a language model writes the locale-specific introductions and short conclusions supplied in the spec.

## When to Use

- A local SEO page needs the standard two frequency/research tables.
- The same verified metrics must be reproduced consistently in RU, DE, and EN.
- Do not use to invent keywords, prose, traffic forecasts, or missing API values.

## Inputs

1. A raw Keyword Planner historical-metrics response with its request settings and returned results.
2. A comparison JSON whose records contain city, topic, monthly searches, bid micros, organic result count, and classified site-type counts from saved XMLRiver evidence.
3. A task spec defining the expected Keyword Planner geography/language/network, one to seven ordered city-qualified keywords, ordered comparison cities, and locale copy for `ru`, `de`, and `en`.

All file paths in the spec are resolved relative to the spec file. Start from `references/spec-example.json`; field-level source contracts are in `references/input-schema.md`.

Locale copy must provide the two titles, two introductions, both header arrays, competition labels, missing-value label, first-table display labels, city display keys, site-type labels, and one AI-authored short conclusion per comparison city. Scripts must not generate the conclusions or translate them.

## Table Contract

### Table 1 — city-qualified commercial queries

Columns:

1. industry/query;
2. average monthly searches;
3. Google Ads competition plus index `/100`;
4. low–high top-of-page bid.

Use only `avgMonthlySearches`, `competition`, `competitionIndex`, `lowTopOfPageBidMicros`, and `highTopOfPageBidMicros` returned for the ordered keyword. Match normalized `text` and `closeVariants`; never silently pair a different query. Missing fields render as the locale's explicit “not available” label, never zero.

### Table 2 — one comparable SEO query across cities

Columns:

1. localized city/query key;
2. average monthly searches;
3. Google Ads top-of-page bid range;
4. classified composition of the saved organic results;
5. AI-authored short conclusion.

Site-type counts must sum to `organic_total`. Keep categories distinct: local service sites, aggregators/reviews, franchises, informational pages, and other pages. The conclusion may interpret the verified row but must not promise ranking, traffic, leads, or CPC.

## How to Run

Use `terminal(command="python3 <skill_dir>/scripts/build_tables.py tables-spec.json", timeout=120)`. Start from `references/spec-example.json`; the input and output schemas are documented in `references/input-schema.md`. The script writes the output path declared by the spec and prints a JSON summary with locale count, row counts, frequency range, CPC range, and derived 12-month period.

## Procedure

1. Collect an explicit city-qualified German keyword list through Keyword Planner. Declare the approved `geoTargetConstants`, `language`, and `keywordPlanNetwork` in `expected_keyword_planner`; for the current German workflow use Germany `2276`, German `1001`, and `GOOGLE_SEARCH`. Completion: save the raw request and response without editing values, and require the saved request to match the spec exactly.
2. Resolve every requested keyword by normalized returned `text` or `closeVariants`. Completion: exactly one metrics row maps to each requested keyword; ambiguous or missing matches block the table.
3. Build the comparison dataset from the same query intent across the approved city set. Join saved XMLRiver results with reviewed classifications and assert category totals equal actual result counts. Completion: no city row lacks source evidence.
4. Have the model write locale-specific introductions and concise row conclusions from the verified data. Keep identifiers and metrics exact. Completion: every comparison city has one conclusion in RU, DE, and EN.
5. Run `build_tables.py`. Completion: output has exactly two blocks per locale, 1–7 rows in table 1, the approved city count in table 2, string cells only, and `data.spacing.padding_bottom: "!pb-22"` in both blocks.
6. Insert the output into the fresh page-ID-100 structure without changing unrelated block fields. Preserve `type: "audit-table"` and the template's block placement.
7. Independently compare output metrics to raw evidence and semantically review all locale prose. Completion: all numbers round-trip; no source-language residue or unsupported claim remains.

## Formatting Rules

- Page ID `100` is the canonical formatting reference: use a space thousands separator and a decimal comma in RU, DE, and EN unless an approved replacement template explicitly changes them.
- Declare separators in every locale spec; never infer them from the machine locale or silently normalize existing values.
- Keep the euro sign and explicit low–high range. If either bid bound is missing, render the missing-value label instead of a partial range.
- Derive the period from returned `monthlySearchVolumes`; do not hardcode a calendar range from the run date.
- Preserve keywords and source identifiers exactly. Localize labels and explanations, not API tokens or query evidence.
- Use `<b>`, never `<strong>`, in supplied HTML introductions.

## Pitfalls

- `avgMonthlySearches` is a historical estimate, not clicks, impressions, city residents, or guaranteed traffic.
- Top-of-page bids are estimates, not actual CPC or cost per lead.
- Google may normalize hyphenated city names; inspect `closeVariants` before calling a result missing.
- A missing metric is not zero. Do not calculate a range from absent endpoints.
- Do not let a script write conclusions: deterministic code assembles data, while the model owns editorial interpretation.
- Do not reuse another region's city order, comparison scope, links, or conclusions.
- Do not restore the obsolete `!pb-[22rem]`; the canonical class string is `!pb-22`.

## Verification

Completion requires raw-source mapping for every row, normalized keyword uniqueness, exact source-setting match, twelve unique consecutive monthly periods, exact non-negative integer metrics without float truncation, complete bid ranges with low not exceeding high (or explicit absence of both bounds), category counts reconstructed from the classified organic results, identical underlying metrics across locales, locale-specific numeric formatting, three `ru/de/en` payloads, two `audit-table` blocks per locale, six total `!pb-22` values, no `<strong>` in any displayed field, and independent review of introductions and conclusions.

## References

- `references/spec-example.json` — complete portable task-spec example.
- `references/input-schema.md` — required Google Ads, comparison, locale, and output shapes.
