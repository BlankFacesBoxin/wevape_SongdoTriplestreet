import json
from pathlib import Path
from django.http import HttpResponse, JsonResponse, HttpResponseNotAllowed
from dashboard.server import analyze
from pos_parser import json_default
from preview_site.sample import snapshot, VERSION

ASSETS = Path(__file__).resolve().parents[1] / 'dashboard' / 'static'

class PreviewBoundary:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.get_host()  # Enforce explicit allowed hosts, including with DEBUG=False.
        if request.method not in ('GET', 'HEAD'):
            response = HttpResponseNotAllowed(['GET', 'HEAD'])
        else:
            response = self.get_response(request)
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        response['X-Frame-Options'] = 'DENY'
        if request.method == 'HEAD':
            response.content = b''
        return response

def home(request):
    html = (ASSETS / 'index.html').read_text(encoding='utf-8')
    for before, after in {
        '단일 매장 · 로컬 분석': '공개 미리보기 · 가상 예시',
        'LOCAL WORKSPACE': 'SYNTHETIC PREVIEW',
        '● 로컬 전용': '● 가상 예시 전용',
        '1차 MVP': '공개 미리보기',
        '미확정 분석 데이터': '가상의 예시 데이터 · 실제 매장 매출 아님',
        '원본 파일을 외부로 전송하지 않습니다.': '실제 파일·고객 정보는 사용하지 않습니다.',
        '원본 파싱·검증 결과를 불러오는 중…': '가상 생성 데이터의 파싱 결과를 불러오는 중…',
        '서버 시작 시 기존 파서로 원본을 다시 읽은 메모리 스냅샷입니다.': '프로세스 시작 후 가상 엑셀을 생성·파싱한 메모리 스냅샷입니다. 해시는 가상 파일에 대한 값입니다.',
    }.items():
        html = html.replace(before, after)
    begin = html.index('<article class="card"><div class="card-head"><h2>현재 구현 범위</h2>')
    end = html.index('</article>', begin) + len('</article>')
    html = html[:begin] + '<article class="card"><div class="review-content"><h2>미리보기 범위</h2><p>모든 수치·상품·주문·검증 이슈는 가상 예시입니다. 날짜 필터, 매출 비교, 상품·카테고리, 검증 화면을 확인할 수 있습니다. DB·로그인·업로드·승인·실제 매출 조회 기능은 이 미리보기에서 제공하지 않습니다. 날짜 완전성 및 실제 매장 검증 상태를 나타내지 않습니다.</p></div></article>' + html[end:]
    return HttpResponse(html)

def analysis(request):
    if set(request.GET) - {'start', 'end'} or any(len(v) != 1 for _, v in request.GET.lists()):
        return JsonResponse({'error': '지원하지 않는 요청입니다.'}, status=400)
    try:
        data = analyze(snapshot(), request.GET.get('start'), request.GET.get('end'))
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    data['meta'].update(preview=True, adapter_version=VERSION)
    return HttpResponse(json.dumps(data, ensure_ascii=False, default=json_default), content_type='application/json; charset=utf-8')

def asset(request, name):
    # name is a constant in urlpatterns; never a user-supplied filesystem path.
    return HttpResponse((ASSETS / name).read_bytes(), content_type=('text/css' if name.endswith('.css') else 'text/javascript') + '; charset=utf-8')

def health(request):
    # Exercise the same synthetic parsing path used by the page, without DB access.
    if not analyze(snapshot())['available']:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok', 'mode': 'synthetic-preview', 'version': VERSION})
