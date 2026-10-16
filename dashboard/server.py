"""Local-only, read-only POS dashboard. No database or result-file writes."""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

from pos_parser import CRITERIA, PAY, ITEM, ITEM_AMOUNT, parse_workbook, json_default

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name('static')
DEFAULT_SOURCE = ROOT / 'data/raw/매출리포트_260901-260930_186838.xlsx'
ADAPTER_VERSION = 'local-dashboard-v1'
ZERO = Decimal(0)


def total(rows, field):
    return sum((r['values'][field] for r in rows), ZERO)


def load_snapshot(path):
    """Call existing parser without invoking legacy scripts that overwrite files."""
    result = parse_workbook(path)
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, default=json_default)
    return {
        'result': result,
        'processed_at': datetime.now(timezone.utc).isoformat(),
        'result_sha256': sha256(canonical.encode('utf-8')).hexdigest(),
        'parser_sha256': sha256((ROOT / 'pos_parser.py').read_bytes()).hexdigest(),
    }


def safe_issue(issue):
    # Do not send raw rows, customer fields, local absolute paths, or arbitrary text.
    return {k: issue[k] for k in ('code', 'severity', 'sheet', 'row', 'rows', 'field', 'key', 'difference', 'cause') if k in issue}


def analyze(snapshot, start=None, end=None):
    r = snapshot['result']
    settings_rows = r['sheets'].get(CRITERIA, {}).get('records', [])
    settings = settings_rows[0]['values'] if settings_rows else {}
    report_start, report_end = settings.get('시작일자'), settings.get('종료일자')
    start, end = start or report_start, end or report_end
    for value in (start, end):
        if value is not None:
            if not isinstance(value, str) or len(value) != 10:
                raise ValueError('날짜는 YYYY-MM-DD 형식이어야 합니다.')
            date.fromisoformat(value)
    if start and end and start > end:
        raise ValueError('시작일은 종료일보다 늦을 수 없습니다.')
    if report_start and report_end and start and end and (start < report_start or end > report_end):
        raise ValueError('원본 보고서 기간 안에서 날짜를 선택해 주세요.')
    errors = [i for i in r['issues'] if i['severity'] == 'error']
    reviews = [i for i in r['issues'] if i['severity'] == 'review']
    usable = not errors and r['totals'] is not None and r['source'].get('unchanged') is True
    metadata = {
        'source_file': Path(r['source']['path']).name,
        'source_sha256': r['source']['sha256_before'],
        'source_sha256_after': r['source']['sha256_after'],
        'source_unchanged': r['source']['unchanged'],
        'schema_version': r['schema_version'], 'adapter_version': ADAPTER_VERSION,
        'parser_sha256': snapshot['parser_sha256'], 'result_sha256': snapshot['result_sha256'],
        'processed_at': snapshot['processed_at'],
        'report_start': report_start, 'report_end': report_end,
        'report_basis': settings.get('매출 정산 기준'),
        'start_time': settings.get('매출 시작 시간'),
        'validation_status': r['validation_status'],
        'confirmed_sales': False, 'database': False, 'coverage_status': 'unknown',
        'filter_start': start, 'filter_end': end,
        'issue_counts': dict(Counter(i['severity'] for i in r['issues'])),
        'unresolved_count': len(errors) + len(reviews),
    }
    # Existing parser has no stage markers. Do not turn inferred completion into
    # a guarantee of global uniqueness, completeness, cancellation, or approval.
    stages = [
        {'name': '셀·헤더·자료형 검사', 'status': 'completed' if r['totals'] is not None else 'error_or_incomplete', 'note': '원본 파서 반환값 기준'},
        {'name': '주문·합계 대조', 'status': 'completed' if r['totals'] is not None else 'not_confirmed', 'note': '검사 실행과 오류 유무는 별개'},
        {'name': '처리 전후 원본 해시', 'status': 'completed' if r['source']['unchanged'] else 'error', 'note': '시작 시 읽은 스냅샷 비교'},
        {'name': '날짜별 데이터 완전성', 'status': 'unverified', 'note': '누락 일자를 휴무·0원으로 간주하지 않음'},
        {'name': '동일 키·동일 시각 주문 구분', 'status': 'unverified', 'note': '고유 거래 식별자가 없어 완전 검증 불가'},
        {'name': '취소의 수량·세액·원거래 대응', 'status': 'unverified', 'note': '현재 파서는 그룹 금액 상계 중심'},
        {'name': '매출 승인', 'status': 'not_implemented', 'note': '자동 확정·승인 기능 없음'},
    ]
    response = {'meta': metadata, 'available': usable, 'stages': stages,
                'issues': [safe_issue(i) for i in r['issues']],
                'observations': r.get('observations'), 'summary': None,
                'daily': [], 'weekdays': [], 'products': [], 'categories': [], 'differences': []}
    if not usable:
        return response
    def in_range(d):
        return start <= d <= end
    p = [row for row in r['sheets'][PAY]['records'] if in_range(row['values']['결제기준일자'])]
    items = [row for row in r['sheets'][ITEM]['records'] if in_range(row['values']['주문기준일자'])]
    orders = [o for o in r['orders'] if in_range(o['key'][0])]
    days = sorted({row['values']['결제기준일자'] for row in p} | {row['values']['주문기준일자'] for row in items})
    response['summary'] = {
        'payment_amount': total(p, '결제금액'), 'item_amount': total(items, ITEM_AMOUNT),
        'difference': total(p, '결제금액') - total(items, ITEM_AMOUNT),
        'vat_difference': total(p, '부가세') - total(items, '부가세액'),
        'approved_events': sum(row['values']['결제상태'] == '승인' for row in p),
        'cancelled_events': sum(row['values']['결제상태'] == '취소' for row in p),
        'net_payment_count': total(p, '결제건수'),
        'approved_amount': total([row for row in p if row['values']['결제상태'] == '승인'], '결제금액'),
        'cancelled_amount': total([row for row in p if row['values']['결제상태'] == '취소'], '결제금액'),
        'positive_quantity': sum((row['values']['수량'] for row in items if row['values']['수량'] > 0), ZERO),
        'negative_quantity': -sum((row['values']['수량'] for row in items if row['values']['수량'] < 0), ZERO),
        'net_quantity': total(items, '수량'),
        'product_discount': total(items, '상품할인 금액'), 'order_discount': total(items, '주문할인 금액'),
        'difference_orders': sum(o['payment_minus_item'] != 0 for o in orders),
        'candidate_order_groups': len(orders),
        'multiple_payments': sum(o['multiple_approved_payments'] for o in orders),
        'cancel_offsets': sum(o['cancel_amounts_offset'] for o in orders),
        'zero_orders': sum(o['zero_order_without_cancel'] for o in orders),
        'observed_days': len(days), 'has_records': bool(p or items),
    }
    for d in days:
        pp = [row for row in p if row['values']['결제기준일자'] == d]
        ii = [row for row in items if row['values']['주문기준일자'] == d]
        response['daily'].append({'date': d, 'payment': total(pp, '결제금액') if pp else None,
                                  'item': total(ii, ITEM_AMOUNT) if ii else None})
    for weekday in range(7):
        rows = [row for row in response['daily'] if date.fromisoformat(row['date']).weekday() == weekday]
        response['weekdays'].append({'weekday': weekday, 'days': len(rows),
            'payment': sum((row['payment'] for row in rows if row['payment'] is not None), ZERO) if rows else None,
            'item': sum((row['item'] for row in rows if row['item'] is not None), ZERO) if rows else None})
    def aggregate(group, key):
        return {**key, 'positive_quantity': sum((row['values']['수량'] for row in group if row['values']['수량'] > 0), ZERO),
            'negative_quantity': -sum((row['values']['수량'] for row in group if row['values']['수량'] < 0), ZERO),
            'net_quantity': total(group, '수량'), 'amount': total(group, ITEM_AMOUNT)}
    products, categories = defaultdict(list), defaultdict(list)
    for row in items:
        v = row['values']
        products[(v['상품명'], v['카테고리'], v['상품코드'])].append(row)
        categories[v['카테고리']].append(row)
    response['products'] = sorted((aggregate(group, {'name': k[0], 'category': k[1], 'code': k[2]}) for k, group in products.items()), key=lambda x: (-x['amount'], x['name']))
    response['categories'] = sorted((aggregate(group, {'name': k}) for k, group in categories.items()), key=lambda x: (-x['amount'], x['name']))
    response['differences'] = [{'date': o['key'][0], 'channel': o['key'][1], 'order': o['key'][2],
        'payment': o['payment_amount'], 'item': o['item_amount'], 'difference': o['payment_minus_item'],
        'payment_rows': o['payment_rows'], 'item_rows': o['item_rows'],
        'has_order_discount': o['has_order_discount']} for o in orders if o['payment_minus_item'] != 0]
    return response


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, snapshot):
        self.snapshot = snapshot
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def send_payload(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        host = self.headers.get('Host', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost'):
            self.send_error(403)
            return
        url = urlparse(self.path)
        if url.path == '/api/analysis':
            try:
                params = parse_qs(url.query)
                if set(params) - {'start', 'end'} or any(len(v) != 1 for v in params.values()):
                    raise ValueError('지원하지 않는 요청입니다.')
                response = analyze(self.server.snapshot, params.get('start', [None])[0], params.get('end', [None])[0])
                self.send_payload(200, json.dumps(response, ensure_ascii=False, default=json_default).encode('utf-8'), 'application/json; charset=utf-8')
            except ValueError as exc:
                self.send_payload(400, json.dumps({'error': str(exc)}, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')
            except Exception:
                import traceback
                traceback.print_exc()
                self.send_payload(500, b'{"error":"Analysis failed. See server terminal."}', 'application/json')
            return
        allowed = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if url.path not in allowed:
            self.send_error(404)
            return
        name, mime = allowed[url.path]
        self.send_payload(200, (ASSETS / name).read_bytes(), mime + '; charset=utf-8')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--input', type=Path, default=DEFAULT_SOURCE)
    cli.add_argument('--port', type=int, default=8765)
    args = cli.parse_args()
    if not 1 <= args.port <= 65535:
        cli.error('포트는 1~65535여야 합니다.')
    print('원본을 읽기 전용으로 파싱·검증합니다…', flush=True)
    try:
        snapshot = load_snapshot(args.input)
        server = DashboardServer(('127.0.0.1', args.port), snapshot)
    except Exception as exc:
        print(f'시작 실패 ({type(exc).__name__}): {exc}', file=sys.stderr)
        return 1
    print(f'Local: http://127.0.0.1:{args.port}', flush=True)
    print('DB 없음 / 미확정 분석 / 종료: Ctrl+C / 원본 변경 반영: 서버 재시작', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
