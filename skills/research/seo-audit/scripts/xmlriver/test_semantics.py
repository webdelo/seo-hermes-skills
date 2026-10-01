"""Synthetic fixtures only; no live API calls or credential reads."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

class CollectorTests(unittest.TestCase):
    def test_dry_run_deduplicates_without_network(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            seeds = root / 'seeds.txt'
            seeds.write_text('  Red   Shoes  \nred shoes\n!Red shoes\n', encoding='utf-8')
            proc = subprocess.run([sys.executable, str(ROOT / 'semantics.py'), '--seeds', str(seeds), '--output', str(root / 'nested' / 'out'), '--regions', '', '--max-requests', '1'], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads((root / 'nested' / 'out' / 'results.json').read_text())
            self.assertEqual(report['seeds'], ['  Red   Shoes  ', '!Red shoes'])
            self.assertEqual(report['summary']['requests_used'], 0)
            self.assertEqual(report['summary']['planned_collection_requests'], 2)
            self.assertEqual(report['summary']['status'], 'dry_run')
            self.assertTrue((root / 'nested' / 'out' / 'keywords.csv').exists())

    def test_collection_preserves_provenance_and_budget(self):
        import semantics
        calls = []
        def transport(request):
            calls.append(request)
            return b'{"popular":[{"text":" Shoes ","value":12}],"associations":[{"text":"shoes","value":7}]}'
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / 'seeds').write_text('seed one\nseed two\n')
            args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', '213', '--execute', '--max-requests', '1'])
            report = semantics.run(args, transport=transport, credentials=('synthetic-user', 'synthetic-key'))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].get_method(), 'GET')
            self.assertIn('pagetype=words', calls[0].full_url)
            self.assertEqual(report['summary']['status'], 'partial')
            self.assertEqual(report['keywords'][0]['phrase'], ' Shoes ')
            self.assertEqual(len(report['keywords'][0]['provenance']), 2)
            self.assertEqual(report['keywords'][0]['provenance'][0]['suggested_value'], 12)
            self.assertEqual(report['keywords'][0]['provenance'][0]['seed'], 'seed one')
            self.assertEqual(report['keywords'][0]['provenance'][0]['regions'], '213')
            self.assertEqual(json.loads((root / 'out' / 'results.json').read_text()), report)

    def test_suggestions_region_and_history_share_budget(self):
        import semantics
        from urllib.parse import parse_qs, urlsplit
        calls = []
        def transport(request):
            calls.append(request)
            if request.data:
                self.assertEqual(json.loads(request.data), {'phrases': ['seed']})
                return b'{"phrases":["Shoe","!shoe"]}'
            return b'{"totalValue":0}'
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / 'seeds').write_text('seed\n')
            args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', '213', '--sources', 'google,yandex', '--execute', '--frequency', '--max-requests', '3'])
            report = semantics.run(args, transport=transport, credentials=('u', 'k'))
            self.assertEqual(len(calls), 3)
            self.assertEqual(urlsplit(calls[0].full_url).path, '/search/xml')
            self.assertNotIn('regions', parse_qs(urlsplit(calls[0].full_url).query))
            self.assertEqual(urlsplit(calls[1].full_url).path, '/search_yandex/xml')
            self.assertEqual(report['keywords'][0]['history_totalValue'], 0)
            self.assertEqual(report['keywords'][1]['history_status'], 'budget_exhausted')
            self.assertEqual(report['keywords'][0]['provenance'][0]['region_status'], 'unsupported')
            self.assertTrue(report['warnings'])
            self.assertEqual(report['summary']['status'], 'partial')

    def test_bad_responses_persist_sanitized_errors_without_retry(self):
        import semantics
        from urllib.error import HTTPError
        failures = [b'<error>synthetic-key</error>', b'{"error":"synthetic-key"}', b'{"popular":{}}', b'{"popular":[{"text":2,"value":1}],"associations":[]}', HTTPError('https://xmlriver.com/?key=synthetic-key', 403, 'synthetic-key', {}, None), TimeoutError('synthetic-key')]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                root = Path(tmp)
                (root / 'seeds').write_text('first\nsecond\n')
                calls = []
                def transport(request):
                    calls.append(request)
                    if len(calls) == 1:
                        if isinstance(failure, Exception):
                            raise failure
                        return failure
                    return b'{"popular":[{"text":"good","value":5}],"associations":[]}'
                args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', '', '--execute'])
                report = semantics.run(args, transport=transport, credentials=('u', 'synthetic-key'))
                self.assertEqual(len(calls), 2)
                self.assertEqual(report['summary']['status'], 'partial')
                self.assertEqual(len(report['errors']), 1)
                self.assertEqual(report['keywords'][0]['phrase'], 'good')
                self.assertNotIn('synthetic-key', (root / 'out' / 'results.json').read_text())

    def test_invalid_history_is_not_zero(self):
        import semantics
        for raw in (b'{}', b'{"totalValue":null}', b'{"totalValue":true}', b'{"totalValue":-1}', b'{"error":"bad","totalValue":0}', b'<error/>'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                root = Path(tmp)
                (root / 'seeds').write_text('seed')
                def transport(request):
                    return raw if 'pagetype=history' in request.full_url else b'{"phrases":["phrase"]}'
                args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', '', '--sources', 'google', '--frequency', '--execute'])
                report = semantics.run(args, transport=transport, credentials=('u', 'k'))
                self.assertIsNone(report['keywords'][0]['history_totalValue'])
                self.assertEqual(report['keywords'][0]['history_status'], 'error')
                self.assertEqual(report['summary']['status'], 'partial')
                self.assertEqual(len(report['errors']), 1)
        for raw in (b'{}', b'{"phrases":"bad"}', b'{"phrases":[1]}'):
            with self.assertRaises(ValueError):
                semantics.decode_response(raw, 'google')

    def test_credentials_preserve_tokens_and_missing_is_persisted(self):
        import semantics
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            envfile = root / '.env.synthetic'
            envfile.write_text('XMLRIVER_USER="user token"\nXMLRIVER_KEY=odd=token#literal\n')
            self.assertEqual(semantics.load_credentials(envfile, {}), ('user token', 'odd=token#literal'))
            self.assertEqual(semantics.load_credentials(envfile, {'XMLRIVER_KEY': 'override'}), ('user token', 'override'))
            (root / 'seeds').write_text('seed')
            args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', '', '--execute'])
            report = semantics.run(args, credentials=('', ''))
            self.assertEqual(report['summary']['status'], 'error')
            self.assertEqual(report['summary']['requests_used'], 0)
            self.assertIn('XMLRIVER_USER', report['errors'][0]['message'])
            self.assertEqual(json.loads((root / 'out' / 'results.json').read_text()), report)

    def test_https_transport_timeout_and_redirect_policy(self):
        import semantics
        from unittest.mock import patch
        from urllib.request import Request
        from urllib.error import HTTPError
        request = Request('https://xmlriver.com/wordstat/new/json?key=synthetic')
        for url in ('http://xmlriver.com/a', 'https://evil.example/a', 'https://xmlriver.com/a'):
            with self.assertRaises(HTTPError):
                semantics.NoRedirect().redirect_request(request, None, 302, 'found', {}, url)
        with self.assertRaises(ValueError):
            semantics.fetch(Request('http://xmlriver.com/a'))
        with patch('urllib.request.OpenerDirector.open') as boundary:
            boundary.return_value.__enter__.return_value.read.return_value = b'{}'
            self.assertEqual(semantics.fetch(request), b'{}')
            self.assertEqual(boundary.call_count, 1)
            self.assertEqual(boundary.call_args.kwargs['timeout'], 30)

    def test_interruption_preserves_checkpoint_and_raw_provenance(self):
        import semantics
        import csv
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / 'seeds').write_text('first\nsecond')
            calls = []
            def transport(request):
                calls.append(request)
                if len(calls) == 2:
                    raise KeyboardInterrupt()
                return b'{"popular":[{"text":"  Raw  ","value":1},{"text":"RAW","value":2}],"associations":[]}'
            args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', '', '--execute'])
            report = semantics.run(args, transport=transport, credentials=('u', 'k'))
            self.assertEqual(report['summary']['status'], 'interrupted')
            self.assertEqual(report['summary']['requests_used'], 2)
            self.assertEqual(report['keywords'][0]['provenance'][1]['raw_phrase'], 'RAW')
            self.assertEqual(json.loads((root / 'out' / 'results.json').read_text()), report)
            with (root / 'out' / 'keywords.csv').open() as f:
                self.assertIn('history_metadata', next(csv.reader(f)))

    def test_checkpoint_before_paid_request_is_truthful(self):
        import semantics
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / 'seeds').write_text('seed')
            args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', '', '--execute'])
            def transport(request):
                checkpoint = json.loads((root / 'out' / 'results.json').read_text())
                self.assertEqual(checkpoint['summary']['status'], 'running')
                self.assertEqual(checkpoint['summary']['requests_used'], 1)
                return b'{"popular":[],"associations":[]}'
            report = semantics.run(args, transport=transport, credentials=('u', 'k'))
            self.assertEqual(report['summary']['status'], 'complete')
            self.assertEqual(report['errors'], [])

    def test_cli_validation_and_missing_credentials_exit_nonzero(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'semantics.py', root / 'scripts' / 'semantics.py')
            (root / 'seeds').write_text('seed')
            command = [sys.executable, str(root / 'scripts' / 'semantics.py'), '--seeds', str(root / 'seeds'), '--output', str(root / 'out')]
            for flags in ([], ['--regions', '', '--max-requests', '0'], ['--regions', '', '--sources', 'invalid'], ['--regions', '', '--execute']):
                proc = subprocess.run(command + flags, env={'XMLRIVER_USER': '', 'XMLRIVER_KEY': '', 'HERMES_HOME': str(root)}, text=True, capture_output=True)
                self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertIn('XMLRIVER_USER', proc.stdout)

    def test_duplicate_seeds_keep_first_seen_order(self):
        import semantics
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            (root / 'seeds').write_text(' A \nB\na\n')
            args = semantics.parser().parse_args(['--seeds', str(root / 'seeds'), '--output', str(root / 'out'), '--regions', ''])
            self.assertEqual(semantics.run(args)['seeds'], [' A ', 'B'])

if __name__ == '__main__':
    unittest.main()
