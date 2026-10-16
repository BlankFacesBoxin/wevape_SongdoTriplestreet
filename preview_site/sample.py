"""Generate fictional OOXML in a temporary directory, parse once per process.

No input path, upload, external data, or production environment is accepted.
The workbook exists only for the duration of parsing and is then deleted.
"""
from datetime import date, datetime, timezone, timedelta
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pos_parser import parse_workbook, json_default
from preview_site.fixture_writer import payment, item, sheets, write_xlsx

VERSION = 'fictional-preview-v1'

@lru_cache(maxsize=1)
def snapshot():
    payments, items = [], []
    for day_index in range(21):
        day = (date(2030, 2, 1) + timedelta(days=day_index)).isoformat()
        for product_index in range(4):
            order = f'{day_index:02d}{product_index:03d}'
            qty = 1 + (day_index + product_index) % 4
            price = 8700 + product_index * 2300
            amount = qty * price - 300
            # One intentional fictional discrepancy; no attempt at correction.
            paid = amount - (1 if day_index == 4 and product_index == 0 else 0)
            vat = amount // 11
            payments.append(payment(order, paid, vat, day=day))
            row = item(order, amount, vat, qty, qty * price, -300,
                       day=day, product=f'예시 상품 {chr(65 + product_index)}')
            row[6] = f'DEMO-{product_index:02d}'
            row[7] = '예시 카테고리 ' + ('A' if product_index < 2 else 'B')
            items.append(row)
            if day_index == 6 and product_index == 1:
                payments.append(payment(order, -paid, -vat, status='취소', day=day))
                reverse = row.copy()
                reverse[1] = '취소'
                for column in (11, 12, 13, 14, 15, 16, 18):
                    reverse[column] = -reverse[column]
                items.append(reverse)
            if day_index == 8 and product_index == 2:
                payments[-1][5] = paid - 1000
                payments[-1][6] = vat - 90
                payments.append(payment(order, 1000, 90, method='현금', day=day))
    day = '2030-02-21'
    payments.append(payment('DEMO-ZERO', 0, 0, day=day))
    items.append(item('DEMO-ZERO', 0, 0, price=0, discount=0,
                      day=day, product='예시 무료 상품'))
    with TemporaryDirectory(prefix='wevape-fictional-') as folder:
        path = Path(folder) / 'fictional-preview.xlsx'
        write_xlsx(path, sheets(payments, items))
        result = parse_workbook(path)
    result['source']['path'] = 'fictional-preview.xlsx (가상 생성·실제 POS 아님)'
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, default=json_default)
    return {'result': result, 'processed_at': datetime.now(timezone.utc).isoformat(),
            'result_sha256': sha256(canonical.encode()).hexdigest(),
            'parser_sha256': sha256((Path(__file__).resolve().parents[1] / 'pos_parser.py').read_bytes()).hexdigest()}
