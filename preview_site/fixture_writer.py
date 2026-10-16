"""Minimal synthetic OOXML fixtures, built with stdlib only; no real POS rows."""
from collections import defaultdict
from copy import deepcopy
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZipFile, ZIP_DEFLATED

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
PH=['결제기준일자','결제시각','주문채널','주문번호','결제건수','결제금액','부가세','결제수단','매입사','결제상태','결제취소시각']
IH=['주문기준일자','결제상태','주문시작시각','주문채널','주문번호','상품명','상품코드','카테고리','옵션','상품할인','주문할인','수량','상품가격','옵션가격','상품할인 금액','주문할인 금액','실판매금액 \n (할인, 옵션 포함)','과세여부','부가세액']
SH=['기간','상품명','상품코드','카테고리','판매건수','상품가격','옵션가격','할인','실 판매 금액\n(할인, 옵션 포함)','부가세액']
MH=['현금','카드','QR결제','계좌이체','선불지급수단','기타']
AH=['Alipay+ partner','KB국민카드','NH카드','기타','롯데카드사','비씨카드사','삼성카드사','신한카드','우리카드','위쳇-KSNET','카카오Pay','토스페이','하나카드','현대카드사']
DATE='2030-02-03'


def payment(order='001', amount=110, vat=10, status='승인', method='카드', day=DATE):
    return [day,day+' 12:00:00','테스트채널',order, -1 if status=='취소' else 1,amount,vat,method,None,status,day+' 12:01:00' if status=='취소' else None]


def item(order='001', amount=110, vat=10, qty=1, price=120, discount=-10, status='완료', day=DATE, product='합성상품A'):
    return [day,status,day+' 12:00:00','테스트채널',order,product,None,'합성분류',None,None,'합성할인' if discount else None,qty,price,0,0,discount,amount,'과세',vat]


def sheets(payments=None, items=None):
    payments=deepcopy(payments if payments is not None else [payment()])
    items=deepcopy(items if items is not None else [item()])
    pg=defaultdict(list)
    for r in payments:pg[r[0]].append(r)
    ps=[]
    for day,rs in sorted(pg.items()):
        method_totals={m:sum(r[5] for r in rs if r[7]==m) for m in MH}
        ps.append([day,sum(r[5] for r in rs),sum(r[6] for r in rs),sum(r[4] for r in rs),None]+list(method_totals.values())+[None]+[0]*len(AH))
    ig=defaultdict(list)
    for r in items:ig[(r[0],r[5],r[6],r[7])].append(r)
    ss=[]
    for key,rs in ig.items():
        ss.append(list(key)+[sum(r[11] for r in rs),sum(r[12] for r in rs),sum(r[13] for r in rs),sum(r[14]+r[15] for r in rs),sum(r[16] for r in rs),sum(r[18] for r in rs)])
    days=[r[0] for r in payments+items] or [DATE]
    return {
        '데이터 기준':[['시작일자','종료일자','매출 정산 기준','매출 시작 시간','집계 단위'],[None,None,'설명','설명',None],[min(days),max(days),'주문한 날','00:00:00','일간'],[],['합성 안내문']],
        '결제 합계':[[None]*4+['결제수단별']+[None]*6+['매입사별'],['기간','결제금액','부가세','결제건수',None]+MH+[None]+AH]+ps,
        '상품 주문 합계':[SH.copy()]+ss,
        '결제 상세내역':[PH.copy(),[None,None,None,'합성 설명']]+payments,
        '상품 주문 상세내역':[IH.copy(),[None,'합성 설명']]+items,
    }


def write_xlsx(path, data, bad_dimension=True):
    """Create temporary fixture only. No artifact or original workbook editing."""
    relns='http://schemas.openxmlformats.org/package/2006/relationships'
    docrel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    types=Element('Types',xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
    SubElement(types,'Default',Extension='rels',ContentType='application/vnd.openxmlformats-package.relationships+xml')
    SubElement(types,'Default',Extension='xml',ContentType='application/xml')
    SubElement(types,'Override',PartName='/xl/workbook.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    workbook=Element('workbook',xmlns=NS,attrib={'xmlns:r':docrel})
    tabs=SubElement(workbook,'sheets')
    rels=Element('Relationships',xmlns=relns)
    package=Element('Relationships',xmlns=relns)
    SubElement(package,'Relationship',Id='rId1',Type=docrel+'/officeDocument',Target='xl/workbook.xml')
    with ZipFile(path,'w',ZIP_DEFLATED) as archive:
        for index,(name,rows) in enumerate(data.items(),1):
            SubElement(tabs,'sheet',name=name,sheetId=str(index),attrib={'r:id':f'rId{index}'})
            SubElement(rels,'Relationship',Id=f'rId{index}',Type=docrel+'/worksheet',Target=f'worksheets/sheet{index}.xml')
            SubElement(types,'Override',PartName=f'/xl/worksheets/sheet{index}.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            sheet=Element('worksheet',xmlns=NS)
            if bad_dimension:SubElement(sheet,'dimension',ref='A1')
            content=SubElement(sheet,'sheetData')
            for row_number,values in enumerate(rows,1):
                row=SubElement(content,'row',r=str(row_number))
                for col,v in enumerate(values,1):
                    if v is None:continue
                    n=col;label=''
                    while n:n,m=divmod(n-1,26);label=chr(65+m)+label
                    cell=SubElement(row,'c',r=label+str(row_number))
                    if isinstance(v,dict):
                        SubElement(cell,'f').text=v['formula']
                    elif isinstance(v,str):
                        cell.set('t','inlineStr')
                        SubElement(SubElement(cell,'is'),'t').text=v
                    else:SubElement(cell,'v').text=str(v)
            archive.writestr(f'xl/worksheets/sheet{index}.xml',tostring(sheet))
        archive.writestr('[Content_Types].xml',tostring(types))
        archive.writestr('_rels/.rels',tostring(package))
        archive.writestr('xl/workbook.xml',tostring(workbook))
        archive.writestr('xl/_rels/workbook.xml.rels',tostring(rels))
