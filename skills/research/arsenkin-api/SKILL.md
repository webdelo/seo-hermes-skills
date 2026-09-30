---
name: arsenkin-api
description: "Use when calling ARSENKIN API for rank checks."
version: 0.1.0
author: Daniil Spara, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [arsenkin, seo, positions, google, yandex]
---

# ARSENKIN TOOLS API

Use ARSENKIN TOOLS for asynchronous one-off SEO tasks and the Projects API for saved-project rank collection. Never print or commit an API token.

## Credentials

Set the token outside the repository:

```sh
export ARSENKIN_API_TOKEN='…'
```

- **TOOLS API:** send `Authorization: Bearer <token>`.
- **Projects API:** send `X-Api-Token: <token>`.

## Endpoints

### TOOLS API

All methods are JSON `POST` requests with `Content-Type: application/json`.

| Purpose | Endpoint |
|---|---|
| Limits / active tasks | `https://arsenkin.ru/api/tools/info` |
| Create task | `https://arsenkin.ru/api/tools/set` |
| Check task | `https://arsenkin.ru/api/tools/check` |
| Get completed result | `https://arsenkin.ru/api/tools/get` |

Submit a one-off rank check with `tools_name: "positions"`. Required `data` fields are `queries`, `url`, `se`, and `format`. Google Desktop is `type: 11`, Google Mobile is `12`, and Yandex is `1`. Obtain valid Google region IDs from `https://arsenkin.ru/google_regions.csv`.

Tasks are asynchronous. Store the task ID, poll `/check` no more than once per five seconds, and use `/get` only after a terminal status. Respect the account limits: up to five concurrent tasks and 30 API requests per minute.

### Projects API

Base URL: `https://arsenkin.ru/api/projects/v1`

| Purpose | Endpoint |
|---|---|
| Inspect a project | `GET /projects/{project_id}` |
| Read stored positions | `GET /projects/{project_id}/positions` |
| Start a position collection | `POST /projects/{project_id}/positions/run` |

Before starting a collection, request `GET /projects/{project_id}` and verify the domain, enabled regions, keyword count, and current project status.

To launch a **full** manual collection for all active keywords and all enabled regions, send an empty JSON object:

```json
{}
```

Optional launch fields:

- `sagging_positions: true` — only declining phrases.
- `project_region_ids` — restrict to real region IDs in this project.
- `group_ids` or `keyword_ids` — restrict to real groups or phrases in this project.

A successful launch returns HTTP `202`. It means queued, not finished. Read the project again and follow `status_name`: `queue` → `ongoing` → `finished`. Then retrieve the new positions through the positions endpoint.

A `422 scan_not_started` response does not start or charge a scan. Report its `message`; common causes are an active scan, empty phrase selection, or insufficient owner limits. `403` indicates permission failure or an archived project.

## Python Example

```python
import json
import os
import urllib.request

TOKEN = os.environ["ARSENKIN_API_TOKEN"]
PROJECT_API = "https://arsenkin.ru/api/projects/v1"

def project_request(method, path, body=None):
    request = urllib.request.Request(
        PROJECT_API + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "X-Api-Token": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.status, json.load(response)

project_id = 12345
status, project = project_request("GET", f"/projects/{project_id}")
if project["data"]["status_name"] != "finished":
    raise RuntimeError("A collection is already active")

status, launched = project_request("POST", f"/projects/{project_id}/positions/run", {})
assert status == 202, launched
```

## Verification

For a one-off task, success requires a task ID, a terminal status, and a retrieved result. For project collection, success requires HTTP 202 and a read-back project state of `queue` or `ongoing`; report completion only after the status becomes `finished`.

## Sources

- https://help.arsenkin.ru/api
- https://help.arsenkin.ru/api/single-positions
- https://help.arsenkin.ru/projects-api
- https://arsenkin.ru/google_regions.csv
