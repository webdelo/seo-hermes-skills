"""Offline synthetic fixtures only; no live network. Local http.server on 127.0.0.1 or stubs."""
import importlib.util
import json
import os
import threading
import unittest
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).with_name('page_audit.py')
spec = importlib.util.spec_from_file_location('page_audit', SCRIPT)
pa = importlib.util.module_from_spec(spec) if SCRIPT.exists() else None
if pa:
    spec.loader.exec_module(pa)

HOSTILE_TITLE = '<script>alert(1)</script><img src=x onerror="alert(2)">'

PAGE_HTML = """<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>""" + HOSTILE_TITLE + """</title>
<meta name="description" content="Описание страницы для теста аудита.">
<meta name="keywords" content="сео, аудит">
<meta name="robots" content="index, follow, max-snippet:-1">
<link rel="canonical" href="http://127.0.0.1:PORT/other">
<link rel="alternate" hreflang="ru" href="http://127.0.0.1:PORT/page">
<link rel="alternate" hreflang="en-US" href="http://127.0.0.1:PORT/en">
<link rel="alternate" hreflang="zz_BAD" href="http://127.0.0.1:PORT/bad">
<link rel="icon" href="/favicon.ico">
<meta property="og:title" content="OG заголовок"><meta name="twitter:card" content="summary">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"H"}</script>
<script type="application/ld+json">{broken json</script>
</head><body>
<h1>Первый заголовок</h1>
<h3>Скачок уровня</h3>
<h2></h2>
<p>Текст абзаца один. Опубликовано: 2024-05-01.</p>
<p>Текст абзаца два, немного больше слов для подсчёта статистики.</p>
<a href="/internal-a">Внутренняя ссылка</a>
<a href="/internal-a">Внутренняя ссылка дубль</a>
<a href="/internal-b" rel="nofollow ugc">Другая внутренняя</a>
<a href="https://external.example.org/x" rel="sponsored">Внешняя</a>
<a href="https://second.example.net/y"></a>
<a href="#anchor">Тот же документ</a>
<img src="/a.png" alt="Есть alt" width="10" height="10">
<img src="/b.png">
<img src="/c.webp" alt="" loading="lazy">
<img src="/d.png" alt="ОченьДлинный """ + 'д' * 130 + """">
</body></html>"""

ROBOTS = """User-agent: *
Disallow: /private/

User-agent: Googlebot
Disallow: /p
Allow: /page

Sitemap: http://127.0.0.1:PORT/sitemap.xml
"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>http://127.0.0.1:PORT/page</loc><lastmod>2024-05-01</lastmod></url>
</urlset>"""

PSI_JSON = {
    'loadingExperience': {'metrics': {
        'LARGEST_CONTENTFUL_PAINT_MS': {'percentile': 2100, 'category': 'AVERAGE'},
        'INTERACTION_TO_NEXT_PAINT': {'percentile': 150, 'category': 'GOOD'},
        'CUMULATIVE_LAYOUT_SHIFT_SCORE': {'percentile': 5, 'category': 'GOOD'}}},
    'lighthouseResult': {'audits': {
        'largest-contentful-paint': {'numericValue': 2500.0, 'displayValue': '2.5 s'},
        'cumulative-layout-shift': {'numericValue': 0.02, 'displayValue': '0.02'},
        'total-blocking-time': {'numericValue': 120.0, 'displayValue': '120 ms'}},
        'categories': {'performance': {'score': 0.87}}},
}

PSI_SECRET = 'SUPER-SECRET-PSI-KEY-123456'


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _send(self, code, body=b'', headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        port = self.server.server_address[1]
        def sub(t):
            return t.replace('PORT', str(port)).encode('utf-8')
        path = self.path
        self.server.hits.append(path)
        if path.startswith('/pagespeedonline'):
            if PSI_SECRET not in path:
                return self._send(400, b'{"error":"no key"}', [('Content-Type', 'application/json')])
            return self._send(200, json.dumps(PSI_JSON).encode(), [('Content-Type', 'application/json')])
        if path == '/robots.txt':
            return self._send(200, sub(ROBOTS), [('Content-Type', 'text/plain; charset=utf-8')])
        if path == '/sitemap.xml':
            return self._send(200, sub(SITEMAP), [('Content-Type', 'application/xml')])
        if path == '/page':
            return self._send(200, sub(PAGE_HTML), [
                ('Content-Type', 'text/html; charset=utf-8'),
                ('X-Robots-Tag', 'noindex, nofollow')])
        if path == '/start':
            return self._send(301, b'', [('Location', '/mid')])
        if path == '/mid':
            return self._send(302, b'', [('Location', '/page')])
        if path == '/loop-a':
            return self._send(301, b'', [('Location', '/loop-b')])
        if path == '/loop-b':
            return self._send(301, b'', [('Location', '/loop-a')])
        if path in ('/a.png', '/b.png', '/c.webp', '/d.png', '/favicon.ico'):
            return self._send(200, b'\x89PNG' + b'0' * 60, [('Content-Type', 'image/png')])
        if path in ('/internal-a', '/internal-b', '/en', '/bad', '/other'):
            return self._send(200, b'<html><head><title>t</title></head><body>ok</body></html>',
                              [('Content-Type', 'text/html')])
        if path == '/huge':
            # Bigger than MAX_FETCH_BYTES so a bounded read must truncate it.
            body = b'x' * (pa.MAX_FETCH_BYTES + 4096)
            return self._send(200, body, [('Content-Type', 'text/plain')])
        if path == '/huge-gzip':
            # Small on the wire, far past the cap once decompressed.
            import gzip as _gzip
            body = _gzip.compress(b'y' * (pa.MAX_FETCH_BYTES * 3))
            return self._send(200, body, [('Content-Type', 'text/plain'),
                                          ('Content-Encoding', 'gzip')])
        return self._send(404, b'not found', [('Content-Type', 'text/plain')])


class ServerMixin:
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.srv.hits = []
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%d' % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()


class ResponseSizeCapTests(ServerMixin, unittest.TestCase):
    """A hostile or merely huge response must never be read into memory unbounded."""

    def test_body_is_capped_and_flagged(self):
        self.assertIsNotNone(pa, 'page_audit implementation is missing')
        fetch = pa.http_fetcher('test-agent', timeout=20)
        record = fetch(self.base + '/huge')
        self.assertEqual(record['status'], 200)
        self.assertTrue(record['truncated'])
        self.assertEqual(len(record['body']), pa.MAX_FETCH_BYTES)
        self.assertEqual(record['truncated_at_bytes'], pa.MAX_FETCH_BYTES)

    def test_normal_body_not_flagged(self):
        fetch = pa.http_fetcher('test-agent', timeout=20)
        record = fetch(self.base + '/page')
        self.assertFalse(record['truncated'])

    def test_compressed_body_capped_after_decompression(self):
        """A few KB on the wire must not become hundreds of MB in memory."""
        fetch = pa.http_fetcher('test-agent', timeout=20)
        record = fetch(self.base + '/huge-gzip')
        self.assertEqual(record['status'], 200)
        self.assertTrue(record['truncated'])
        self.assertLessEqual(len(record['body']), pa.MAX_FETCH_BYTES)

    def test_truncated_sitemap_yields_unknown_not_warn(self):
        """Truncation must not be reported as 'URL is absent from the sitemap'."""
        rules = pa.RobotsRules.parse('Sitemap: http://example.test/sitemap.xml\n')

        def fetcher(url, method='GET'):
            return {'url': url, 'method': method, 'status': 200, 'headers': {},
                    'body': b'<urlset><url><loc>http://example.test/other</loc></url>',
                    'error': None, 'size_bytes': pa.MAX_FETCH_BYTES,
                    'truncated': True, 'truncated_at_bytes': pa.MAX_FETCH_BYTES}

        result = pa.check_sitemaps('http://example.test/page', rules, fetcher=fetcher, delay=0)
        self.assertEqual(result['verdict'], 'unknown')
        self.assertTrue(result['evidence'].get('any_truncated'))


class SitemapCoverageTests(unittest.TestCase):
    """Absence of a URL may only be claimed when coverage was genuinely complete."""

    INDEX = (b'<sitemapindex>'
             + b''.join(b'<loc>http://example.test/s%d.xml</loc>' % i for i in range(40))
             + b'</sitemapindex>')

    @staticmethod
    def _rules():
        return pa.RobotsRules.parse('Sitemap: http://example.test/sitemap.xml\n')

    @staticmethod
    def _record(url, status=200, body=b'', error=None):
        return {'url': url, 'method': 'GET', 'status': status, 'headers': {},
                'body': body, 'error': error, 'size_bytes': len(body), 'truncated': False}

    def test_all_children_timeout_is_unknown(self):
        """The real-world regression: every child timed out, 0 URLs scanned."""
        def fetcher(url, method='GET'):
            if url.endswith('/sitemap.xml'):
                return self._record(url, body=self.INDEX)
            return self._record(url, status=None, error='timeout: read timed out')

        result = pa.check_sitemaps('http://example.test/page', self._rules(),
                                   fetcher=fetcher, delay=0)
        self.assertEqual(result['verdict'], 'unknown')
        self.assertEqual(result['evidence']['urls_scanned'], 0)
        self.assertTrue(result['evidence'].get('any_unreadable'))

    def test_unvisited_index_tail_is_unknown(self):
        """Children beyond the cap were never opened, so absence is unproven."""
        def fetcher(url, method='GET'):
            if url.endswith('/sitemap.xml'):
                return self._record(url, body=self.INDEX)
            return self._record(url, body=b'<urlset><url><loc>http://example.test/x</loc></url></urlset>')

        result = pa.check_sitemaps('http://example.test/page', self._rules(),
                                   fetcher=fetcher, delay=0, cap=3)
        self.assertEqual(result['verdict'], 'unknown')
        self.assertGreater(result['evidence']['unvisited_sitemaps'], 0)

    def test_complete_coverage_without_url_is_warn(self):
        """Single flat sitemap, fully read, URL genuinely absent -> a real finding."""
        def fetcher(url, method='GET'):
            return self._record(
                url, body=b'<urlset><url><loc>http://example.test/other</loc></url></urlset>')

        result = pa.check_sitemaps('http://example.test/page', self._rules(),
                                   fetcher=fetcher, delay=0)
        self.assertEqual(result['verdict'], 'warn')
        self.assertEqual(result['evidence']['urls_scanned'], 1)

    def test_url_present_is_ok(self):
        def fetcher(url, method='GET'):
            return self._record(
                url,
                body=b'<urlset><url><loc>http://example.test/page</loc>'
                     b'<lastmod>2024-05-01</lastmod></url></urlset>')

        result = pa.check_sitemaps('http://example.test/page', self._rules(),
                                   fetcher=fetcher, delay=0)
        self.assertEqual(result['verdict'], 'ok')
        self.assertEqual(result['evidence']['lastmod_for_url'], '2024-05-01')


class RedirectTests(ServerMixin, unittest.TestCase):
    def test_chain_following(self):
        self.assertIsNotNone(pa, 'page_audit implementation is missing')
        fetcher = pa.http_fetcher(pa.USER_AGENTS['auto'], timeout=10)
        result = pa.follow_redirects(self.base + '/start', fetcher, max_redirects=10)
        self.assertEqual([h['status'] for h in result['chain']], [301, 302, 200])
        self.assertEqual(result['final_url'], self.base + '/page')
        self.assertEqual(result['hops'], 2)
        self.assertFalse(result['loop_detected'])

    def test_loop_detection(self):
        fetcher = pa.http_fetcher(pa.USER_AGENTS['auto'], timeout=10)
        result = pa.follow_redirects(self.base + '/loop-a', fetcher, max_redirects=10)
        self.assertTrue(result['loop_detected'])
        self.assertLessEqual(len(result['chain']), 11)

    def test_max_redirects_truncation(self):
        fetcher = pa.http_fetcher(pa.USER_AGENTS['auto'], timeout=10)
        result = pa.follow_redirects(self.base + '/start', fetcher, max_redirects=1)
        self.assertTrue(result['truncated'])


class RobotsTests(unittest.TestCase):
    def test_allow_disallow_precedence(self):
        rules = pa.RobotsRules.parse(ROBOTS.replace('PORT', '8000'))
        self.assertEqual(rules.sitemaps, ['http://127.0.0.1:8000/sitemap.xml'])
        # Googlebot group: Allow:/page (longer) beats Disallow:/p
        allowed = rules.verdict('/page', 'Googlebot')
        self.assertTrue(allowed['allowed'])
        self.assertEqual(allowed['rule'], ('allow', '/page'))
        blocked = rules.verdict('/profile', 'Googlebot')
        self.assertFalse(blocked['allowed'])
        self.assertEqual(blocked['rule'], ('disallow', '/p'))
        # Wildcard group applies to other agents
        star = rules.verdict('/private/x', 'SeoTechnicalAudit')
        self.assertFalse(star['allowed'])
        self.assertTrue(rules.verdict('/p', 'SeoTechnicalAudit')['allowed'])

    def test_wildcards_and_anchor(self):
        rules = pa.RobotsRules.parse('User-agent: *\nDisallow: /*.pdf$\nAllow: /ok/*/keep\n')
        self.assertFalse(rules.verdict('/files/a.pdf', 'Googlebot')['allowed'])
        self.assertTrue(rules.verdict('/files/a.pdf?x=1', 'Googlebot')['allowed'])
        self.assertTrue(rules.verdict('/ok/any/keep', 'Googlebot')['allowed'])

    def test_empty_robots_allows_everything(self):
        rules = pa.RobotsRules.parse('')
        self.assertTrue(rules.verdict('/anything', 'Googlebot')['allowed'])


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.html = PAGE_HTML.replace('PORT', '8000')
        self.facts = pa.parse_html(self.html)
        self.base = 'http://127.0.0.1:8000/page'

    def test_noindex_from_meta_and_header(self):
        directives = pa.robots_directives({'x-robots-tag': 'noindex, nofollow'}, self.facts)
        self.assertTrue(directives['noindex'])
        self.assertTrue(directives['nofollow'])
        self.assertIn('http_header', directives['noindex_sources'])
        facts2 = pa.parse_html('<html><head><meta name="robots" content="NOINDEX"></head><body></body></html>')
        d2 = pa.robots_directives({}, facts2)
        self.assertTrue(d2['noindex'])
        self.assertIn('meta_robots', d2['noindex_sources'])
        d3 = pa.robots_directives({}, pa.parse_html(
            '<html><head><meta name="googlebot" content="noindex"></head></html>'))
        self.assertTrue(d3['noindex'])
        self.assertIn('meta_googlebot', d3['noindex_sources'])
        d4 = pa.robots_directives({}, pa.parse_html('<html><head></head><body></body></html>'))
        self.assertFalse(d4['noindex'])

    def test_canonical_mismatch(self):
        check = pa.check_canonical(self.base, self.facts, {})
        self.assertEqual(check['evidence']['canonical_html'], 'http://127.0.0.1:8000/other')
        self.assertFalse(check['evidence']['self_referential'])
        self.assertTrue(check['evidence']['mismatch'])
        self.assertEqual(check['verdict'], 'warn')
        same = pa.check_canonical('http://127.0.0.1:8000/other', self.facts, {})
        self.assertTrue(same['evidence']['self_referential'])
        self.assertEqual(same['verdict'], 'ok')
        hdr = pa.check_canonical(self.base, pa.parse_html('<html><head></head></html>'),
                                 {'link': '<http://127.0.0.1:8000/hdr>; rel="canonical"'})
        self.assertEqual(hdr['evidence']['canonical_header'], 'http://127.0.0.1:8000/hdr')

    def test_jsonld_parsing_with_malformed_block(self):
        sd = pa.check_structured_data(self.facts)
        ev = sd['evidence']
        self.assertEqual(ev['jsonld_blocks_total'], 2)
        self.assertEqual(ev['jsonld_parse_errors_count'], 1)
        self.assertEqual(ev['types'], ['Article'])
        article = [r for r in ev['required_properties'] if r['type'] == 'Article'][0]
        self.assertIn('author', article['missing'])
        self.assertIn('datePublished', article['missing'])
        self.assertTrue(ev['heuristic_note'])
        self.assertEqual(sd['verdict'], 'fail')  # malformed JSON-LD block is a hard failure

    def test_heading_outline_and_jumps(self):
        headings = pa.check_headings(self.facts)
        ev = headings['evidence']
        self.assertEqual([(h['level'], h['text']) for h in ev['outline']][0], (1, 'Первый заголовок'))
        self.assertEqual(ev['h1_count'], 1)
        self.assertEqual(ev['empty_headings'], 1)
        self.assertEqual(ev['level_jumps'], [{'from': 1, 'to': 3, 'index': 1}])

    def test_image_alt_accounting(self):
        images = pa.check_images(self.facts, self.base, fetcher=None)
        ev = images['evidence']
        self.assertEqual(ev['total'], 4)
        self.assertEqual(ev['missing_alt'], 1)
        self.assertEqual(ev['empty_alt'], 1)
        self.assertEqual(ev['alt_too_long'], 1)
        self.assertEqual(ev['without_dimensions'], 3)
        self.assertEqual(ev['lazy_loading'], 1)
        self.assertEqual(ev['next_gen_format'], 1)
        self.assertEqual(ev['sizes_status'], 'not_requested')

    def test_link_classification(self):
        links = pa.check_links(self.facts, self.base)
        ev = links['evidence']
        self.assertEqual(ev['internal_count'], 4)
        self.assertEqual(ev['external_count'], 2)
        self.assertEqual(ev['unique_internal_targets'], 3)
        self.assertEqual(ev['same_page_links'], 1)
        self.assertEqual(ev['empty_anchors'], 1)
        self.assertEqual(ev['rel_values']['nofollow'], 1)
        self.assertEqual(ev['rel_values']['ugc'], 1)
        self.assertEqual(ev['rel_values']['sponsored'], 1)
        self.assertEqual(sorted(ev['external_domains']), ['external.example.org', 'second.example.net'])

    def test_title_pixel_width_is_approximate(self):
        width = pa.title_pixel_width('Test Title')
        self.assertIsInstance(width, int)
        self.assertGreater(width, 0)
        self.assertGreater(pa.title_pixel_width('WWWWWWWWWW'), pa.title_pixel_width('iiiiiiiiii'))

    def test_variant_url_generation(self):
        variants = pa.variant_urls('https://www.example.com/Page')
        keys = {v['name'] for v in variants}
        self.assertTrue({'http_www', 'https_www', 'http_root', 'https_root',
                         'trailing_slash', 'uppercase'} <= keys)
        by = {v['name']: v['url'] for v in variants}
        self.assertEqual(by['http_root'], 'http://example.com/Page')
        self.assertEqual(by['https_www'], 'https://www.example.com/Page')
        self.assertEqual(by['trailing_slash'], 'https://www.example.com/Page/')
        self.assertEqual(by['uppercase'], 'https://www.example.com/PAGE')


class VariantProbeTests(ServerMixin, unittest.TestCase):
    def test_probe_variants_reports_redirect_targets(self):
        fetcher = pa.http_fetcher(pa.USER_AGENTS['auto'], timeout=10)
        probes = pa.probe_variants(self.base + '/start', fetcher, max_redirects=5, delay=0)
        by = {p['name']: p for p in probes}
        self.assertEqual(by['http_root']['final_url'], self.base + '/page')
        self.assertEqual(by['http_root']['status'], 200)
        self.assertEqual(by['http_root']['chain_statuses'], [301, 302, 200])

    def test_duplicate_summary(self):
        self.assertIsNone(pa.duplicate_summary(None))
        probes = [{'name': 'a', 'status': 200, 'final_url': 'https://x.test/p'},
                  {'name': 'b', 'status': 200, 'final_url': 'https://x.test/p/'},
                  {'name': 'c', 'status': 404, 'final_url': 'https://x.test/q'}]
        self.assertEqual(pa.duplicate_summary(probes),
                         ['https://x.test/p', 'https://x.test/p/'])


class UnknownStatusTests(unittest.TestCase):
    def test_psi_unknown_without_key(self):
        check = pa.check_performance('http://127.0.0.1:1/page', None, None, 'PAGESPEED_API_KEY', Path('.'))
        self.assertEqual(check['verdict'], 'unknown')
        self.assertIn('PAGESPEED_API_KEY', check['reason_ru'])
        self.assertIsNone(check['evidence']['field_data'])

    def test_render_unknown_without_renderer(self):
        with tempfile.TemporaryDirectory() as d:
            check = pa.check_rendering('http://127.0.0.1:1/x', 100, 5, Path(d),
                                       renderer_finder=lambda: None, timeout=5)
            self.assertEqual(check['verdict'], 'unknown')
            self.assertIn('рендер', check['reason_ru'].lower())
            self.assertIsNone(check['evidence']['rendered_word_count'])

    def test_render_not_requested_is_unknown(self):
        check = pa.check_rendering_skipped()
        self.assertEqual(check['verdict'], 'unknown')

    def test_tls_unknown_for_http_scheme(self):
        check = pa.check_tls('http://example.com/x', timeout=5, connector=None)
        self.assertEqual(check['verdict'], 'unknown')
        self.assertIsNone(check['evidence']['expires_in_days'])


class NoNetworkModeTests(unittest.TestCase):
    def test_dry_run_makes_zero_network_calls(self):
        calls = []
        original = pa.http_fetcher
        pa.http_fetcher = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network in dry-run'))
        try:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / 'run'
                code = pa.main(['--url', 'https://example.com/p', '--out', str(out), '--dry-run'])
        finally:
            pa.http_fetcher = original
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])

    def test_render_only_makes_zero_network_calls(self):
        original = pa.http_fetcher
        pa.http_fetcher = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network in render-only'))
        try:
            with tempfile.TemporaryDirectory() as d:
                run = Path(d) / 'run'
                (run / 'raw').mkdir(parents=True)
                audit = {
                    'meta': {'url': 'https://example.com/p', 'final_url': 'https://example.com/p',
                             'timestamp_utc': '2026-01-01T00:00:00+00:00', 'script_version': pa.VERSION,
                             'user_agent': 'x', 'checks_ran': ['transport'], 'checks_skipped': []},
                    'summary': {'counts': {'ok': 1, 'warn': 0, 'fail': 0, 'unknown': 0},
                                'indexable': True, 'index_blockers': []},
                    'checks': {'transport': {'verdict': 'ok', 'reason_ru': 'Норма',
                                             'title_ru': 'Транспорт', 'evidence': {'status': 200}}},
                    'issues': [],
                }
                (run / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False), encoding='utf-8')
                code = pa.main(['--render-only', str(run)])
                self.assertEqual(code, 0)
                self.assertTrue((run / 'dashboard.html').exists())
                self.assertTrue((run / 'issues.csv').exists())
        finally:
            pa.http_fetcher = original


class EndToEndTests(ServerMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / 'run'
        os.environ['TEST_PSI_KEY'] = PSI_SECRET
        cls.psi_original = pa.PSI_ENDPOINT
        pa.PSI_ENDPOINT = cls.base + '/pagespeedonline/v5/runPagespeed'
        cls.code = pa.main(['--url', cls.base + '/page', '--out', str(cls.out),
                            '--psi-key-env', 'TEST_PSI_KEY', '--timeout', '10', '--json'])
        cls.audit = json.loads((cls.out / 'audit.json').read_text(encoding='utf-8'))
        cls.dashboard = (cls.out / 'dashboard.html').read_text(encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        pa.PSI_ENDPOINT = cls.psi_original
        os.environ.pop('TEST_PSI_KEY', None)
        cls.tmp.cleanup()
        super().tearDownClass()

    def test_exit_code_zero_and_artifacts(self):
        self.assertEqual(self.code, 0)
        for name in ('audit.json', 'issues.csv', 'dashboard.html'):
            self.assertTrue((self.out / name).is_file(), name)
        raw = {p.name for p in (self.out / 'raw').iterdir()}
        self.assertIn('page.html', raw)
        self.assertIn('robots.txt', raw)
        self.assertIn('headers.json', raw)
        self.assertTrue(any(n.startswith('psi_') for n in raw), raw)

    def test_meta_block(self):
        meta = self.audit['meta']
        self.assertEqual(meta['url'], self.base + '/page')
        self.assertEqual(meta['script_version'], pa.VERSION)
        self.assertTrue(meta['timestamp_utc'].endswith('+00:00'))
        self.assertIn('checks_ran', meta)
        self.assertIn('checks_skipped', meta)

    def test_indexability_reports_blockers(self):
        summary = self.audit['summary']
        self.assertFalse(summary['indexable'])
        blockers = ' '.join(summary['index_blockers'])
        self.assertIn('noindex', blockers.lower())

    def test_hostile_title_is_escaped_in_dashboard(self):
        self.assertIn(HOSTILE_TITLE, self.audit['checks']['head_meta']['evidence']['title']['text'])
        self.assertNotIn('<script>alert(1)</script>', self.dashboard)
        self.assertNotIn('onerror="alert(2)"', self.dashboard)
        self.assertNotIn('<img src=x onerror', self.dashboard)
        self.assertIn('&lt;script&gt;alert(1)', self.dashboard)

    def test_dashboard_is_self_contained_russian(self):
        self.assertTrue(self.dashboard.startswith('<!doctype html>'))
        self.assertIn('lang="ru"', self.dashboard)
        self.assertIn('--bg', self.dashboard)  # CSS variables
        self.assertNotIn('src="http', self.dashboard)
        self.assertNotIn('@import', self.dashboard)
        self.assertNotIn('fonts.googleapis', self.dashboard)
        self.assertIn('Индексируемость', self.dashboard)

    def test_psi_key_never_leaks_into_artifacts(self):
        for path in self.out.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                self.assertNotIn(PSI_SECRET.encode(), data, 'key leaked in %s' % path.name)
        self.assertEqual(self.audit['checks']['performance']['verdict'] in ('ok', 'warn', 'fail'), True)
        field = self.audit['checks']['performance']['evidence']['field_data']
        self.assertEqual(field['mobile']['LCP_ms'], 2100)

    def test_sitemap_contains_url(self):
        ev = self.audit['checks']['sitemaps']['evidence']
        self.assertTrue(ev['url_found'])
        self.assertEqual(ev['lastmod_for_url'], '2024-05-01')

    def test_hreflang_malformed_and_missing_self(self):
        ev = self.audit['checks']['hreflang']['evidence']
        self.assertEqual(len(ev['entries']), 3)
        self.assertIn('zz_BAD', ' '.join(ev['malformed']))
        self.assertTrue(ev['self_reference'])

    def test_issues_csv_columns_and_russian(self):
        import csv as csvmod
        with (self.out / 'issues.csv').open(encoding='utf-8-sig', newline='') as f:
            rows = list(csvmod.reader(f))
        self.assertEqual(rows[0], ['id', 'category', 'severity', 'verdict', 'element',
                                   'evidence', 'recommendation'])
        self.assertGreater(len(rows), 1)
        self.assertTrue(any(any('\u0400' <= ch <= '\u04ff' for ch in ''.join(r)) for r in rows[1:]))

    def test_refuses_existing_run_dir(self):
        code = pa.main(['--url', self.base + '/page', '--out', str(self.out)])
        self.assertNotEqual(code, 0)

    def test_content_and_transport_evidence(self):
        content = self.audit['checks']['content']['evidence']
        self.assertGreater(content['word_count'], 5)
        self.assertEqual(content['paragraphs'], 2)
        self.assertIsNotNone(content['text_to_html_ratio'])
        transport = self.audit['checks']['transport']['evidence']
        self.assertEqual(transport['status'], 200)
        self.assertEqual(transport['scheme'], 'http')
        self.assertIsNotNone(transport['response_time_ms'])
        crawl = self.audit['checks']['crawlability']['evidence']
        self.assertEqual(crawl['robots_txt_status'], 200)

    def test_no_secret_headers_stored(self):
        headers = json.loads((self.out / 'raw' / 'headers.json').read_text(encoding='utf-8'))
        text = json.dumps(headers).lower()
        for banned in ('cookie', 'authorization', 'set-cookie'):
            self.assertNotIn(banned, text)


class NoExtrasTests(ServerMixin, unittest.TestCase):
    def test_no_network_extras_marks_dependent_checks_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'run'
            code = pa.main(['--url', self.base + '/page', '--out', str(out),
                            '--no-network-extras', '--timeout', '10'])
            self.assertEqual(code, 0)
            audit = json.loads((out / 'audit.json').read_text(encoding='utf-8'))
            self.assertEqual(audit['checks']['sitemaps']['verdict'], 'unknown')
            self.assertEqual(audit['checks']['performance']['verdict'], 'unknown')
            self.assertIsNone(audit['checks']['canonical']['evidence']['variants'])
            self.assertEqual(audit['checks']['images']['evidence']['sizes_status'],
                             'not_requested')
            self.assertFalse(audit['meta']['network_extras'])


class UrlValidationTests(unittest.TestCase):
    def test_rejects_credentials_and_bad_schemes(self):
        for bad in ('https://user:pw@example.com/', 'javascript:alert(1)', 'ftp://example.com/',
                    'not a url', 'example.com/page'):
            with self.assertRaises(ValueError):
                pa.normalize_url(bad)
        self.assertEqual(pa.normalize_url('https://Example.com/A?b=1#frag'),
                         'https://example.com/A?b=1')


if __name__ == '__main__':
    unittest.main()
