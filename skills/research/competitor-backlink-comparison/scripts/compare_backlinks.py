#!/usr/bin/env python3
"""Compare exact landing-page backlinks with Ahrefs and DataForSEO.

The aggregation and rendering functions are pure/testable. Network collection is
kept behind injectable request functions and is never used by the test suite.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

AHREFS_BASE = "https://api.ahrefs.com/v3/"
DFS_BASE = "https://api.dataforseo.com/v3/"
CREDENTIAL_NAMES = ("AHREFS_API_KEY", "DFS_LOGIN", "DFS_PASSWORD")
DEFAULT_ROW_LIMIT = 1000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirect refused", headers, fp)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--spec", required=True, type=Path, help="JSON comparison specification")
    result.add_argument("--out", required=True, type=Path, help="new or empty output directory")
    result.add_argument("--from-cache", type=Path, help="directory containing api-cache.json; performs no API calls")
    return result


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("Active HERMES_HOME/.env permissions must be 0600")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in CREDENTIAL_NAMES or name in values:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[name] = value
    return values


def load_credentials(environ: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Load secrets from the process first, then the active HERMES_HOME only."""
    env = os.environ if environ is None else environ
    loaded = {name: env.get(name, "") for name in CREDENTIAL_NAMES}
    missing = [name for name, value in loaded.items() if not value]
    if missing:
        hermes_home = env.get("HERMES_HOME", "")
        file_values = _parse_env_file(Path(hermes_home) / ".env") if hermes_home else {}
        for name in missing:
            if file_values.get(name):
                loaded[name] = file_values[name]
    missing = [name for name, value in loaded.items() if not value]
    if missing:
        # Names are safe; values are deliberately never interpolated.
        raise ValueError("Missing required credentials: " + ", ".join(missing))
    return loaded


def _request_json(request: Request, timeout: int = 30) -> Any:
    if urlsplit(request.full_url).scheme != "https":
        raise ValueError("API requests require HTTPS")
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"API request failed with HTTP status {exc.code}") from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("API request failed without a usable JSON response") from None


def _ahrefs_get(path: str, params: Mapping[str, Any], key: str,
                transport: Callable[[Request], Any] = _request_json) -> Any:
    query = urlencode({**params, "output": "json"})
    request = Request(AHREFS_BASE + path + "?" + query, headers={"Authorization": "Bearer " + key})
    return transport(request)


def _dfs_post(path: str, tasks: List[Mapping[str, Any]], login: str, password: str,
              transport: Callable[[Request], Any] = _request_json) -> Any:
    token = base64.b64encode((login + ":" + password).encode("utf-8")).decode("ascii")
    request = Request(
        DFS_BASE + path,
        data=json.dumps(tasks).encode("utf-8"),
        headers={"Authorization": "Basic " + token, "Content-Type": "application/json"},
        method="POST",
    )
    return transport(request)


def _validate_dfs_response(response: Any) -> None:
    if not isinstance(response, dict):
        raise RuntimeError("DataForSEO returned a malformed response")
    status_code = response.get("status_code")
    status_message = response.get("status_message")
    if not isinstance(status_code, int) or not isinstance(status_message, str):
        raise RuntimeError("DataForSEO response is missing status_code or status_message")
    if not 20000 <= status_code < 30000:
        raise RuntimeError(f"DataForSEO top-level error (status code {status_code})")
    tasks = response.get("tasks")
    if not isinstance(tasks, list):
        raise RuntimeError("DataForSEO response is missing tasks")
    for task in tasks:
        if not isinstance(task, dict):
            raise RuntimeError("DataForSEO returned a malformed task")
        task_code = task.get("status_code")
        task_message = task.get("status_message")
        if not isinstance(task_code, int) or not isinstance(task_message, str):
            raise RuntimeError("DataForSEO task is missing status_code or status_message")
        if not 20000 <= task_code < 30000:
            raise RuntimeError(f"DataForSEO task error (status code {task_code})")


def _items_from_response(response: Any) -> List[Dict[str, Any]]:
    if isinstance(response, dict):
        for direct_key in ("backlinks", "items"):
            value = response.get(direct_key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        tasks = response.get("tasks")
        if isinstance(tasks, list):
            rows: List[Dict[str, Any]] = []
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                for result in task.get("result") or []:
                    if isinstance(result, dict) and isinstance(result.get("items"), list):
                        rows.extend(row for row in result["items"] if isinstance(row, dict))
            return rows
    return []


def _summary_from_dfs(response: Any, target: str) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    for task in response.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        for result in task.get("result") or []:
            if not isinstance(result, dict):
                continue
            items = result.get("items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_target = item.get("target") or item.get("url")
                    if item_target == target:
                        return item
            if result.get("target") == target:
                return result
    return {}


def _dr_from_response(response: Any) -> Optional[float]:
    if not isinstance(response, dict):
        return None
    candidates: List[Any] = [response.get("domain_rating")]
    for key in ("domain_rating", "metrics"):
        value = response.get(key)
        if isinstance(value, dict):
            candidates.append(value.get("domain_rating"))
    for candidate in candidates:
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            return candidate
    return None


def _canonical_domain(value: str) -> str:
    if value != value.strip() or not re.fullmatch(
        r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*",
        value,
    ):
        raise ValueError("Spec focal_domain must be a plain hostname without scheme, path, query, port, or whitespace")
    canonical = value.lower()
    return canonical[4:] if canonical.startswith("www.") else canonical


def validate_spec(spec: Any) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("Spec must be a JSON object")
    focal = spec.get("focal_domain")
    clusters = spec.get("clusters")
    if not isinstance(focal, str) or not focal:
        raise ValueError("Spec focal_domain must be a nonempty string")
    canonical_focal = _canonical_domain(focal)
    if not isinstance(clusters, dict) or not clusters:
        raise ValueError("Spec clusters must be a nonempty object")
    target_count = 0
    target_domains = set()
    for name, urls in clusters.items():
        if not isinstance(name, str) or not name or not isinstance(urls, list) or not urls:
            raise ValueError("Every cluster must have a name and a nonempty URL array")
        target_count += len(urls)
        for url in urls:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if not parsed or parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("Every cluster entry must be an absolute HTTP or HTTPS URL")
            domain = parsed.hostname.lower()
            target_domains.add(domain[4:] if domain.startswith("www.") else domain)
    if target_count > 1000:
        raise ValueError("Spec supports at most 1000 target URLs")
    if len(target_domains) > 100:
        raise ValueError("Spec supports at most 100 unique target domains")
    row_limit = spec.get("row_limit", DEFAULT_ROW_LIMIT)
    if not isinstance(row_limit, int) or isinstance(row_limit, bool) or not 1 <= row_limit <= 1000:
        raise ValueError("row_limit must be an integer from 1 to 1000")
    return {**spec, "focal_domain": canonical_focal}


def target_entries(spec: Mapping[str, Any]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    seen = set()
    for cluster, urls in spec["clusters"].items():
        for url in urls:
            if url in seen:
                raise ValueError(f"Target URL appears more than once: {url}")
            seen.add(url)
            entries.append({"cluster": cluster, "url": url, "domain": (urlsplit(url).hostname or "").lower()})
    return entries


def collect_live(spec: Mapping[str, Any], credentials: Mapping[str, str],
                 ahrefs_transport: Callable[[Request], Any] = _request_json,
                 dfs_transport: Callable[[Request], Any] = _request_json) -> Dict[str, Any]:
    """Collect bounded exact-URL data. Callers must approve paid calls first."""
    spec = validate_spec(spec)
    entries = target_entries(spec)
    urls = [entry["url"] for entry in entries]
    domains = sorted({entry["domain"] for entry in entries} | {spec["focal_domain"].lower()})
    limit = spec.get("row_limit", DEFAULT_ROW_LIMIT)
    collected_at = datetime.now(timezone.utc).isoformat()

    ratings: Dict[str, Dict[str, Any]] = {}
    for domain in domains:
        response = _ahrefs_get(
            "site-explorer/domain-rating",
            {"target": domain, "date": collected_at[:10]},
            credentials["AHREFS_API_KEY"], ahrefs_transport,
        )
        ratings[domain] = {"domain_rating": _dr_from_response(response)}

    ahrefs_rows: Dict[str, List[Dict[str, Any]]] = {}
    for url in urls:
        response = _ahrefs_get(
            "site-explorer/all-backlinks",
            {
                "target": url,
                "mode": "exact",
                "history": "live",
                "aggregation": "all",
                "limit": limit,
                "select": "url_from,url_to,first_seen_link,title,anchor,link_type,is_spam,page_type_source,is_content,is_dofollow,root_name_source",
            },
            credentials["AHREFS_API_KEY"], ahrefs_transport,
        )
        ahrefs_rows[url] = _items_from_response(response)

    dfs_summary_response = _dfs_post(
        "backlinks/bulk_pages_summary/live",
        [{"targets": urls}], credentials["DFS_LOGIN"], credentials["DFS_PASSWORD"], dfs_transport,
    )
    _validate_dfs_response(dfs_summary_response)
    dfs_summaries = {url: _summary_from_dfs(dfs_summary_response, url) for url in urls}
    dfs_rows: Dict[str, List[Dict[str, Any]]] = {}
    for url in urls:
        response = _dfs_post(
            "backlinks/backlinks/live",
            [{"target": url, "mode": "as_is", "limit": limit}],
            credentials["DFS_LOGIN"], credentials["DFS_PASSWORD"], dfs_transport,
        )
        _validate_dfs_response(response)
        dfs_rows[url] = _items_from_response(response)

    return {
        "collected_at": collected_at,
        "ahrefs": {"domain_ratings": ratings, "backlinks": ahrefs_rows},
        "dataforseo": {"page_summaries": dfs_summaries, "backlinks": dfs_rows},
    }


def _source_url(row: Mapping[str, Any]) -> str:
    for key in ("url_from", "source_url", "url", "referring_page_url"):
        if isinstance(row.get(key), str):
            return row[key]
    return ""


def _target_url(row: Mapping[str, Any]) -> str:
    for key in ("url_to", "target_url", "target"):
        if isinstance(row.get(key), str):
            return row[key]
    return ""


def donor_domain(row: Mapping[str, Any]) -> str:
    explicit = row.get("root_name_source") or row.get("domain_from") or row.get("referring_domain")
    value = explicit if isinstance(explicit, str) else (urlsplit(_source_url(row)).hostname or "")
    value = value.lower().rstrip(".")
    return value[4:] if value.startswith("www.") else value


def classify_ahrefs_link(row: Mapping[str, Any]) -> str:
    if row.get("is_spam") is True:
        return "spam"
    provider_type = str(row.get("page_type_source") or "").lower()
    if re.search(r"(?:profile|member|author)", provider_type):
        return "profile"
    if row.get("is_content") is True or "/article" in provider_type or "article" in provider_type:
        return "article"
    if re.search(r"(?:homepage|\bhome\b)", provider_type):
        return "home"
    url = _source_url(row)
    parsed = urlsplit(url)
    haystack = " ".join([parsed.hostname or "", parsed.path, str(row.get("title") or "")]).lower()
    if re.search(r"(?:casino|poker|betting|buy[-_ ]?links?|payday|viagra|adult)", haystack):
        return "spam"
    path = parsed.path.rstrip("/").lower()
    if path in ("", "/"):
        return "home"
    if re.search(r"/(?:user|users|profile|profiles|member|members|author|authors)(?:/|$)", path):
        return "profile"
    if re.search(r"/(?:blog|news|article|articles|post|posts|guide|guides)(?:/|$)", path):
        return "article"
    return "other"


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def count_new_links(rows: Iterable[Mapping[str, Any]], now: datetime) -> Dict[str, int]:
    now = now.astimezone(timezone.utc)
    counts = {"days_365": 0, "days_183": 0}
    seconds = {"days_365": 365 * 86400, "days_183": 183 * 86400}
    for row in rows:
        first_seen = _parse_timestamp(row.get("first_seen_link") or row.get("first_seen"))
        if first_seen is None:
            continue
        age = (now - first_seen).total_seconds()
        if age < 0:
            continue
        for key, maximum in seconds.items():
            if age <= maximum:
                counts[key] += 1
    return counts


def _unique_observed_targets(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    return sorted({_target_url(row) for row in rows if _target_url(row)})


def aggregate(spec: Mapping[str, Any], payload: Mapping[str, Any]) -> Dict[str, Any]:
    spec = validate_spec(spec)
    collected_at = _parse_timestamp(payload.get("collected_at")) or datetime.now(timezone.utc)
    ahrefs = payload.get("ahrefs") if isinstance(payload.get("ahrefs"), dict) else {}
    dfs = payload.get("dataforseo") if isinstance(payload.get("dataforseo"), dict) else {}
    ahrefs_by_target = ahrefs.get("backlinks") if isinstance(ahrefs.get("backlinks"), dict) else {}
    dfs_by_target = dfs.get("backlinks") if isinstance(dfs.get("backlinks"), dict) else {}
    summaries = dfs.get("page_summaries") if isinstance(dfs.get("page_summaries"), dict) else {}
    targets: Dict[str, Any] = {}
    for entry in target_entries(spec):
        url = entry["url"]
        a_rows = [row for row in ahrefs_by_target.get(url, []) if isinstance(row, dict)]
        d_rows = [row for row in dfs_by_target.get(url, []) if isinstance(row, dict)]
        classes = {name: 0 for name in ("article", "profile", "home", "spam", "other")}
        for row in a_rows:
            classes[classify_ahrefs_link(row)] += 1
        targets[url] = {
            "cluster": entry["cluster"],
            "domain": entry["domain"],
            "is_focal": _canonical_domain(entry["domain"]) == spec["focal_domain"],
            "requested_target_url": url,
            "ahrefs": {
                "raw_backlink_rows": len(a_rows),
                "dofollow_rows": sum(row.get("is_dofollow") is True for row in a_rows),
                "unique_donor_domains": len({donor_domain(row) for row in a_rows if donor_domain(row)}),
                "classification": classes,
                "new_links": count_new_links(a_rows, collected_at),
            },
            "dataforseo": {
                "raw_backlink_rows": len(d_rows),
                "unique_donor_domains": len({donor_domain(row) for row in d_rows if donor_domain(row)}),
                "page_summary": summaries.get(url, {}),
            },
            "target_observations": {
                "ahrefs_observed_urls": _unique_observed_targets(a_rows),
                "dataforseo_observed_urls": _unique_observed_targets(d_rows),
            },
        }
    ratings: Dict[str, Any] = {}
    for domain, value in (ahrefs.get("domain_ratings") or {}).items():
        ratings[domain] = value.get("domain_rating") if isinstance(value, dict) else value
    return {
        "focal_domain": spec["focal_domain"],
        "collected_at": payload.get("collected_at"),
        "source_policy": "separate_non_additive",
        "warnings": [
            "Domain Rating is a per-domain metric and is not additive.",
            "Ahrefs and DataForSEO must not be merged into one backlink or donor count.",
        ],
        "domain_ratings": ratings,
        "targets": targets,
    }


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _write_raw_csv(path: Path, source: str, spec: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    source_data = payload.get(source) if isinstance(payload.get(source), dict) else {}
    rows_by_target = source_data.get("backlinks") if isinstance(source_data.get("backlinks"), dict) else {}
    entries = {entry["url"]: entry for entry in target_entries(spec)}
    field_names = {"cluster", "requested_target_url", "requested_domain"}
    output_rows: List[Dict[str, Any]] = []
    for requested_url, raw_rows in rows_by_target.items():
        entry = entries.get(requested_url, {"cluster": "", "domain": ""})
        for raw in raw_rows if isinstance(raw_rows, list) else []:
            if not isinstance(raw, dict):
                continue
            row = {"cluster": entry["cluster"], "requested_target_url": requested_url, "requested_domain": entry["domain"]}
            row.update({key: _csv_value(value) for key, value in raw.items()})
            if source == "ahrefs":
                row["classification"] = classify_ahrefs_link(raw)
            field_names.update(row)
            output_rows.append(row)
    leading = ["cluster", "requested_target_url", "requested_domain"]
    if source == "ahrefs":
        leading.append("classification")
    fields = leading + sorted(field_names - set(leading))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)


def _md_text(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").replace("`", "\\`")


def _md_code(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    if "|" in text or "`" in text:
        return "<code>" + html.escape(text).replace("|", "&#124;") + "</code>"
    return f"`{text}`"


def render_report(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Сравнение ссылочных профилей",
        "",
        f"Дата сбора: {_md_code(summary.get('collected_at') or 'не указана')}.",
        "",
        "## Важные ограничения",
        "",
        "- DR нельзя складывать: это отдельная метрика каждого домена.",
        "- Ahrefs и DataForSEO нельзя объединять в один счётчик ссылок или доноров.",
        "- Строки обратных ссылок и уникальные домены-доноры показаны отдельно.",
        "",
        "## DR по доменам (Ahrefs)",
        "",
        "| Домен | DR |",
        "|---|---:|",
    ]
    for domain, rating in sorted(summary.get("domain_ratings", {}).items()):
        lines.append(f"| {_md_text(domain)} | {_md_text(rating if rating is not None else 'нет данных')} |")
    lines.extend([
        "",
        "## Сравнение по кластерам",
        "",
        "Выгруженные backlink-строки — ограниченная выборка строк. DataForSEO summary показан отдельно и не считается числом выгруженных строк.",
        "",
    ])
    clusters: Dict[str, List[Any]] = {}
    for url, target in summary.get("targets", {}).items():
        clusters.setdefault(target["cluster"], []).append((url, target))
    for cluster, cluster_targets in clusters.items():
        lines.extend([
            f"## Кластер: {_md_text(cluster)}",
            "",
            "| Роль | Точный URL | Ahrefs: строки | Ahrefs: доноры | Ahrefs: dofollow | DataForSEO: строки | DataForSEO: доноры | DFS summary: backlinks | DFS summary: referring_domains |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for url, target in cluster_targets:
            a = target["ahrefs"]
            d = target["dataforseo"]
            page_summary = d.get("page_summary") if isinstance(d.get("page_summary"), dict) else {}
            role = "**Основной сайт**" if target.get("is_focal") else "Конкурент"
            lines.append(
                f"| {role} | {_md_code(url)} | {a['raw_backlink_rows']} | {a['unique_donor_domains']} | "
                f"{a['dofollow_rows']} | {d['raw_backlink_rows']} | {d['unique_donor_domains']} | "
                f"{page_summary.get('backlinks', 'нет данных')} | {page_summary.get('referring_domains', 'нет данных')} |"
            )
        lines.append("")
        for url, target in cluster_targets:
            a = target["ahrefs"]
            d = target["dataforseo"]
            page_summary = d.get("page_summary") if isinstance(d.get("page_summary"), dict) else {}
            lines.extend([
                f"### {_md_code(url)}" + (" — **основной сайт**" if target.get("is_focal") else ""),
                "",
                f"- Домен: {_md_code(target['domain'])}.",
                f"- Ahrefs, ограниченная выборка строк: {a['raw_backlink_rows']}; домены-доноры — {a['unique_donor_domains']}; dofollow — {a['dofollow_rows']}.",
                f"- Новые по Ahrefs: {a['new_links']['days_365']} за 365 дней; {a['new_links']['days_183']} за 183 дня.",
                "- Классы Ahrefs: " + ", ".join(f"{key} — {value}" for key, value in a["classification"].items()) + ".",
                f"- DataForSEO, ограниченная выборка строк: {d['raw_backlink_rows']}; домены-доноры — {d['unique_donor_domains']}.",
                "- DataForSEO summary (точные метрики страницы): "
                f"backlinks — {page_summary.get('backlinks', 'нет данных')}; "
                f"referring_domains — {page_summary.get('referring_domains', 'нет данных')}.",
                "- Наблюдаемые Ahrefs целевые URL: " + (", ".join(_md_code(item) for item in target["target_observations"]["ahrefs_observed_urls"]) or "нет") + ".",
                "- Наблюдаемые DataForSEO целевые URL: " + (", ".join(_md_code(item) for item in target["target_observations"]["dataforseo_observed_urls"]) or "нет") + ".",
                "",
            ])
    return "\n".join(lines).rstrip() + "\n"


def ensure_output_available(out: Path) -> None:
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("Output directory already exists and is nonempty")


def _set_posix_mode(path: Path, mode: int) -> None:
    if os.name != "posix":
        return
    path.chmod(mode)
    if path.stat().st_mode & 0o777 != mode:
        raise OSError(f"Could not secure output permissions for {path.name}")


def write_outputs(spec: Mapping[str, Any], payload: Mapping[str, Any], out: Path,
                  include_cache: bool = False) -> Dict[str, Any]:
    ensure_output_available(out)
    out.mkdir(parents=True, exist_ok=True)
    _set_posix_mode(out, 0o700)
    summary = aggregate(spec, payload)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_raw_csv(out / "ahrefs_backlinks_raw.csv", "ahrefs", spec, payload)
    _write_raw_csv(out / "dataforseo_backlinks_raw.csv", "dataforseo", spec, payload)
    (out / "report.ru.md").write_text(render_report(summary), encoding="utf-8")
    if include_cache:
        cache_path = out / "api-cache.json"
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _set_posix_mode(cache_path, 0o600)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        spec = validate_spec(json.loads(args.spec.read_text(encoding="utf-8")))
        ensure_output_available(args.out)
        if args.from_cache:
            payload = json.loads((args.from_cache / "api-cache.json").read_text(encoding="utf-8"))
            write_outputs(spec, payload, args.out)
        else:
            credentials = load_credentials()
            payload = collect_live(spec, credentials)
            write_outputs(spec, payload, args.out, include_cache=True)
        print(f"Wrote backlink comparison to {args.out}")
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
