# Input and output schema

All relative paths are resolved from the directory that contains the task spec.

## Google Ads file

Required top-level shape:

```json
{
  "request": {
    "geoTargetConstants": ["geoTargetConstants/2276"],
    "language": "languageConstants/1001",
    "keywordPlanNetwork": "GOOGLE_SEARCH"
  },
  "response": {
    "results": []
  }
}
```

Every matched result requires `text` and `keywordMetrics.monthlySearchVolumes` with exactly 12 unique consecutive `{year, month}` entries. `closeVariants` is optional. The table consumes `avgMonthlySearches`, `competition`, `competitionIndex`, `lowTopOfPageBidMicros`, and `highTopOfPageBidMicros`. Numeric API values may be JSON non-negative integers or digit-only strings; booleans, floats, signed strings, and formatted numbers are rejected. `expected_keyword_planner` in the spec must equal the three saved request fields exactly.

## Comparison file

```json
{
  "records": [
    {
      "city": "Beispielstadt",
      "topic": "seo",
      "monthly_searches": 100,
      "low_top_of_page_bid_micros": "1000000",
      "high_top_of_page_bid_micros": "2000000",
      "organic_total": 2,
      "counts": {"local": 1, "aggregator": 1},
      "top": [
        {"rank": 1, "url": "https://example.org/a", "category": "local"},
        {"rank": 2, "url": "https://example.org/b", "category": "aggregator"}
      ]
    }
  ]
}
```

Required record fields are `city`, `topic`, `monthly_searches`, both bid fields, `organic_total`, `counts`, and `top`. Allowed categories are `local`, `aggregator`, `franchise`, `informational`, and `other`. Counts must be non-negative exact integers, must sum to `organic_total`, and must equal categories reconstructed from `top`. `top` length must equal `organic_total`. Bid bounds must both be exact non-negative integers with low not exceeding high, or both be explicit `null` when the source returned no range; a partial range is rejected.

## Locale objects

The spec must contain exactly `ru`, `de`, and `en`. Each locale requires both titles, both introductions, 4 and 5 headers respectively, all four competition labels, `missing`, exact keyword labels, exact comparison keys, all five site-type labels, one model-authored takeaway per city, and explicit `thousands` and `decimal` separators. Every displayed value must be a non-empty string except `thousands`, which may be empty. `<strong>` is rejected in every displayed field.

## Output

The output is `webdelo.local-seo.tables` version 1. It contains `period`, source path labels, and `locales.ru/de/en`. Every locale contains `first` and `second` `audit-table` payloads plus a source metric fingerprint. Both blocks always contain `data.spacing.padding_bottom: "!pb-22"`; all row cells are strings.
