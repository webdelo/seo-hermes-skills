#!/usr/bin/env python3
"""Page-level SEO technical audit collector; Python 3.9+, standard library only.

Collects raw evidence for one URL, normalizes every check to a verdict
(ok|warn|fail|unknown) with a short Russian explanation, and renders a
self-contained Russian HTML dashboard. A check that could not be performed is
always recorded as 'unknown' with a reason: nothing is ever assumed, estimated
or reported as zero.
"""
import argparse
import csv
import json
import os
import re
import ssl
import subprocess
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, quote

VERSION = '1.0.0'
PSI_ENDPOINT = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
DEFAULT_UA = ('Mozilla/5.0 (compatible; HermesSeoTechnicalAudit/%s; '
              '+one-page technical SEO audit; respects robots.txt)' % VERSION)
USER_AGENTS = {
    'auto': DEFAULT_UA,
    'googlebot-smartphone': ('Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) '
                             'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z Mobile '
                             'Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'),
    'googlebot-desktop': ('Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; '
                          'Googlebot/2.1; +http://www.google.com/bot.html) Chrome/W.X.Y.Z Safari/537.36'),
    'chrome': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
}
OWN_AGENT_TOKEN = 'HermesSeoTechnicalAudit'
SECRET_HEADERS = ('cookie', 'set-cookie', 'authorization', 'proxy-authorization',
                  'www-authenticate', 'x-api-key')
POLITE_DELAY = 0.3
SITEMAP_CAP = 5
# Hard ceiling on a single response body. Guards against multi-hundred-MB sitemaps
# or media files: we read one byte past the cap to detect truncation, then stop.
MAX_FETCH_BYTES = 8 * 1024 * 1024

IMAGE_HEAD_CAP = 15
HREFLANG_PROBE_CAP = 10

CHECK_TITLES = {
    'transport': 'Транспорт и ответ сервера',
    'tls': 'TLS-сертификат',
    'crawlability': 'Доступность для сканирования',
    'canonical': 'Канонизация и дубликаты',
    'indexability': 'Индексируемость',
    'head_meta': 'Head и мета-теги',
    'headings': 'Заголовки H1–H6',
    'content': 'Контент',
    'links': 'Ссылки',
    'images': 'Изображения',
    'structured_data': 'Структурированные данные',
    'hreflang': 'Hreflang',
    'sitemaps': 'Карты сайта',
    'rendering': 'Рендеринг JavaScript',
    'performance': 'Производительность (PageSpeed Insights)',
}
RECOMMENDATIONS = {
    'transport': 'Проверить цепочку редиректов, коды ответа и время отклика на стороне сервера.',
    'tls': 'Проверить срок действия и цепочку TLS-сертификата, включить HSTS.',
    'crawlability': 'Согласовать robots.txt, X-Robots-Tag и мета-robots с целью индексации страницы.',
    'canonical': 'Указать один самоссылающийся rel=canonical и свести дубликаты http/https и www/non-www редиректом 301.',
    'indexability': 'Убрать директивы, блокирующие индексацию, если страница должна быть в индексе.',
    'head_meta': 'Заполнить и укоротить title и meta description, добавить viewport, charset и lang.',
    'headings': 'Оставить один H1, убрать пустые заголовки и не пропускать уровни.',
    'content': 'Увеличить объём уникального текста и указать даты публикации и обновления.',
    'links': 'Исправить пустые анкоры, проверить rel-атрибуты и полноту внутренней перелинковки.',
    'images': 'Добавить осмысленные alt, атрибуты width/height, lazy-loading и форматы WebP/AVIF.',
    'structured_data': 'Исправить ошибки JSON-LD и добавить обязательные свойства схемы; затем проверить в Rich Results Test.',
    'hreflang': 'Исправить коды языков, добавить самоссылку и убедиться в доступности альтернатив.',
    'sitemaps': 'Добавить URL в XML-карту сайта и указать корректный lastmod.',
    'rendering': 'Проверить рендеринг вручную: важный контент не должен зависеть только от JavaScript.',
    'performance': 'Получить ключ PageSpeed Insights API и измерить Core Web Vitals по полевым данным.',
}
SEVERITY = {'fail': 'высокая', 'warn': 'средняя', 'unknown': 'нет данных', 'ok': 'нет'}

# Approximate per-character advance widths, Arial-like 20px (Google SERP title).
# Documented as APPROXIMATE: real width depends on font, rendering and device.
PIXEL_WIDTHS = {
    ' ': 5, '!': 6, '"': 7, '#': 11, '$': 11, '%': 18, '&': 13, "'": 4, '(': 7, ')': 7,
    '*': 8, '+': 12, ',': 5, '-': 7, '.': 5, '/': 6, '0': 11, '1': 11, '2': 11, '3': 11,
    '4': 11, '5': 11, '6': 11, '7': 11, '8': 11, '9': 11, ':': 5, ';': 5, '<': 12, '=': 12,
    '>': 12, '?': 11, '@': 20, 'A': 13, 'B': 13, 'C': 14, 'D': 14, 'E': 13, 'F': 12,
    'G': 16, 'H': 14, 'I': 6, 'J': 10, 'K': 13, 'L': 11, 'M': 17, 'N': 14, 'O': 16,
    'P': 13, 'Q': 16, 'R': 14, 'S': 13, 'T': 12, 'U': 14, 'V': 13, 'W': 19, 'X': 13,
    'Y': 13, 'Z': 12, '[': 6, '\\': 6, ']': 6, '^': 9, '_': 11, '`': 7, 'a': 11, 'b': 11,
    'c': 10, 'd': 11, 'e': 11, 'f': 6, 'g': 11, 'h': 11, 'i': 4, 'j': 4, 'k': 10, 'l': 4,
    'm': 17, 'n': 11, 'o': 11, 'p': 11, 'q': 11, 'r': 7, 's': 10, 't': 6, 'u': 11, 'v': 10,
    'w': 14, 'x': 10, 'y': 10, 'z': 10, '{': 7, '|': 5, '}': 7, '~': 12,
}
CYRILLIC_WIDTH = 11
DEFAULT_WIDTH = 10
SCHEMA_REQUIRED = {
    'Article': ['headline', 'author', 'datePublished'],
    'NewsArticle': ['headline', 'author', 'datePublished'],
    'BlogPosting': ['headline', 'author', 'datePublished'],
    'Product': ['name', 'offers'],
    'FAQPage': ['mainEntity'],
    'BreadcrumbList': ['itemListElement'],
    'Organization': ['name', 'url'],
    'Person': ['name'],
    'LocalBusiness': ['name', 'address'],
}
HEURISTIC_NOTE = ('Локальная эвристическая проверка по минимальной таблице требований. '
                  'Это НЕ Google Rich Results Test и не гарантия расширенных результатов.')


# --------------------------------------------------------------------------- utils

def normalize_url(value):
    """Validate and normalize an absolute HTTP(S) URL; credentials are forbidden."""
    if not value or not isinstance(value, str) or re.search(r'\s', value):
        raise ValueError('Invalid URL')
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('URL must be absolute http(s)')
    if parts.username or parts.password:
        raise ValueError('Credentials in URLs are forbidden')
    host = parts.hostname.encode('idna').decode().lower()
    if parts.port:
        host += ':%d' % parts.port
    return urlunsplit((parts.scheme.lower(), host, parts.path or '/', parts.query, ''))


def canonical_form(url):
    """Loose comparison form: no fragment, lowercase scheme/host, empty path as '/'."""
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    host = (p.hostname or '').lower()
    if p.port:
        host += ':%d' % p.port
    return urlunsplit((p.scheme.lower(), host, p.path or '/', p.query, ''))


def save_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def sanitize_headers(headers):
    return {k: v for k, v in (headers or {}).items() if k.lower() not in SECRET_HEADERS}


def verdict(name, level, reason, evidence):
    return {'title_ru': CHECK_TITLES.get(name, name), 'verdict': level,
            'reason_ru': reason, 'evidence': evidence}


def display(value):
    if value is None:
        return 'нет данных'
    if value is True:
        return 'да'
    if value is False:
        return 'нет'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def title_pixel_width(text, table=None):
    """APPROXIMATE pixel width (Arial-like 20px). Never a measured value."""
    table = PIXEL_WIDTHS if table is None else table
    total = 0
    for ch in text or '':
        if ch in table:
            total += table[ch]
        elif '\u0400' <= ch <= '\u04ff':
            total += CYRILLIC_WIDTH
        else:
            total += DEFAULT_WIDTH
    return total


# --------------------------------------------------------------------------- fetch

def http_fetcher(user_agent, timeout=20):
    """Return fetch(url, method='GET') -> record. No cookies, no credentials, no redirects."""
    import urllib.request
    import urllib.error

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect())

    def fetch(url, method='GET'):
        record = {'url': url, 'method': method, 'status': None, 'headers': {}, 'body': None,
                  'error': None, 'response_time_ms': None, 'size_bytes': None,
                  'transfer_bytes': None, 'content_encoding': None, 'truncated': False}
        try:
            request = urllib.request.Request(url, method=method, headers={
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, identity',
                'Accept-Language': 'ru,en;q=0.8',
            })
            started = time.monotonic()
            try:
                response = opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                if method == 'HEAD':
                    raw = b''
                else:
                    # Bounded read: one byte past the cap tells us it was truncated.
                    raw = response.read(MAX_FETCH_BYTES + 1)
                    if len(raw) > MAX_FETCH_BYTES:
                        raw = raw[:MAX_FETCH_BYTES]
                        record['truncated'] = True
                        record['truncated_at_bytes'] = MAX_FETCH_BYTES
                record['status'] = getattr(response, 'status', None) or response.getcode()
                record['headers'] = {k.lower(): v for k, v in response.headers.items()}
                record['response_time_ms'] = int((time.monotonic() - started) * 1000)
            record['transfer_bytes'] = len(raw)
            encoding = (record['headers'].get('content-encoding') or '').lower().strip()
            record['content_encoding'] = encoding or None
            if raw and 'gzip' in encoding:
                raw = _safe_decompress(raw, 16 + zlib.MAX_WBITS) or raw
            elif raw and 'deflate' in encoding:
                raw = _safe_decompress(raw, -zlib.MAX_WBITS) or _safe_decompress(raw, zlib.MAX_WBITS) or raw
            # A small compressed body can expand far past the cap, so re-apply it
            # after decompression: the ceiling must bound what we keep in memory.
            if len(raw) > MAX_FETCH_BYTES:
                raw = raw[:MAX_FETCH_BYTES]
                record['truncated'] = True
                record['truncated_at_bytes'] = MAX_FETCH_BYTES
            record['body'] = raw
            record['size_bytes'] = len(raw)
        except Exception as exc:  # noqa: BLE001 - one failure must never abort the run
            record['error'] = '%s: %s' % (type(exc).__name__, _scrub(str(exc)))
        return fetch_delay(record)

    return fetch


def _safe_decompress(raw, wbits):
    """Decompress tolerantly: a truncated stream still yields its decoded prefix."""
    try:
        return zlib.decompress(raw, wbits)
    except Exception:  # noqa: BLE001
        pass
    try:
        # Bounded reads can cut a stream mid-way; decompressobj keeps what decoded.
        partial = zlib.decompressobj(wbits).decompress(raw)
        return partial or None
    except Exception:  # noqa: BLE001
        return None


def _scrub(text):
    """Remove anything key-like from messages before it can reach an artifact."""
    text = re.sub(r'(?i)(key|token|password|secret)=[^&\s]+', r'\1=[REDACTED]', text or '')
    return text[:300]


def fetch_delay(record):
    return record


def charset_of(record, html_text=None):
    content_type = (record.get('headers') or {}).get('content-type', '')
    match = re.search(r'charset\s*=\s*"?([\w.:+-]+)', content_type, re.I)
    if match:
        return match.group(1).lower(), 'http_header'
    if html_text:
        match = re.search(r'<meta[^>]+charset\s*=\s*["\']?([\w.:+-]+)', html_text, re.I)
        if match:
            return match.group(1).lower(), 'meta'
    return None, None


def decode_body(record):
    body = record.get('body') or b''
    probe = body[:4096].decode('ascii', errors='replace')
    name, source = charset_of(record, probe)
    for candidate in [name, 'utf-8', 'cp1251']:
        if not candidate:
            continue
        try:
            return body.decode(candidate, errors='strict'), candidate, source or 'fallback'
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode('utf-8', errors='replace'), 'utf-8', 'replace'


def follow_redirects(url, fetcher, max_redirects=10):
    """Follow Location hops manually; detect loops and truncation."""
    chain, seen = [], set()
    current, loop, truncated = url, False, False
    final = None
    while True:
        record = fetcher(current)
        location = (record.get('headers') or {}).get('location')
        hop = {'url': current, 'status': record.get('status'), 'location': location,
               'error': record.get('error'), 'response_time_ms': record.get('response_time_ms')}
        chain.append(hop)
        final = record
        seen.add(canonical_form(current))
        if record.get('error') or not record.get('status'):
            break
        if not (300 <= record['status'] < 400 and location):
            break
        nxt = urljoin(current, location)
        hop['resolved_location'] = nxt
        if canonical_form(nxt) in seen:
            loop = True
            break
        if len(chain) > max_redirects:
            truncated = True
            break
        current = nxt
        time.sleep(0)
    return {'chain': chain, 'final_url': current, 'final': final, 'hops': len(chain) - 1,
            'loop_detected': loop, 'truncated': truncated, 'max_redirects': max_redirects}


# --------------------------------------------------------------------------- robots

@dataclass
class RobotsGroup:
    agents: list = field(default_factory=list)
    rules: list = field(default_factory=list)  # (type, pattern)


class RobotsRules:
    """Googlebot-style robots.txt matching: longest match wins, Allow wins ties."""

    def __init__(self, groups=None, sitemaps=None, source_text=''):
        self.groups = groups or []
        self.sitemaps = sitemaps or []
        self.source_text = source_text

    @classmethod
    def parse(cls, text):
        groups, sitemaps = [], []
        current, expecting_agent = None, False
        for raw_line in (text or '').splitlines():
            line = raw_line.split('#', 1)[0].strip()
            if not line or ':' not in line:
                continue
            field_name, _, value = line.partition(':')
            field_name, value = field_name.strip().lower(), value.strip()
            if field_name == 'user-agent':
                if current is None or not expecting_agent:
                    current = RobotsGroup()
                    groups.append(current)
                current.agents.append(value.lower())
                expecting_agent = True
            elif field_name in ('allow', 'disallow'):
                if current is None:
                    current = RobotsGroup(agents=['*'])
                    groups.append(current)
                expecting_agent = False
                if value:
                    current.rules.append((field_name, value))
                elif field_name == 'disallow':
                    pass  # empty Disallow means allow everything; no rule recorded
            elif field_name == 'sitemap':
                sitemaps.append(value)
        return cls(groups, sitemaps, text or '')

    def group_for(self, agent):
        agent = (agent or '*').lower()
        best, best_len = None, -1
        for group in self.groups:
            for token in group.agents:
                if token != '*' and agent.startswith(token) and len(token) > best_len:
                    best, best_len = group, len(token)
        if best is not None:
            return best
        for group in self.groups:
            if '*' in group.agents:
                return group
        return None

    @staticmethod
    def _match(pattern, path):
        regex = ''
        anchored = pattern.endswith('$')
        body = pattern[:-1] if anchored else pattern
        for ch in body:
            regex += '.*' if ch == '*' else re.escape(ch)
        regex = '^' + regex + ('$' if anchored else '')
        return re.search(regex, path) is not None

    def verdict(self, path, agent):
        path = path or '/'
        group = self.group_for(agent)
        if group is None:
            return {'allowed': True, 'rule': None, 'group_agents': None,
                    'reason': 'no_matching_group'}
        best = None
        for kind, pattern in group.rules:
            if not self._match(pattern, path):
                continue
            score = (len(pattern), 1 if kind == 'allow' else 0)
            if best is None or score > best[0]:
                best = (score, kind, pattern)
        if best is None:
            return {'allowed': True, 'rule': None, 'group_agents': group.agents,
                    'reason': 'no_matching_rule'}
        return {'allowed': best[1] == 'allow', 'rule': (best[1], best[2]),
                'group_agents': group.agents, 'reason': 'longest_match'}


# --------------------------------------------------------------------------- HTML

SKIP_TEXT_TAGS = {'script', 'style', 'noscript', 'template', 'svg', 'head'}
HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}


@dataclass
class HtmlFacts:
    html_length: int = 0
    title: object = None
    metas: list = field(default_factory=list)
    link_tags: list = field(default_factory=list)
    links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    headings: list = field(default_factory=list)
    jsonld_raw: list = field(default_factory=list)
    html_lang: object = None
    charset_meta: object = None
    text: str = ''
    paragraphs: int = 0
    has_microdata: bool = False
    has_rdfa: bool = False
    base_href: object = None

    def meta(self, name):
        name = name.lower()
        for item in self.metas:
            if (item.get('name') or '').lower() == name:
                return item.get('content')
        return None

    def meta_prefix(self, prefix):
        prefix = prefix.lower()
        out = []
        for item in self.metas:
            key = (item.get('property') or item.get('name') or '').lower()
            if key.startswith(prefix):
                out.append({'key': key, 'content': item.get('content')})
        return out


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.facts = HtmlFacts()
        self.skip_depth = 0
        self.heading_stack = []
        self.anchor_stack = []
        self.jsonld_capture = None
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else '') for k, v in attrs}
        f = self.facts
        if tag == 'html':
            f.html_lang = a.get('lang')
        elif tag == 'base' and a.get('href'):
            f.base_href = a['href']
        elif tag == 'meta':
            f.metas.append({'name': a.get('name'), 'property': a.get('property'),
                            'http-equiv': a.get('http-equiv'), 'content': a.get('content'),
                            'charset': a.get('charset')})
            if a.get('charset'):
                f.charset_meta = a['charset']
            if (a.get('http-equiv') or '').lower() == 'content-type' and 'charset' in (a.get('content') or '').lower():
                f.charset_meta = f.charset_meta or a.get('content')
        elif tag == 'link':
            f.link_tags.append(a)
        elif tag == 'img':
            f.images.append(a)
        elif tag == 'p':
            f.paragraphs += 1
        elif tag == 'a':
            entry = {'href': a.get('href'), 'rel': a.get('rel') or '', 'text_parts': [],
                     'target': a.get('target')}
            f.links.append(entry)
            self.anchor_stack.append(entry)
        elif tag in HEADING_TAGS:
            entry = {'level': int(tag[1]), 'text_parts': []}
            f.headings.append(entry)
            self.heading_stack.append(entry)
        elif tag == 'script' and (a.get('type') or '').lower().strip() == 'application/ld+json':
            self.jsonld_capture = []
        if tag == 'title':
            # Browsers treat <title> as escapable raw text: markup inside it is not a tag.
            self.set_cdata_mode('title')
        if any(k in a for k in ('itemscope', 'itemtype', 'itemprop')):
            f.has_microdata = True
        if any(k in a for k in ('vocab', 'typeof', 'property', 'resource')) and tag != 'meta':
            f.has_rdfa = True
        if tag in SKIP_TEXT_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in SKIP_TEXT_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag == 'a' and self.anchor_stack:
            self.anchor_stack.pop()
        if tag in HEADING_TAGS and self.heading_stack:
            self.heading_stack.pop()
        if tag == 'script' and self.jsonld_capture is not None:
            self.facts.jsonld_raw.append(''.join(self.jsonld_capture))
            self.jsonld_capture = None

    def handle_data(self, data):
        if self.jsonld_capture is not None:
            self.jsonld_capture.append(data)
            return
        if self.skip_depth:
            return
        if self.anchor_stack:
            self.anchor_stack[-1]['text_parts'].append(data)
        for heading in self.heading_stack:
            heading['text_parts'].append(data)
        self.text_parts.append(data)


def parse_html(html_text):
    parser = _Collector()
    try:
        parser.feed(html_text or '')
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup must not abort the run
        pass
    facts = parser.facts
    facts.html_length = len(html_text or '')
    match = re.search(r'<title[^>]*>(.*?)</title>', html_text or '', re.I | re.S)
    facts.title = match.group(1).strip() if match else None
    facts.text = re.sub(r'\s+', ' ', ''.join(parser.text_parts)).strip()
    for link in facts.links:
        link['text'] = re.sub(r'\s+', ' ', ''.join(link.pop('text_parts'))).strip()
    for heading in facts.headings:
        heading['text'] = re.sub(r'\s+', ' ', ''.join(heading.pop('text_parts'))).strip()
    if facts.html_lang is None:
        match = re.search(r'<html[^>]+lang\s*=\s*["\']?([\w-]+)', html_text or '', re.I)
        facts.html_lang = match.group(1) if match else None
    return facts


def parse_link_header(value):
    """Parse an HTTP Link header into [{'url', 'rel', 'hreflang', ...}]."""
    out = []
    for part in re.split(r',(?=\s*<)', value or ''):
        match = re.match(r'\s*<([^>]*)>\s*(.*)', part)
        if not match:
            continue
        entry = {'url': match.group(1).strip()}
        for name, quoted, bare in re.findall(r'([\w*-]+)\s*=\s*(?:"([^"]*)"|([^;,\s]+))',
                                             match.group(2)):
            entry[name.lower()] = quoted if quoted else bare
        out.append(entry)
    return out


# --------------------------------------------------------------------------- checks

def check_transport(url, redirects, decoded_charset, charset_source):
    final = redirects.get('final') or {}
    headers = sanitize_headers(final.get('headers'))
    parts = urlsplit(redirects.get('final_url') or url)
    evidence = {
        'requested_url': url,
        'final_url': redirects.get('final_url'),
        'status': final.get('status'),
        'hops': redirects.get('hops'),
        'redirect_chain': [{k: v for k, v in hop.items()} for hop in redirects.get('chain', [])],
        'loop_detected': redirects.get('loop_detected'),
        'truncated_at_max_redirects': redirects.get('truncated'),
        'scheme': parts.scheme,
        'https': parts.scheme == 'https',
        'hsts': headers.get('strict-transport-security'),
        'response_time_ms': final.get('response_time_ms'),
        'content_type': headers.get('content-type'),
        'content_encoding': final.get('content_encoding'),
        'charset': decoded_charset,
        'charset_source': charset_source,
        'size_bytes': final.get('size_bytes'),
        'transfer_bytes': final.get('transfer_bytes'),
        'error': final.get('error'),
        'response_headers': headers,
    }
    if final.get('error') or not final.get('status'):
        return verdict('transport', 'unknown',
                       'Ответ не получен: сетевая ошибка, данные недоступны.', evidence)
    status = final['status']
    if redirects.get('loop_detected'):
        return verdict('transport', 'fail', 'Обнаружен цикл редиректов.', evidence)
    if redirects.get('truncated'):
        return verdict('transport', 'fail',
                       'Превышен лимит редиректов, конечный URL не достигнут.', evidence)
    if status >= 500:
        return verdict('transport', 'fail', 'Серверная ошибка %d.' % status, evidence)
    if status >= 400:
        return verdict('transport', 'fail', 'Клиентская ошибка %d: страница недоступна.' % status, evidence)
    reasons = []
    level = 'ok'
    if parts.scheme != 'https':
        reasons.append('страница отдаётся по HTTP без шифрования')
        level = 'fail'
    if redirects.get('hops', 0) >= 2:
        reasons.append('цепочка из %d редиректов' % redirects['hops'])
        level = 'fail' if level == 'fail' else 'warn'
    elif redirects.get('hops', 0) == 1:
        reasons.append('один редирект до конечного URL')
        level = 'fail' if level == 'fail' else 'warn'
    if not evidence['hsts'] and parts.scheme == 'https':
        reasons.append('нет заголовка HSTS')
        level = 'fail' if level == 'fail' else 'warn'
    if (final.get('response_time_ms') or 0) > 1500:
        reasons.append('время ответа %d мс' % final['response_time_ms'])
        level = 'fail' if level == 'fail' else 'warn'
    return verdict('transport', level,
                   ('Ответ %d: ' % status) + ('; '.join(reasons) if reasons else 'замечаний нет.'),
                   evidence)


def check_tls(url, timeout=20, connector=None):
    parts = urlsplit(url)
    evidence = {'host': parts.hostname, 'scheme': parts.scheme, 'subject': None, 'issuer': None,
                'not_before': None, 'not_after': None, 'expires_in_days': None, 'error': None}
    if parts.scheme != 'https':
        evidence['error'] = 'not_https'
        return verdict('tls', 'unknown',
                       'Проверка сертификата невозможна: схема не HTTPS.', evidence)
    try:
        cert = (connector or _tls_peer_cert)(parts.hostname, parts.port or 443, timeout)
    except Exception as exc:  # noqa: BLE001
        evidence['error'] = '%s: %s' % (type(exc).__name__, _scrub(str(exc)))
        return verdict('tls', 'unknown',
                       'Сертификат не проверен: ошибка соединения TLS.', evidence)
    evidence['subject'] = _flatten_cert_name(cert.get('subject'))
    evidence['issuer'] = _flatten_cert_name(cert.get('issuer'))
    evidence['not_before'] = cert.get('notBefore')
    evidence['not_after'] = cert.get('notAfter')
    try:
        expiry = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
        days = (expiry - datetime.now(timezone.utc)).days
        evidence['expires_in_days'] = days
    except Exception:  # noqa: BLE001
        return verdict('tls', 'unknown', 'Дата окончания сертификата не разобрана.', evidence)
    if days < 0:
        return verdict('tls', 'fail', 'Сертификат истёк %d дней назад.' % abs(days), evidence)
    if days < 14:
        return verdict('tls', 'fail', 'Сертификат истекает через %d дней.' % days, evidence)
    if days < 30:
        return verdict('tls', 'warn', 'Сертификат истекает через %d дней.' % days, evidence)
    return verdict('tls', 'ok', 'Сертификат валиден, осталось %d дней.' % days, evidence)


def _tls_peer_cert(host, port, timeout):
    import socket
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            return tls.getpeercert()


def _flatten_cert_name(value):
    if not value:
        return None
    return ', '.join('%s=%s' % (k, v) for group in value for k, v in group)


def robots_directives(headers, facts):
    sources = {'http_header': (headers or {}).get('x-robots-tag'),
               'meta_robots': facts.meta('robots'),
               'meta_googlebot': facts.meta('googlebot')}
    result = {'noindex': False, 'nofollow': False, 'noarchive': False, 'none': False,
              'max_snippet': None, 'max_image_preview': None, 'max_video_preview': None,
              'noindex_sources': [], 'nofollow_sources': [], 'raw': sources,
              'directives_by_source': {}}
    for source, value in sources.items():
        if not value:
            continue
        tokens = [t.strip().lower() for t in re.split(r'[,\n]', value) if t.strip()]
        result['directives_by_source'][source] = tokens
        for token in tokens:
            key, _, argument = token.partition(':')
            key, argument = key.strip(), argument.strip()
            if key in ('noindex', 'none'):
                result['noindex'] = True
                result['noindex_sources'].append(source)
                if key == 'none':
                    result['none'] = True
                    result['nofollow'] = True
                    result['nofollow_sources'].append(source)
            elif key == 'nofollow':
                result['nofollow'] = True
                result['nofollow_sources'].append(source)
            elif key == 'noarchive':
                result['noarchive'] = True
            elif key == 'max-snippet':
                result['max_snippet'] = argument
            elif key == 'max-image-preview':
                result['max_image_preview'] = argument
            elif key == 'max-video-preview':
                result['max_video_preview'] = argument
    result['noindex_sources'] = sorted(set(result['noindex_sources']))
    result['nofollow_sources'] = sorted(set(result['nofollow_sources']))
    return result


def check_crawlability(final_url, headers, facts, robots_record, rules, directives):
    path = urlsplit(final_url).path or '/'
    query = urlsplit(final_url).query
    match_path = path + (('?' + query) if query else '')
    googlebot = rules.verdict(match_path, 'Googlebot') if rules else None
    evidence = {
        'robots_txt_url': (robots_record or {}).get('url'),
        'robots_txt_status': (robots_record or {}).get('status'),
        'robots_txt_error': (robots_record or {}).get('error'),
        'matched_path': match_path,
        'googlebot_allowed': None if googlebot is None else googlebot['allowed'],
        'googlebot_rule': None if googlebot is None else (
            None if not googlebot['rule'] else '%s: %s' % googlebot['rule']),
        'googlebot_group': None if googlebot is None else googlebot.get('group_agents'),
        'sitemaps_in_robots': rules.sitemaps if rules else None,
        'x_robots_tag': (headers or {}).get('x-robots-tag'),
        'meta_robots': facts.meta('robots'),
        'meta_googlebot': facts.meta('googlebot'),
        'directives': directives,
    }
    if rules is None:
        return verdict('crawlability', 'unknown',
                       'robots.txt не получен: правила сканирования неизвестны.', evidence)
    if googlebot and not googlebot['allowed']:
        return verdict('crawlability', 'fail',
                       'URL запрещён в robots.txt для Googlebot правилом %s: %s.' % googlebot['rule'],
                       evidence)
    if directives['noindex']:
        return verdict('crawlability', 'fail',
                       'Сканирование разрешено, но есть директива noindex (%s).'
                       % ', '.join(directives['noindex_sources']), evidence)
    if directives['nofollow']:
        return verdict('crawlability', 'warn',
                       'Сканирование разрешено, но ссылки помечены nofollow.', evidence)
    return verdict('crawlability', 'ok', 'Сканирование и индексация директивами не запрещены.', evidence)


def check_canonical(final_url, facts, headers, variants=None):
    html_canonical = None
    for tag in facts.link_tags:
        rels = (tag.get('rel') or '').lower().split()
        if 'canonical' in rels and tag.get('href'):
            html_canonical = urljoin(facts.base_href or final_url, tag['href'])
            break
    header_canonical = None
    for entry in parse_link_header((headers or {}).get('link')):
        if 'canonical' in (entry.get('rel') or '').lower().split():
            header_canonical = urljoin(final_url, entry['url'])
            break
    effective = html_canonical or header_canonical
    evidence = {
        'final_url': final_url,
        'canonical_html': html_canonical,
        'canonical_header': header_canonical,
        'canonical_effective': effective,
        'self_referential': None if effective is None else canonical_form(effective) == canonical_form(final_url),
        'mismatch': None if effective is None else canonical_form(effective) != canonical_form(final_url),
        'conflict_html_vs_header': bool(html_canonical and header_canonical
                                        and canonical_form(html_canonical) != canonical_form(header_canonical)),
        'canonical_count_html': sum(1 for t in facts.link_tags
                                    if 'canonical' in (t.get('rel') or '').lower().split()),
        'variants': variants,
    }
    if effective is None:
        return verdict('canonical', 'warn',
                       'rel=canonical отсутствует и в HTML, и в HTTP-заголовке.', evidence)
    if evidence['canonical_count_html'] > 1:
        return verdict('canonical', 'fail',
                       'В HTML найдено несколько rel=canonical (%d).' % evidence['canonical_count_html'],
                       evidence)
    if evidence['conflict_html_vs_header']:
        return verdict('canonical', 'fail',
                       'Канонический URL в HTML и в HTTP-заголовке различаются.', evidence)
    if evidence['mismatch']:
        return verdict('canonical', 'warn',
                       'Канонический URL не совпадает с конечным URL страницы.', evidence)
    return verdict('canonical', 'ok', 'Канонический URL самоссылающийся.', evidence)


def variant_urls(url):
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    port = ':%d' % parts.port if parts.port else ''
    root = host[4:] if host.startswith('www.') else host
    www = host if host.startswith('www.') else 'www.' + host
    path = parts.path or '/'
    def build(scheme, hostname, new_path=None):
        return urlunsplit((scheme, hostname + port, new_path or path, parts.query, ''))
    toggled = path[:-1] if path.endswith('/') and path != '/' else path + '/'
    out = [
        {'name': 'http_root', 'url': build('http', root)},
        {'name': 'https_root', 'url': build('https', root)},
        {'name': 'http_www', 'url': build('http', www)},
        {'name': 'https_www', 'url': build('https', www)},
        {'name': 'trailing_slash', 'url': build(parts.scheme, host, toggled)},
        {'name': 'uppercase', 'url': build(parts.scheme, host, path.upper())},
    ]
    return out


def probe_variants(url, fetcher, max_redirects=5, delay=POLITE_DELAY):
    probes = []
    for variant in variant_urls(url):
        if delay:
            time.sleep(delay)
        result = follow_redirects(variant['url'], fetcher, max_redirects=max_redirects)
        final = result.get('final') or {}
        probes.append({
            'name': variant['name'], 'url': variant['url'],
            'status': final.get('status'),
            'final_url': result.get('final_url'),
            'chain_statuses': [hop.get('status') for hop in result.get('chain', [])],
            'hops': result.get('hops'),
            'loop_detected': result.get('loop_detected'),
            'error': final.get('error'),
        })
    return probes


def duplicate_summary(probes):
    """Distinct 200-responding targets among URL variants; None when not probed."""
    if not probes:
        return None
    return sorted({canonical_form(p['final_url']) for p in probes
                   if p.get('status') == 200 and p.get('final_url')})


def check_indexability(transport, crawl, canonical, directives):
    blockers = []
    if transport['evidence'].get('status') in (None,):
        blockers.append('ответ сервера не получен')
    elif (transport['evidence']['status'] or 0) >= 400:
        blockers.append('код ответа %s' % transport['evidence']['status'])
    if crawl['evidence'].get('googlebot_allowed') is False:
        blockers.append('запрет в robots.txt: %s' % crawl['evidence'].get('googlebot_rule'))
    if directives['noindex']:
        blockers.append('noindex (%s)' % ', '.join(directives['noindex_sources']))
    if canonical['evidence'].get('mismatch'):
        blockers.append('канонический URL указывает на другую страницу (не строгий блокер, но сигнал)')
    unknowns = []
    if crawl['evidence'].get('googlebot_allowed') is None:
        unknowns.append('robots.txt недоступен')
    evidence = {'blockers': blockers, 'unknowns': unknowns,
                'status': transport['evidence'].get('status'),
                'robots_allowed': crawl['evidence'].get('googlebot_allowed'),
                'noindex': directives['noindex'],
                'noindex_sources': directives['noindex_sources'],
                'canonical_effective': canonical['evidence'].get('canonical_effective')}
    hard = [b for b in blockers if 'не строгий блокер' not in b]
    if hard:
        evidence['indexable'] = False
        return verdict('indexability', 'fail',
                       'Страница не индексируется: ' + '; '.join(hard) + '.', evidence)
    if unknowns:
        evidence['indexable'] = None
        return verdict('indexability', 'unknown',
                       'Вывод невозможен: ' + '; '.join(unknowns) + '.', evidence)
    evidence['indexable'] = True
    if blockers:
        return verdict('indexability', 'warn',
                       'Явных блокировок нет, но есть сигналы: ' + '; '.join(blockers) + '.', evidence)
    return verdict('indexability', 'ok', 'Явных препятствий для индексации не найдено.', evidence)


def check_head_meta(final_url, facts, favicon=None):
    title = facts.title
    description = facts.meta('description')
    evidence = {
        'title': {'text': title, 'length_chars': None if title is None else len(title),
                  'pixel_width_approx': None if title is None else title_pixel_width(title),
                  'pixel_note_ru': 'Ширина приблизительная: таблица средних ширин символов, Arial ~20px.'},
        'meta_description': {'text': description,
                             'length_chars': None if description is None else len(description)},
        'meta_keywords': facts.meta('keywords'),
        'viewport': facts.meta('viewport'),
        'charset_meta': facts.charset_meta,
        'html_lang': facts.html_lang,
        'open_graph': facts.meta_prefix('og:'),
        'twitter': facts.meta_prefix('twitter:'),
        'favicon': favicon,
    }
    problems, level = [], 'ok'
    if not title:
        problems.append('title отсутствует')
        level = 'fail'
    else:
        if len(title) < 10:
            problems.append('title короче 10 символов')
            level = 'warn'
        if len(title) > 70:
            problems.append('title длиннее 70 символов')
            level = 'warn'
        if evidence['title']['pixel_width_approx'] > 600:
            problems.append('приблизительная ширина title выше 600 px')
            level = 'warn'
    if not description:
        problems.append('meta description отсутствует')
        level = 'fail' if level == 'fail' else 'warn'
    elif not 50 <= len(description) <= 320:
        problems.append('длина meta description %d символов вне диапазона 50–320' % len(description))
        level = 'fail' if level == 'fail' else 'warn'
    if not evidence['viewport']:
        problems.append('нет meta viewport')
        level = 'fail' if level == 'fail' else 'warn'
    if not evidence['charset_meta']:
        problems.append('нет meta charset')
        level = 'fail' if level == 'fail' else 'warn'
    if not evidence['html_lang']:
        problems.append('нет атрибута lang у html')
        level = 'fail' if level == 'fail' else 'warn'
    if not evidence['open_graph']:
        problems.append('нет Open Graph разметки')
        level = 'fail' if level == 'fail' else 'warn'
    return verdict('head_meta', level,
                   '; '.join(problems) + '.' if problems else 'Основные мета-теги на месте.',
                   evidence)


def check_headings(facts):
    outline = [{'index': i, 'level': h['level'], 'text': h['text']}
               for i, h in enumerate(facts.headings)]
    h1 = [h for h in outline if h['level'] == 1]
    empty = [h for h in outline if not h['text']]
    jumps, previous = [], None
    for item in outline:
        if previous is not None and item['level'] - previous > 1:
            jumps.append({'from': previous, 'to': item['level'], 'index': item['index']})
        previous = item['level']
    evidence = {'outline': outline, 'total': len(outline), 'h1_count': len(h1),
                'h1_texts': [h['text'] for h in h1], 'empty_headings': len(empty),
                'empty_heading_indexes': [h['index'] for h in empty], 'level_jumps': jumps,
                'counts_by_level': {'h%d' % n: sum(1 for h in outline if h['level'] == n)
                                    for n in range(1, 7)}}
    problems, level = [], 'ok'
    if len(h1) == 0:
        problems.append('H1 отсутствует')
        level = 'fail'
    elif len(h1) > 1:
        problems.append('найдено %d тегов H1' % len(h1))
        level = 'warn'
    if empty:
        problems.append('пустых заголовков: %d' % len(empty))
        level = 'fail' if level == 'fail' else 'warn'
    if jumps:
        problems.append('пропуски уровней: %d' % len(jumps))
        level = 'fail' if level == 'fail' else 'warn'
    if not outline:
        return verdict('headings', 'fail', 'Заголовки H1–H6 не найдены.', evidence)
    return verdict('headings', level,
                   '; '.join(problems) + '.' if problems else 'Структура заголовков корректна.',
                   evidence)


DATE_PATTERNS = [
    r'\b(\d{4}-\d{2}-\d{2})\b',
    r'\b(\d{1,2}\.\d{1,2}\.\d{4})\b',
    r'\b(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})\b',
]


def detect_language(text):
    letters = [ch for ch in (text or '') if ch.isalpha()]
    if len(letters) < 40:
        return {'detected': None, 'method': 'insufficient_text',
                'note_ru': 'Текста слишком мало для определения языка.'}
    cyrillic = sum(1 for ch in letters if '\u0400' <= ch <= '\u04ff')
    latin = sum(1 for ch in letters if 'a' <= ch.lower() <= 'z')
    share = cyrillic / len(letters)
    if share > 0.6:
        detected = 'ru'
    elif latin / len(letters) > 0.6:
        detected = 'en'
    else:
        detected = None
    return {'detected': detected, 'cyrillic_share': round(share, 3),
            'latin_share': round(latin / len(letters), 3), 'method': 'alphabet_heuristic',
            'note_ru': 'Грубая эвристика по алфавиту: различает только кириллицу и латиницу.'}


def check_content(facts, html_text, structured_types_data=None):
    words = [w for w in re.split(r'[^\w\u0400-\u04ff-]+', facts.text) if w]
    ratio = None
    if facts.html_length:
        ratio = round(len(facts.text) / facts.html_length, 4)
    published, updated = None, None
    for item in (structured_types_data or []):
        if isinstance(item, dict):
            published = published or item.get('datePublished')
            updated = updated or item.get('dateModified')
    meta_published = None
    for entry in facts.metas:
        key = (entry.get('property') or entry.get('name') or '').lower()
        if key in ('article:published_time', 'datepublished'):
            meta_published = meta_published or entry.get('content')
        if key in ('article:modified_time', 'og:updated_time', 'datemodified'):
            updated = updated or entry.get('content')
    published = published or meta_published
    visible_dates = []
    for pattern in DATE_PATTERNS:
        visible_dates += re.findall(pattern, facts.text)
    language = detect_language(facts.text)
    evidence = {
        'word_count': len(words), 'char_count': len(facts.text),
        'html_length': facts.html_length, 'text_to_html_ratio': ratio,
        'paragraphs': facts.paragraphs,
        'published_date': published, 'updated_date': updated,
        'visible_dates_in_text': visible_dates[:10],
        'declared_lang': facts.html_lang, 'detected_language': language,
        'lang_mismatch': (None if not language.get('detected') or not facts.html_lang
                          else not facts.html_lang.lower().startswith(language['detected'])),
        'text_sample': facts.text[:400],
    }
    problems, level = [], 'ok'
    if len(words) < 50:
        problems.append('текста мало: %d слов' % len(words))
        level = 'fail'
    elif len(words) < 300:
        problems.append('объём текста ниже 300 слов (%d)' % len(words))
        level = 'warn'
    if ratio is not None and ratio < 0.05:
        problems.append('отношение текста к HTML %.3f' % ratio)
        level = 'fail' if level == 'fail' else 'warn'
    if not published and not visible_dates:
        problems.append('дата публикации не обнаружена')
        level = 'fail' if level == 'fail' else 'warn'
    if evidence['lang_mismatch']:
        problems.append('объявленный lang="%s" не совпадает с эвристикой (%s)'
                        % (facts.html_lang, language['detected']))
        level = 'fail' if level == 'fail' else 'warn'
    return verdict('content', level,
                   '; '.join(problems) + '.' if problems else 'Контент по базовым метрикам в норме.',
                   evidence)


def check_links(facts, final_url):
    base = facts.base_href or final_url
    host = (urlsplit(final_url).hostname or '').lower()
    internal, external, rel_counts = [], [], {}
    empty_anchors, same_page, other_schemes = 0, 0, []
    for link in facts.links:
        href = (link.get('href') or '').strip()
        rels = [r.lower() for r in (link.get('rel') or '').split()]
        for rel in rels:
            rel_counts[rel] = rel_counts.get(rel, 0) + 1
        if not href:
            continue
        if href.lower().startswith(('mailto:', 'tel:', 'javascript:', 'data:')):
            other_schemes.append(href[:80])
            continue
        absolute = urljoin(base, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ('http', 'https'):
            other_schemes.append(absolute[:80])
            continue
        entry = {'href': href, 'absolute': absolute, 'anchor': link.get('text'),
                 'rel': ' '.join(rels) or None}
        if (parts.hostname or '').lower() == host:
            internal.append(entry)
            if canonical_form(absolute) == canonical_form(final_url):
                same_page += 1
        else:
            external.append(entry)
        if not link.get('text'):
            empty_anchors += 1
    evidence = {
        'total_links': len(facts.links),
        'internal_count': len(internal), 'external_count': len(external),
        'unique_internal_targets': len({canonical_form(e['absolute']) for e in internal}),
        'same_page_links': same_page, 'empty_anchors': empty_anchors,
        'rel_values': {'nofollow': rel_counts.get('nofollow', 0), 'ugc': rel_counts.get('ugc', 0),
                       'sponsored': rel_counts.get('sponsored', 0), 'all': rel_counts},
        'external_domains': sorted({(urlsplit(e['absolute']).hostname or '').lower()
                                    for e in external}),
        'internal_anchors': [{'anchor': e['anchor'], 'url': e['absolute'], 'rel': e['rel']}
                             for e in internal],
        'external_links': external,
        'non_http_links': other_schemes,
    }
    problems, level = [], 'ok'
    if empty_anchors:
        problems.append('ссылок без анкорного текста: %d' % empty_anchors)
        level = 'warn'
    if not internal:
        problems.append('нет внутренних ссылок')
        level = 'fail'
    if rel_counts.get('nofollow') and len(internal) and rel_counts['nofollow'] >= len(internal):
        problems.append('много внутренних ссылок с nofollow')
        level = 'fail' if level == 'fail' else 'warn'
    return verdict('links', level,
                   '; '.join(problems) + '.' if problems else 'Ссылочная структура без явных проблем.',
                   evidence)


NEXT_GEN = ('.webp', '.avif')


def check_images(facts, final_url, fetcher=None, rules=None, cap=IMAGE_HEAD_CAP,
                 delay=POLITE_DELAY):
    base = facts.base_href or final_url
    rows = []
    for img in facts.images:
        src = (img.get('src') or img.get('data-src') or '').strip()
        absolute = urljoin(base, src) if src else None
        alt = img.get('alt')
        rows.append({
            'src': src or None, 'absolute': absolute,
            'alt': alt, 'alt_missing': 'alt' not in img,
            'alt_empty': 'alt' in img and (alt or '').strip() == '',
            'alt_length': None if alt is None else len(alt),
            'alt_too_long': bool(alt and len(alt) > 125),
            'width': img.get('width') or None, 'height': img.get('height') or None,
            'has_dimensions': bool(img.get('width') and img.get('height')),
            'loading': img.get('loading') or None,
            'lazy': (img.get('loading') or '').lower() == 'lazy' or 'data-src' in img,
            'next_gen': bool(absolute and urlsplit(absolute).path.lower().endswith(NEXT_GEN)),
            'bytes': None, 'head_status': None,
        })
    sizes_status = 'not_requested'
    if fetcher is not None:
        sizes_status = 'requested_head'
        checked = 0
        for row in rows:
            if checked >= cap or not row['absolute']:
                continue
            if rules is not None and not _own_allowed(rules, row['absolute']):
                row['head_status'] = 'robots_disallow'
                continue
            if delay:
                time.sleep(delay)
            record = fetcher(row['absolute'], method='HEAD')
            checked += 1
            row['head_status'] = record.get('status') or record.get('error')
            length = (record.get('headers') or {}).get('content-length')
            row['bytes'] = int(length) if (length or '').isdigit() else None
        if checked == 0:
            sizes_status = 'no_images_requested'
    evidence = {
        'total': len(rows),
        'missing_alt': sum(1 for r in rows if r['alt_missing']),
        'empty_alt': sum(1 for r in rows if r['alt_empty']),
        'alt_too_long': sum(1 for r in rows if r['alt_too_long']),
        'without_dimensions': sum(1 for r in rows if not r['has_dimensions']),
        'lazy_loading': sum(1 for r in rows if r['lazy']),
        'next_gen_format': sum(1 for r in rows if r['next_gen']),
        'sizes_status': sizes_status,
        'head_cap': cap,
        'images': rows,
    }
    if not rows:
        return verdict('images', 'unknown', 'Изображений в HTML не найдено; проверять нечего.', evidence)
    problems, level = [], 'ok'
    if evidence['missing_alt']:
        problems.append('без атрибута alt: %d' % evidence['missing_alt'])
        level = 'fail'
    if evidence['alt_too_long']:
        problems.append('alt длиннее 125 символов: %d' % evidence['alt_too_long'])
        level = 'fail' if level == 'fail' else 'warn'
    if evidence['without_dimensions']:
        problems.append('без width/height: %d' % evidence['without_dimensions'])
        level = 'fail' if level == 'fail' else 'warn'
    if evidence['next_gen_format'] == 0:
        problems.append('нет форматов WebP/AVIF')
        level = 'fail' if level == 'fail' else 'warn'
    return verdict('images', level,
                   '; '.join(problems) + '.' if problems else 'Изображения размечены корректно.',
                   evidence)


def _iter_jsonld_nodes(value):
    if isinstance(value, dict):
        if '@graph' in value and isinstance(value['@graph'], list):
            for item in value['@graph']:
                yield from _iter_jsonld_nodes(item)
        yield value
        for key in ('mainEntity', 'itemListElement', 'author', 'publisher'):
            child = value.get(key)
            if isinstance(child, (dict, list)):
                yield from _iter_jsonld_nodes(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_jsonld_nodes(item)


def check_structured_data(facts):
    parsed, errors, nodes = [], [], []
    for index, raw in enumerate(facts.jsonld_raw):
        try:
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            errors.append({'block_index': index, 'error': _scrub(str(exc)),
                           'snippet': (raw or '').strip()[:200]})
            continue
        parsed.append({'block_index': index, 'data': data})
        nodes.extend(list(_iter_jsonld_nodes(data)))
    types = []
    for node in nodes:
        node_type = node.get('@type')
        for value in (node_type if isinstance(node_type, list) else [node_type]):
            if isinstance(value, str) and value not in types:
                types.append(value)
    required = []
    for node in nodes:
        node_type = node.get('@type')
        for value in (node_type if isinstance(node_type, list) else [node_type]):
            if not isinstance(value, str) or value not in SCHEMA_REQUIRED:
                continue
            need = SCHEMA_REQUIRED[value]
            missing = [k for k in need if not node.get(k)]
            required.append({'type': value, 'required': need,
                             'present': [k for k in need if node.get(k)], 'missing': missing})
    evidence = {
        'jsonld_blocks_total': len(facts.jsonld_raw),
        'jsonld_blocks_parsed': len(parsed),
        'jsonld_parse_errors_count': len(errors),
        'jsonld_parse_errors': errors,
        'types': types,
        'required_properties': required,
        'microdata_present': facts.has_microdata,
        'rdfa_present': facts.has_rdfa,
        'blocks': parsed,
        'heuristic_note': HEURISTIC_NOTE,
    }
    if not facts.jsonld_raw and not facts.has_microdata and not facts.has_rdfa:
        return verdict('structured_data', 'warn',
                       'Структурированные данные не найдены (JSON-LD, микроданные, RDFa).', evidence)
    problems, level = [], 'ok'
    if errors:
        problems.append('блоков JSON-LD с ошибкой разбора: %d' % len(errors))
        level = 'fail'
    incomplete = [r for r in required if r['missing']]
    if incomplete:
        problems.append('не хватает обязательных свойств: '
                        + '; '.join('%s → %s' % (r['type'], ', '.join(r['missing']))
                                    for r in incomplete))
        level = 'fail' if level == 'fail' else 'warn'
    return verdict('structured_data', level,
                   ('; '.join(problems) + '. ' if problems else 'Разметка разобрана без ошибок. ')
                   + HEURISTIC_NOTE, evidence)


HREFLANG_RE = re.compile(r'^(x-default|[a-z]{2,3}(-[A-Za-z]{4})?(-([A-Za-z]{2}|\d{3}))?)$', re.I)


def check_hreflang(final_url, facts, headers, fetcher=None, rules=None, delay=POLITE_DELAY):
    entries = []
    for tag in facts.link_tags:
        rels = (tag.get('rel') or '').lower().split()
        if 'alternate' in rels and tag.get('hreflang'):
            entries.append({'source': 'html', 'hreflang': tag['hreflang'],
                            'url': urljoin(facts.base_href or final_url, tag.get('href') or '')})
    for entry in parse_link_header((headers or {}).get('link')):
        if 'alternate' in (entry.get('rel') or '').lower().split() and entry.get('hreflang'):
            entries.append({'source': 'http_header', 'hreflang': entry['hreflang'],
                            'url': urljoin(final_url, entry['url'])})
    malformed = [e['hreflang'] for e in entries if not HREFLANG_RE.match(e['hreflang'] or '')]
    self_ref = any(canonical_form(e['url']) == canonical_form(final_url) for e in entries)
    reachability = None
    if entries and fetcher is not None:
        reachability = []
        for entry in entries[:HREFLANG_PROBE_CAP]:
            if rules is not None and not _own_allowed(rules, entry['url']):
                reachability.append({'url': entry['url'], 'status': None,
                                     'note': 'robots_disallow'})
                continue
            if delay:
                time.sleep(delay)
            result = follow_redirects(entry['url'], fetcher, max_redirects=3)
            final = result.get('final') or {}
            reachability.append({'url': entry['url'], 'status': final.get('status'),
                                 'final_url': result.get('final_url'),
                                 'error': final.get('error')})
    evidence = {'entries': entries, 'count': len(entries), 'malformed': malformed,
                'self_reference': self_ref if entries else None,
                'reachability': reachability,
                'reachability_status': 'checked' if reachability is not None
                else ('not_requested' if entries else 'no_entries')}
    if not entries:
        return verdict('hreflang', 'unknown',
                       'Аннотации hreflang отсутствуют: многоязычность не заявлена, проверять нечего.',
                       evidence)
    problems, level = [], 'ok'
    if malformed:
        problems.append('некорректные коды: %s' % ', '.join(malformed))
        level = 'fail'
    if not self_ref:
        problems.append('нет самоссылки hreflang')
        level = 'fail'
    if reachability:
        bad = [r for r in reachability if r.get('status') != 200]
        if bad:
            problems.append('недоступных альтернатив: %d' % len(bad))
            level = 'fail' if level == 'fail' else 'warn'
    return verdict('hreflang', level,
                   '; '.join(problems) + '.' if problems else 'Аннотации hreflang корректны.',
                   evidence)


def check_sitemaps(final_url, rules, fetcher=None, raw_dir=None, cap=SITEMAP_CAP,
                   delay=POLITE_DELAY):
    evidence = {'sitemaps_in_robots': None, 'fetched': [], 'url_found': None,
                'lastmod_for_url': None, 'cap': cap, 'urls_scanned': 0}
    if rules is None:
        return verdict('sitemaps', 'unknown',
                       'robots.txt недоступен: список карт сайта неизвестен.', evidence)
    evidence['sitemaps_in_robots'] = list(rules.sitemaps)
    if not rules.sitemaps:
        return verdict('sitemaps', 'warn', 'В robots.txt нет директив Sitemap.', evidence)
    if fetcher is None:
        return verdict('sitemaps', 'unknown',
                       'Карты сайта не запрашивались (сетевые дополнения отключены).', evidence)
    target = canonical_form(final_url)
    found, lastmod = False, None
    queue = list(rules.sitemaps)[:cap]
    fetched_count = 0
    while queue and fetched_count < cap:
        url = queue.pop(0)
        if not _own_allowed(rules, url):
            evidence['fetched'].append({'url': url, 'status': None, 'note': 'robots_disallow'})
            continue
        if delay:
            time.sleep(delay)
        record = fetcher(url)
        fetched_count += 1
        text = ''
        if record.get('body'):
            text = record['body'].decode('utf-8', errors='replace')
        entry = {'url': url, 'status': record.get('status'), 'error': record.get('error'),
                 'bytes': record.get('size_bytes'), 'is_index': '<sitemapindex' in text.lower(),
                 'truncated': bool(record.get('truncated'))}
        if entry['truncated']:
            evidence['any_truncated'] = True
        if entry['error'] or (entry['status'] and entry['status'] >= 400):
            evidence['any_unreadable'] = True
        if raw_dir is not None and record.get('body'):
            name = 'sitemap_%d.xml' % fetched_count
            (Path(raw_dir) / name).write_bytes(record['body'])
            entry['raw_file'] = 'raw/' + name
        if entry['is_index'] and fetched_count < cap:
            children = re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', text)
            entry['child_sitemaps'] = len(children)
            # The cap means we may only sample an index: record the shortfall so the
            # verdict can never claim full coverage it did not have.
            budget = cap - fetched_count
            if len(children) > budget:
                evidence['unvisited_sitemaps'] = (evidence.get('unvisited_sitemaps', 0)
                                                  + len(children) - budget)
            queue.extend(children[:budget])
        else:
            for block in re.findall(r'<url>(.*?)</url>', text, re.S):
                loc = re.search(r'<loc>\s*([^<\s]+)\s*</loc>', block)
                evidence['urls_scanned'] += 1
                if loc and canonical_form(loc.group(1)) == target:
                    found = True
                    mod = re.search(r'<lastmod>\s*([^<\s]+)\s*</lastmod>', block)
                    lastmod = mod.group(1) if mod else None
                    entry['contains_audited_url'] = True
        evidence['fetched'].append(entry)
    evidence['url_found'] = found
    evidence['lastmod_for_url'] = lastmod
    if not any(e.get('status') == 200 for e in evidence['fetched']):
        return verdict('sitemaps', 'unknown', 'Ни одна карта сайта не получена.', evidence)
    if not found:
        # "Not found" is only a finding when coverage was actually complete.
        # Timeouts, errors, truncation or an unvisited index tail all mean the
        # URL's absence was never established — that is 'unknown', not 'warn'.
        gaps = []
        if evidence.get('any_truncated'):
            gaps.append('часть карт прочитана не полностью (лимит %d МБ)'
                        % (MAX_FETCH_BYTES // (1024 * 1024)))
        if evidence.get('any_unreadable'):
            gaps.append('часть карт не получена (таймаут или ошибка)')
        if evidence.get('unvisited_sitemaps'):
            gaps.append('не проверено карт из индекса: %d (лимит --sitemap-cap=%d)'
                        % (evidence['unvisited_sitemaps'], cap))
        if not evidence.get('urls_scanned'):
            gaps.append('ни одного URL не просканировано')
        if gaps:
            return verdict('sitemaps', 'unknown',
                           'Отсутствие URL в картах сайта не доказано: %s.' % '; '.join(gaps),
                           evidence)
        return verdict('sitemaps', 'warn',
                       'URL не найден в проверенных картах сайта (просканировано %d URL).'
                       % evidence['urls_scanned'], evidence)
    if not lastmod:
        return verdict('sitemaps', 'warn', 'URL есть в карте сайта, но без lastmod.', evidence)
    return verdict('sitemaps', 'ok', 'URL присутствует в карте сайта, lastmod %s.' % lastmod, evidence)


def _own_allowed(rules, url):
    """Respect robots.txt for the agent's own extra fetches (same host only)."""
    if rules is None:
        return True
    parts = urlsplit(url)
    path = (parts.path or '/') + (('?' + parts.query) if parts.query else '')
    return rules.verdict(path, OWN_AGENT_TOKEN)['allowed']


# --------------------------------------------------------------------------- rendering

def find_renderer():
    """Locate a headless Chromium binary from the Playwright cache, else npx agent-browser."""
    candidates = []
    cache = Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
                 or (Path.home() / 'Library/Caches/ms-playwright'))
    if cache.is_dir():
        for directory in sorted(cache.glob('chromium_headless_shell-*'), reverse=True):
            candidates += list(directory.glob('*/chrome-headless-shell'))
        for directory in sorted(cache.glob('chromium-*'), reverse=True):
            candidates += list(directory.glob('*/Chromium.app/Contents/MacOS/Chromium'))
            candidates += list(directory.glob('*/chrome'))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return {'kind': 'chromium', 'command': [str(candidate)]}
    from shutil import which
    if which('npx'):
        return {'kind': 'agent-browser', 'command': ['npx', '--yes', 'agent-browser']}
    return None


def check_rendering_skipped():
    return verdict('rendering', 'unknown',
                   'Рендеринг не запрашивался: запустите с --render, чтобы сравнить HTML и DOM.',
                   {'rendered_word_count': None, 'rendered_link_count': None,
                    'raw_word_count': None, 'raw_link_count': None, 'renderer': None})


def check_rendering(url, raw_word_count, raw_link_count, raw_dir, renderer_finder=find_renderer,
                    timeout=60):
    evidence = {'raw_word_count': raw_word_count, 'raw_link_count': raw_link_count,
                'rendered_word_count': None, 'rendered_link_count': None, 'renderer': None,
                'renderer_kind': None, 'error': None, 'raw_file': None,
                'word_delta': None, 'link_delta': None}
    renderer = renderer_finder()
    if not renderer:
        evidence['error'] = 'no_renderer_available'
        return verdict('rendering', 'unknown',
                       'Рендеринг не выполнен: headless-браузер не найден на этой машине.', evidence)
    evidence['renderer_kind'] = renderer['kind']
    evidence['renderer'] = ' '.join(renderer['command'])
    try:
        if renderer['kind'] == 'chromium':
            import tempfile
            with tempfile.TemporaryDirectory() as profile:
                command = renderer['command'] + [
                    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                    '--user-data-dir=' + profile, '--virtual-time-budget=8000',
                    '--dump-dom', url]
                proc = subprocess.run(command, capture_output=True, timeout=timeout)
        else:
            proc = subprocess.run(renderer['command'] + ['--dump-dom', url],
                                  capture_output=True, timeout=timeout)
        rendered = proc.stdout.decode('utf-8', errors='replace')
        if not rendered.strip():
            evidence['error'] = 'empty_dom (exit %s)' % proc.returncode
            return verdict('rendering', 'unknown',
                           'Рендеринг не дал DOM: результат пустой, данные недоступны.', evidence)
    except Exception as exc:  # noqa: BLE001
        evidence['error'] = '%s: %s' % (type(exc).__name__, _scrub(str(exc)))
        return verdict('rendering', 'unknown',
                       'Рендеринг завершился ошибкой: данные недоступны.', evidence)
    if raw_dir is not None:
        (Path(raw_dir) / 'rendered.html').write_text(rendered, encoding='utf-8')
        evidence['raw_file'] = 'raw/rendered.html'
    facts = parse_html(rendered)
    rendered_words = len([w for w in re.split(r'[^\w\u0400-\u04ff-]+', facts.text) if w])
    rendered_links = len([l for l in facts.links if (l.get('href') or '').strip()])
    evidence['rendered_word_count'] = rendered_words
    evidence['rendered_link_count'] = rendered_links
    evidence['word_delta'] = None if raw_word_count is None else rendered_words - raw_word_count
    evidence['link_delta'] = None if raw_link_count is None else rendered_links - raw_link_count
    if raw_word_count and rendered_words > raw_word_count * 1.3:
        return verdict('rendering', 'warn',
                       'После рендеринга слов больше на %d: контент зависит от JavaScript.'
                       % evidence['word_delta'], evidence)
    if raw_word_count and rendered_words < raw_word_count * 0.7:
        return verdict('rendering', 'warn',
                       'После рендеринга слов меньше на %d: часть контента удаляется скриптами.'
                       % abs(evidence['word_delta']), evidence)
    return verdict('rendering', 'ok',
                   'Существенных различий между исходным HTML и DOM не обнаружено.', evidence)


# --------------------------------------------------------------------------- performance

PSI_FIELD_KEYS = {'LARGEST_CONTENTFUL_PAINT_MS': 'LCP_ms',
                  'INTERACTION_TO_NEXT_PAINT': 'INP_ms',
                  'CUMULATIVE_LAYOUT_SHIFT_SCORE': 'CLS_x100'}
PSI_LAB_AUDITS = ('largest-contentful-paint', 'cumulative-layout-shift', 'total-blocking-time',
                  'first-contentful-paint', 'speed-index', 'interactive')


def check_performance(url, key, fetcher, env_name, raw_dir, timeout=60, delay=POLITE_DELAY):
    evidence = {'psi_env_var': env_name, 'strategies': {}, 'field_data': None, 'lab_data': None,
                'raw_files': [], 'note_ru':
                'Полевые данные CrUX и лабораторные метрики Lighthouse — разные источники; '
                'лабораторные значения не являются полевыми.'}
    if not key:
        return verdict('performance', 'unknown',
                       'Данные PageSpeed Insights недоступны: нужен ключ API в переменной '
                       'окружения %s. Core Web Vitals локально не оцениваются.' % env_name,
                       evidence)
    if fetcher is None:
        return verdict('performance', 'unknown',
                       'Запросы к PageSpeed Insights отключены (--no-network-extras).', evidence)
    field, lab = {}, {}
    for strategy in ('mobile', 'desktop'):
        request_url = ('%s?url=%s&strategy=%s&category=performance&key=%s'
                       % (PSI_ENDPOINT, quote(url, safe=''), strategy, quote(key, safe='')))
        if delay:
            time.sleep(delay)
        record = fetcher(request_url)
        safe_url = request_url.replace(key, '[REDACTED]')
        status = {'status': record.get('status'), 'error': record.get('error'),
                  'request_url_redacted': safe_url}
        body = record.get('body') or b''
        data = None
        if body:
            try:
                data = json.loads(body.decode('utf-8', errors='replace'))
            except Exception as exc:  # noqa: BLE001
                status['parse_error'] = _scrub(str(exc))
        if data is not None and raw_dir is not None:
            name = 'psi_%s.json' % strategy
            save_json(Path(raw_dir) / name, data)
            evidence['raw_files'].append('raw/' + name)
            status['raw_file'] = 'raw/' + name
        if isinstance(data, dict) and record.get('status') == 200:
            metrics = ((data.get('loadingExperience') or {}).get('metrics') or {})
            field[strategy] = {PSI_FIELD_KEYS[k]: (metrics[k] or {}).get('percentile')
                               for k in PSI_FIELD_KEYS if k in metrics} or None
            if field.get(strategy):
                field[strategy]['categories'] = {PSI_FIELD_KEYS[k]: (metrics[k] or {}).get('category')
                                                 for k in PSI_FIELD_KEYS if k in metrics}
                field[strategy]['source'] = 'CrUX field data'
            audits = ((data.get('lighthouseResult') or {}).get('audits') or {})
            lab[strategy] = {k: {'numericValue': (audits.get(k) or {}).get('numericValue'),
                                 'displayValue': (audits.get(k) or {}).get('displayValue')}
                             for k in PSI_LAB_AUDITS if k in audits}
            score = (((data.get('lighthouseResult') or {}).get('categories') or {})
                     .get('performance') or {}).get('score')
            lab[strategy]['performance_score'] = score
            lab[strategy]['source'] = 'Lighthouse lab data'
        evidence['strategies'][strategy] = status
    evidence['field_data'] = field or None
    evidence['lab_data'] = lab or None
    if not field and not lab:
        return verdict('performance', 'unknown',
                       'PageSpeed Insights не вернул данные: ответ пустой или с ошибкой.', evidence)
    if not field:
        return verdict('performance', 'unknown',
                       'Полевые данные CrUX отсутствуют (мало трафика). Есть только лабораторные '
                       'метрики Lighthouse, их нельзя считать полевыми.', evidence)
    lcp = (field.get('mobile') or {}).get('LCP_ms')
    cls = (field.get('mobile') or {}).get('CLS_x100')
    inp = (field.get('mobile') or {}).get('INP_ms')
    problems = []
    if lcp is not None and lcp > 2500:
        problems.append('LCP %s мс выше 2500' % lcp)
    if inp is not None and inp > 200:
        problems.append('INP %s мс выше 200' % inp)
    if cls is not None and cls > 10:
        problems.append('CLS %.2f выше 0.10' % (cls / 100))
    if problems:
        return verdict('performance', 'warn',
                       'Полевые Core Web Vitals (mobile): ' + '; '.join(problems) + '.', evidence)
    return verdict('performance', 'ok',
                   'Полевые Core Web Vitals (mobile) в пределах порогов Google.', evidence)


def check_favicon(final_url, facts, fetcher=None, rules=None):
    href = None
    for tag in facts.link_tags:
        rels = (tag.get('rel') or '').lower().split()
        if any(r in rels for r in ('icon', 'shortcut', 'apple-touch-icon')) and tag.get('href'):
            href = urljoin(facts.base_href or final_url, tag['href'])
            break
    info = {'declared': href, 'status': None, 'bytes': None, 'content_type': None,
            'aspect_ratio': None, 'note_ru': None}
    if not href:
        info['note_ru'] = 'Favicon не объявлен в HTML.'
        return info
    if fetcher is None:
        info['note_ru'] = 'Favicon не запрашивался (сетевые дополнения отключены).'
        return info
    if not _own_allowed(rules, href):
        info['note_ru'] = 'Запрос favicon запрещён robots.txt.'
        return info
    record = fetcher(href)
    info['status'] = record.get('status') or record.get('error')
    info['bytes'] = record.get('size_bytes')
    info['content_type'] = (record.get('headers') or {}).get('content-type')
    size = _image_dimensions(record.get('body') or b'')
    if size:
        info['width'], info['height'] = size
        info['aspect_ratio'] = round(size[0] / size[1], 3) if size[1] else None
    else:
        info['note_ru'] = 'Размеры favicon не определены: формат не распознан локально.'
    return info


def _image_dimensions(data):
    """PNG/GIF header sizes only; other formats return None (never guessed)."""
    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24:
        return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if data[:6] in (b'GIF87a', b'GIF89a') and len(data) >= 10:
        return int.from_bytes(data[6:8], 'little'), int.from_bytes(data[8:10], 'little')
    return None


# --------------------------------------------------------------------------- report

def build_issues(checks):
    issues = []
    for index, (name, check) in enumerate(checks.items(), 1):
        if check['verdict'] == 'ok':
            continue
        issues.append({
            'id': '%s-%02d' % (name.upper().replace('_', '-'), index),
            'category': CHECK_TITLES.get(name, name),
            'severity': SEVERITY.get(check['verdict'], 'нет'),
            'verdict': check['verdict'],
            'element': _issue_element(name, check),
            'evidence': check['reason_ru'],
            'recommendation': RECOMMENDATIONS.get(name, 'Проверить вручную.'),
        })
    return issues


def _issue_element(name, check):
    evidence = check.get('evidence') or {}
    for key in ('final_url', 'requested_url', 'matched_path', 'canonical_effective', 'psi_env_var'):
        if evidence.get(key):
            return str(evidence[key])
    return CHECK_TITLES.get(name, name)


def write_issues_csv(path, issues):
    columns = ['id', 'category', 'severity', 'verdict', 'element', 'evidence', 'recommendation']
    with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for issue in issues:
            cells = [display(issue.get(col)) for col in columns]
            # Prevent spreadsheet formula injection; audit.json keeps exact strings.
            writer.writerow(["'" + c if c.lstrip().startswith(('=', '+', '-', '@', '\t', '\r'))
                             else c for c in cells])


CSS = """:root{--bg:#0c1424;--panel:#152136;--line:#30405a;--text:#e6edf7;--muted:#a8c5ef;
--accent:#92d6ff;--ok:#5fd38d;--warn:#ffd58b;--fail:#ff8f8f;--unknown:#b7c4d8}
*{box-sizing:border-box}body{font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--text);margin:0;padding:28px}main{max-width:1500px;margin:auto}
h1,h2,h3{color:var(--accent);margin:0 0 12px}section{background:var(--panel);padding:20px;
margin:18px 0;border-radius:12px;border:1px solid var(--line)}table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;
max-width:620px;overflow-wrap:anywhere}th{color:var(--muted);font-weight:600}
.scroll{overflow:auto}.badge{display:inline-block;padding:2px 10px;border-radius:20px;
font-size:13px;font-weight:600;color:#0c1424}.b-ok{background:var(--ok)}.b-warn{background:var(--warn)}
.b-fail{background:var(--fail)}.b-unknown{background:var(--unknown)}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}.card{background:var(--bg);
border:1px solid var(--line);border-radius:10px;padding:12px 18px;min-width:120px}
.card b{display:block;font-size:22px;color:var(--accent)}.muted{color:var(--muted)}
.note{color:var(--warn)}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}"""


def _esc(value):
    return escape(display(value), quote=True)


def _render_value(value, depth=0):
    if isinstance(value, dict):
        if not value:
            return '<span class="muted">пусто</span>'
        if depth > 4:
            return '<pre>' + _esc(value) + '</pre>'
        rows = ''.join('<tr><th>' + _esc(k) + '</th><td>' + _render_value(v, depth + 1)
                       + '</td></tr>' for k, v in value.items())
        return '<div class="scroll"><table>' + rows + '</table></div>'
    if isinstance(value, list):
        if not value:
            return '<span class="muted">пусто</span>'
        if all(isinstance(item, dict) for item in value) and depth <= 4:
            columns = []
            for item in value:
                for key in item:
                    if key not in columns:
                        columns.append(key)
            head = ''.join('<th>' + _esc(c) + '</th>' for c in columns)
            body = ''.join('<tr>' + ''.join('<td>' + _render_value(item.get(c), depth + 1)
                                            + '</td>' for c in columns) + '</tr>'
                           for item in value[:200])
            extra = ('<p class="note">Показаны первые 200 из %d строк.</p>' % len(value)
                     if len(value) > 200 else '')
            return '<div class="scroll"><table><thead><tr>' + head + '</tr></thead><tbody>' \
                + body + '</tbody></table></div>' + extra
        return '<ul>' + ''.join('<li>' + _render_value(item, depth + 1) + '</li>'
                                for item in value[:200]) + '</ul>'
    return _esc(value)


def render_dashboard(audit, path):
    meta, summary = audit['meta'], audit['summary']
    counts = summary['counts']
    indexable = summary.get('indexable')
    index_text = {True: 'Индексируется', False: 'Не индексируется',
                  None: 'Вывод невозможен'}[indexable]
    index_class = {True: 'b-ok', False: 'b-fail', None: 'b-unknown'}[indexable]
    parts = ['<!doctype html><html lang="ru"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta name="robots" content="noindex">',
             '<title>Технический SEO-аудит страницы</title><style>', CSS,
             '</style></head><body><main>',
             '<h1>Технический SEO-аудит страницы</h1>',
             '<section><table>',
             '<tr><th>Проверенный URL</th><td>' + _esc(meta.get('url')) + '</td></tr>',
             '<tr><th>Конечный URL</th><td>' + _esc(meta.get('final_url')) + '</td></tr>',
             '<tr><th>Время сбора (UTC)</th><td>' + _esc(meta.get('timestamp_utc')) + '</td></tr>',
             '<tr><th>Версия скрипта</th><td>' + _esc(meta.get('script_version')) + '</td></tr>',
             '<tr><th>User-Agent</th><td>' + _esc(meta.get('user_agent')) + '</td></tr>',
             '<tr><th>Индексируемость</th><td><span class="badge ' + index_class + '">'
             + _esc(index_text) + '</span></td></tr>',
             '</table>']
    if summary.get('index_blockers'):
        parts.append('<p class="note">Причины: ' + _esc('; '.join(summary['index_blockers']))
                     + '</p>')
    parts.append('<div class="cards">' + ''.join(
        '<div class="card"><b>%d</b><span>%s</span></div>' % (counts.get(key, 0), label)
        for key, label in (('fail', 'критично'), ('warn', 'предупреждения'),
                           ('ok', 'норма'), ('unknown', 'нет данных'))) + '</div>')
    parts.append('<p class="muted">Проверки выполнены: ' + _esc(', '.join(meta.get('checks_ran') or []))
                 + '<br>Пропущены или без данных: '
                 + _esc(', '.join(meta.get('checks_skipped') or []) or '—') + '</p></section>')
    for name, check in audit['checks'].items():
        parts.append('<section><h2>' + _esc(check.get('title_ru') or CHECK_TITLES.get(name, name))
                     + ' <span class="badge b-' + _esc(check['verdict']) + '">'
                     + _esc(check['verdict']) + '</span></h2>')
        parts.append('<p>' + _esc(check.get('reason_ru')) + '</p>')
        parts.append(_render_value(check.get('evidence')))
        parts.append('</section>')
    if audit.get('issues'):
        parts.append('<section><h2>Сводка находок</h2>'
                     + _render_value(audit['issues']) + '</section>')
    parts.append('<section><p class="muted">Все значения взяты из файлов каталога raw/ и из '
                 'audit.json без пересчёта и без оценок. Проверки со статусом «unknown» не '
                 'выполнены — это не «норма» и не ноль. Ширина title приблизительная. Проверка '
                 'структурированных данных локальная и не заменяет Google Rich Results Test. '
                 'Ключ PageSpeed Insights не сохраняется ни в одном артефакте.</p></section>')
    parts.append('</main></body></html>')
    html = ''.join(parts)
    Path(path).write_text(html, encoding='utf-8')
    return html


# --------------------------------------------------------------------------- run

def plan_requests(url, args):
    plan = [{'step': 'page', 'method': 'GET', 'url': url,
             'note': 'основной запрос с ручным следованием редиректам (лимит %d)' % args.max_redirects}]
    parts = urlsplit(url)
    robots = urlunsplit((parts.scheme, parts.netloc, '/robots.txt', '', ''))
    plan.append({'step': 'robots', 'method': 'GET', 'url': robots, 'note': 'правила сканирования'})
    if not args.no_network_extras:
        for variant in variant_urls(url):
            plan.append({'step': 'variant:' + variant['name'], 'method': 'GET',
                         'url': variant['url'], 'note': 'проверка дублей и редиректов'})
        plan.append({'step': 'sitemaps', 'method': 'GET', 'url': '<из robots.txt>',
                     'note': 'до %d карт сайта' % SITEMAP_CAP})
        plan.append({'step': 'images', 'method': 'HEAD', 'url': '<из HTML>',
                     'note': 'до %d изображений' % IMAGE_HEAD_CAP})
        plan.append({'step': 'hreflang', 'method': 'GET', 'url': '<из HTML/заголовков>',
                     'note': 'до %d альтернатив' % HREFLANG_PROBE_CAP})
        plan.append({'step': 'favicon', 'method': 'GET', 'url': '<из HTML>', 'note': 'иконка сайта'})
    if args.render:
        plan.append({'step': 'render', 'method': 'BROWSER', 'url': url,
                     'note': 'headless Chromium --dump-dom'})
    if os.environ.get(args.psi_key_env):
        plan.append({'step': 'psi', 'method': 'GET', 'url': PSI_ENDPOINT + '?strategy=mobile&key=[REDACTED]',
                     'note': 'PageSpeed Insights mobile + desktop'})
    else:
        plan.append({'step': 'psi', 'method': 'SKIPPED', 'url': PSI_ENDPOINT,
                     'note': 'нет ключа в переменной окружения ' + args.psi_key_env})
    return plan


def run_audit(url, out, args):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory is not empty; use a fresh run directory')
    raw = out / 'raw'
    raw.mkdir(parents=True)
    user_agent = USER_AGENTS[args.user_agent]
    fetcher = http_fetcher(user_agent, timeout=args.timeout)
    extras = None if args.no_network_extras else fetcher
    ran, skipped = [], []

    redirects = follow_redirects(url, fetcher, max_redirects=args.max_redirects)
    final_record = redirects.get('final') or {}
    final_url = redirects.get('final_url') or url
    headers = sanitize_headers(final_record.get('headers'))
    html_text, charset, charset_source = decode_body(final_record)
    if final_record.get('body'):
        (raw / 'page.html').write_bytes(final_record['body'])
    save_json(raw / 'headers.json', {
        'requested_url': url, 'final_url': final_url, 'user_agent': user_agent,
        'redirect_chain': redirects['chain'], 'response_headers': headers,
        'note': 'Заголовки авторизации и сессий в артефакты не записываются.'})
    facts = parse_html(html_text)

    robots_parts = urlsplit(final_url)
    robots_url = urlunsplit((robots_parts.scheme, robots_parts.netloc, '/robots.txt', '', ''))
    time.sleep(POLITE_DELAY)
    robots_record = fetcher(robots_url)
    rules = None
    if robots_record.get('status') == 200 and robots_record.get('body') is not None:
        robots_text = robots_record['body'].decode('utf-8', errors='replace')
        (raw / 'robots.txt').write_text(robots_text, encoding='utf-8')
        rules = RobotsRules.parse(robots_text)
    elif robots_record.get('status') in (404, 410):
        (raw / 'robots.txt').write_text('', encoding='utf-8')
        rules = RobotsRules.parse('')  # missing robots.txt means everything is allowed

    directives = robots_directives(headers, facts)
    checks = {}
    checks['transport'] = check_transport(url, redirects, charset, charset_source)
    checks['tls'] = check_tls(final_url, timeout=args.timeout)
    checks['crawlability'] = check_crawlability(final_url, headers, facts, robots_record,
                                                rules, directives)
    probes = None
    if extras is not None:
        probes = probe_variants(final_url, fetcher, max_redirects=args.max_redirects,
                                delay=POLITE_DELAY)
    checks['canonical'] = check_canonical(final_url, facts, headers, variants=probes)
    checks['canonical']['evidence']['distinct_200_variant_targets'] = duplicate_summary(probes)
    checks['canonical']['evidence']['variants_note_ru'] = (
        'Каждый вариант URL запрошен отдельно; показан конечный URL после редиректов.'
        if probes else 'Варианты URL не проверялись (--no-network-extras).')
    checks['indexability'] = check_indexability(checks['transport'], checks['crawlability'],
                                                checks['canonical'], directives)
    favicon = check_favicon(final_url, facts, fetcher=extras, rules=rules)
    checks['head_meta'] = check_head_meta(final_url, facts, favicon=favicon)
    checks['headings'] = check_headings(facts)
    checks['structured_data'] = check_structured_data(facts)
    nodes = [b['data'] for b in checks['structured_data']['evidence']['blocks']]
    flat_nodes = []
    for node in nodes:
        flat_nodes.extend(list(_iter_jsonld_nodes(node)))
    checks['content'] = check_content(facts, html_text, flat_nodes)
    checks['links'] = check_links(facts, final_url)
    checks['images'] = check_images(facts, final_url, fetcher=extras, rules=rules)
    checks['hreflang'] = check_hreflang(final_url, facts, headers, fetcher=extras, rules=rules)
    checks['sitemaps'] = check_sitemaps(final_url, rules, fetcher=extras, raw_dir=raw)
    if args.render:
        checks['rendering'] = check_rendering(
            final_url, checks['content']['evidence']['word_count'],
            checks['links']['evidence']['total_links'], raw, timeout=max(args.timeout * 3, 60))
    else:
        checks['rendering'] = check_rendering_skipped()
    psi_key = os.environ.get(args.psi_key_env) or None
    checks['performance'] = check_performance(final_url, psi_key, extras, args.psi_key_env, raw,
                                              timeout=args.timeout)

    for name, check in checks.items():
        (skipped if check['verdict'] == 'unknown' else ran).append(CHECK_TITLES.get(name, name))
    counts = {level: sum(1 for c in checks.values() if c['verdict'] == level)
              for level in ('ok', 'warn', 'fail', 'unknown')}
    audit = {
        'meta': {'url': url, 'final_url': final_url,
                 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                 'script_version': VERSION, 'user_agent': user_agent,
                 'user_agent_preset': args.user_agent, 'timeout_s': args.timeout,
                 'max_redirects': args.max_redirects,
                 'network_extras': not args.no_network_extras,
                 'render_requested': bool(args.render),
                 'psi_key_env': args.psi_key_env, 'psi_key_present': bool(psi_key),
                 'checks_ran': ran, 'checks_skipped': skipped,
                 'raw_files': sorted(p.name for p in raw.iterdir())},
        'summary': {'counts': counts,
                    'indexable': checks['indexability']['evidence'].get('indexable'),
                    'index_blockers': checks['indexability']['evidence'].get('blockers', [])},
        'checks': checks,
        'issues': build_issues(checks),
    }
    audit['meta']['raw_files'] = sorted(p.name for p in raw.iterdir())
    _assert_no_secret(audit, psi_key)
    save_json(out / 'audit.json', audit)
    write_issues_csv(out / 'issues.csv', audit['issues'])
    render_dashboard(audit, out / 'dashboard.html')
    return audit


def _assert_no_secret(value, secret):
    """Hard guarantee: the PSI key must never reach an artifact."""
    if not secret:
        return
    if secret in json.dumps(value, ensure_ascii=False, default=str):
        raise ValueError('Refusing to write artifacts: API key found in payload')


def render_only(run_dir):
    run = Path(run_dir)
    audit = json.loads((run / 'audit.json').read_text(encoding='utf-8'))
    audit.setdefault('issues', build_issues(audit.get('checks', {})))
    write_issues_csv(run / 'issues.csv', audit['issues'])
    render_dashboard(audit, run / 'dashboard.html')
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Технический SEO-аудит одной страницы: сбор сырых данных, audit.json, '
                    'issues.csv и автономный HTML-дашборд. Только стандартная библиотека.')
    parser.add_argument('--url', help='Absolute http(s) URL of the page to audit')
    parser.add_argument('--out', help='Fresh run directory for artifacts')
    parser.add_argument('--user-agent', choices=sorted(USER_AGENTS), default='auto')
    parser.add_argument('--render', action='store_true',
                        help='Compare raw HTML with rendered DOM via headless Chromium')
    parser.add_argument('--psi-key-env', default='PAGESPEED_API_KEY',
                        help='Env var holding the PageSpeed Insights API key (never stored)')
    parser.add_argument('--timeout', type=int, default=20)
    parser.add_argument('--max-redirects', type=int, default=10)
    parser.add_argument('--no-network-extras', action='store_true',
                        help='Only the page and robots.txt; everything else becomes unknown')
    parser.add_argument('--render-only', metavar='RUN_DIR',
                        help='Rebuild dashboard.html and issues.csv from audit.json; zero network')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print the planned request list without any network call')
    parser.add_argument('--json', action='store_true', help='Print the run summary as JSON')
    args = parser.parse_args(argv)

    try:
        if args.render_only:
            if args.url or args.out or args.dry_run:
                parser.error('--render-only cannot be combined with collection options')
            audit = render_only(args.render_only)
            payload = {'ok': True, 'mode': 'render-only',
                       'run': str(Path(args.render_only).resolve()),
                       'counts': audit.get('summary', {}).get('counts')}
            print(json.dumps(payload, ensure_ascii=False) if args.json
                  else 'Дашборд перестроен без сетевых запросов: dashboard.html, issues.csv')
            return 0
        if not args.url:
            parser.error('--url is required unless --render-only')
        if args.timeout <= 0 or not 0 <= args.max_redirects <= 50:
            parser.error('--timeout must be positive and --max-redirects within 0..50')
        url = normalize_url(args.url)
        if args.dry_run:
            plan = plan_requests(url, args)
            print(json.dumps({'url': url, 'user_agent': USER_AGENTS[args.user_agent],
                              'request_count': len(plan), 'plan': plan},
                             ensure_ascii=False, indent=2))
            return 0
        if not args.out:
            parser.error('--out is required')
        audit = run_audit(url, args.out, args)
        summary = {'ok': True, 'url': url, 'final_url': audit['meta']['final_url'],
                   'indexable': audit['summary']['indexable'],
                   'counts': audit['summary']['counts'],
                   'out': str(Path(args.out).resolve())}
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print('Аудит завершён: %s → %s (fail=%d, warn=%d, ok=%d, unknown=%d)'
                  % (url, summary['out'], audit['summary']['counts']['fail'],
                     audit['summary']['counts']['warn'], audit['summary']['counts']['ok'],
                     audit['summary']['counts']['unknown']))
        return 0
    except SystemExit:
        raise
    except (ValueError, OSError, KeyError) as exc:
        import sys
        print('Ошибка: некорректные аргументы, недоступная цель или занятый каталог (%s: %s)'
              % (type(exc).__name__, _scrub(str(exc))), file=sys.stderr)
        return 2


if __name__ == '__main__':
    import sys
    sys.exit(main())
