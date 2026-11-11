#!/usr/bin/env python3
"""Extract a bounded main-text sequence from HTML without media attributes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from lxml import etree, html
except ImportError:
    print("error: lxml is required; install it in a task-local virtual environment", file=sys.stderr)
    raise SystemExit(2)


DEFAULT_START_XPATH = "//*[self::h1 or self::h2 or self::h3]"
DEFAULT_STOP_TOKENS = (
    "related-articles", "related_articles", "relatedarticles", "related-posts",
    "related_posts", "relatedposts", "related-content", "related_content",
    "recommended", "recommendations", "recommendation", "more-stories",
    "more_articles", "more-articles", "you-may-also-like", "you_may_also_like",
    "read-also", "read_also", "also-read", "also_read", "further-reading",
    "article-footer", "article-detail-footer",
    "comments", "comment-list", "comment_list", "comment-form", "comment_form",
    "comment-section", "comment_section", "respond", "discussion", "disqus",
    "related articles", "related posts", "recommended articles", "you may also like",
    "read also", "also read", "further reading", "leave a comment", "join the discussion",
    "похожие статьи", "связанные статьи", "материалы по теме", "рекомендуем",
    "читайте также", "комментарии", "оставить комментарий", "обсуждение",
    "ähnliche artikel", "verwandte artikel", "empfohlene artikel", "kommentare",
    "artículos relacionados", "articulos relacionados", "comentarios",
    "articles connexes", "articles similaires", "commentaires",
)
STOP_CONTAINER_TAGS = {"section", "div", "aside", "footer", "form", "ol", "ul"}
STOP_HEADING_TAGS = {"h2", "h3", "h4", "h5", "h6"}
SKIP_ANCESTOR_TAGS = {
    "script", "style", "noscript", "template", "svg", "canvas", "picture",
    "video", "audio", "source", "track", "iframe", "object", "embed", "form",
    "button", "nav", "footer", "aside",
}
BLOCKING_DESCENDANTS = {
    "address", "article", "aside", "blockquote", "details", "dialog", "div", "dl",
    "fieldset", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "main", "nav", "ol", "p", "pre", "section", "table", "ul",
}
TEXT_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "dd", "blockquote", "pre", "figcaption", "div", "table"}
HIDDEN_TOKENS = {"hidden", "sr-only", "visually-hidden", "screen-reader-text", "cookie", "consent", "modal", "popup"}
WHITESPACE_RE = re.compile(r"\s+")
TOKEN_SPLIT_RE = re.compile(r"[^a-zа-яёäöüßáéíóúàâçèêëîïôûùüÿñæœ0-9]+", re.I)


def normalize_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value or "").strip()


def normalize_signal(value: str) -> str:
    value = normalize_text(value).casefold().replace("_", "-")
    return TOKEN_SPLIT_RE.sub(" ", value).strip()


def element_xpath(node) -> str:
    return node.getroottree().getpath(node)


def signal_values(node) -> list[str]:
    values = []
    for name, value in node.attrib.items():
        lname = name.casefold()
        if lname in {"id", "class", "role", "aria-label"} or lname.startswith("data-"):
            values.append(str(value))
    if node.tag in STOP_HEADING_TAGS:
        values.append(node.text_content())
    return values


def stop_reason(node, stop_tokens: Iterable[str]) -> str | None:
    tag = str(node.tag).casefold() if isinstance(node.tag, str) else ""
    if tag not in STOP_CONTAINER_TAGS and tag not in STOP_HEADING_TAGS:
        return None
    signals = [normalize_signal(v) for v in signal_values(node) if normalize_text(v)]
    for raw_token in stop_tokens:
        token = normalize_signal(raw_token)
        if not token:
            continue
        for signal in signals:
            if token in signal:
                return raw_token
    return None


def is_hidden_or_skipped(node) -> bool:
    current = node
    while current is not None and isinstance(current.tag, str):
        tag = current.tag.casefold()
        if tag in SKIP_ANCESTOR_TAGS:
            return True
        if "hidden" in current.attrib or current.attrib.get("aria-hidden", "").casefold() == "true":
            return True
        style = current.attrib.get("style", "").replace(" ", "").casefold()
        if "display:none" in style or "visibility:hidden" in style:
            return True
        classes = set(TOKEN_SPLIT_RE.split(current.attrib.get("class", "").casefold()))
        if classes & HIDDEN_TOKENS:
            return True
        current = current.getparent()
    return False


def has_ancestor_tag(node, tags: set[str], stop_at=None) -> bool:
    current = node.getparent()
    while current is not None and current is not stop_at:
        if isinstance(current.tag, str) and current.tag.casefold() in tags:
            return True
        current = current.getparent()
    return False


def simple_div(node) -> bool:
    for descendant in node.iterdescendants():
        if isinstance(descendant.tag, str) and descendant.tag.casefold() in BLOCKING_DESCENDANTS:
            return False
    return bool(normalize_text(node.text_content()))


def table_text(node) -> str:
    lines = []
    caption = node.xpath("./caption[1]")
    if caption:
        cap = normalize_text(caption[0].text_content())
        if cap:
            lines.append(cap)
    for row in node.xpath(".//tr"):
        cells = [normalize_text(cell.text_content()) for cell in row.xpath("./th|./td")]
        cells = [cell for cell in cells if cell]
        if cells:
            lines.append("\t".join(cells))
    if not lines:
        fallback = normalize_text(node.text_content())
        if fallback:
            lines.append(fallback)
    return "\n".join(lines)


def block_for(node) -> dict | None:
    tag = node.tag.casefold()
    if tag == "div" and not simple_div(node):
        return None
    if tag == "table":
        text_value = table_text(node)
        kind = "table"
    else:
        text_value = normalize_text(node.text_content())
        kind = "heading" if tag.startswith("h") else tag
    if not text_value:
        return None
    if tag == "li":
        if has_ancestor_tag(node, {"li"}):
            return None
        text_value = f"- {text_value}"
        kind = "list_item"
    return {"type": kind, "tag": tag, "text": text_value, "xpath": element_xpath(node)}


def choose_start(root, start_xpath: str, prefer_h1: bool):
    matches = [n for n in root.xpath(start_xpath) if isinstance(getattr(n, "tag", None), str)]
    if not matches:
        return None, []
    if prefer_h1:
        for node in matches:
            if node.tag.casefold() == "h1":
                return node, matches
    return matches[0], matches


def extract_html(raw: bytes, source: str, start_xpath: str = DEFAULT_START_XPATH,
                 prefer_h1: bool = True, extra_stop_tokens: Iterable[str] = ()) -> dict:
    parser = html.HTMLParser(encoding="utf-8", recover=True, remove_comments=True)
    try:
        root = html.fromstring(raw, parser=parser, base_url=source)
    except (etree.ParserError, ValueError) as exc:
        return {"source": source, "error": f"html_parse_error: {exc}", "text": "", "blocks": [], "warnings": []}

    start, matches = choose_start(root, start_xpath, prefer_h1)
    base = {
        "source": source,
        "start_xpath": start_xpath,
        "selection_policy": "prefer_first_h1_then_first_match" if prefer_h1 else "first_match",
        "warnings": [],
    }
    if start is None:
        return {**base, "error": "no_start_heading", "start": None, "stop": None, "blocks": [], "counts": {"blocks": 0, "words": 0, "characters": 0}, "text": ""}

    if start.tag.casefold() != "h1":
        base["warnings"].append("no_h1")

    stop_tokens = tuple(DEFAULT_STOP_TOKENS) + tuple(extra_stop_tokens)
    ordered = [n for n in root.iter() if isinstance(getattr(n, "tag", None), str)]
    start_index = ordered.index(start)
    stop_node = None
    reason = None
    for node in ordered[start_index + 1:]:
        found = stop_reason(node, stop_tokens)
        if found:
            stop_node, reason = node, found
            break

    blocks = []
    seen = set()
    for node in ordered[start_index:]:
        if node is stop_node:
            break
        tag = node.tag.casefold()
        if tag not in TEXT_TAGS or is_hidden_or_skipped(node):
            continue
        if tag != "table" and has_ancestor_tag(node, {"table"}):
            continue
        block = block_for(node)
        if not block:
            continue
        key = (block["type"], block["text"])
        if key in seen:
            continue
        seen.add(key)
        blocks.append(block)

    text_value = "\n\n".join(block["text"] for block in blocks)
    words = len(re.findall(r"\b[\w’-]+\b", text_value, flags=re.UNICODE))
    if words < 20:
        base["warnings"].append("short_extraction")
    stop = (
        {"reason": reason, "tag": stop_node.tag.casefold(), "xpath": element_xpath(stop_node), "signal": normalize_text(" | ".join(signal_values(stop_node)))}
        if stop_node is not None else
        {"reason": "end_of_document", "tag": None, "xpath": None, "signal": None}
    )
    return {
        **base,
        "error": None,
        "start": {"tag": start.tag.casefold(), "text": normalize_text(start.text_content()), "xpath": element_xpath(start), "match_count": len(matches)},
        "stop": stop,
        "blocks": blocks,
        "counts": {"blocks": len(blocks), "words": words, "characters": len(text_value)},
        "text": text_value,
    }


def fetch_url(url: str, timeout: float, max_bytes: int) -> tuple[bytes, dict]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; HermesPageText/1.0; +https://github.com/webdelo/seo-hermes-skills)", "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError(f"unsupported content type: {content_type}")
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError(f"response exceeds --max-bytes ({max_bytes})")
            charset = response.headers.get_content_charset() or "utf-8"
            if charset.casefold() != "utf-8":
                raw = raw.decode(charset, errors="replace").encode("utf-8")
            return raw, {"requested_url": url, "final_url": response.geturl(), "http_status": response.status, "content_type": content_type}
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error: {exc.reason}") from exc


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--html-file", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--start-xpath", default=DEFAULT_START_XPATH)
    parser.add_argument("--no-prefer-h1", action="store_true")
    parser.add_argument("--stop-token", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-bytes", type=int, default=10_000_000)
    parser.add_argument("--text-out", type=Path)
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        if args.url:
            raw, retrieval = fetch_url(args.url, args.timeout, args.max_bytes)
            source = retrieval["final_url"]
        else:
            raw = args.html_file.read_bytes()
            source = args.base_url or args.html_file.resolve().as_uri()
            retrieval = {"requested_url": source, "final_url": source, "http_status": None, "content_type": "text/html"}
        result = extract_html(raw, source, args.start_xpath, not args.no_prefer_h1, args.stop_token)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result["retrieval"] = {**retrieval, "retrieved_at": retrieved_at}
    text_payload = result["text"]
    json_payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.text_out:
        args.text_out.parent.mkdir(parents=True, exist_ok=True)
        args.text_out.write_text(text_payload + ("\n" if text_payload else ""), encoding="utf-8")
    else:
        print(text_payload)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json_payload, encoding="utf-8")
    if result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
        return 3
    print(f"extracted {result['counts']['blocks']} blocks, {result['counts']['words']} words; stop={result['stop']['reason']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
