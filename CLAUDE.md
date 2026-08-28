# 프로젝트 AI 코딩 규칙 (Claude Code용)

세션 내부에서 새로운 컨벤션 지정 또는 프로젝트의 변화를 기록하라고 할 때는 `[yyyymmdd]_제목`을 넣고, 그 다음 줄부터 개조식으로 내용을 추가한다.
- **1. 진행 및 응답 규칙**은 절대로 변경하지 않는다.

---

## 1. 진행 및 응답 규칙 (가장 중요)

* **명시적 지시 전 코딩 절대 금지**: 사용자가 **"수정해"**, **"그대로 진행해"**, **"작업시작해"**라고 명시적으로 지시하기 전까지는 절대로 임의로 소스 코드를 작성하거나 수정하지 않는다.
  * **계획(Plan) 사전 승인 필수**: 항상 먼저 계획을 제시하여 사용자의 사전 승인을 받은 후에만 코딩 단계로 진입한다.
  * **계획의 추상화 수준**: 파일명·함수·줄 단위의 구체적 코드 변경 명세를 적지 않고, 아래 두 가지만 담는다.
    1. **요구사항 이해**: 사용자의 요청 내용을 스스로 재정리하여 기술.
    2. **할 작업**: 구현/수정할 기능 동작 단위를 제시 (UI 관련 시 표현 방식 필수 포함 — 예: "진행바는 별도 카드가 아니라 화면을 덮는 오버레이 모달로 구성").
  * 세부 결정은 승인 후 코딩 단계에서 처리한다.
  * 코딩 완료 후에는 테스트 코드를 실행하여 결과를 검증하고 함께 보고한다.
* **질의응답 및 원인 분석 시 수정 금지**:
  * 가능성/방법 문의("~할 수 없어?"): 실제 코드를 작성하지 않고 **적용 가능한 방법과 방향성만 텍스트로 제시**한다.
  * 원인 분석 요청("왜 그렇지?", "원인 파악해", "다시 확인해봐"): **원인 분석 결과와 제안 수정안만 텍스트로 제시**한다.
  * 반영은 사용자가 검토 후 선택·지시했을 때만 수행하며, 기준이 모호할 때는 임의 추측하지 않고 사용자에게 먼저 질문한다.
* **컨벤션 추가 규칙**: 세션 내부에서 새로운 컨벤션 지정 또는 프로젝트 변화를 기록할 때는 `[yyyymmdd]_제목` 형식 아래 개조식으로 추가한다.

---

## 2. 개발 원칙

* **규칙 1 — 역할 분담 및 Thin Client**
  * 프론트엔드(HTML/JS)는 데이터 렌더링 및 사용자 입력 중계만 담당한다.
  * 모든 비즈니스 연산, 데이터 가공, 유효성 검증은 백엔드(Python)가 전담하며 RESTful HTTP API(JSON)로 통신한다.
  * Flask 진입점은 `app.py` 팩토리 파일 하나로 단일화한다. REST 엔드포인트는 `backend/app/api/routes_*.py`에 도메인별 Blueprint로 분리하여 등록한다.
* **규칙 2 — 명세 및 주석 표준**
  * 모든 Python 모듈, 클래스, 함수(메서드) 시작부에 한글 독스트링(Docstring)으로 목적, 매개변수 타입/설명, 반환값을 명시한다.
  * 복잡한 비즈니스 로직 및 주요 조건 분기점에는 상세한 인라인 한글 주석을 작성한다.
* **규칙 3 — 주 객체 중심 모듈화 및 크기 제한**
  * 모든 Python 파일(`.py`)은 하나의 주 객체(Main Class 1개) 중심으로 구성한다.
  * 단일 파일 길이는 주석/독스트링 포함 200줄 이내, 개별 메서드는 30줄 이내를 원칙으로 한다.
  * 기준 초과가 불가피할 경우 초과 사유를 `docs/size_exceptions.md`에 기록하고 사용자 검토를 받는다.
* **규칙 4 — UI 레이아웃 및 공통 사이드바 규격**
  * **진입 분기**: `index.html`에서 기기(PC/모바일)를 자동 감지하여 분기 이동한다.
  * **PC 환경**: `frontend/pages/*.html` 구조, 좌측 사이드바 + 우측 메인 콘텐츠 2분할 레이아웃을 사용한다.
    * 레이아웃 시프트 방지를 위해 `#sidebar-container` 너비는 `width: 220px; flex-shrink: 0;`로 고정한다.
    * 사이드바는 Jinja2 `{% include %}` 등 서버 템플릿 방식으로 렌더링하여 콘텐츠 깜박임을 방지한다 (JS 사후 주입 금지).
    * 활성 메뉴(`active`) 표시는 요청 경로 기준으로 서버 렌더링 시점에 결정한다.
  * **모바일 환경**: `frontend/mobile/pages/*.html` 구조, 상단 헤더 + 하단 탭바 레이아웃을 사용하며 공통 네비게이션은 동적 주입한다.
  * **경로 참조**: HTML 내 리소스 참조는 상대경로(`../css/...`, `../js/...`)를 표준으로 한다.
* **규칙 5 — 데이터 주도 입출력 검증 및 매개변수 완전성**
  * 소스 코드와 단위 테스트는 1:1로 매칭(`backend/tests/.../test_*.py`)하며 케이스별 순번(`test_01_...`)을 부여한다.
  * 입출력 테스트 데이터는 `backend/tests/fixtures/` 내 JSON/TXT 파일로 분리하고, 기본값이 있는 매개변수도 생략 없이 `input`에 기재한다.
  * `inspect` 모듈로 파라미터 완전성을 자동 검증한 후 `[입력값 | 예상값 | 실제 실행 결과]`를 대조 출력한다.
  * 정답 데이터 생성 스크립트 작성 시 대상 fixture 파일과 동일한 베이스명(예: `test_01_truth.py` → `test_01_truth.json`)을 사용한다.
* **규칙 6 — 배치 연산, 외부 시스템 연동 및 알림 (마무리 단계 적용)**
  * 프로젝트 배포 직전 단계에서 적용하며, 대량 데이터 처리는 `BatchProcessor` 클래스가 전담한다.
  * 외부 연동은 전용 REST API(`/api/batch/...`)를 통해 JSON으로 통신하며, 결과/에러는 `DiscordNotifier`를 통해 웹훅으로 발송한다.
* **규칙 7 — 보안 및 배포 환경 최적화**
  * PythonAnywhere 호환 Flask 기반 REST API 및 SQLite(`data/app.db`)를 표준으로 사용한다.
  * 민감한 설정값은 `.env` 파일로 관리하며 `.gitignore`에 등록한다.

---

## 3. 추가 규칙

* **가상환경**: 새 프로젝트 생성 시 항상 프로젝트 루트 내 `.venv` 가상환경을 생성하고 진행한다.
* **테스트 동기화 시점**: 소스가 변경되더라도 사용자가 **"테스트 코드 작성해"**라고 명시적으로 요청할 때만 테스트 코드 및 Fixture를 작성·갱신한다.

---

## 4. 프로젝트 표준 폴더 구조

```text
my_project/
│
├── app.py                         # Flask 앱 팩토리 및 서버 진입점 (Blueprint 등록)
├── backend/                       # [파이썬 백엔드] 비즈니스 로직 및 DB 연동 전담
│   ├── app/
│   │   ├── core/                  # DB 연결 및 전역 설정 (config.py, database.py)
│   │   ├── models/                # DB 모델 클래스
│   │   ├── api/                   # 라우팅 계층: 도메인별 Blueprint 분리 (routes_*.py)
│   │   ├── repositories/          # DB CRUD 전담 클래스
│   │   └── services/              # 순수 비즈니스 로직 (batch_processor, discord_notifier 등)
│   │
│   ├── tests/
│   │   ├── fixtures/              # 테스트 입출력 데이터 (JSON/TXT, 생성 스크립트)
│   │   └── test_*.py              # 객체별 1:1 전용 테스트 (test_01_... 순번 표기)
│   │
│   └── requirements.txt
│
├── data/
│   └── app.db                     # SQLite 로컬 DB (.gitignore 대상)
│
├── frontend/                      # [웹 UI] Thin Client (정적 파일)
│   ├── components/                # PC 공통 UI 컴포넌트 (sidebar.html)
│   ├── pages/                     # PC 개별 화면 (상대경로 참조)
│   ├── css/                       # PC 스타일시트 (common.css: 220px 고정)
│   ├── js/                        # PC 자바스크립트 (api.js 등)
│   ├── mobile/                    # 모바일 전용 영역 (components, pages, css, js)
│   └── index.html                 # 접속 기기 감지 후 PC/Mobile 분기
│
├── .env                           # 보안 환경변수
├── .gitignore
└── README.md
```

---

## 5. 빌드·실행·아키텍처 (Claude Code 참고용)

### 5.1 자주 쓰는 명령어

* **웹 서버 구동**: `python app.py`
  * 환경변수: `FLASK_HOST`(기본 0.0.0.0), `FLASK_PORT`(기본 5000), `FLASK_DEBUG`(기본 True)
* **데이터 수집 파이프라인**: `python run_data_collection.py --mode incremental|full --stage all|1|2|3 [--start YYYYMMDD --end YYYYMMDD]`
  * 1단계: 종목 마스터/타깃 종목 · 2단계: 지수·환율 · 3단계: 타깃별 OHLCV/수급 (기본 20050101~)
* **백테스트 실행**: `python run_backtest.py --combo all|1..21 --target "KOSPI 200,KOSDAQ 150" [--start YYYYMMDD --end YYYYMMDD]`
  * 단독 전략 1~8, 복합 전략 9~21 (`backtest_engine.STRATEGY_COMBOS`). 초기자본 기본 300만 원, 최대 3슬롯.
* **의존성 설치**: `pip install -r backend/requirements.txt`
* **전체 테스트**(unittest, `backend.*` import 해석을 위해 저장소 루트에서 실행): `python -m unittest discover -s backend/tests -v`
* **단일 테스트**: `python -m unittest backend.tests.test_09_backtest_engine -v`

### 5.2 아키텍처 개요

* **프레임워크**: `requirements.txt`에 FastAPI가 있으나 실제 구동 앱은 **Flask**. 진입점은 `app.py` 단일 파일.
* **라우팅**: Blueprint 2개가 모두 `/api` prefix를 공유한다.
  * `backend/app/api/routes.py` (`api_bp`) — 시장 데이터, 동기화, 종목 검색/필터, 차트, 지수
  * `backend/app/api/routes_paper.py` (`paper_api_bp`) — 백테스트 실행/진행률, 리더보드, 모의투자 포트폴리오/매매
* **계층 구조**: `api/routes_*` → `repositories/*` (DB CRUD 전담) → `models/*` (SQLAlchemy ORM). 순수 연산 로직은 `services/*` (`backtest_engine`, `*_collector`, `proposal_advisor`, `proposal_advisor_cache`, `kospi_regime_analyzer`).
* **DB**: SQLAlchemy. `DATABASE_URL` 기본값 `sqlite:///./data/app.db`. `db_manager.create_all_tables()`가 테이블 생성과 함께 `paper_*` 테이블에 대한 임시 `ALTER TABLE` 마이그레이션(`account_type` 컬럼)도 수행한다.
* **프론트엔드 현황**: 실제 화면은 저장소 루트 `templates/`(Jinja 서버 렌더) + `static/`(JS/CSS)로 구성된다. 위 4장의 `frontend/` 디렉터리 구조는 목표 구조이며 현재 코드와 다르다.
  * `/proposal` 라우트는 모바일 User-Agent를 감지해 `/proposal-mobile`로 리다이렉트한다.
  * 두 투자제안 화면 모두 첫 응답 깜빡임 방지를 위해 `latest_trading_date`, `kospi_regime`을 SSR로 주입한다.
* **전략 모듈**: `backend/app/services/strategies/` 아래 `base_strategy.py` 기반의 s1~s5 및 변형(s1a/s1b/s1c 등).
* **수집 파이프라인**: `run_data_collection.py`의 `run_pipeline()`이 3단계를 증분/전체 모드로 실행하며, API(`/api/sync`)에서도 동일 로직을 호출한다.

### 5.3 [20260828]_로컬 알림 훅 (Windows 토스트 + Discord 웹훅)

* **목적**: 개발자가 세션을 떠나 있어도 확인 요청·작업 완료·장시간 방치를 알림으로 통지.
* **구성 위치**: 스크립트는 `.claude/hooks/*.ps1`, 훅 등록은 `.claude/settings.local.json`(개인·비공개, git 미추적). 저장소 공유 설정(`settings.json`) 아님.
* **트리거별 동작**:
  * `Notification` 훅 → 확인/권한 요청 또는 입력 대기 시 **즉시** Windows 토스트 (소리 `Reminder`). 이벤트 종류 필터링 없음.
  * `UserPromptSubmit` 훅 → 턴 시작 시각 기록, 대기 중이던 Discord 예약 취소.
  * `Stop` 훅 → 턴 소요시간이 `>= 15초`면 "작업 완료" 토스트 (소리 `Default`, 본문 = 세션이름 + 20자 이내 작업요약). 이어서 60초 방치 감시(`Watch-Idle.ps1`)를 백그라운드로 예약.
  * `SessionEnd` 훅 → 세션 종료 시 방치 알림 예약 취소(세션을 닫았으면 Discord 미발송).
* **60초 방치 판정**: `Stop` 시점 토큰이 60초 뒤에도 유효(=이후 새 입력·새 응답·세션종료 없음)하면 Discord 웹훅으로 `세션이름 + 작업요약` 전송.
* **상태 파일**: `%TEMP%\claude\notify\<session_id>\` (turn_start, pending_notify, toast_*.json).
* **Windows PowerShell 5.1 한글 인코딩 주의(중요)**:
  * 모든 훅 `.ps1`은 **UTF-8 BOM**으로 저장한다(BOM 없으면 CP949로 오독되어 한글 리터럴 깨짐).
  * 프로세스 간 한글 전달은 명령줄 인자 금지 → **UTF-8 JSON 파일**로 넘긴다(`Show-Toast.ps1 -ParamFile`).
  * `Invoke-RestMethod` 웹훅 본문은 `charset=utf-8`을 줘도 UTF-8로 안 나감 → `[Text.Encoding]::UTF8.GetBytes()` **바이트 배열**로 전송한다.
* **토스트 표시 방식**: BurntToast 모듈 있으면 소리 토스트, 없으면 **폴백**(비프음 + NotifyIcon 풍선). 자동 설치는 하지 않음. 깔끔한 토스트를 원하면 `Install-Module BurntToast -Scope CurrentUser`.
* **Discord 웹훅 URL**: `Hook-Stop.ps1` 상단 `$WebhookUrl` 변수에 하드코딩(로컬 전용 설정).