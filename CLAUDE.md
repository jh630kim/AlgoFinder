# 프로젝트 AI 코딩 규칙 (Claude Code용)

일반 코딩 규칙은 `Coding_Rule.md`를 가장 우선 적용한다. 이 문서는 그 위에 얹는 본 프로젝트 전용 규칙을 정의한다.

세션 초기에 claude.md를 숙지하라고 하는 경우, 내용을 네가 이해하면 되지, 굳이 화면에 출력할 필요는 없다.

---

## 1. 진행 및 응답 규칙 (가장 중요)

* **명시적 지시 전 코딩 금지**: 사용자가 "명시적으로 진행하라"고 지시하기 전까지는 소스 코드를 작성·수정하지 않고, 먼저 계획을 세워 보고한다.
  * **계획의 목적**: 구체적인 구현 명세가 아니라, 사용자의 의도가 제대로 전달되었는지 Claude의 언어로 되짚어 확인받는 것이다.
  * **계획서에 담는 것 (아래 4가지뿐이며, 그 이상은 담지 않는다)**:
    1. 사용자의 의도를 Claude의 언어로 재정리한 내용
    2. 그 이해에 문제나 모호한 점은 없는지
    3. 개선할 점은 없는지
    4. UI 관련 작업이면 화면 표현 방식 (예: "진행바는 별도 카드가 아니라 화면을 덮는 오버레이 모달로 구성")
  * **계획서에 쓰지 않는 것**: 파일명·함수명·줄 단위 변경 명세, 구현 단계 분해. 구체적인 구현 방법은 승인 후 코딩 단계에서 Claude가 알아서 정하며 별도로 보고하지 않는다.
* **질의응답·원인 분석 요청 시 수정 금지**: "~할 수 없어?", "왜 그렇지?", "원인 파악해", "다시 확인해봐" 같은 요청에는 코드를 수정하지 않는다. 원인 분석 결과와 개선 계획을 세워 텍스트로 보고하고, 반영은 사용자가 검토 후 지시했을 때만 수행한다.

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

* **가상환경**: 프로젝트 루트의 `.venv`를 사용한다. 없으면 만든다.
* **테스트 동기화 시점**: 소스가 변경되더라도 사용자가 **"테스트 코드 작성해"**라고 명시적으로 요청할 때만 테스트 코드 및 Fixture를 작성·갱신한다.

### 3.1 파일 변경 색상 표기

* 적용 대상: 소스 코드(`.py`/`.js`/`.html`/`.css` 등)와 `CLAUDE.md`는 제외하고, 그 밖의 `.md` 문서를 수정할 때 모두 적용한다.
* 변경분 표기: 이번 수정에서 추가·변경한 텍스트만 `<span style="color:red">...</span>`로 감싸 빨간색으로 저장한다.
* 이전 표기 원복: 직전까지 빨간색이던 부분은 이번 수정 대상이 아니면 `<span>` 래핑을 제거해 원래 색(검은색)으로 되돌린다.
* 결과적으로 문서에는 항상 "가장 최근 1회 수정분"만 빨간색으로 남는다.
* 표(table) 셀 안에서도 셀 텍스트 단위로 동일하게 `<span>`을 적용한다.
* 신규 문서 최초 생성 시에는 색상 표기를 하지 않는다(전체가 신규이므로).

### 3.2 계획 문서

* `docs/`에 계획 문서를 `.md` 포맷으로 작성할 때는 파일 이름을 `세션이름.md`로 한다.

### 3.3 컨벤션·변경 기록

* 세션 내부에서 새로운 컨벤션을 지정하거나 프로젝트 변화를 기록할 때는 `[yyyymmdd]_제목` 형식 아래 개조식으로 이 문서에 추가한다.

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

### 5.3 요청 시 Discord 알림

* 사용자가 "디스코드로 알려줘" 등 알림을 **명시적으로 요청할 때만** 적용한다.
* **동작**: 작업이 끝나면 Claude가 Discord 웹훅으로 완료 메시지(세션이름 + 20자 이내 작업요약)를 직접 전송한다.
* **전송 방법**: `.claude/notify.local.json`의 `discord_webhook_url`을 읽어, `{"content": "<메시지>"}`를 **UTF-8 JSON**으로 그 URL에 POST 한다 (`Content-Type: application/json`, 예: `curl --data-binary @file`). 성공 시 HTTP 204.
* **웹훅 URL 보관** (git 커밋 금지):
  * URL은 이 문서에 직접 쓰지 않는다. `.claude/notify.local.json`의 `discord_webhook_url` 키에 저장한다.
  * 이 파일은 **반드시 `.gitignore`에 등록**한다 (`.claude/*.local.json` 패턴). 개인·비공개, 저장소에 올리지 않는다.
