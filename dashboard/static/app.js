'use strict';
const $ = id => document.getElementById(id);
const STATE = {data: null, page: 'overview', productPage: 0, differencePage: 0, request: null};
const PAGES = {
  overview: ['운영 요약', '매장 운영 요약', '결제와 상품 데이터를 함께 살펴보는 매장 운영 현황입니다.'],
  sales: ['매출 분석', '매출 흐름 살펴보기', '날짜와 요일별로 결제 기준·상품 기준 금액을 비교합니다.'],
  products: ['상품·카테고리', '상품 판매 분석', '원본 상품과 카테고리별 판매량·금액을 확인합니다.'],
  validation: ['데이터 검증', '검증 결과 확인', '차이를 숨기지 않고, 확인된 범위와 미확인 사항을 함께 표시합니다.'],
  source: ['데이터 출처', '분석 데이터의 출처', '단일 원본 파일과 처리 결과 버전을 추적합니다.']
};
const STATUS = {review_required: '검토 필요', checks_passed: '자동 검사 통과 · 미승인', error: '검증 오류'};
function node(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function replace(id, ...children) { $(id).replaceChildren(...children); }
function exact(value) {
  const s = String(value);
  if (!/^-?\d+(\.0+)?$/.test(s)) throw new Error('원 단위 정수가 아닌 값입니다. 자동 반올림하지 않습니다.');
  return BigInt(s.split('.')[0]);
}
function number(value) { return value === null || value === undefined ? '—' : exact(value).toLocaleString('ko-KR'); }
function won(value) { return value === null || value === undefined ? '—' : `${number(value)}원`; }
function share(value, denominator) {
  if (value === null || denominator === null || exact(denominator) === 0n) return '—';
  const tenths = exact(value) * 1000n / exact(denominator);
  const sign = tenths < 0n ? '-' : '';
  const absolute = tenths < 0n ? -tenths : tenths;
  return `${sign}${absolute / 10n}.${absolute % 10n}%`;
}
function table(headers, rows, leftColumns = []) {
  if (!rows.length) return node('p', '선택 기간에 표시할 기록이 없습니다. 미관측을 매출 0으로 단정하지 않습니다.', 'empty');
  const t = node('table'), head = node('thead'), body = node('tbody'), hr = node('tr');
  headers.forEach(h => { const th = node('th', h); th.scope = 'col'; hr.append(th); });
  head.append(hr);
  rows.forEach(row => {
    const tr = node('tr');
    row.forEach((v, i) => {
      const td = node('td', v, leftColumns.includes(i) ? 'left' : '');
      tr.append(td);
    });
    body.append(tr);
  });
  t.append(head, body); return t;
}
function kpi(label, value, note, cls = '', unit = '') {
  const card = node('article', null, `kpi ${cls}`), content = node('div', value, 'kpi-value');
  if (unit) content.append(node('small', unit));
  card.append(node('div', label, 'kpi-label'), content, node('div', note, 'kpi-note')); return card;
}
function go(page) {
  STATE.page = page;
  for (const [id, values] of Object.entries(PAGES)) {
    $(id).hidden = id !== page;
    document.querySelector(`[data-page="${id}"]`).classList.toggle('active', id === page);
    if (id === page) {
      $('breadcrumb').textContent = values[0]; $('page-title').textContent = values[1];
      $('page-description').textContent = values[2]; document.title = `WEVAPE · ${values[0]}`;
    }
  }
}
function svgElement(tag, attrs = {}, text) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, String(v)));
  if (text !== undefined) e.textContent = text;
  return e;
}
function chart(rows, labelField = 'date') {
  if (!rows.length) return node('p', '선택 기간의 관측 데이터가 없습니다.', 'empty');
  const w = 850, h = 290, left = 70, right = 25, top = 28, bottom = 43;
  const values = rows.flatMap(r => [r.payment, r.item]).filter(v => v !== null).map(v => Number(exact(v)));
  if (!values.length) return node('p', '금액을 확인할 수 없습니다.', 'empty');
  const lo = Math.min(0, ...values), hi = Math.max(1, ...values), range = hi - lo;
  // Only chart geometry uses Number. Money display/calculation remains exact.
  const y = v => top + (hi - v) / range * (h - top - bottom);
  const x = i => left + (rows.length === 1 ? (w - left - right) / 2 : i / (rows.length - 1) * (w - left - right));
  const svg = svgElement('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': '결제 기준과 상품 기준 금액 비교. 정확한 금액은 표에서 확인할 수 있습니다.'});
  for (let i = 0; i <= 4; i++) {
    const v = lo + range * i / 4, yy = y(v);
    svg.append(svgElement('line', {x1: left, x2: w - right, y1: yy, y2: yy, stroke: '#e9eee6', 'stroke-dasharray': '3 5'}));
    svg.append(svgElement('text', {x: left - 10, y: yy + 3, 'text-anchor': 'end', fill: '#8a968a', 'font-size': 10}, `${(v / 10000).toFixed(v < 100000 ? 1 : 0)}만`));
  }
  for (const [field, color, dashed] of [['payment', '#15735e', false], ['item', '#98b47b', true]]) {
    let path = '', connected = false;
    rows.forEach((r, i) => {
      if (r[field] === null) { connected = false; return; }
      path += `${connected ? 'L' : 'M'}${x(i)},${y(Number(exact(r[field])))} `; connected = true;
    });
    svg.append(svgElement('path', {d: path, fill: 'none', stroke: color, 'stroke-width': dashed ? 2 : 2.5, ...(dashed ? {'stroke-dasharray': '5 4'} : {})}));
    rows.forEach((r, i) => {
      if (r[field] === null) return;
      const circle = svgElement('circle', {cx: x(i), cy: y(Number(exact(r[field]))), r: 3, fill: color});
      circle.append(svgElement('title', {}, `${r[labelField]} · ${field === 'payment' ? '결제' : '상품'} ${won(r[field])}`)); svg.append(circle);
    });
  }
  rows.forEach((r, i) => {
    if (i % Math.max(1, Math.ceil(rows.length / 8)) === 0 || i === rows.length - 1) {
      const label = labelField === 'date' ? r.date.slice(5).replace('-', '.') : r[labelField];
      svg.append(svgElement('text', {x: x(i), y: h - 13, 'text-anchor': 'middle', fill: '#82907f', 'font-size': 10}, label));
    }
  });
  return svg;
}
function paginate(id, current, total, size, onChange) {
  const pages = Math.max(1, Math.ceil(total / size)), previous = node('button', '이전'), next = node('button', '다음');
  previous.disabled = current === 0; next.disabled = current >= pages - 1;
  previous.onclick = () => onChange(current - 1); next.onclick = () => onChange(current + 1);
  replace(id, node('span', `${total.toLocaleString('ko-KR')}개 · ${current + 1} / ${pages}`), previous, next);
}
function renderProducts() {
  const d = STATE.data, query = $('product-search').value.trim().toLocaleLowerCase('ko-KR');
  const field = $('product-sort').value;
  const rows = [...d.products].filter(r => `${r.name} ${r.category}`.toLocaleLowerCase('ko-KR').includes(query));
  rows.sort((a, b) => { const diff = exact(b[field]) - exact(a[field]); return diff < 0n ? -1 : diff > 0n ? 1 : a.name.localeCompare(b.name, 'ko'); });
  const start = STATE.productPage * 15;
  $('product-count').textContent = `${rows.length}개`;
  replace('product-table', table(['순위', '상품명', '카테고리', '양수수량', '음수수량 절댓값', '순수량', '상품 기준 금액'], rows.slice(start, start + 15).map((r, i) => [start + i + 1, r.name, r.category, number(r.positive_quantity), number(r.negative_quantity), number(r.net_quantity), won(r.amount)]), [1, 2]));
  paginate('product-pagination', STATE.productPage, rows.length, 15, p => { STATE.productPage = p; renderProducts(); });
}
function renderDifferences() {
  const rows = STATE.data.differences, start = STATE.differencePage * 20;
  $('difference-count').textContent = `${rows.length}건`;
  if (!rows.length && STATE.data.available) {
    replace('difference-table', node('p', '선택 기간에서 계산된 금액 불일치가 없습니다. 데이터 완전성·고유성 확인과는 별개입니다.', 'empty'));
  } else {
    replace('difference-table', table(['기준일자', '주문번호', '결제금액', '상품금액', '차액', '주문할인', '원본 결제 / 상품 행'], rows.slice(start, start + 20).map(r => [r.date, r.order, won(r.payment), won(r.item), won(r.difference), r.has_order_discount ? '있음 · 원인 미확정' : '없음', `${r.payment_rows.join(', ')} / ${r.item_rows.join(', ')}`])));
  }
  paginate('difference-pagination', STATE.differencePage, rows.length, 20, p => { STATE.differencePage = p; renderDifferences(); });
}
function render(d) {
  const m = d.meta, s = d.summary, valid = d.available && s && s.has_records;
  const selected = key => valid ? s[key] : null;
  $('report-period').textContent = `원본 ${m.report_start || '미확인'} ~ ${m.report_end || '미확인'}`;
  for (const id of ['start-date', 'end-date']) { $(id).min = m.report_start || ''; $(id).max = m.report_end || ''; }
  $('start-date').value = m.filter_start || ''; $('end-date').value = m.filter_end || '';
  $('source-short').textContent = `출처: ${m.source_file} · ${m.schema_version}`;
  $('snapshot-short').textContent = `결과 ${m.result_sha256.slice(0, 12)} · 파일 전체 상태: ${STATUS[m.validation_status] || m.validation_status}`;
  $('nav-issues').textContent = m.unresolved_count;
  $('overview-status').textContent = STATUS[m.validation_status] || m.validation_status;
  $('overview-status').className = `status-chip ${m.validation_status === 'error' ? 'bad' : ''}`;
  replace('kpis',
    kpi('결제 기준 금액', number(selected('payment_amount')), '선택 기간 · 결제금액 부호 포함 합계', 'featured', '원'),
    kpi('상품 기준 금액', number(selected('item_amount')), '선택 기간 · 옵션·할인·취소 반영', '', '원'),
    kpi('결제 − 상품 차액', number(selected('difference')), '선택 기간 · 임의 보정 없음', 'attention', '원'),
    kpi('미해결 검증 이슈', String(m.unresolved_count), '파일 전체 · error + review · info 제외', 'attention', '건'));
  const summary = node('div', null, 'validation-rows');
  for (const [label, value, note] of [
    ['매출 확정 여부', '미확정', '승인 기능 없음'],
    ['금액 불일치 주문', number(selected('difference_orders')), '선택 기간'],
    ['부가세 차액', won(selected('vat_difference')), '결제 − 상품'],
    ['데이터 완전성', '미확인', '파일 내 기록만 분석']]) {
    const row = node('div', null, 'summary-row'), text = node('div', label); text.append(node('small', ` · ${note}`)); row.append(text, node('strong', value)); summary.append(row);
  }
  replace('validation-summary', summary);
  const eventStats = [
    ['승인 결제 이벤트', selected('approved_events'), '결제상태 = 승인 · 고객 수 아님'],
    ['취소 결제 이벤트', selected('cancelled_events'), '결제상태 = 취소'],
    ['순결제건수', selected('net_payment_count'), '원본 결제건수의 부호 포함 합'],
    ['복수 승인 결제 주문', selected('multiple_payments'), '동일 후보 키의 승인 2행 이상'],
    ['상품 순수량', selected('net_quantity'), '양수수량 − 음수수량 절댓값']
  ];
  replace('event-stats', ...eventStats.map(([label, value, note]) => { const e = node('div', null, 'stat'); e.append(node('span', label), node('strong', number(value)), node('small', note)); return e; }));
  replace('overview-chart', chart(d.daily)); replace('daily-chart', chart(d.daily));
  replace('daily-table', table(['기준일자', '결제 기준', '상품 기준', '결제 − 상품'], d.daily.map(r => [r.date, won(r.payment), won(r.item), r.payment === null || r.item === null ? '—' : won(exact(r.payment) - exact(r.item))])));
  const weekdays = ['월', '화', '수', '목', '금', '토', '일'];
  replace('weekday-chart', chart(d.weekdays.map(r => ({...r, label: weekdays[r.weekday]})), 'label'));
  replace('weekday-table', table(['요일', '관측 일수', '결제 합계', '상품 합계'], d.weekdays.map(r => [weekdays[r.weekday], r.days ? `${r.days}일` : '관측 없음', won(r.payment), won(r.item)])));
  renderProducts(); renderDifferences();
  const max = d.categories.reduce((value, r) => exact(r.amount) > value ? exact(r.amount) : value, 1n);
  replace('category-bars', ...d.categories.slice(0, 6).map(r => { const row = node('div', null, 'bar-row'), track = node('div', null, 'bar-track'), bar = node('div', null, 'bar-fill'); bar.style.width = `${Math.max(0, Number(exact(r.amount) * 100n / max))}%`; track.append(bar); row.append(node('span', r.name), track, node('span', won(r.amount), 'amount')); return row; }));
  replace('category-table', table(['카테고리', '양수수량', '음수수량 절댓값', '순수량', '수량 비중', '상품 기준 금액', '금액 비중'], d.categories.map(r => [r.name, number(r.positive_quantity), number(r.negative_quantity), number(r.net_quantity), share(r.net_quantity, s?.net_quantity ?? null), won(r.amount), share(r.amount, s?.item_amount ?? null)])));
  replace('validation-cards', kpi('파일 전체 검증', STATUS[m.validation_status] || m.validation_status, '자동 검사와 매출 승인 구분', 'attention'), kpi('선택 기간 금액 차액', won(selected('difference')), '결제 − 상품 · 보정 없음', 'attention'), kpi('선택 기간 부가세 차액', won(selected('vat_difference')), '양쪽 세액 원본 합계의 차이', 'attention'), kpi('매출 확정', '아니요', '자동 확정·승인 미구현'));
  const stageStatus = {completed: '실행 확인', error_or_incomplete: '오류 또는 미완료', not_confirmed: '실행 미확인', error: '오류', unverified: '미검증', not_implemented: '미구현'};
  replace('stage-table', table(['단계', '상태', '확인 범위'], d.stages.map(r => [r.name, stageStatus[r.status], r.note]), [0, 1, 2]));
  replace('cancel-review', ...[
    `승인 결제금액 ${won(selected('approved_amount'))} / 취소 결제금액 ${won(selected('cancelled_amount'))}. 취소 부호가 이미 포함되어 있어 다시 차감하지 않습니다.`,
    `상품 양수수량 ${number(selected('positive_quantity'))} / 음수수량 절댓값 ${number(selected('negative_quantity'))} / 순수량 ${number(selected('net_quantity'))}. 음수수량의 운영 의미는 상태와 함께 검토해야 합니다.`,
    `상품할인 ${won(selected('product_discount'))} / 주문할인 ${won(selected('order_discount'))}. 취소에 의한 할인 상계를 포함합니다. 복합 할인명의 개별 금액은 분리하지 않습니다.`,
    `금액 상계 취소 그룹 ${number(selected('cancel_offsets'))}개 / 남는 0원 주문 ${number(selected('zero_orders'))}개. 후보 주문 그룹은 고객 수가 아닙니다. 객단가는 미제공입니다.`,
    '다른 날 환불·부분환불, 취소 수량·세액·원거래 일대일 대응은 검증되지 않았습니다.'
  ].map(text => node('p', text)));
  const issueContent = [];
  const codes = {};
  for (const i of d.issues) { const key = `${i.severity} · ${i.code}`; codes[key] = (codes[key] || 0) + 1; }
  const list = node('ul', null, 'review-list'); Object.entries(codes).forEach(([code, count]) => list.append(node('li', `${code}: ${count}건`))); issueContent.push(list);
  const details = node('details'); details.append(node('summary', '파일 전체 이슈 상세 (원본 행·후보 키)'), node('pre', JSON.stringify(d.issues, null, 2))); issueContent.push(details);
  const observationDetails = node('details'); observationDetails.append(node('summary', '부가세 관찰 결과 (확정된 세금 규칙 아님)'), node('pre', d.observations ? JSON.stringify(d.observations, null, 2) : '미실행 또는 결과 없음')); issueContent.push(observationDetails);
  replace('issues-list', ...issueContent);
  const info = [['원본 파일', m.source_file], ['원본 SHA-256 (처리 전)', m.source_sha256], ['원본 SHA-256 (처리 후)', m.source_sha256_after], ['처리 전후 동일 여부', m.source_unchanged ? '동일' : '변경 감지'], ['관찰된 데이터 형식 버전', m.schema_version], ['파서 코드 SHA-256', m.parser_sha256], ['대시보드 처리 버전', m.adapter_version], ['전체 파서 결과 SHA-256', m.result_sha256], ['이번 실행 처리 시각', new Date(m.processed_at).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'}) + ' (Asia/Seoul)'], ['원본 기간·기준', `${m.report_start} ~ ${m.report_end} / ${m.report_basis} / ${m.start_time}`], ['현재 선택 기간', `${m.filter_start} ~ ${m.filter_end}`], ['데이터 완전성', '미확인 · 기간 전체가 완전하다고 단정하지 않음'], ['저장·승인', m.database ? '비공개 DB · 검토 수용된 단일 버전 · 확정 매출 아님' : '메모리 스냅샷 · DB 미사용 · 승인·자동 확정 없음']];
  replace('provenance', ...info.flatMap(([label, value]) => [node('dt', label), node('dd', value)]));
  if (!d.available) { $('error').hidden = false; $('error').textContent = '파서 오류 또는 무결성 문제로 분석을 중단했습니다. 금액을 0으로 표시하지 않습니다. 데이터 검증 화면에서 확인해 주세요.'; }
}
async function load(query = '') {
  if (STATE.request) STATE.request.abort();
  const request = new AbortController(); STATE.request = request;
  $('loading').hidden = false; $('loading').textContent = '원본 파서 결과를 불러오는 중…'; $('apply').disabled = true; $('error').hidden = true;
  try {
    const response = await fetch(`/api/analysis${query}`, {signal: request.signal});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    STATE.data = data; STATE.productPage = STATE.differencePage = 0; render(data);
  } catch (error) {
    if (error.name === 'AbortError') return;
    $('error').textContent = `조회 실패: ${error.message} 필터 적용에 실패한 경우 기존 화면은 이전 조회 결과입니다.`; $('error').hidden = false;
  } finally {
    if (STATE.request === request) { $('loading').hidden = true; $('apply').disabled = false; }
  }
}
document.querySelectorAll('[data-page]').forEach(button => button.onclick = () => go(button.dataset.page));
$('go-validation').onclick = $('review-link').onclick = () => go('validation');
$('date-form').onsubmit = event => { event.preventDefault(); load(`?${new URLSearchParams({start: $('start-date').value, end: $('end-date').value})}`); };
$('reset').onclick = () => load();
$('product-search').oninput = $('product-sort').onchange = () => { if (STATE.data) { STATE.productPage = 0; renderProducts(); } };
load();
