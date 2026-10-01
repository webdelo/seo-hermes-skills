"""Bounded XMLRiver collector. Standard library only; dry-run by default."""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.error import HTTPError
from urllib.parse import urlsplit


class NoRedirect(HTTPRedirectHandler):
    """Reject even same-origin redirects: no hidden extra paid requests."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError('', code, 'Redirect blocked', {}, None)


def fetch(request):
    url = urlsplit(request.full_url)
    if url.scheme != 'https' or url.netloc != 'xmlriver.com':
        raise ValueError('Only fixed XMLRiver HTTPS origin allowed')
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        return response.read()



def identity(text):
    return ' '.join(text.split()).casefold()


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--regions', required=True, help='Explicit region IDs; empty string means all')
    p.add_argument('--device', default='')
    p.add_argument('--sources', default='wordstat')
    p.add_argument('--max-requests', type=positive, default=10)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--execute', action='store_true')
    p.add_argument('--frequency', action='store_true')
    return p


def persist(output, report):
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'results.json'
    temp = output / '.results.json.tmp'
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, target)
    with (output / '.keywords.csv.tmp').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['phrase', 'provenance', 'history_totalValue', 'history_status', 'history_metadata'])
        for row in report['keywords']:
            writer.writerow([row['phrase'], json.dumps(row['provenance'], ensure_ascii=False), row.get('history_totalValue'), row.get('history_status', 'not_requested'), json.dumps(row.get('history_metadata', {}), ensure_ascii=False)])
    os.replace(output / '.keywords.csv.tmp', output / 'keywords.csv')


def decode_response(raw, kind):
    data = json.loads(raw)
    if not isinstance(data, dict) or 'error' in data or 'errors' in data:
        raise ValueError('API error or unexpected schema')
    if kind == 'wordstat':
        for group in ('popular', 'associations'):
            if not isinstance(data.get(group), list):
                raise ValueError('Unexpected wordstat schema')
            for item in data[group]:
                if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not item['text'].strip() or not valid_number(item.get('value')):
                    raise ValueError('Unexpected wordstat item')
    elif kind == 'history':
        if not valid_number(data.get('totalValue')):
            raise ValueError('Missing or invalid totalValue')
    else:
        if not isinstance(data.get('phrases'), list) or any(not isinstance(s, str) or not s.strip() for s in data['phrases']):
            raise ValueError('Unexpected suggestions schema')
    return data


def valid_number(value):
    import math
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def load_credentials(path=None, environ=None):
    environ = os.environ if environ is None else environ
    home = environ.get('HERMES_HOME')
    path = Path(path) if path is not None else (Path(home) / '.env' if home else None)
    values = {}
    if path is not None and path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            name, value = line.split('=', 1)
            name = name.strip()
            if name in ('XMLRIVER_USER', 'XMLRIVER_KEY'):
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                values[name] = value
    return tuple(environ.get(name, values.get(name, '')) for name in ('XMLRIVER_USER', 'XMLRIVER_KEY'))


def run(args, transport=None, credentials=None):
    unique_seeds = {}
    for seed in args.seeds.read_text(encoding='utf-8').splitlines():
        if seed.strip():
            unique_seeds.setdefault(identity(seed), seed)
    seeds = list(unique_seeds.values())
    sources = list(dict.fromkeys(args.sources.split(',')))
    if not sources or any(s not in ('wordstat', 'google', 'yandex') for s in sources):
        raise ValueError('sources must be wordstat,google,yandex')
    report = {'seeds': seeds, 'keywords': [], 'errors': [], 'metadata': {'regions': args.regions, 'device': args.device, 'started_at': datetime.now(timezone.utc).isoformat()}, 'summary': {'status': 'dry_run', 'requests_used': 0, 'max_requests': args.max_requests, 'planned_collection_requests': len(seeds) * len(sources), 'unique_phrases': 0}}
    report['warnings'] = []
    if 'google' in sources and args.regions:
        report['warnings'].append('Google suggestions: requested regions unsupported; no region filter applied.')
    persist(args.output, report)
    if args.execute:
        credentials = load_credentials() if credentials is None else credentials
        if not all(credentials):
            report['summary']['status'] = 'error'
            report['errors'].append({'stage': 'credentials', 'message': 'Missing XMLRIVER_USER or XMLRIVER_KEY; load the skill for secure setup in the active Hermes profile.'})
            persist(args.output, report)
            return report
        transport = fetch if transport is None else transport
        from urllib.parse import urlencode
        from urllib.request import Request
        report['summary']['status'] = 'running'
        index = {}
        for seed in seeds:
            for source in sources:
                if report['summary']['requests_used'] >= args.max_requests:
                    report['summary']['status'] = 'partial'
                    continue
                params = dict(user=credentials[0], key=credentials[1], query=seed, regions=args.regions, device=args.device, pagetype='words')
                if source == 'wordstat':
                    request = Request('https://xmlriver.com/wordstat/new/json?' + urlencode(params))
                else:
                    params = dict(user=credentials[0], key=credentials[1], setab='tips')
                    if source == 'yandex':
                        params['lr'] = args.regions
                    path = '/search/xml' if source == 'google' else '/search_yandex/xml'
                    request = Request('https://xmlriver.com' + path + '?' + urlencode(params), data=json.dumps({'phrases': [seed]}).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
                report['summary']['requests_used'] += 1
                persist(args.output, report)
                try:
                    data = decode_response(transport(request), source)
                except KeyboardInterrupt:
                    report['summary']['status'] = 'interrupted'
                    report['errors'].append({'stage': 'request', 'message': 'Interrupted; last request may have been charged.'})
                    persist(args.output, report)
                    return report
                except Exception:
                    report['errors'].append(dict(seed=seed, source=source, stage='collection', message='Request failed: network, API error, or invalid response; no retry.'))
                    report['summary']['status'] = 'partial'
                    persist(args.output, report)
                    continue
                groups = data if source == 'wordstat' else {'tips': [{'text': phrase, 'value': None} for phrase in data['phrases']]}
                for category in (('popular', 'associations') if source == 'wordstat' else ('tips',)):
                    for item in groups[category]:
                        key = identity(item['text'])
                        if key not in index:
                            index[key] = {'phrase': item['text'], 'provenance': []}
                            report['keywords'].append(index[key])
                        index[key]['provenance'].append(dict(seed=seed, raw_phrase=item['text'], source=source, category=category, suggested_value=item['value'], regions=args.regions if source != 'google' else None, region_status='unsupported' if source == 'google' and args.regions else 'applied' if args.regions else 'all', device=args.device if source == 'wordstat' else None, device_status='applied' if source == 'wordstat' else 'unsupported', collected_at=datetime.now(timezone.utc).isoformat()))
                report['summary']['unique_phrases'] = len(index)
                persist(args.output, report)
        if args.frequency:
            for row in report['keywords']:
                row['history_totalValue'] = None
                row['history_status'] = 'budget_exhausted'
                row['history_metadata'] = dict(regions=args.regions, device=args.device, measured_at=datetime.now(timezone.utc).isoformat())
                if report['summary']['requests_used'] >= args.max_requests:
                    report['summary']['status'] = 'partial'
                    continue
                params = dict(user=credentials[0], key=credentials[1], query=row['phrase'], regions=args.regions, device=args.device, pagetype='history')
                report['summary']['requests_used'] += 1
                persist(args.output, report)
                try:
                    data = decode_response(transport(Request('https://xmlriver.com/wordstat/new/json?' + urlencode(params))), 'history')
                    row['history_totalValue'] = data['totalValue']
                    row['history_status'] = 'ok'
                except KeyboardInterrupt:
                    report['summary']['status'] = 'interrupted'
                    report['errors'].append({'stage': 'request', 'message': 'Interrupted; last request may have been charged.'})
                    persist(args.output, report)
                    return report
                except Exception:
                    row['history_status'] = 'error'
                    report['errors'].append(dict(phrase=row['phrase'], source='wordstat', stage='history', message='History request failed or totalValue missing/invalid; no retry.'))
                    report['summary']['status'] = 'partial'
                persist(args.output, report)
        if report['summary']['status'] == 'running':
            report['summary']['status'] = 'complete'
        persist(args.output, report)
    return report


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        report = run(args)
    except (OSError, ValueError):
        print('Input/output or configuration error; check paths and flags.')
        return 2
    print(json.dumps(report['summary'], ensure_ascii=False))
    if report['summary']['status'] == 'error':
        for error in report['errors']:
            print(error['message'])
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
