#!/usr/bin/env python3
"""Retrieve verbatim prompts and fan-out queries from DataForSEO."""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MENTIONS_URL = "https://api.dataforseo.com/v3/ai_optimization/llm_mentions/search_mentions/live"
SCRAPER_URL = "https://api.dataforseo.com/v3/ai_optimization/chat_gpt/llm_scraper/live/advanced"
LOCATION_CODE = 2840
LANGUAGE_NAME = "English"
LANGUAGE_CODE = "en"
PLATFORM = "chat_gpt"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep Basic auth on the fixed DataForSEO origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, code, "redirect blocked", headers, fp)


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and value))


def encode_keyword(value: str) -> str:
    """Escape characters DataForSEO otherwise decodes in keyword fields."""
    return value.replace("%", "%25").replace("+", "%2B")


def fanout_values(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError("DataForSEO fan_out_queries have an unexpected shape")
    return value


def result_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    task = checked_task(response)
    result = task.get("result")
    if not isinstance(result, list):
        raise RuntimeError("DataForSEO result has an unexpected shape")
    if not result:
        return []
    if not isinstance(result[0], dict):
        raise RuntimeError("DataForSEO result has an unexpected shape")
    items = result[0].get("items")
    if items is None:
        return []
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise RuntimeError("DataForSEO items have an unexpected shape")
    return items


def checked_task(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError("DataForSEO response has an unexpected shape")
    if response.get("status_code") != 20000:
        raise RuntimeError(f"DataForSEO top-level status {response.get('status_code')}")
    tasks = response.get("tasks") or []
    if not isinstance(tasks, list):
        raise RuntimeError("DataForSEO tasks have an unexpected shape")
    if len(tasks) != 1:
        raise RuntimeError("DataForSEO response did not contain exactly one task")
    task = tasks[0]
    if not isinstance(task, dict):
        raise RuntimeError("DataForSEO task has an unexpected shape")
    if task.get("status_code") != 20000:
        raise RuntimeError(f"DataForSEO task status {task.get('status_code')}")
    return task


def request_json(url: str, payload: list[dict[str, Any]], login: str, password: str) -> dict[str, Any]:
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=240) as response:
            data = json.load(response)
            if not isinstance(data, dict):
                raise RuntimeError("DataForSEO response has an unexpected shape")
            return data
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"DataForSEO HTTP status {exc.code}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DataForSEO network error: {exc.reason}") from None
    except (TimeoutError, socket.timeout):
        raise RuntimeError("DataForSEO request timed out") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("DataForSEO returned malformed JSON") from None


def prepare_out(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if path.exists() and any(path.iterdir()):
        raise RuntimeError("output directory must be new or empty")
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)
    return path


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def read_input(path_text: str) -> str:
    with Path(path_text).expanduser().open("r", encoding="utf-8", newline="") as input_file:
        return input_file.read()


def history(query: str, out: Path, login: str, password: str) -> dict[str, Any]:
    collected: dict[str, list[str]] = {"question": [], "fan_out_queries": []}
    calls = []
    responses: dict[str, dict[str, Any]] = {}
    for scope in ("question", "fan_out_queries"):
        payload = [{
            "language_name": LANGUAGE_NAME,
            "location_code": LOCATION_CODE,
            "target": [{"keyword": encode_keyword(query), "search_scope": [scope], "match_type": "partial_match"}],
            "platform": PLATFORM,
            "order_by": ["ai_search_volume,desc"],
            "limit": 1000,
            "tag": scope,
        }]
        response = request_json(MENTIONS_URL, payload, login, password)
        task = checked_task(response)
        items = result_items(response)
        responses[scope] = response
        result_pages = task["result"]
        result_page = result_pages[0] if result_pages else {}
        if not isinstance(result_page, dict):
            raise RuntimeError("DataForSEO result has an unexpected shape")
        if scope == "question":
            collected[scope] = dedupe([
                value
                for item in items
                for value in [item.get("question")]
                if isinstance(value, str)
            ])
        else:
            collected[scope] = dedupe([
                fanout
                for item in items
                for fanout in fanout_values(item.get("fan_out_queries"))
            ])
        calls.append({
            "scope": scope,
            "top_level_status_code": response.get("status_code"),
            "task_status_code": task.get("status_code"),
            "cost": task.get("cost"),
            "records": len(items),
            "total_count": result_page.get("total_count", len(items)),
            "truncated": int(result_page.get("total_count") or len(items)) > len(items),
        })
    for scope, response in responses.items():
        write_json(out / f"raw-{scope}.json", response)
    write_json(out / "prompts.json", collected["question"])
    write_json(out / "fan_out_queries.json", collected["fan_out_queries"])
    return {
        "mode": "history", "input": query, "platform": PLATFORM,
        "location_code": LOCATION_CODE, "language": LANGUAGE_NAME,
        "prompts_count": len(collected["question"]),
        "fan_out_queries_count": len(collected["fan_out_queries"]),
        "truncated": any(call["truncated"] for call in calls),
        "calls": calls,
    }


def scrape(prompt: str, out: Path, login: str, password: str) -> dict[str, Any]:
    payload = [{
        "keyword": encode_keyword(prompt), "location_code": LOCATION_CODE,
        "language_code": LANGUAGE_CODE, "force_web_search": True,
        "tag": "user_exact_prompt",
    }]
    response = request_json(SCRAPER_URL, payload, login, password)
    task = checked_task(response)
    results = task.get("result")
    if not isinstance(results, list):
        raise RuntimeError("DataForSEO result has an unexpected shape")
    result = results[0] if results else {}
    if not isinstance(result, dict):
        raise RuntimeError("DataForSEO result has an unexpected shape")
    fanouts = dedupe(fanout_values(result.get("fan_out_queries")))
    write_json(out / "raw-scrape.json", response)
    write_json(out / "prompt.json", [prompt])
    write_json(out / "fan_out_queries.json", fanouts)
    return {
        "mode": "scrape", "input": prompt, "platform": "ChatGPT LLM Scraper",
        "location_code": LOCATION_CODE, "language": LANGUAGE_CODE,
        "force_web_search": True, "prompts_count": 1,
        "fan_out_queries_count": len(fanouts),
        "top_level_status_code": response.get("status_code"),
        "task_status_code": task.get("status_code"),
        "cost": task.get("cost"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    p_history = sub.add_parser("history")
    p_history.add_argument("--input-file", required=True)
    p_history.add_argument("--out", required=True)
    p_scrape = sub.add_parser("scrape")
    p_scrape.add_argument("--input-file", required=True)
    p_scrape.add_argument("--out", required=True)
    args = parser.parse_args()
    login, password = os.getenv("DFS_LOGIN"), os.getenv("DFS_PASSWORD")
    if not login or not password:
        print("blocked: DFS_LOGIN and DFS_PASSWORD are required", file=sys.stderr)
        return 2
    try:
        out = prepare_out(args.out)
        user_input = read_input(args.input_file)
        if not user_input:
            raise RuntimeError("input file is empty")
        summary = history(user_input, out, login, password) if args.mode == "history" else scrape(user_input, out, login, password)
        write_json(out / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
