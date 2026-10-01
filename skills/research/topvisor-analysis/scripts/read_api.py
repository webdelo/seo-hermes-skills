"""Bounded Topvisor read-only collector, Python stdlib, no retries or redirects."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.error

ALLOWED = frozenset(('get/projects_2/projects', 'get/positions_2/history'))
BASE = 'https://api.topvisor.com/v2/json/'
class Blocked(Exception):
    pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def load_credentials(env_file=None):
    names = ('TOPVISOR_USER_ID', 'TOPVISOR_API_KEY')
    values = {n: os.environ.get(n, '') for n in names}
    if env_file is None and os.environ.get('HERMES_HOME'):
        candidate = Path(os.environ['HERMES_HOME']) / '.env'
        if candidate.is_file():
            env_file = candidate
    if env_file:
        seen = set()
        for line in Path(env_file).read_text(encoding='utf-8-sig').splitlines():
            m = re.match(r'^\s*(?:export\s+)?(TOPVISOR_USER_ID|TOPVISOR_API_KEY)\s*=(.*)$', line)
            if not m:
                continue
            n, v = m.groups()
            if n in seen:
                raise Blocked('Duplicate credential assignment')
            seen.add(n)
            v = v.strip()
            if v.startswith(('"', "'")):
                end = v.find(v[0], 1)
                if end < 0 or (v[end+1:].strip() and not v[end+1:].strip().startswith('#')):
                    raise Blocked('Invalid credential syntax')
                v = v[1:end]
            else:
                v = re.split(r'\s+#', v, maxsplit=1)[0].rstrip()
            values[n] = v
    uid, key = (values[n] for n in names)
    if not re.fullmatch(r'[0-9]+', uid) or not re.fullmatch(r'[\x21-\x7e]+', key):
        raise Blocked('Missing or invalid credentials; values suppressed')
    return uid, key

def write_json(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def redact(value, key):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if any(x in k.lower() for x in ('token', 'password', 'secret', 'authorization', 'api_key')) else redact(v, key) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(x, key) for x in value]
    if isinstance(value, str):
        return value.replace(key, '[REDACTED]')
    return value

def request(method, params, uid, key):
    if method not in ALLOWED:
        raise Blocked('Forbidden operation')
    req = urllib.request.Request(BASE + method, data=json.dumps(params).encode(), method='POST', headers={
        'Content-Type': 'application/json', 'User-Id': uid, 'Authorization': 'bearer ' + key})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=45) as r:
            body = r.read(16000001)
    except urllib.error.HTTPError as exc:
        raise Blocked('HTTP ' + str(exc.code) + '; no retry') from None
    except (urllib.error.URLError, TimeoutError):
        raise Blocked('Network/TLS unavailable; no retry') from None
    if len(body) > 16000000:
        raise Blocked('Response exceeds size limit')
    obj = json.loads(body)
    if not isinstance(obj, dict) or obj.get('errors') or obj.get('result') is None:
        raise Blocked('API error or unsupported response; details suppressed')
    return redact(obj, key)

def collect(method, params, out, uid, key, transport=request):
    if method not in ALLOWED:
        raise Blocked('Forbidden operation')
    if not isinstance(params, dict):
        raise Blocked('Parameters must be an object')
    # Only documented selectors; no arbitrary credentials or alternative endpoint fields.
    common = {'fields', 'limit', 'offset', 'filters', 'orders'}
    extra = {'show_searchers_and_regions'} if method.endswith('projects') else {
        'project_id', 'regions_indexes', 'dates', 'date1', 'date2', 'type_range', 'show_headers',
        'show_exists_dates', 'positions_fields'}
    if set(params) - common - extra:
        raise Blocked('Unsupported parameter')
    if params.get('offset', 0) != 0:
        raise Blocked('Full collection must start at offset zero')
    limit = params.get('limit', 1000)
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise Blocked('Invalid limit')
    out = Path(out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    merged, seen, proofs = [], set(), []
    offset, total, headers = 0, None, None
    history = method.endswith('/history')
    for page in range(50):
        payload = dict(params, offset=offset, limit=limit)
        data = transport(method, payload, uid, key)
        if not isinstance(data, dict) or data.get('errors') or data.get('result') is None:
            raise Blocked('API error')
        result = data['result']
        if history:
            if not isinstance(result, dict):
                raise Blocked('Unsupported history schema')
            entries = result.get('keywords')
            current = result.get('headers')
            if page == 0:
                headers = current
            elif current != headers:
                raise Blocked('History headers changed during collection')
        else:
            entries = result
        if not isinstance(entries, list):
            raise Blocked('Unsupported rows schema')
        if 'total' in data:
            value = data['total']
            if isinstance(value, bool) or not re.fullmatch(r'[0-9]+', str(value)):
                raise Blocked('Invalid total')
            t = int(value)
            if total is not None and t != total:
                raise Blocked('Total changed during collection')
            total = t
        for row in entries:
            if not isinstance(row, dict) or 'id' not in row:
                raise Blocked('Row missing id')
            identity = str(row['id'])
            if identity in seen:
                raise Blocked('Duplicate row id')
            seen.add(identity)
            merged.append(row)
        path = out / ('page-' + str(page) + '.json')
        write_json(path, redact(data, key))
        proofs.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'parameters': redact(payload, key), 'fetched_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        nxt = data.get('nextOffset')
        if nxt is None:
            if total is not None and len(merged) != total:
                raise Blocked('Count differs from total')
            write_json(out / 'merged.json', {'rows': merged, 'headers': headers})
            evidence = {'method': method, 'count': len(merged), 'declared_total': total,
                'pagination_complete': True, 'measurement_completion': 'not_certified', 'pages': proofs}
            write_json(out / 'evidence.json', evidence)
            return evidence
        if isinstance(nxt, bool) or not re.fullmatch(r'[0-9]+', str(nxt)) or int(nxt) <= offset or not entries:
            raise Blocked('Invalid pagination continuation')
        offset = int(nxt)
    raise Blocked('Page budget exhausted')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--method', required=True, choices=sorted(ALLOWED))
    p.add_argument('--params', required=True, help='JSON request selectors, no secrets')
    p.add_argument('--out', required=True, help='New output directory; never overwritten')
    p.add_argument('--env-file', help='Optional .env from verified active Hermes profile; never printed')
    args = p.parse_args()
    os.umask(0o077)
    try:
        uid, key = load_credentials(args.env_file)
        params = json.loads(Path(args.params).read_text())
        result = collect(args.method, params, args.out, uid, key)
        print(json.dumps({'status': 'pass', 'rows': result['count'], 'pages': len(result['pages']), 'output': args.out}))
    except Blocked as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}))
        return 1
    except Exception:
        print(json.dumps({'status': 'blocked', 'reason': 'Local input or response invalid; details suppressed'}))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
