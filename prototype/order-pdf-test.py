"""Inspect actual Chromium A5 PDFs produced by order-test.cjs (pip install pymupdf)."""
import json
import re
from pathlib import Path
import pymupdf

out = Path(__file__).resolve().parent.parent / 'demo-assets/screenshots/orders'
report = []
phrase = 'Nội dung kiểm thử dài, giữ nguyên cách dùng.'
for name, pages, items in [('draft', 1, 0), ('prescription', 1, 1), ('consultation', 1, 3),
                           ('mixed', 2, 4), ('five', 1, 5), ('long', None, 24), ('oversize', None, 1)]:
    doc = pymupdf.open(out / (name + '.pdf'))
    text = '\n'.join(p.get_text() for p in doc)
    normalized = ' '.join(text.split())
    if pages is not None:
        assert len(doc) == pages, (name, 'page count', len(doc), pages)
    else:
        assert len(doc) > 1, (name, 'must paginate')
    for page in doc:
        assert abs(page.rect.width - 148 / 25.4 * 72) < 1
        assert abs(page.rect.height - 210 / 25.4 * 72) < 1
        assert page.get_text().strip(), (name, 'blank page')
        for x0, y0, x1, y1, *_ in page.get_text('words'):
            assert x0 >= 0 and y0 >= 0 and x1 <= page.rect.width + 1 and y1 <= page.rect.height + 1, (name, 'clipped text')
    if name == 'draft':
        assert 'BẢN NHÁP' in text and 'Desloratadine' not in text
    else:
        assert len(re.findall(r'^\d+\. ', text, re.M)) == items, (name, 'missing or duplicate item')
    if name in ['consultation', 'five', 'long', 'oversize']:
        assert 'Bác sĩ tư vấn' in text and 'Mang theo phiếu này' in text
        assert 'Bác sĩ khám' not in text and 'Desloratadine' not in text
    if name == 'prescription':
        assert 'Bác sĩ khám' in text and 'Cicaderm' not in text
    if name in ['five', 'long', 'oversize']:
        assert 'FOOTER_END_MARKER' in doc[-1].get_text()
    if name in ['long', 'oversize']:
        expected = 24 * 8 if name == 'long' else 220
        assert normalized.count(phrase) == expected, (name, 'lost long instructions', normalized.count(phrase))
    if name in ['five', 'consultation', 'long']:
        doc[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(out / (name + '.png'))
    report.append(dict(file=name + '.pdf', pages=len(doc), items=items, status='PASS'))
(out / 'pdf-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
