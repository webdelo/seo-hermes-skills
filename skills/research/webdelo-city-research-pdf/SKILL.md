---
name: webdelo-city-research-pdf
description: Build verified PDF reports for Webdelo city SEO research.
version: 0.1.0
author: Spara Daniil, Hermes Agent
license: Proprietary
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [webdelo, pdf, local-seo, research, reportlab]
    related_skills: [webdelo-local-seo-pages]
---

# Webdelo City Research PDF

Build a Russian-language PDF research report from the same verified data used by a Webdelo local SEO page. The PDF is a derived deliverable: never retype metrics or SERP rows and never make new network requests while rendering it.

## When to Use

- The user requests a PDF alongside a Webdelo city SEO page.
- The report must reproduce the page's two audit tables and saved XMLRiver results.
- Do not use for generic PDF editing, OCR, forms, or unrelated documents.

## Prerequisites

- Python 3.11+ with `reportlab` and `pypdf` in a virtual environment.
- A final reviewed page export containing exactly two Russian `audit-table` blocks.
- Saved XMLRiver JSON responses for every SERP section named in the report.
- A UTF-8 JSON spec with city, research scope, frequency/CPC ranges, period, report date, source paths, and output path.

## Input Contract

The spec has this shape:

```json
{
  "city": "Mannheim",
  "city_ru": "Мангейм",
  "scope": "города земли Баден-Вюртемберг",
  "frequency_range": "90–2 400",
  "cpc_range": "€1,20–€12,40",
  "ads_period": "сентябрь 2025 — август 2026",
  "report_date": "15 октября 2026",
  "page_json": "final-page.json",
  "xmlriver_files": ["serp-1.json", "serp-2.json"],
  "output": "mannheim-seo-report.pdf"
}
```

Resolve relative paths against the spec directory. `page_json` is the final reviewed envelope, not an earlier draft. Each XMLRiver file must contain `query`, `results`, collection metadata, and real returned rows.

## How to Run

Use `terminal(command="python3 <skill_dir>/scripts/build_report.py report-spec.json", timeout=300)`. The script renders a landscape A4 PDF with a white background, repeated table headers, Cyrillic-capable embedded fonts, page numbers, source captions, and one section per saved SERP.

## Procedure

1. Freeze the final RU page payload and raw evidence before PDF work. Completion: the two page tables and every report number are traceable to saved files.
2. Write the task-specific spec. Set city, regional comparison scope, request ranges, Google Ads period, report date, and XMLRiver files explicitly; never inherit scope text from a neighboring city. Completion: every spec path exists.
3. Run `scripts/build_report.py`. Completion: it exits zero and prints JSON with `status: ok`, output path, page count, two table titles, and all included queries.
4. Read the PDF metadata and extracted text. Completion: the city, scope, frequency range, CPC range, both table titles, and every XMLRiver query are present.
5. Rasterize at least the title page and one dense table/SERP page, then inspect them visually. Completion: white background, Cyrillic glyphs, no clipping, no overlapping rows, and legible URLs.
6. Compare PDF table row counts with the source JSON and compare every SERP row count with the corresponding raw response. Completion: no row was added, omitted, or silently truncated beyond the explicitly declared limit.
7. Deliver the PDF only after the local SEO page's independent critic has accepted the underlying evidence. The PDF cannot repair or supersede rejected source data.

## Content Rules

- Use the final RU payload's two `audit-table` objects verbatim for headers and cell values.
- State Google Ads geography, language, network, period, and that bids/search volumes are historical estimates, not guaranteed CPC or traffic.
- State XMLRiver query, city/location ID, country, language, device, collection timestamp, and actual returned result count.
- Say “up to 10” only when the saved response supports it; report the actual count when fewer rows were returned.
- Preserve source URLs and query spelling exactly. Do not normalize or translate identifiers in the PDF builder.
- Keep generation deterministic. A language model may write approved narrative before rendering, but the script only assembles verified strings and data.

## Pitfalls

- Do not build from a stale aggregate after a late page correction; rebuild from the latest reviewed envelope.
- Do not hardcode a developer's home path, macOS-only font, city, date, period, or regional scope.
- Do not use a font without Cyrillic coverage; extracted text passing does not replace raster inspection.
- Do not re-query XMLRiver or Google Ads during PDF rendering; that creates a report inconsistent with the page.
- Do not treat an empty metric as zero or invent a CPC bound.
- Do not claim a complete top 10 when the saved endpoint returned nine results.

## Verification

Completion requires: builder exit zero; parseable PDF; nonzero page count; extracted-text assertions for city, scope, both ranges, both table titles, and every query; source-to-PDF row-count checks; and visual review of representative rasterized pages. Record every limitation in the report rather than filling gaps with model-generated data.
