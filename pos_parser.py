"""Read-only parser for the TOSS report layout observed in September 2026.

No import-time I/O, network, corrections, database, or implicit output files.
Amounts are Decimal; JSON encodes decimals as exact decimal strings.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import warnings
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import openpyxl

SCHEMA_VERSION = 'toss-report-observed-2026-09-v1'
CRITERIA = '데이터 기준'
PAY_SUM = '결제 합계'
ITEM_SUM = '상품 주문 합계'
PAY = '결제 상세내역'
ITEM = '상품 주문 상세내역'
METHODS = ['현금', '카드', 'QR결제', '계좌이체', '선불지급수단', '기타']
ACQUIRERS = ['Alipay+ partner', 'KB국민카드', 'NH카드', '기타', '롯데카드사',
             '비씨카드사', '삼성카드사', '신한카드', '우리카드', '위쳇-KSNET',
             '카카오Pay', '토스페이', '하나카드', '현대카드사']

HEADERS = {
    CRITERIA: ['시작일자', '종료일자', '매출 정산 기준', '매출 시작 시간', '집계 단위'],
    PAY_SUM: ['기간', '결제금액', '부가세', '결제건수'] + ['결제수단별/'+h for h in METHODS] + ['매입사별/'+h for h in ACQUIRERS],
    ITEM_SUM: ['기간', '상품명', '상품코드', '카테고리', '판매건수', '상품가격', '옵션가격', '할인', '실 판매 금액(할인, 옵션 포함)', '부가세액'],
    PAY: ['결제기준일자', '결제시각', '주문채널', '주문번호', '결제건수', '결제금액', '부가세', '결제수단', '매입사', '결제상태', '결제취소시각'],
    ITEM: ['주문기준일자', '결제상태', '주문시작시각', '주문채널', '주문번호', '상품명', '상품코드', '카테고리', '옵션', '상품할인', '주문할인', '수량', '상품가격', '옵션가격', '상품할인 금액', '주문할인 금액', '실판매금액(할인, 옵션 포함)', '과세여부', '부가세액'],
}
ITEM_AMOUNT = HEADERS[ITEM][16]
ITEM_SUM_AMOUNT = HEADERS[ITEM_SUM][8]
NUMERIC = {
    CRITERIA: [], PAY_SUM: HEADERS[PAY_SUM][1:],
    ITEM_SUM: HEADERS[ITEM_SUM][4:], PAY: ['결제건수', '결제금액', '부가세'],
    ITEM: HEADERS[ITEM][11:17]+['부가세액'],
}
DATES = {CRITERIA: ['시작일자', '종료일자'], PAY_SUM: ['기간'], ITEM_SUM: ['기간'], PAY: ['결제기준일자'], ITEM: ['주문기준일자']}
TIMES = {CRITERIA: [], PAY_SUM: [], ITEM_SUM: [], PAY: ['결제시각', '결제취소시각'], ITEM: ['주문시작시각']}
OPTIONAL = {'상품코드', '옵션', '상품할인', '주문할인', '매입사', '결제취소시각'}


def _label(v):
    return re.sub(r'\s+', '', v) if isinstance(v, str) else v


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def order_key(row, sheet):
    """Candidate key scoped to ONE store/report; never a payment/line unique ID."""
    v = row['values']
    return (v['결제기준일자' if sheet == PAY else '주문기준일자'], v['주문채널'], v['주문번호'])


def _issue(result, code, severity='error', **context):
    result['issues'].append({'code': code, 'severity': severity, **context})


def _read_sheet(ws, result):
    name = ws.title
    try:
        advertised = ws.calculate_dimension()
    except ValueError:
        advertised = None  # Dimension may be absent as well as inaccurate.
    ws.reset_dimensions()  # The original workbook advertises A1 for all sheets.
    grid, cell_errors = [], []
    for cells in ws.iter_rows():
        row = []
        for cell in cells:
            row.append(cell.value)
            if cell.data_type in ('f', 'e'):
                cell_errors.append({'cell': cell.coordinate, 'kind': cell.data_type})
        grid.append(row)
    sheet = {'advertised_dimension': advertised, 'actual_rows': len(grid),
             'actual_columns': max(map(len, grid), default=0), 'raw_rows': grid,
             'columns': [], 'records': []}
    result['sheets'][name] = sheet
    for problem in cell_errors:
        _issue(result, 'UNSUPPORTED_FORMULA_OR_ERROR', sheet=name, **problem)
    if name not in HEADERS:
        _issue(result, 'UNRECOGNIZED_SHEET', 'review', sheet=name)
        return
    header_row, start = (2, 3) if name == PAY_SUM else (1, 3 if name in (PAY, ITEM, CRITERIA) else 2)
    sheet.update(header_row=header_row, data_start_row=start)
    if len(grid) < header_row:
        _issue(result, 'MISSING_HEADER', sheet=name)
        return
    canonical = {_label(h): h for h in HEADERS[name]}
    group = None
    seen = set()
    for index, raw_header in enumerate(grid[header_row-1]):
        if name == PAY_SUM:
            marker = grid[0][index] if index < len(grid[0]) else None
            if marker not in (None, ''):
                group = marker.strip() if isinstance(marker, str) else marker
        if raw_header in (None, ''):
            sheet['columns'].append({'index': index+1, 'raw_header': raw_header, 'group': group, 'field': None})
            continue
        label = (str(group)+'/' if group else '')+str(raw_header)
        field = canonical.get(_label(label))
        sheet['columns'].append({'index': index+1, 'raw_header': raw_header, 'group': group, 'field': field})
        if field is None:
            _issue(result, 'UNRECOGNIZED_COLUMN', sheet=name, column=index+1, header=label)
        elif field in seen:
            _issue(result, 'DUPLICATE_COLUMN', sheet=name, column=index+1, field=field)
        else:
            seen.add(field)
    for h in HEADERS[name]:
        if h not in seen:
            _issue(result, 'MISSING_COLUMN', sheet=name, field=h)
    if seen != set(HEADERS[name]) or any(i['severity']=='error' and i.get('sheet')==name for i in result['issues']):
        return
    selected = list(enumerate(grid[start-1:], start))
    if name == CRITERIA:
        selected = selected[:1]  # Rows 4/5 are blank / explanatory, retained raw.
    for row_number, raw in selected:
        if not any(v not in (None, '') for v in raw):
            continue
        record = {'row': row_number, 'values': {}}
        values = record['values']
        for column in sheet['columns']:
            h = column['field']
            v = raw[column['index']-1] if column['index']<=len(raw) else None
            if h is None:
                if v not in (None, ''):
                    _issue(result, 'DATA_IN_SEPARATOR', sheet=name, row=row_number, column=column['index'])
                continue
            values[h] = v
            if v in (None, ''):
                if h not in OPTIONAL:
                    _issue(result, 'MISSING_VALUE', sheet=name, row=row_number, field=h)
                continue
            try:
                if h in NUMERIC[name]:
                    if isinstance(v, bool) or not isinstance(v, (int, float, Decimal)):
                        raise ValueError('expected numeric Excel cell')
                    number = Decimal(str(v))
                    if not number.is_finite():
                        raise ValueError('non-finite number')
                    if h in ('수량', '판매건수', '결제건수') and number != number.to_integral_value():
                        raise ValueError('fractional count is outside the observed contract')
                    values[h] = number
                elif h in DATES[name]:
                    if not isinstance(v, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
                        raise ValueError('expected YYYY-MM-DD string')
                    date.fromisoformat(v)
                elif h in TIMES[name]:
                    if not isinstance(v, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', v):
                        raise ValueError('expected YYYY-MM-DD HH:MM:SS string')
                    datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
                elif name == CRITERIA and h == '매출 시작 시간':
                    if not isinstance(v,str) or not re.fullmatch(r'\d{2}:\d{2}:\d{2}',v):
                        raise ValueError('expected HH:MM:SS string')
                    datetime.strptime(v,'%H:%M:%S')
                elif not isinstance(v, str) or not v.strip():
                    raise ValueError('expected non-empty text; numeric IDs are not padded by guessing')
            except (ValueError, ArithmeticError) as exc:
                _issue(result, 'INVALID_VALUE', sheet=name, row=row_number, field=h, reason=str(exc))
        if len(raw)>len(sheet['columns']) and any(v not in (None,'') for v in raw[len(sheet['columns']):]):
            _issue(result, 'DATA_WITHOUT_HEADER', sheet=name, row=row_number)
        sheet['records'].append(record)
    if not sheet['records']:
        _issue(result, 'NO_RECORDS', sheet=name)


def _sum(rows, field):
    return sum((r['values'][field] for r in rows), Decimal(0))


def _groups(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return grouped


def _validate(result):
    tables = {n: s['records'] for n,s in result['sheets'].items() if n in HEADERS}
    p, items = tables[PAY], tables[ITEM]
    pg = _groups(p, lambda r: order_key(r, PAY))
    ig = _groups(items, lambda r: order_key(r, ITEM))
    criteria = tables[CRITERIA][0]['values']
    if criteria['시작일자']>criteria['종료일자']:
        _issue(result, 'INVALID_PERIOD')
    if (criteria['매출 정산 기준'], criteria['매출 시작 시간'], criteria['집계 단위']) != ('주문한 날','00:00:00','일간'):
        _issue(result, 'UNVERIFIED_REPORT_BASIS', 'review', values=criteria)
    for name, rows in tables.items():
        if name == CRITERIA:
            continue
        counts = defaultdict(list)
        for row in rows:
            counts[tuple(row['values'].items())].append(row['row'])
            for h in DATES[name]:
                if not criteria['시작일자'] <= row['values'][h] <= criteria['종료일자']:
                    _issue(result, 'DATE_OUTSIDE_REPORT', sheet=name, row=row['row'], field=h)
        for row_numbers in counts.values():
            if len(row_numbers)>1:
                _issue(result, 'EXACT_DUPLICATE_ROWS', 'review', sheet=name, rows=row_numbers)
    for name,rows,known in [(PAY,p,{'승인','취소'}),(ITEM,items,{'완료','취소'})]:
        for r in rows:
            v=r['values']
            if v['결제상태'] not in known:
                _issue(result,'UNVERIFIED_STATUS','review',sheet=name,row=r['row'],value=v['결제상태'])
            if name==PAY and v['결제상태']=='취소' and not v['결제취소시각']:
                _issue(result,'MISSING_CANCEL_TIME',sheet=name,row=r['row'])
            time_field = '결제시각' if name==PAY else '주문시작시각'
            if order_key(r,name)[0]!=v[time_field][:10]:
                _issue(result,'BASIS_DATE_TIME_DIFFERENCE','review',sheet=name,row=r['row'])
            if v['결제상태']=='취소' and (v['결제금액' if name==PAY else ITEM_AMOUNT]>0 or v['결제건수' if name==PAY else '수량']>=0):
                _issue(result,'CANCEL_SIGN_INCONSISTENT','review',sheet=name,row=r['row'])
    orders=[]
    for key in sorted(pg.keys()|ig.keys()):
        pp,ii=pg.get(key,[]),ig.get(key,[])
        payment,product=_sum(pp,'결제금액'),_sum(ii,ITEM_AMOUNT)
        starts=sorted(set(r['values']['주문시작시각'] for r in ii))
        entry={'key':key,'payment_rows':[r['row'] for r in pp], 'item_rows':[r['row'] for r in ii],
               'matched':bool(pp and ii),'ambiguous':len(starts)>1,
               'payment_amount':payment,'item_amount':product,'payment_minus_item':payment-product,
               'payment_vat':_sum(pp,'부가세'),'item_vat':_sum(ii,'부가세액'),
               'payment_states':dict(Counter(r['values']['결제상태'] for r in pp)),
               'item_states':dict(Counter(r['values']['결제상태'] for r in ii)),
               'has_order_discount':any(r['values']['주문할인 금액']!=0 for r in ii),
               'has_cancel':any(r['values']['결제상태']=='취소' for r in pp+ii),
               'multiple_approved_payments':sum(r['values']['결제상태']=='승인' for r in pp)>1}
        entry['cancel_amounts_offset']=entry['has_cancel'] and entry['matched'] and payment==product==0
        entry['zero_order_without_cancel']=entry['matched'] and not entry['has_cancel'] and payment==0
        orders.append(entry)
        if not entry['matched']:
            _issue(result,'UNMATCHED_ORDER',key=key,missing_side=PAY if not pp else ITEM)
        if entry['ambiguous']:
            _issue(result,'AMBIGUOUS_ORDER_KEY',key=key,item_start_times=starts)
        if entry['matched'] and payment!=product:
            _issue(result,'ORDER_AMOUNT_DIFFERENCE','review',key=key,difference=payment-product,has_order_discount=entry['has_order_discount'],cause='unconfirmed')
        if entry['has_cancel'] and not entry['cancel_amounts_offset']:
            _issue(result,'CANCEL_NOT_FULLY_OFFSET','review',key=key)
    result['orders']=orders
    # Compare independent summaries at the same grain, never join raw line sets.
    daily=[]
    date_groups={n:_groups(tables[n],lambda r:r['values'][DATES[n][0]]) for n in (PAY_SUM,ITEM_SUM,PAY,ITEM)}
    for day in sorted(set().union(*(g.keys() for g in date_groups.values()))):
        groups={n:g.get(day,[]) for n,g in date_groups.items()}
        row={'date':day,'payment_summary':_sum(groups[PAY_SUM],'결제금액'), 'payment_detail':_sum(groups[PAY],'결제금액'),
             'item_summary':_sum(groups[ITEM_SUM],ITEM_SUM_AMOUNT), 'item_detail':_sum(groups[ITEM],ITEM_AMOUNT)}
        for summary,detail,fields in [(PAY_SUM,PAY,[('결제금액','결제금액'),('부가세','부가세'),('결제건수','결제건수')]),(ITEM_SUM,ITEM,[(ITEM_SUM_AMOUNT,ITEM_AMOUNT),('부가세액','부가세액'),('판매건수','수량')])]:
            if len(groups[summary])>1 and summary==PAY_SUM:
                _issue(result,'DUPLICATE_SUMMARY_KEY',sheet=summary,date=day)
            if not groups[summary] or not groups[detail]:
                _issue(result,'MISSING_DAILY_SIDE',sheet=summary,date=day)
            for sf,df in fields:
                if _sum(groups[summary],sf)!=_sum(groups[detail],df):
                    _issue(result,'DAILY_SUMMARY_DIFFERENCE',sheet=summary,date=day,field=sf,summary=_sum(groups[summary],sf),detail=_sum(groups[detail],df))
        daily.append(row)
    result['daily']=daily
    sg=_groups(tables[ITEM_SUM],lambda r:tuple(r['values'][h] for h in ('기간','상품명','상품코드','카테고리')))
    dg=_groups(items,lambda r:tuple(r['values'][h] for h in ('주문기준일자','상품명','상품코드','카테고리')))
    for key in sg.keys()|dg.keys():
        aa,bb=sg.get(key,[]),dg.get(key,[])
        if len(aa)>1:
            _issue(result,'DUPLICATE_SUMMARY_KEY',sheet=ITEM_SUM,key=key)
        for sf,df in [('판매건수','수량'),('상품가격','상품가격'),('옵션가격','옵션가격'),(ITEM_SUM_AMOUNT,ITEM_AMOUNT),('부가세액','부가세액'),('할인',None)]:
            detail=_sum(bb,df) if df else _sum(bb,'상품할인 금액')+_sum(bb,'주문할인 금액')
            if not aa or not bb or _sum(aa,sf)!=detail:
                _issue(result,'PRODUCT_SUMMARY_DIFFERENCE',key=key,field=sf,summary=_sum(aa,sf),detail=detail)
    for name,rows,amount,discounts in [(ITEM,items,ITEM_AMOUNT,['상품할인 금액','주문할인 금액']),(ITEM_SUM,tables[ITEM_SUM],ITEM_SUM_AMOUNT,['할인'])]:
        for r in rows:
            v=r['values']
            if v['상품가격']+v['옵션가격']+sum(v[h] for h in discounts)!=v[amount]:
                _issue(result,'ITEM_EQUATION_DIFFERENCE',sheet=name,row=r['row'])
    for r in tables[PAY_SUM]:
        if sum(r['values']['결제수단별/'+h] for h in METHODS)!=r['values']['결제금액']:
            _issue(result,'PAYMENT_METHOD_SUM_DIFFERENCE',sheet=PAY_SUM,row=r['row'])
    # Empirical observations, NOT a general tax or discount policy.
    tax_observations={
        'item_rounding_mismatch_rows':[r['row'] for r in items if (r['values'][ITEM_AMOUNT]/11).quantize(Decimal(1),rounding=ROUND_HALF_UP)!=r['values']['부가세액']],
        'payment_order_status_truncation_mismatches':[],
        'basis':'empirical September observation; not a confirmed tax rule',
    }
    for key,rows in _groups(p,lambda r:(order_key(r,PAY),r['values']['결제상태'])).items():
        if (_sum(rows,'결제금액')/11).quantize(Decimal(1),rounding=ROUND_DOWN)!=_sum(rows,'부가세'):
            tax_observations['payment_order_status_truncation_mismatches'].append(key)
    result['observations']=tax_observations
    totals={'payment_amount':_sum(p,'결제금액'),'item_amount':_sum(items,ITEM_AMOUNT),
            'payment_vat':_sum(p,'부가세'),'item_vat':_sum(items,'부가세액'),
            'net_payment_count':_sum(p,'결제건수'),'net_quantity':_sum(items,'수량'),
            'product_discount':_sum(items,'상품할인 금액'),'order_discount':_sum(items,'주문할인 금액'),
            'payment_rows':len(p),'item_rows':len(items),'payment_order_groups':len(pg),'item_order_groups':len(ig)}
    totals.update(payment_minus_item=totals['payment_amount']-totals['item_amount'],payment_minus_item_vat=totals['payment_vat']-totals['item_vat'])
    result['totals']=totals
    if totals['payment_minus_item_vat']:
        _issue(result,'TOTAL_VAT_DIFFERENCE','review',difference=totals['payment_minus_item_vat'],cause='unconfirmed')


def parse_workbook(path):
    """Read a byte snapshot, retain raw cells + typed records + separate diagnostics.

    Structural/type errors disable aggregation (totals=None), never silently skip
    invalid rows. Valid but inconsistent files retain totals with error/review flags.
    """
    path=Path(path).resolve()
    if path.suffix.lower()!='.xlsx':
        raise ValueError('Only the observed .xlsx format is supported')
    payload=path.read_bytes()
    before=hashlib.sha256(payload).hexdigest()
    result={'schema_version':SCHEMA_VERSION,'source':{'path':str(path),'sha256_before':before},
            'sheets':{},'issues':[],'totals':None,'orders':[],'daily':[], 'confirmed_sales':False}
    wb=None
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',UserWarning)
            wb=openpyxl.load_workbook(BytesIO(payload),read_only=True,data_only=False,keep_links=False)
            for ws in wb:
                _read_sheet(ws,result)
        for warning in caught:
            _issue(result,'WORKBOOK_READER_WARNING','info',message=str(warning.message))
        for name in HEADERS:
            if name not in result['sheets']:
                _issue(result,'MISSING_SHEET',sheet=name)
        if not any(i['severity']=='error' for i in result['issues']):
            _validate(result)
    finally:
        if wb is not None:
            wb.close()
        after=sha256(path)
        result['source'].update(sha256_after=after,unchanged=before==after)
    if not result['source']['unchanged']:
        _issue(result,'SOURCE_CHANGED_DURING_READ')
    result['validation_status']='error' if any(i['severity']=='error' for i in result['issues']) else 'review_required' if any(i['severity']=='review' for i in result['issues']) else 'checks_passed'
    return result


def json_default(value):
    if isinstance(value,Decimal):
        return format(value,'f')
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,help='Optional NEW .json outside data/raw; existing paths refused')
    parser.add_argument('--summary',action='store_true',help='Print compact validation summary instead of raw records')
    args=parser.parse_args()
    if args.output:
        output=args.output.resolve()
        raw_root=Path(__file__).resolve().parent/'data'/'raw'
        if output==args.input.resolve() or output.is_relative_to(raw_root) or output.suffix!='.json' or output.exists():
            parser.error('Output must be a NEW .json outside data/raw and different from input')
    try:
        result=parse_workbook(args.input)
    except (OSError,ValueError,openpyxl.utils.exceptions.InvalidFileException,BadZipFile,ParseError) as exc:
        print(json.dumps({'error':type(exc).__name__,'message':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
    if args.summary:
        compact={k:result[k] for k in ('schema_version','source','validation_status','confirmed_sales','totals')}
        compact['issue_counts']=dict(Counter(i['code'] for i in result['issues']))
        compact['order_counts']={
            'unmatched':sum(not r['matched'] for r in result['orders']),
            'ambiguous':sum(r['ambiguous'] for r in result['orders']),
            'amount_differences':sum(r['payment_minus_item']!=0 for r in result['orders'] if r['matched']),
            'cancel_offsets':sum(r['cancel_amounts_offset'] for r in result['orders']),
            'multiple_payments':sum(r['multiple_approved_payments'] for r in result['orders']),
            'zero_without_cancel':sum(r['zero_order_without_cancel'] for r in result['orders']),
        }
        result=compact
    encoded=json.dumps(result,ensure_ascii=False,indent=2,default=json_default)
    if args.output:
        with args.output.open('x',encoding='utf-8') as f:
            f.write(encoded+'\n')
    else:
        print(encoded)
    return 2 if result['validation_status']=='error' else 1 if result['validation_status']=='review_required' else 0


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
