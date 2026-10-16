# WEVAPE 공개 미리보기 배포 안내

이 배포는 **가상 데이터 전용**이며 운영 서비스가 아닙니다. 실제 POS 파일, 고객 정보, 분석 결과, 운영 DB, 비밀키를 사용하지 않습니다. 로그인 없이 누구나 볼 수 있으므로 실제 데이터 연결을 추가하지 마세요.

## 확인한 현재 구조

- `secure_site/urls.py`: `/login/` → 인증 후 `/`, 관리자 `/imports/`, 보호된 `/api/analysis` 등. `secure_templates/`, `secure_static/`은 로그인·가져오기·세션 UI입니다.
- 기존 운영 실행 진입점은 `gunicorn secure_site.wsgi:application`입니다. 필수 환경변수·PostgreSQL 및 운영 검증이 필요하므로 이번 미리보기에 사용하지 않습니다. `manage_secure.py runserver` 역시 운영 설정을 요구합니다.
- 기존 로컬 `python -m dashboard.server --port 8765`는 실제 POS 파일을 읽습니다. 외부 배포에 사용하지 않습니다.
- 새 미리보기는 기존 대시보드 HTML/CSS/JS와 집계 함수를 재사용합니다. `preview_site.wsgi:application`으로만 실행하며 `/`, `/api/analysis`, `/app.js`, `/style.css`, `/healthz`만 제공합니다. 업로드·로그인·DB·승인은 없습니다.
- 2030-02-01~21의 가상 상품·주문을 코드로 생성해 임시 가상 엑셀을 기존 파서로 읽습니다. 취소·복수 결제·0원·1원 불일치도 가상 사례입니다. 임시 엑셀은 파싱 후 삭제하며 결과는 메모리에만 둡니다. 프로세스 재시작마다 생성 파일 해시와 처리 시각이 달라질 수 있습니다. 표시된 해시는 실제 매출 파일의 해시가 아닙니다.

## 1. Windows에서 먼저 확인

현재 작업 PC에서는 프로젝트 루트의 `powershell -ExecutionPolicy Bypass -File .\run_preview.ps1`로 기존 준비된 Python과 의존성을 사용할 수 있습니다. 이 명령은 새 패키지를 설치하지 않습니다. 아래는 다른 PC 또는 새 환경에서의 방법입니다.

프로젝트 루트 또는 내보낸 배포 폴더에서 PowerShell을 엽니다. Python 3.12가 필요합니다. 새 PC에서만 다음으로 전용 가상환경을 준비하세요.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-preview.txt
.\.venv\Scripts\python.exe -m preview_site.server --port 8766
```

브라우저: http://127.0.0.1:8766/ . 종료는 Ctrl+C입니다. 이 주소는 PC 내부용이며 휴대폰용 외부 주소가 아닙니다. Gunicorn은 Linux 호스팅에서 사용하고 Windows에서는 위 서버를 사용합니다. 개발 실행 서버를 인터넷에 직접 노출하지 마세요.

## 2. 배포 전용 폴더 생성 및 점검

**원래 프로젝트 전체를 GitHub에 올리지 않습니다.** 프로젝트 루트에서:

```powershell
python scripts/export_preview.py
Get-ChildItem -Recurse -File .runtime\preview-deploy
```

출력은 `.runtime/preview-deploy/`입니다. 기존 폴더가 있으면 덮어쓰지 않습니다. 다시 내보낼 때는 `--output .runtime/preview-deploy-v2`처럼 새 경로를 지정하세요. 허용한 소스만 복사하며 `preview-manifest.json`에 파일별 SHA-256을 기록합니다. 원본 `data/`, `analysis/`, `.env*`, `.git/`, `.runtime/`, 운영 보안 모듈 및 DB 모델은 복사하지 않습니다. 단, 예시 안내서 안에 제외 경로가 텍스트로 언급될 수 있습니다.

배포 폴더에는 `preview_site/`, `dashboard/server.py`, 대시보드 정적 파일 3개, `pos_parser.py`, 의존성 목록, Dockerfile, `render.yaml`, 안내서, ignore 파일, manifest만 있어야 합니다. 파서와 기존 서버 소스는 집계 재사용에 필요하지만 원본 파일은 포함되지 않습니다. 실행 진입점을 변경하지 마세요. 실제 자료를 새로 추가하지 마세요.

## 3. 사용자가 수행: 별도 GitHub 저장소 생성

현재 원본 Git 저장소에는 remote와 추적 파일이 없습니다. 이번 작업은 커밋·푸시하지 않습니다. GitHub에서 **새로운 비공개 저장소**를 만들고, 아래 명령은 반드시 내보낸 폴더 안에서만 실행하세요. 원본 프로젝트에서 `git add .`를 하지 마세요.

```powershell
Set-Location .runtime\preview-deploy
git init -b main
git add preview_site dashboard pos_parser.py requirements-preview.txt Dockerfile.preview render.yaml PREVIEW_DEPLOYMENT.md .dockerignore .gitignore preview-manifest.json
git diff --cached --name-only
git diff --cached --stat
# 목록에 실제 자료나 비밀 파일이 없는지 직접 확인한 뒤 실행
git commit -m "Add synthetic-only homepage preview"
git remote add origin <사용자가_생성한_새_GitHub_저장소_URL>
git push -u origin main
```

이 명령은 사용자가 수행할 절차이며 이번 작업에서 실행한 것이 아닙니다. 배포 폴더의 `render.yaml`은 루트 `render.preview.yaml`을 복사한 파일입니다.

## 4. 사용자가 수행: Render 연결 및 배포

Render는 Django/Python과 Docker 웹 서비스를 지원하므로 기존 기술을 유지할 수 있습니다. 정적 페이지만 배포하는 방식과 달리 서버에서 날짜 필터 및 파서 기반 예시 집계를 유지합니다. 이번에는 운영 DB가 필요 없습니다.

1. Render 계정을 만들고 GitHub의 **새 미리보기 저장소만** 연결합니다.
2. New → Blueprint에서 저장소와 `render.yaml`을 선택합니다. Web Service 하나, Docker, Free, `/healthz`, DB 없음인지 확인하고 적용합니다. 계정의 Free 사용 가능 여부와 화면에 표시된 비용을 확인합니다. 유료 전환은 별도 선택입니다.
3. Blueprint 대신 New → Web Service를 쓰면 Runtime Docker, Dockerfile `./Dockerfile.preview`, Context `.`, Health Check `/healthz`, Free를 선택합니다. 별도 Python build/start 명령은 입력하지 않습니다. Dockerfile이 설치와 실행을 담당합니다.
4. 빌드·기동 로그와 Health Check 성공을 확인합니다. Docker 내부 실행 명령은 아래와 같습니다.

```sh
gunicorn preview_site.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 2 --timeout 60 --access-logfile - --error-logfile -
```

5. Render 화면에서 실제로 발급된 HTTPS URL을 복사하여 PC와 휴대폰에서 엽니다. 가상 예시 표시, 날짜 필터, 상품 검색, 검증 상세가 나오는지 확인합니다. 발급 전 URL을 임의로 만들 수 없습니다.

Render Free 서비스는 비활동 15분 후 중지될 수 있어 다음 접속 시 기동 대기가 생깁니다. 상시 운영 보장이나 운영 배포 완료를 의미하지 않습니다. 미리보기 종료 시 Render에서 해당 서비스만 중지/삭제할 수 있습니다. 이번 준비 작업에서는 Render 계정 연결·외부 배포·실제 URL 확인을 수행하지 않습니다.

공식 문서: https://render.com/docs/docker , https://render.com/docs/blueprint-spec , https://render.com/docs/web-services , https://render.com/docs/free

## 환경변수

| 변수 | 설정 방법 | 용도 |
|---|---|---|
| `PORT` | Render 제공, 미지정 시 10000 | 0.0.0.0 바인딩 |
| `RENDER_EXTERNAL_HOSTNAME` | Render 자동 제공 | Django 허용 호스트에 실제 도메인 추가 |
| `PYTHONDONTWRITEBYTECODE` / `PYTHONUNBUFFERED` | Dockerfile에서 1 | 캐시 방지·로그 출력 |
| `DJANGO_SETTINGS_MODULE` | 사용자가 설정하지 않음 | WSGI가 preview_site.settings만 허용 |

`DATABASE_URL`, `WEVAPE_SECRET_KEY`, `WEVAPE_DATA_KEY`, `.env` 등은 넣지 않습니다. 미리보기의 고정 Django 키는 인증·세션·서명 기능이 없는 공개 데모 설정이며 운영 키가 아닙니다. 사용자 지정 도메인은 아직 지원 설정에 포함하지 않았습니다. 추가하려면 호스트 허용 정책을 별도로 검토합니다.

## 오류 확인 및 확인 범위

- 로컬: 실행한 터미널의 traceback 확인. 의존성 오류면 실행 Python과 가상환경 경로 확인. 포트 충돌이면 `--port 8767` 사용.
- Render: Build Logs(설치/이미지), Runtime Logs(기동), Events(Health Check)를 순서대로 확인. `/healthz`가 200인지 확인. 400이면 `RENDER_EXTERNAL_HOSTNAME` 및 접속 도메인 확인. 운영용 `secure_site.wsgi` 또는 운영 환경변수를 잘못 설정하지 않았는지 확인.
- `/healthz`는 합성 데이터 파싱과 집계도 확인합니다. 파싱 오류를 0원 정상 결과로 바꾸지 않습니다.
- DB 생성, 마이그레이션, collectstatic, 운영 자료 업로드는 필요 없으며 실행하지 않습니다. 정적 파일은 정확히 두 경로만 Django가 제공합니다.
- Docker 이미지 빌드 및 외부 URL 접속 확인은 실제 호스팅 이후 별도 검증 대상입니다. 로컬 테스트 결과는 작업 완료 보고를 참고하세요.
- 후속 운영 개발은 비공개 서비스에서 진행하고, 이 공개 미리보기와 실제 자료를 혼합하지 않습니다.
