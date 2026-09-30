---
name: google-ads-keyplanner
description: Use Webdelo’s Google Ads Key Planner access.
version: 0.1.0
author: Spara Daniil, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Google Ads, Key Planner, SEO, service account]
---

# Webdelo Google Ads Key Planner

This skill documents the existing Webdelo Google Ads access workflow; it does not create a new OAuth client or service account. The ready implementation uses `webdelo@fedorov.iam.gserviceaccount.com` to request Keyword Planner historical metrics for explicit keyword lists.

## When to Use

- Use when querying Google Ads Keyword Planner historical metrics with the Webdelo service account.
- Use when checking the existing service-account setup or explaining required credentials.
- Do not use for Google Workspace data or for creating/editing Ads campaigns.

## Prerequisites

1. Read `README.md`. The private service-account JSON must be downloaded separately and never placed in Git or chat.
2. The active `$HERMES_HOME/.env` must contain `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_ADS_CUSTOMER_ID`. The JSON must belong to `webdelo@fedorov.iam.gserviceaccount.com`.
3. The Python environment must contain `google-auth`. Verify without exposing secrets: `terminal(command="python3 -c 'from google.oauth2 import service_account; print(\"google-auth available\")'", timeout=30)`.
4. The service account must have access to the target Google Ads account, and the API project must have an eligible developer token. See `README.md`.

## Procedure

1. Start from the existing implementation at `$HERMES_HOME/google_ads_service_account_siding_metrics.py`; do not recreate its authentication flow. Completion: the source uses the service-account credential file and the `adwords` OAuth scope.
2. For a new research task, create a task-specific copy rather than editing the baseline. Change only the keyword list, locale constants, output filename, and explicitly required API version. Completion: original script remains unchanged and the task copy names its output file.
3. Run the task copy through `terminal(command="python3 /path/to/task_metrics.py", timeout=120)`. Completion: it reports `SERVICE_ACCOUNT_METRICS_COMPLETE` and names the saved JSON output.
4. Read the saved JSON with `read_file` before reporting metrics. Completion: result count and every reported number are taken from the response, not inferred.

## Current Scope

The existing implementation calls `generateKeywordHistoricalMetrics` with explicit keywords, English (`languageConstants/1000`), United States (`geoTargetConstants/2840`), and `GOOGLE_SEARCH_AND_PARTNERS`. It returns monthly history, average monthly searches, competition, competition index, and top-of-page bid ranges when supplied by Google.

It is not a generic keyword-idea generator. Add `generateKeywordIdeas` only when that separate capability is requested and test it against the configured account.

## Pitfalls

- The service-account JSON key authenticates the request but does not itself authorize Google Ads account access; the service-account email must be added in Google Ads **Admin → Access and security**.
- A developer token is required by Google Ads API. Its access level and permissible use must allow live keyword research.
- Customer IDs contain 10 digits; omit hyphens in API paths.
- Do not treat missing metrics as zero. Google may omit fields or return no result for a term.
- Never print, paste, commit, or upload the JSON key, developer token, OAuth tokens, or `.env` contents.

## Verification

- Verify the credential file is present and that its JSON `client_email` is exactly `webdelo@fedorov.iam.gserviceaccount.com` without outputting its private key.
- A successful live run saves a JSON response and reports a non-negative number of results.
- Before relying on a new target account, inspect API errors from the saved response and resolve authorization, developer-token, or customer-ID failures explicitly.
