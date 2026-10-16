#!/usr/bin/env python3
import argparse
import html
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


def fail(message):
    raise SystemExit(message)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        fail(f'Cannot read JSON {path}: {exc}')


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def visible_text(value):
    parser = TextExtractor()
    parser.feed(str(value))
    return html.unescape(' '.join(''.join(parser.parts).split()))


def font_pair():
    candidates = [
        (Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'), Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')),
        (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')),
        (Path('C:/Windows/Fonts/arial.ttf'), Path('C:/Windows/Fonts/arialbd.ttf')),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            return regular, bold
    fail('No Cyrillic-capable font pair found; install DejaVu Sans or Arial')


def main():
    parser = argparse.ArgumentParser(description='Build a verified Webdelo city SEO research PDF')
    parser.add_argument('spec')
    args = parser.parse_args()
    spec_path = Path(args.spec).resolve()
    spec = load_json(spec_path)
    base = spec_path.parent
    required = ['city', 'city_ru', 'scope', 'frequency_range', 'cpc_range', 'ads_period', 'report_date', 'page_json', 'xmlriver_files', 'output']
    missing = [key for key in required if not spec.get(key)]
    if missing:
        fail(f'Missing spec fields: {missing}')
    page_path = (base / spec['page_json']).resolve()
    output = (base / spec['output']).resolve()
    xml_paths = [(base / value).resolve() for value in spec['xmlriver_files']]
    if not page_path.exists() or any(not path.exists() for path in xml_paths):
        fail('One or more source paths do not exist')
    page = load_json(page_path)
    blocks = page['sections']['blocks']['ru'][0]
    tables = [block for block in blocks if block.get('type') == 'audit-table']
    if len(tables) != 2:
        fail(f'Expected exactly two RU audit tables, got {len(tables)}')
    serps = [load_json(path) for path in xml_paths]
    required_serp_fields = ['query', 'city', 'xmlriver_loc', 'country', 'language', 'device', 'collected_at', 'results']
    for source, path in zip(serps, xml_paths):
        missing_serp = [key for key in required_serp_fields if source.get(key) in (None, '', [])]
        if missing_serp:
            fail(f'Invalid XMLRiver schema in {path}; missing: {missing_serp}')
        if not isinstance(source['results'], list):
            fail(f'Invalid XMLRiver results type: {path}')
        for index, result in enumerate(source['results'], 1):
            if result.get('rank') is None or not result.get('url'):
                fail(f'Invalid XMLRiver result {index} in {path}')

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from pypdf import PdfReader
    except ImportError as exc:
        fail(f'Missing dependency: {exc}. Install reportlab and pypdf in a virtual environment')

    regular, bold = font_pair()
    pdfmetrics.registerFont(TTFont('ReportRegular', str(regular)))
    pdfmetrics.registerFont(TTFont('ReportBold', str(bold)))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RU', parent=styles['BodyText'], fontName='ReportRegular', fontSize=8.2, leading=10.4, textColor=colors.HexColor('#202124')))
    styles.add(ParagraphStyle(name='SmallRU', parent=styles['RU'], fontSize=7, leading=8.5, textColor=colors.HexColor('#526174')))
    styles.add(ParagraphStyle(name='TitleRU', parent=styles['Title'], fontName='ReportBold', fontSize=22, leading=26, textColor=colors.HexColor('#0759A3'), spaceAfter=8*mm))
    styles.add(ParagraphStyle(name='H1RU', parent=styles['Heading1'], fontName='ReportBold', fontSize=15, leading=18, textColor=colors.HexColor('#0759A3'), spaceBefore=4*mm, spaceAfter=3*mm))
    styles.add(ParagraphStyle(name='CoverRU', parent=styles['RU'], fontSize=11, leading=15, alignment=TA_CENTER, textColor=colors.HexColor('#344256')))

    def paragraph(value, style='RU'):
        return Paragraph(html.escape(visible_text(value)), styles[style])

    def render_table(headers, rows):
        count = max(1, len(headers))
        widths = [190*mm/count] * count
        table = Table([[paragraph(cell, 'SmallRU') for cell in headers]] + [[paragraph(cell, 'SmallRU') for cell in row] for row in rows], colWidths=widths, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EAF3FC')),
            ('FONTNAME', (0, 0), (-1, 0), 'ReportBold'),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#D7E0E8')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]))
        return table

    story = [
        Spacer(1, 25*mm),
        Paragraph(f'SEO в {html.escape(spec["city_ru"])}: спрос, ставки и органическая выдача', styles['TitleRU']),
        Paragraph(f'Исследование Webdelo · {html.escape(spec["scope"])}', styles['CoverRU']),
        Spacer(1, 10*mm),
        Paragraph('Ключевые параметры', styles['H1RU']),
        paragraph(f'Частотность выбранных запросов: {spec["frequency_range"]} в месяц. Диапазон ставки для верхней части страницы Google Ads: {spec["cpc_range"]}.'),
        Spacer(1, 3*mm),
        paragraph(f'Google Ads Keyword Planner: Германия (2276), немецкий язык (1001), Google Search; исторические оценки за период {spec["ads_period"]}.'),
        Spacer(1, 3*mm),
        paragraph('Частотность и ставки не гарантируют трафик, клики, фактический CPC или позиции.'),
        PageBreak(),
    ]
    table_titles = []
    for number, block in enumerate(tables, 1):
        data = block.get('data', {}).get('table', {})
        headers = data.get('headers')
        rows = [row.get('cols') for row in data.get('rows', [])]
        if not isinstance(headers, list) or not headers or not rows or any(not isinstance(row, list) or len(row) != len(headers) for row in rows):
            fail(f'Invalid audit table schema in block {block.get("block_id")}')
        title = block.get('title') or f'Таблица {number}'
        table_titles.append(title)
        story.extend([Paragraph(f'{number}. {html.escape(title)}', styles['H1RU']), render_table(headers, rows), paragraph(f'Источник и дата отчёта: {spec["report_date"]}.', 'SmallRU'), PageBreak()])
    queries = []
    for number, source in enumerate(serps, 3):
        queries.append(source['query'])
        rows = []
        for result in source['results']:
            rows.append([str(result.get('rank', '')), html.unescape(result.get('title') or ''), urlparse(result.get('url') or '').netloc, html.unescape(result.get('snippet') or '')])
        caption = f'Источник: XMLRiver. Запрос: {source["query"]}. Фактически получено: {len(rows)} результатов.'
        for key, label in [('city', 'Город'), ('xmlriver_loc', 'Location ID'), ('country', 'Страна'), ('language', 'Язык'), ('device', 'Устройство'), ('collected_at', 'Собрано')]:
            if source.get(key) is not None:
                caption += f' {label}: {source[key]}.'
        story.extend([Paragraph(f'{number}. Органический топ: {html.escape(source["query"])}', styles['H1RU']), render_table(['№', 'Заголовок', 'Домен', 'Сниппет'], rows), paragraph(caption, 'SmallRU')])
        if number < len(serps) + 2:
            story.append(PageBreak())

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.white)
        canvas.rect(0, 0, landscape(A4)[0], landscape(A4)[1], fill=1, stroke=0)
        canvas.setFont('ReportRegular', 7)
        canvas.setFillColor(colors.HexColor('#526174'))
        canvas.drawString(12*mm, 7*mm, f'Webdelo · SEO-исследование {spec["city"]}')
        canvas.drawRightString(landscape(A4)[0] - 12*mm, 7*mm, f'Страница {doc.page}')
        canvas.restoreState()

    output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output), pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=13*mm, title=f'SEO {spec["city"]} Research Report')
    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    reader = PdfReader(str(output))
    extracted = '\n'.join(page.extract_text() or '' for page in reader.pages)
    required_text = [spec['city_ru'], spec['scope'], spec['frequency_range'], spec['cpc_range'], *table_titles, *queries]
    absent = [value for value in required_text if value not in extracted]
    if absent:
        fail(f'PDF text verification failed; missing: {absent}')
    result = {'status': 'ok', 'output': str(output), 'page_count': len(reader.pages), 'table_titles': table_titles, 'queries': queries, 'serp_row_counts': [len(source['results']) for source in serps]}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
