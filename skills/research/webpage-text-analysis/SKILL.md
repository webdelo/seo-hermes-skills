---
name: webpage-text-analysis
description: "Use when extracting and analyzing webpage body text."
version: 0.1.0
author: matfeia2414g, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [content-extraction, webpage, text-analysis, seo]
    related_skills: []
---

# Webpage Text Analysis

Extract the meaningful article or landing-page text from raw HTML, then analyze only the extracted corpus. The extractor starts at the first heading matched by `//*[self::h1 or self::h2 or self::h3]`, preferring the first `h1` when one exists, and stops before related-content, recommendation, discussion, or comment blocks.

## When to Use

- Extract and analyze the main copy of an article, guide, category, service, or landing page.
- Preserve paragraphs, headings, lists, simple text containers, blockquotes, code blocks, captions, and table text.
- Exclude menus, media metadata, page chrome, related articles, recommendations, and comments.

Do not use for pages whose meaningful text appears only after client-side rendering, authenticated pages, or bulk crawling without explicit scope. Use direct HTTP only; do not start browser automation for this skill.

## Prerequisites

- Python 3.11+.
- Python package `lxml`.
- Network access to the target URL, unless analyzing a saved HTML file.

If `lxml` is unavailable, create a task-local virtual environment and install it there. Do not modify the system Python environment.

## How to Run

Resolve this skill's directory from the loaded skill metadata, then invoke its script through `terminal`:

```bash
python "<skill_dir>/scripts/extract_page_text.py" \
  --url "https://example.com/page" \
  --text-out page.txt \
  --json-out page.json
```

For saved HTML:

```bash
python "<skill_dir>/scripts/extract_page_text.py" \
  --html-file page.html \
  --base-url "https://example.com/page" \
  --text-out page.txt \
  --json-out page.json
```

Optional controls:

- `--start-xpath '//*[self::h1 or self::h2 or self::h3]'` changes the heading lookup.
- `--no-prefer-h1` uses the first matched heading instead of preferring `h1`.
- `--stop-token TOKEN` adds a site-specific stop marker; repeat as needed.
- `--timeout 30` and `--max-bytes 10000000` bound HTTP retrieval.

## Procedure

### 1. Retrieve the source

Run the extractor against the requested URL. Do not substitute search snippets or remembered copy for fetched HTML. If HTTP retrieval fails because of robots, authentication, bot protection, or JavaScript rendering, report that limitation instead of analyzing a different corpus.

Completion criterion: the JSON artifact records the requested source, final URL, HTTP status, and retrieval timestamp.

### 2. Confirm the start boundary

The canonical heading lookup is:

```xpath
//*[self::h1 or self::h2 or self::h3]
```

From these matches, use the first `h1`; if there is no `h1`, use the first matched `h2` or `h3`. Include that heading in the corpus and take eligible text in document order below it. If the user explicitly requires strict first-match behavior, pass `--no-prefer-h1`.

Completion criterion: `start.tag`, `start.text`, and `start.xpath` in JSON identify the chosen boundary. If no matching heading exists, stop and report `no_start_heading`; do not silently scrape the whole page.

### 3. Enforce the end boundary

Stop before the first structural block whose id, class, role, aria-label, data attributes, or heading text identifies related articles, recommendations, “read also,” discussion, comment forms, or comment lists. The script includes English, Russian, German, Spanish, French, and common widget markers such as `disqus`.

Add `--stop-token` when a site's marker is not covered. Treat the first stop match as a boundary, not as content. Do not continue scraping below it.

Completion criterion: JSON records either `stop.reason` and `stop.xpath` or the explicit fallback `end_of_document`.

### 4. Validate the corpus

Read the text and JSON artifacts before analysis. Confirm:

- paragraphs and subsequent headings are present;
- list items are preserved as list items;
- tables retain row and cell structure;
- simple-text `div` elements are included without duplicating descendant paragraphs;
- `img`, `video`, `audio`, `source`, and `track` metadata is absent;
- image `alt` and media labels were not copied;
- related-article cards, comment text, forms, navigation, and footer copy are absent.

If the corpus is suspiciously short, inspect `warnings`, the start heading, and the stop match. Retry once with a justified site-specific stop token or saved raw HTML; never weaken all boundaries merely to increase word count.

Completion criterion: the selected blocks form one coherent main-content sequence and excluded content is not present.

### 5. Analyze only the verified extraction

Follow the user's requested analysis dimensions. If none are given, return:

1. page topic and search/user intent;
2. concise outline of the actual heading structure;
3. key claims, entities, facts, and offers stated in the text;
4. coverage gaps and unanswered user questions;
5. repetition, vague passages, and structural problems;
6. evidence/trust weaknesses, separating missing support from falsehood;
7. prioritized content improvements with references to exact extracted passages.

Do not analyze absent layout, images, video, metadata, links, schema, or technical SEO signals from this corpus. Label inferences as inferences. Quote only text that exists in the extraction.

Completion criterion: every content finding is traceable to the extracted corpus, and limitations are stated.

## Output Contract

The script writes:

- plain text with headings, list markers, and tab-separated table cells;
- JSON with retrieval metadata, start/stop boundaries, ordered typed blocks, counts, warnings, and the complete extracted text.

Report extraction diagnostics before analysis:

```text
Source: <final URL>
Start: <tag + heading text>
Stop: <reason or end_of_document>
Blocks: <count>; words: <count>
Warnings: <none or list>
```

## Pitfalls

- The XPath is a start-boundary method, not proof that the chosen heading belongs to the main article. Validate its text.
- A page may contain a modal or header `h1` before the article. Use saved HTML plus a narrower `--start-xpath` only when evidence supports it.
- Generic words such as “more” or “news” are not safe stop markers. Add site-specific tokens only when they identify a structural boundary.
- `div` text is included only when the container has no descendant block element; this prevents parent/child duplication.
- Table cells are emitted through their table block, not again as standalone text.
- Hidden, navigation, form, footer, and media subtrees are skipped.
- HTTP source extraction cannot recover text rendered exclusively by JavaScript.

## Verification

Before delivering an analysis, verify:

- [ ] The exact canonical XPath was used unless the user approved a narrower selector.
- [ ] The selected start is an `h1`, or the JSON explains the `h2`/`h3` fallback.
- [ ] No whole-page fallback occurred after `no_start_heading`.
- [ ] The stop boundary precedes related articles/comments when such a block exists.
- [ ] Paragraphs, lists, simple-text divs, and tables are represented.
- [ ] No image/video/audio alt or metadata text appears.
- [ ] The analysis cites only the extracted corpus.
- [ ] Text and JSON artifacts are retained when reproducibility matters.
