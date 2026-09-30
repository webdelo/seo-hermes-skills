# SEO Hermes Skills

Reusable Hermes skills for Webdelo SEO workflows.

## Bonadomus SEO API

`skills/research/bonadomus-seo-api/SKILL.md` documents how to read and safely update catalog-page SEO metadata and editorial HTML on Bonadomus. It includes the approved city-page editorial layout based on `/dania-beach`.

## Google Ads Key Planner

`skills/research/google-ads-keyplanner/SKILL.md` documents the existing Webdelo service-account workflow for Google Ads Keyword Planner historical metrics. Its `README.md` explains how to download the JSON key separately; no credentials are committed to this repository.

### Admin setup

An administrator must create a personal access token in **Bonadomus admin → IDX → SEO API → Tokens**. Grant only the required ability:

- `seo:read` — inspect pages and templates;
- `seo:write` — update page metadata and editorial blocks;
- `seo:templates` — update shape-wide templates.

Keep the token outside this repository and provide it to the active process as `BONADOMUS_SEO_API_TOKEN`. Tokens must never be committed, included in skills, or pasted into chat.
