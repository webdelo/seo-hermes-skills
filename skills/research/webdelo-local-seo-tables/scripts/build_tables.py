#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

CATEGORIES = ['local', 'aggregator', 'franchise', 'informational', 'other']
REQUIRED_LOCALES = ['ru', 'de', 'en']


def fail(message):
    raise SystemExit(message)


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        fail(f'Cannot read JSON {path}: {exc}')


def norm(value):
    return re.sub(r'\s+', ' ', str(value).casefold().replace('-', ' ')).strip()


MONTHS = {
    'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'APRIL': 4,
    'MAY': 5, 'JUNE': 6, 'JULY': 7, 'AUGUST': 8,
    'SEPTEMBER': 9, 'OCTOBER': 10, 'NOVEMBER': 11, 'DECEMBER': 12,
}


def exact_nonnegative_int(value, label):
    if isinstance(value, bool):
        fail(f'{label} must be a non-negative integer')
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r'\d+', value):
        number = int(value)
    else:
        fail(f'{label} must be a non-negative integer or digit-only string')
    if number < 0:
        fail(f'{label} must be non-negative')
    return number


def integer(value, thousands, missing):
    if value is None:
        return missing
    number = exact_nonnegative_int(value, 'display integer')
    return f'{number:,}'.replace(',', thousands)


def euros(micros, decimal, missing):
    if micros is None:
        return missing
    value = exact_nonnegative_int(micros, 'bid micros') / 1_000_000
    return ('€' + f'{value:.2f}').replace('.', decimal)


def bid_range(low, high, decimal, missing):
    if low is None and high is None:
        return missing
    if low is None or high is None:
        fail('both bid bounds must be present or both null')
    low_value = exact_nonnegative_int(low, 'low bid micros')
    high_value = exact_nonnegative_int(high, 'high bid micros')
    if low_value > high_value:
        fail('low bid micros exceeds high bid micros')
    return f'{euros(low_value, decimal, missing)}–{euros(high_value, decimal, missing)}'


def month_period(results):
    periods = []
    for row_index, row in enumerate(results):
        metrics = row.get('keywordMetrics') or {}
        history = metrics.get('monthlySearchVolumes') or []
        if len(history) != 12:
            fail(f'Keyword Planner row {row_index} does not have exactly 12 monthlySearchVolumes')
        parsed = []
        for item in history:
            year = exact_nonnegative_int(item.get('year'), f'row {row_index} monthly year')
            month_name = item.get('month')
            if month_name not in MONTHS:
                fail(f'row {row_index}: invalid month {month_name!r}')
            parsed.append((year, MONTHS[month_name], month_name))
        if len({(year, month) for year, month, _ in parsed}) != 12:
            fail(f'row {row_index}: duplicate monthly periods')
        parsed.sort(key=lambda value: (value[0], value[1]))
        ordinals = [year * 12 + month - 1 for year, month, _ in parsed]
        if ordinals != list(range(ordinals[0], ordinals[0] + 12)):
            fail(f'row {row_index}: monthly periods are not 12 consecutive months')
        periods.append(parsed)
    first = periods[0]
    if any([(year, month) for year, month, _ in period] != [(year, month) for year, month, _ in first] for period in periods[1:]):
        fail('Keyword Planner rows do not share the same 12-month period')
    return {
        'start': {'year': first[0][0], 'month': first[0][2]},
        'end': {'year': first[-1][0], 'month': first[-1][2]},
    }


def match_keywords(requested, results):
    index = {}
    for row_index, row in enumerate(results):
        aliases = [row.get('text'), *(row.get('closeVariants') or [])]
        for alias in aliases:
            if alias:
                index.setdefault(norm(alias), set()).add(row_index)
    matched_indexes = []
    for keyword in requested:
        candidates = sorted(index.get(norm(keyword), set()))
        if len(candidates) != 1:
            fail(f'Keyword {keyword!r} matched {len(candidates)} rows')
        matched_indexes.append(candidates[0])
    if len(set(matched_indexes)) != len(matched_indexes):
        fail('Multiple requested keywords map to the same Keyword Planner row')
    return [results[row_index] for row_index in matched_indexes]


def validate_locale(locale, cfg, keywords, cities):
    required = ['first_title', 'first_intro', 'first_headers', 'second_title', 'second_intro', 'second_headers', 'competition_labels', 'missing', 'first_labels', 'comparison_keys', 'site_type_labels', 'takeaways', 'thousands', 'decimal']
    missing = [key for key in required if key not in cfg]
    if missing:
        fail(f'{locale}: missing locale fields {missing}')
    scalar_fields = ['first_title', 'first_intro', 'second_title', 'second_intro', 'missing', 'thousands', 'decimal']
    for field in scalar_fields:
        if not isinstance(cfg[field], str) or (field != 'thousands' and not cfg[field].strip()):
            fail(f'{locale}: {field} must be a non-empty string')
    if len(cfg['thousands']) > 1 or len(cfg['decimal']) != 1:
        fail(f'{locale}: separators must be explicit single characters; thousands may be empty')
    if not isinstance(cfg['first_headers'], list) or not isinstance(cfg['second_headers'], list) or len(cfg['first_headers']) != 4 or len(cfg['second_headers']) != 5:
        fail(f'{locale}: header count mismatch')
    if any(not isinstance(value, str) or not value.strip() for value in [*cfg['first_headers'], *cfg['second_headers']]):
        fail(f'{locale}: headers must be non-empty strings')
    if set(cfg['competition_labels']) != {'LOW', 'MEDIUM', 'HIGH', 'UNSPECIFIED'}:
        fail(f'{locale}: competition label keys mismatch')
    if set(cfg['site_type_labels']) != set(CATEGORIES):
        fail(f'{locale}: site type label keys mismatch')
    if set(cfg['first_labels']) != set(keywords):
        fail(f'{locale}: first_labels must exactly match requested keywords')
    if set(cfg['comparison_keys']) != set(cities) or set(cfg['takeaways']) != set(cities):
        fail(f'{locale}: comparison keys/takeaways must exactly match cities')
    dictionaries = ['competition_labels', 'site_type_labels', 'first_labels', 'comparison_keys', 'takeaways']
    for field in dictionaries:
        if not isinstance(cfg[field], dict) or any(not isinstance(value, str) or not value.strip() for value in cfg[field].values()):
            fail(f'{locale}: {field} values must be non-empty strings')
    displayed = [cfg['first_title'], cfg['first_intro'], *cfg['first_headers'], cfg['second_title'], cfg['second_intro'], *cfg['second_headers'], cfg['missing']]
    for field in dictionaries:
        displayed.extend(cfg[field].values())
    if '<strong' in json.dumps(displayed, ensure_ascii=False).casefold():
        fail(f'{locale}: forbidden <strong>')


def main():
    parser = argparse.ArgumentParser(description='Build two verified Webdelo local SEO tables')
    parser.add_argument('spec')
    args = parser.parse_args()
    spec_path = Path(args.spec).resolve()
    spec = load(spec_path)
    base = spec_path.parent
    required = ['google_ads_file', 'comparison_file', 'expected_keyword_planner', 'first_keywords', 'comparison_topic', 'comparison_cities', 'locales', 'output']
    missing = [key for key in required if spec.get(key) is None or spec.get(key) == '']
    if missing:
        fail(f'Missing spec fields: {missing}')
    keywords = spec['first_keywords']
    cities = spec['comparison_cities']
    if not isinstance(keywords, list) or not 1 <= len(keywords) <= 7 or any(not isinstance(value, str) or not value.strip() for value in keywords):
        fail('first_keywords must contain 1–7 non-empty strings')
    if len({norm(value) for value in keywords}) != len(keywords):
        fail('first_keywords must be unique after normalization')
    if not isinstance(cities, list) or not cities or any(not isinstance(value, str) or not value.strip() for value in cities) or len(set(cities)) != len(cities):
        fail('comparison_cities must be a non-empty unique list of strings')
    if not isinstance(spec['comparison_topic'], str) or not spec['comparison_topic'].strip():
        fail('comparison_topic must be a non-empty string')
    if not isinstance(spec['locales'], dict) or set(spec['locales']) != set(REQUIRED_LOCALES):
        fail('locales must be exactly ru, de, en')
    for locale in REQUIRED_LOCALES:
        validate_locale(locale, spec['locales'][locale], keywords, cities)

    ads = load((base / spec['google_ads_file']).resolve())
    request = ads.get('request') or {}
    expected_settings = spec['expected_keyword_planner']
    expected_keys = {'geoTargetConstants', 'language', 'keywordPlanNetwork'}
    if not isinstance(expected_settings, dict) or set(expected_settings) != expected_keys:
        fail(f'expected_keyword_planner must contain exactly {sorted(expected_keys)}')
    actual_settings = {key: request.get(key) for key in expected_keys}
    if actual_settings != expected_settings:
        fail(f'Unexpected Keyword Planner settings: expected {expected_settings}, got {actual_settings}')
    results = (ads.get('response') or {}).get('results')
    if not isinstance(results, list) or not results:
        fail('No Keyword Planner results')
    matched = match_keywords(keywords, results)
    period = month_period(matched)

    comparison = load((base / spec['comparison_file']).resolve())
    if not isinstance(comparison.get('records'), list):
        fail('comparison_file.records must be a list')
    records = [row for row in comparison['records'] if isinstance(row, dict) and row.get('topic') == spec['comparison_topic']]
    by_city = {}
    for record in records:
        city = record.get('city')
        if not isinstance(city, str) or not city.strip():
            fail('Comparison record city must be a non-empty string')
        if city in by_city:
            fail(f'Duplicate comparison city: {city}')
        by_city[city] = record
    if set(by_city) != set(cities):
        fail(f'Comparison city mismatch: expected {cities}, got {sorted(by_city)}')
    validated_comparison = {}
    required_record_fields = {'city', 'topic', 'monthly_searches', 'low_top_of_page_bid_micros', 'high_top_of_page_bid_micros', 'organic_total', 'counts', 'top'}
    for city in cities:
        record = by_city[city]
        missing_fields = sorted(required_record_fields - set(record))
        if missing_fields:
            fail(f'{city}: missing comparison fields {missing_fields}')
        monthly = exact_nonnegative_int(record['monthly_searches'], f'{city} monthly_searches')
        low_raw = record['low_top_of_page_bid_micros']
        high_raw = record['high_top_of_page_bid_micros']
        if low_raw is None and high_raw is None:
            low_bid = high_bid = None
        elif low_raw is None or high_raw is None:
            fail(f'{city}: both bid bounds must be present or both null')
        else:
            low_bid = exact_nonnegative_int(low_raw, f'{city} low bid micros')
            high_bid = exact_nonnegative_int(high_raw, f'{city} high bid micros')
            if low_bid > high_bid:
                fail(f'{city}: low bid exceeds high bid')
        organic_total = exact_nonnegative_int(record['organic_total'], f'{city} organic_total')
        counts = record['counts']
        if not isinstance(counts, dict) or set(counts) - set(CATEGORIES):
            fail(f'{city}: counts must be an object containing only known site categories')
        parsed_counts = {key: exact_nonnegative_int(counts.get(key, 0), f'{city} count {key}') for key in CATEGORIES}
        top = record['top']
        if not isinstance(top, list) or len(top) != organic_total:
            fail(f'{city}: top result count does not equal organic_total')
        derived_counts = {key: 0 for key in CATEGORIES}
        for result_index, result in enumerate(top):
            if not isinstance(result, dict) or result.get('category') not in CATEGORIES:
                fail(f'{city}: top result {result_index} has an invalid category')
            derived_counts[result['category']] += 1
        if sum(parsed_counts.values()) != organic_total or parsed_counts != derived_counts:
            fail(f'{city}: category counts do not match organic_total and classified top results')
        validated_comparison[city] = {
            'monthly_searches': monthly,
            'low_top_of_page_bid_micros': low_bid,
            'high_top_of_page_bid_micros': high_bid,
            'organic_total': organic_total,
            'counts': parsed_counts,
        }

    output = {'format': 'webdelo.local-seo.tables', 'version': 1, 'period': period, 'source': {'google_ads_file': spec['google_ads_file'], 'comparison_file': spec['comparison_file']}, 'locales': {}}
    all_freq = []
    all_lows = []
    all_highs = []
    metric_fingerprint = []
    for keyword, row in zip(keywords, matched):
        metrics = row.get('keywordMetrics') or {}
        metric_fingerprint.append([keyword, metrics.get('avgMonthlySearches'), metrics.get('competition'), metrics.get('competitionIndex'), metrics.get('lowTopOfPageBidMicros'), metrics.get('highTopOfPageBidMicros')])
        if metrics.get('avgMonthlySearches') is not None:
            all_freq.append(exact_nonnegative_int(metrics['avgMonthlySearches'], f'{keyword} avgMonthlySearches'))
        if metrics.get('lowTopOfPageBidMicros') is not None:
            all_lows.append(exact_nonnegative_int(metrics['lowTopOfPageBidMicros'], f'{keyword} low bid micros'))
        if metrics.get('highTopOfPageBidMicros') is not None:
            all_highs.append(exact_nonnegative_int(metrics['highTopOfPageBidMicros'], f'{keyword} high bid micros'))

    for locale in REQUIRED_LOCALES:
        cfg = spec['locales'][locale]
        first_rows = []
        for keyword, row in zip(keywords, matched):
            metrics = row.get('keywordMetrics') or {}
            competition = metrics.get('competition') or 'UNSPECIFIED'
            if competition not in cfg['competition_labels']:
                fail(f'{locale}: unknown competition value {competition}')
            index_value = metrics.get('competitionIndex')
            competition_index = None if index_value is None else exact_nonnegative_int(index_value, f'{keyword} competitionIndex')
            if competition_index is not None and competition_index > 100:
                fail(f'{keyword}: competitionIndex exceeds 100')
            competition_cell = cfg['competition_labels'][competition] if competition_index is None else f'{cfg["competition_labels"][competition]} ({competition_index}/100)'
            first_rows.append({'cols': [cfg['first_labels'][keyword], integer(metrics.get('avgMonthlySearches'), cfg['thousands'], cfg['missing']), competition_cell, bid_range(metrics.get('lowTopOfPageBidMicros'), metrics.get('highTopOfPageBidMicros'), cfg['decimal'], cfg['missing'])]})
        second_rows = []
        for city in cities:
            record = validated_comparison[city]
            structure = '; '.join(f'{cfg["site_type_labels"][key]} — {record["counts"][key]}' for key in CATEGORIES if record['counts'][key])
            second_rows.append({'cols': [cfg['comparison_keys'][city], integer(record['monthly_searches'], cfg['thousands'], cfg['missing']), bid_range(record['low_top_of_page_bid_micros'], record['high_top_of_page_bid_micros'], cfg['decimal'], cfg['missing']), structure, cfg['takeaways'][city]]})
        first = {'type': 'audit-table', 'title': cfg['first_title'], 'content': cfg['first_intro'], 'data': {'label': '', 'classes_bg': 'default', 'spacing': {'padding_bottom': '!pb-22'}, 'table': {'headers': cfg['first_headers'], 'rows': first_rows}}}
        second = {'type': 'audit-table', 'title': cfg['second_title'], 'content': cfg['second_intro'], 'data': {'label': '', 'classes_bg': 'default', 'spacing': {'padding_bottom': '!pb-22'}, 'table': {'headers': cfg['second_headers'], 'rows': second_rows}}}
        output['locales'][locale] = {'first': first, 'second': second, 'metric_fingerprint': metric_fingerprint}

    fingerprints = [output['locales'][locale]['metric_fingerprint'] for locale in REQUIRED_LOCALES]
    if not all(fingerprint == fingerprints[0] for fingerprint in fingerprints[1:]):
        fail('Underlying metrics differ across locales')
    for locale in REQUIRED_LOCALES:
        for key in ['first', 'second']:
            block = output['locales'][locale][key]
            if block['data']['spacing']['padding_bottom'] != '!pb-22':
                fail('Spacing invariant failed')
            if any(not isinstance(cell, str) for row in block['data']['table']['rows'] for cell in row['cols']):
                fail('All output cells must be strings')
    destination = (base / spec['output']).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {'status': 'ok', 'output': str(destination), 'locales': len(output['locales']), 'first_rows': len(keywords), 'second_rows': len(cities), 'padding_values': 6, 'period': period, 'frequency_range': [min(all_freq), max(all_freq)] if all_freq else None, 'cpc_range_micros': [min(all_lows), max(all_highs)] if all_lows and all_highs else None}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
