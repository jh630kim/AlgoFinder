# 웹서버(Koyeb) 배포 계획 — 대화 정리본

> 목적: 지금까지 논의한 내용을 정리해 **이해가 맞는지 사용자가 검토**하기 위한 문서.
> 이 문서 작성이 첫 단계이며, 코드 작업은 사용자 승인 후 시작한다.

---

## 1. 한 줄 요약

하나의 `master` 브랜치·하나의 코드로, **로컬에서는 20년치 전체 데이터 + 모든 화면**,
**Koyeb 웹서버에서는 1년치 데이터 + 투자제안 모바일 화면만** 동작하게 한다.
차이는 브랜치/포크가 아니라 **환경변수(실행 프로필)**로 제어한다.
가상매매 기록(`paper_*`의 `prop`)만 **Turso(libSQL)**에 두어 PC·모바일이 공유하고,
양쪽 화면에서 **JSON 내보내기/불러오기**로 백업·복원할 수 있게 한다.

---

## 2. 확정된 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 호스팅 | **Koyeb 무료** (PythonAnywhere 대신) | git push 자동배포, 아웃바운드 화이트리스트 없음, HTTPS 자동 |
| 브랜치 전략 | 단일 `master`, 포크 없음 | 동작 차이는 환경변수로 |
| 실행 프로필 | `APP_PROFILE` = `full`(로컬) / `web`(Koyeb) | 화면·라우트 노출 범위 분기 |
| 로컬 동작 | 지금과 100% 동일 (전체 DB, 전체 화면, 동기화 버튼 활성) | `.env` 비우면 기존 그대로 |
| 웹 동작 | 투자제안 모바일 화면만, 읽기 전용(`READONLY=1`), `FLASK_DEBUG=False`, gunicorn 구동 | 경량·안전 |
| 시세 DB (로컬) | `data/app.db` 전체 (~221MB, 2005~), 독립 운용 | 개발·백테스트용 |
| 시세 DB (웹) | **1년 롤링 창**으로 다이어트, Docker 이미지에 구움 (~20~40MB 예상) | Koyeb 무료는 영속 디스크 없음 |
| 웹 DB 포함 대상 | `investor_trading_daily`(1년·타깃종목만), `market_indices_daily`(1년), `all_stock_master`(전체), `target_stocks` | 투자제안 연산에 필요한 최소 |
| 웹 DB 제외 대상 | `strategy_leaderboard` / `strategy_trade_logs` / `strategy_daily_equity`(백테스트 전용), `sync_logs`, `paper_*`의 `rec` 데이터 | 투자제안 화면이 안 읽음 |
| 왜 1년이면 되나 | 투자제안 연산은 지표 워밍업용 **최대 ~200일** 과거치만 사용 (`load_market_dataframe`가 시작일 앞 200일 버퍼) | 1년이면 200일선·볼린저 등 전부 커버 |
| 웹 DB 갱신 — 수집 | **증분**(새 거래일 1일치만), 보관본은 GitHub **Release 자산**으로 유지 | 매일 1년치 재수집은 과부하 |
| 웹 DB 갱신 — 배포 | **파일 통째 교체** (Dockerfile이 빌드 시 Release에서 받아 이미지에 굽고 Koyeb redeploy) | 컨테이너 영속 쓰기 불가 |
| 갱신 주기·주체 | **GitHub Actions cron 매일 1회** (PC 꺼져 있어도 됨) | 무인 자동화 |
| 파생 캐시 | 매일 재생성 (`kospi_regime`, `proposal_advisor_cache`) | 지수·가격 바뀌면 무효화됨 |
| 가상매매 저장소 | **Turso(libSQL)** 단일 원본, `PAPER_DATABASE_URL` 환경변수로 연결 | 재배포에도 유지, SQLite 방언 그대로라 이식 최소 |
| 연결 방식 | **방법 1** — PC 로컬 앱과 Koyeb 앱 모두 Turso에 직접 연결 (`prop`만) | 항상 일치, 병합 로직 불필요 |
| paper 연결 라우팅 | **`account_type`별 분기**: `rec`→로컬 `app.db`, `prop`→Turso(`PAPER_DATABASE_URL`, 없으면 로컬 폴백) | 같은 3테이블이지만 쿼리·트랜잭션이 계좌유형별로 완전 분리돼 안전 |
| 모의투자(`rec`) | 로컬 전용, 이번 작업 범위 아님 | 웹은 투자제안만 |
| 백업 | PC·모바일 양쪽에서 가상매매 **JSON 내보내기/불러오기** | 무료 티어 약관 변동 대비 |
| 불러오기 방식 | **전체 교체** — `prop` 3테이블 비우고 파일로 재구성. 직전 상태 자동 백업 다운로드 | 백업/복원/기기이동 목적에 부합, 규칙 단순 |
| 내보내기 범위 | **계좌 + 보유 + 체결 이력 전체** | 전체 교체와 일관, 크기 무시 가능(&lt;1MB) |
| 모바일 매매 | **허용** — 매수/매도는 Turso에 기록(영속). `READONLY`는 시세 DB 쓰기만 차단 | 폰에서 바로 매매 가능 |
| 시세 창 길이 | **365일** | 최장 지표는 sma60 + 엔진 200일 버퍼. 최신 거래일 기준 계산이라 365면 큰 마진 |
| 테스트 코드 | 이번 작업 **제외** | 규칙상 명시 요청 시에만 |
| Turso 선택 근거 | Neon/Supabase 대비 이식 비용 최소. 단 신생 → **자체 JSON 백업 필수** | — |

---

## 3. 실행 프로필별 환경변수

| 변수 | 로컬(`full`) | Koyeb(`web`) | 설명 |
|---|---|---|---|
| `APP_PROFILE` | `full` 또는 미설정 | `web` | 화면·라우트 노출 범위 |
| `DATABASE_URL` | 미설정(→`data/app.db`) | 이미지 내 경량 DB 경로 | 시세 DB 위치 |
| `READONLY` | `0` | `1` | 시세 DB 쓰기(동기화 버튼/`/api/sync`)만 차단. 가상매매는 영향 없음 |
| `PAPER_DATABASE_URL` | Turso 주소 (`prop`을 PC·모바일 공유하려면 필수) | Turso 주소 | `prop` 가상매매 저장소. 미설정 시 `prop`도 로컬 `app.db` 폴백 |
| `FLASK_DEBUG` | `True` | `False` | — |

---

## 4. 매일 갱신 흐름 (자동)

```
[GitHub Actions cron]  매일 1회
  1. Release에서 보관본(롤링 1년치 경량 DB) 내려받기
  2. 새 거래일 증분 수집 (--mode incremental)
  3. 1년 창 밖으로 밀려난 날짜 삭제 (롤링 유지)
  4. 파생 캐시 재생성 (kospi_regime, proposal_advisor_cache)
  5. 갱신된 경량 DB를 Release 자산으로 업로드
  6. Koyeb redeploy 훅 호출
  7. 결과/에러 Discord 알림
        │
        ▼
[Koyeb]  새 이미지 빌드
  - Dockerfile이 Release에서 최신 경량 DB 취득 → 이미지에 포함
  - gunicorn app:app 로 기동 (APP_PROFILE=web, READONLY=1)
```

가상매매(`paper_*`)는 이 흐름과 무관하게 **Turso에 상시 유지**된다.

---

## 5. 데이터 위치 최종 정리

| 데이터 | 로컬 | Koyeb | Turso |
|---|---|---|---|
| 시세(OHLCV·수급·지수·환율) | 전체 20년 `app.db` | 1년치 이미지 내 파일 | — |
| 종목 마스터/타깃 | `app.db` | 이미지 내 파일 | — |
| 백테스트 결과(`strategy_*`) | `app.db` | 제외 | — |
| 모의투자 `paper_*`(`rec`) | `app.db` | 제외 | — |
| 투자제안 가상매매 `paper_*`(`prop`) | Turso(방법1) | Turso | ✅ 원본 |

---

## 6. 결정 완료 (2026-08-28 확정)

| # | 항목 | 결정 |
|---|---|---|
| 1 | 불러오기 방식 | **전체 교체** (병합 미구현). 불러오기 직전 상태 자동 백업 다운로드 |
| 2 | 내보내기 범위 | **계좌 + 보유 + 체결 이력 전체** |
| 3 | 모바일 매매 | **허용** — 매수/매도는 Turso에 기록. `READONLY`는 시세 DB 쓰기만 차단 |
| 4 | paper 연결 | **`account_type`별 라우팅** — `rec`→로컬 `app.db`, `prop`→Turso(미설정 시 로컬 폴백) |
| 5 | 테스트 코드 | **이번 작업 제외** |
| 6 | 시세 창 길이 | **365일** (최장 지표 sma60 + 엔진 200일 버퍼를 큰 마진으로 커버) |

---

## 7. 웹서버 등록 과정 — 역할 분담

> 순서상 **"내가 할 일" 대부분(코드·스크립트·Dockerfile·Actions)이 먼저** 끝나야
> 사용자가 Koyeb 빌드를 돌릴 수 있다. 아래는 논리 순서가 아니라 역할 구분이다.

### 7-A. 사용자(내)가 할 일 — 자세히

#### (1) GitHub 준비
- [ ] `master`가 GitHub 원격에 push 되어 있는지 확인 (없으면 원격 저장소 생성 후 push)
- [ ] 저장소 Settings → Actions → 활성화 확인
- [ ] Settings → Actions → General → Workflow permissions를 **Read and write**로 (Release 자산 갱신용)

#### (2) Turso 계정·DB
- [ ] https://turso.tech 가입 (GitHub 로그인)
- [ ] 데이터베이스 1개 생성, 리전 선택(서울 가까운 곳)
- [ ] 접속 정보 발급: **Database URL**(`libsql://...`)과 **auth token** 복사해 안전한 곳에 보관
- [ ] (선택) CLI 설치해 `turso db shell`로 접속 테스트

#### (3) Koyeb 계정·앱
- [ ] https://koyeb.com 가입 (GitHub 로그인). 결제수단 등록 요구 여부 확인
- [ ] 기존에 배포돼 있던 다른 코드가 있으면 해당 App/Service **삭제**
- [ ] **Create App** → GitHub 저장소 연결 → `master` 선택
- [ ] Builder: **Dockerfile** 선택 (경로는 내가 알려줄 위치)
- [ ] Instance: **Free (eco/nano)**, 리전 선택
- [ ] 환경변수 입력:
  - `APP_PROFILE=web`
  - `READONLY=1`
  - `FLASK_DEBUG=False`
  - `DATABASE_URL=` (이미지 내 경량 DB 경로 — 내가 확정해서 전달)
  - `PAPER_DATABASE_URL=` (Turso Database URL + token 조합 형식 — 내가 형식 전달)
  - `PORT` 등 Koyeb이 요구하는 값
- [ ] Health check 경로 지정 (내가 알려줌)
- [ ] 첫 배포 실행 → **Build/Runtime 로그 확인**

#### (4) 배포 자동화용 시크릿·훅
- [ ] Koyeb App settings에서 **Deploy webhook URL** 생성 → 복사
- [ ] GitHub 저장소 Settings → Secrets and variables → Actions 에 등록:
  - `TURSO_DATABASE_URL`
  - `TURSO_AUTH_TOKEN`
  - `KOYEB_DEPLOY_HOOK_URL`
  - `DISCORD_WEBHOOK_URL` (알림용, 기존 값 재사용 가능)
  - (수집 소스가 계정 필요 시) 관련 자격정보

#### (5) 최초 데이터 적재
- [ ] 내가 만든 다이어트 스크립트를 **로컬에서 1회 실행**해 최초 경량 DB 생성
- [ ] 생성된 파일을 GitHub **Release 자산으로 업로드** (내가 태그/이름 규칙 전달)
- [ ] Actions 워크플로 수동 실행(`workflow_dispatch`)으로 전체 파이프라인 1회 검증

#### (6) 동작 확인
- [ ] `https://<앱이름>.koyeb.app/` 접속 → **투자제안 모바일 화면**이 뜨는지
- [ ] PC 페이지/백테스트 URL이 차단(404/리다이렉트)되는지
- [ ] 동기화 버튼이 안 보이는지, `/api/sync` 호출이 막히는지
- [ ] 휴대폰으로 접속 → **홈 화면에 추가(PWA)**
- [ ] 휴대폰에서 가상매매 1건 → 잠시 후 **PC 로컬 앱(투자제안)에서도 보이는지** (Turso 공유 확인)
- [ ] **JSON 내보내기** 눌러 파일 받기 → 내용 확인
- [ ] 받은 파일 일부 수정 후 **불러오기** → 확인 모달 → 반영 결과 확인

#### (7) 다음날 자동 갱신 확인
- [ ] Actions 탭에서 cron 실행 성공 여부
- [ ] Release 자산이 새로 갱신됐는지 (수정 시각)
- [ ] Koyeb이 자동 재배포됐는지
- [ ] 화면 상단 "최근 수집일"이 갱신됐는지
- [ ] Discord로 완료 알림이 왔는지

#### (8) 로컬 설정 정리
- [ ] 미확정 4번 결정에 따라 로컬 `.env`에 `PAPER_DATABASE_URL`을 넣을지 말지 설정
- [ ] 넣는 경우: 로컬 앱 재기동 후 투자제안 포트폴리오가 Turso를 보는지 확인

---

### 7-B. 내(Claude)가 할 일 — 제목 + 요약

| # | 제목 | 요약 |
|---|---|---|
| 1 | 실행 프로필 분기 | `APP_PROFILE`(full/web)에 따라 라우트 등록 범위와 랜딩 화면을 다르게. web이면 투자제안 모바일만 노출, PC·백테스트 라우트 비활성. |
| 2 | 읽기 전용 모드 | `READONLY=1`이면 수급 동기화 버튼 숨김, `/api/sync` 및 시세 쓰기 엔드포인트 차단. 가상매매(Turso 쓰기)는 제외. |
| 3 | paper_* 저장소 연결 분기 | `account_type`별 세션 라우팅 — `rec`→메인 엔진(로컬 `app.db`), `prop`→`PAPER_DATABASE_URL`(Turso, 없으면 메인 폴백). Turso 엔진에도 `paper_*` 스키마 보장, libSQL에서 `ALTER TABLE` 마이그레이션 무해하게 보정. |
| 4 | 가상매매 JSON 내보내기 | `prop` 계좌·보유·체결을 스키마 버전 포함 단일 JSON으로 반환하는 조회 + PC·모바일 화면 포트폴리오 카드에 "내보내기" 버튼(브라우저 다운로드). |
| 5 | 가상매매 JSON 불러오기 | 업로드 파일 검증 → 직전 상태 자동 백업 다운로드 → `prop` 데이터 전체 교체. "완전 대체" 확인 모달 + 결과 토스트. |
| 6 | DB 다이어트 스크립트 | 전체 DB에서 최근 **365일** + 타깃 종목 + `paper_*` 스키마(데이터 제외)만 남긴 경량 SQLite 생성. `strategy_*`/`sync_logs`/`rec`/`prop` 데이터 제외. |
| 7 | 롤링 증분 갱신 스크립트 | 보관된 경량 DB 로드 → 새 거래일 증분 수집 → 1년 창 밖 삭제 → 파생 캐시 재생성 → 산출. |
| 8 | Dockerfile + 실행 설정 | 경량 의존성 설치, 빌드 시 Release에서 경량 DB 취득, gunicorn으로 `app:app` 구동, 헬스체크 경로. |
| 9 | GitHub Actions 워크플로 | cron + 수동실행으로 7번 파이프라인 실행 → Release 자산 갱신 → Koyeb redeploy 훅 호출 → Discord 알림. |
| 10 | 경량 서빙 의존성 정리 | `fastapi`/`uvicorn`/`psycopg2` 제외한 서빙 전용 requirements 정리(기존 `deploy/requirements-pa.txt` 재활용). |
| 11 | 환경변수·배포 문서 | 필요한 환경변수 목록, 로컬 vs Koyeb 설정값 표, 최초 배포 순서, 기존 `deploy/`(PythonAnywhere용) 정리. |
| 12 | (선택) PWA 매니페스트 | 휴대폰 홈 화면 추가 시 브라우저 저장소 수명 연장(특히 iOS Safari 7일 정책 회피). |
| 13 | ~~테스트 코드~~ | 이번 작업 제외 확정. 추후 "테스트 코드 작성해" 지시 시 다이어트/증분/JSON 입출력 대상. |

---

## 8. 이해가 맞는지 확인 포인트

- [ ] 단일 브랜치 + 환경변수 프로필 방식이 맞다
- [ ] 웹은 "투자제안 모바일 화면 + 1년치 읽기 전용"이 맞다
- [ ] 웹 DB는 매 배포마다 통째 교체, 만드는 과정만 증분이 맞다
- [ ] 갱신 주체는 GitHub Actions(무인)가 맞다 — PC가 아니다
- [ ] 가상매매는 Turso 단일 원본, PC·모바일 직접 연결(방법 1)이 맞다
- [ ] 로컬 전체 앱 동작은 지금과 달라지지 않는다 (`.env` 안 건드리면)
- [ ] JSON 내보내기/불러오기는 PC·모바일 양쪽 투자제안 화면에 있다
- [ ] `rec`는 로컬 `app.db`, `prop`은 Turso로 `account_type`별 라우팅한다
- [ ] 모바일에서도 매수/매도가 되며, 그 기록은 Turso에 영속된다

이 문서 내용이 맞으면 승인 회신을 주시면 코딩 단계로 들어갑니다. (6장 결정 완료)

---

## 9. 구현 현황 (2026-08-29 야간 배치)

§7-B(내가 할 일) 중 **코드·스크립트·설정 1~12는 구현·로컬 검증 완료**. §7-A(사용자
계정 작업)는 미착수. 커밋: `ca942db`(1~5), `b5d373b`(6~7), `02ac501`(8~12). push 안 함.

| # | 항목 | 상태 |
|---|---|---|
| 1 | 실행 프로필 분기 | 완료 — `config.APP_PROFILE`, `app.py` `before_request` 게이트(web이면 PC 4페이지 → `/proposal-mobile` 302) |
| 2 | 읽기 전용 모드 | 완료 — `config.READONLY`, `/api/sync*` 403, `index.html` 동기화 버튼 조건부 숨김. 가상매매 쓰기는 허용 |
| 3 | paper_* 저장소 연결 분기 | 완료 — `db_manager.get_paper_session(account_type)`, `prop`+`PAPER_DATABASE_URL`이면 전용 엔진(없으면 메인 폴백). routes_paper 5개 라우트 2세션 분리. **libSQL 실연결은 Turso 계정 필요로 미검증**, 로컬 폴백만 검증 |
| 4 | 가상매매 JSON 내보내기 | 완료 — `GET /api/paper-trading/export`, PC/모바일 `⬇️ 내보내기` 버튼 |
| 5 | 가상매매 JSON 불러오기 | 완료 — `POST /api/paper-trading/import`(스키마 검증 → 직전상태 backup 반환 → 전체 교체), `⬆️ 불러오기` 버튼(백업 자동 다운로드). 왕복 검증 |
| 6 | DB 다이어트 스크립트 | 완료 — `deploy/build_lite_db.py`. 231MB → **20.4MB**. 이 경량 DB로 web 프로필 구동 시 추천 결과가 full DB와 동일 |
| 7 | 롤링 증분 갱신 스크립트 | 완료 — `deploy/roll_lite_db.py`. 프루닝/VACUUM 검증. 증분 수집은 KRX 라이브라 CI에서(`--skip-collect` 기본) |
| 8 | Dockerfile + 실행 설정 | 완료 — `Dockerfile`, `.dockerignore`. Docker 미설치로 이미지 빌드는 미실행 |
| 9 | GitHub Actions 워크플로 | 완료 — `.github/workflows/roll-lite-db.yml`. 시크릿 미설정 시 각 단계 skip |
| 10 | 경량 서빙 의존성 | 완료 — `deploy/requirements-web.txt` |
| 11 | 환경변수·배포 문서 | 완료 — `deploy/README.md` |
| 12 | PWA 매니페스트 | 완료 — `static/manifest.webmanifest` + 모바일 head 메타. 아이콘 PNG는 사용자 추가 필요 |

**사용자 조치 필요(§7-A)**: GitHub 원격 push·Actions 권한, Turso 가입·DB·토큰,
Koyeb 앱 생성·환경변수·빌드인자(`LITE_DB_URL`)·배포 훅, GitHub Secrets 등록,
최초 경량 DB를 `lite-db` Release 자산으로 업로드. 상세 체크리스트는 `deploy/README.md`.

---

## 10. <span style="color:red">[20260829] 호스트 변경: Koyeb → Render</span>

<span style="color:red">Koyeb가 2026-02 Mistral AI에 인수되며 **신규 가입자에게 무료 티어를 중단**(유료 플랜만
가능). 대시보드에 Web Service 생성 UI 자체가 노출되지 않음 → 호스트를 **Render.com** 으로 교체한다.
경량 DB·Turso·GitHub Actions 롤링 구조는 그대로다.</span>

| <span style="color:red">항목</span> | <span style="color:red">Koyeb(폐기)</span> | <span style="color:red">Render(신규)</span> |
|---|---|---|
| <span style="color:red">서비스</span> | <span style="color:red">Koyeb App</span> | <span style="color:red">Render Web Service (Free, Singapore)</span> |
| <span style="color:red">빌더</span> | <span style="color:red">Dockerfile + build-arg `LITE_DB_URL`</span> | <span style="color:red">Dockerfile. Render 무료는 build-arg UI 없음 → `Dockerfile` 의 `ARG LITE_DB_URL` 기본값을 공개 Release URL로 고정</span> |
| <span style="color:red">포트</span> | <span style="color:red">`PORT` 주입</span> | <span style="color:red">`PORT` 주입(≈10000). 환경변수로 직접 넣지 않음</span> |
| <span style="color:red">헬스체크</span> | <span style="color:red">`/proposal-mobile`</span> | <span style="color:red">`/proposal-mobile` (동일)</span> |
| <span style="color:red">재배포 훅</span> | <span style="color:red">Secret `KOYEB_DEPLOY_HOOK_URL`</span> | <span style="color:red">Secret `RENDER_DEPLOY_HOOK_URL`, `roll-lite-db.yml` 스텝명 `Trigger Render deploy`</span> |
| <span style="color:red">무료 제약</span> | <span style="color:red">(신규 불가)</span> | <span style="color:red">15분 유휴 시 슬립 → 첫 접속 콜드스타트(~50초), 750h/월</span> |

<span style="color:red">**코드 변경(커밋)**: `Dockerfile`(`LITE_DB_URL` 기본값), `.github/workflows/roll-lite-db.yml`
(Render 훅), `deploy/README.md`, `docs/배포준비.md`. 실행 체크리스트는 `docs/배포준비.md` 참조.</span>
