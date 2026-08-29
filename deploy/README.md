# 배포 (<span style="color:red">Render</span> + 경량 1년치 DB)

전체 설계는 [`../docs/web_deploy_plan.md`](../docs/web_deploy_plan.md) 참고. 실행 체크리스트는
[`../docs/배포준비.md`](../docs/배포준비.md). 이 문서는 실행 요약이다.

<span style="color:red">> 2026-08-29: Koyeb가 Mistral AI에 인수되며 신규 무료 티어 중단 → 호스트를 **Render.com** 으로 교체.</span>

## 환경변수

| 변수 | 로컬(full) | <span style="color:red">Render(web)</span> | 설명 |
|---|---|---|---|
| `APP_PROFILE` | 미설정 또는 `full` | `web` | `web`이면 `/`,`/backtest`,`/recommendation`,`/proposal` → `/proposal-mobile` 302 |
| `READONLY` | `0`(기본) | `1` | `/api/sync*` 403 차단. 가상매매(paper) 쓰기는 영향 없음 |
| `DATABASE_URL` | 미설정(→`sqlite:///./data/app.db`) | `sqlite:///./data/app_lite.db` | 시세 DB 위치 |
| `PAPER_DATABASE_URL` | 선택(Turso 주소) | Turso 주소 | `prop` 가상매매 저장소. 미설정 시 `prop`도 `DATABASE_URL` 폴백 |
| `FLASK_DEBUG` | `True` | `False` | — |
| `DISCORD_WEBHOOK_URL` | 선택 | 선택 | 추천종목 전달 / 배치 알림 |
| `KRX_ID` / `KRX_PW` | 수집 시 필요 | 불필요 | 롤링 증분 수집(Actions)에서 사용 |
| <span style="color:red">`PORT`</span> | <span style="color:red">—</span> | <span style="color:red">입력 금지(Render 자동 주입)</span> | <span style="color:red">Dockerfile CMD가 `${PORT:-8000}` 처리</span> |

로컬은 `.env` 를 비워두면 지금과 100% 동일하게 동작한다.

## 스크립트

| 스크립트 | 역할 |
|---|---|
| `deploy/build_lite_db.py` | `data/app.db` → `data/app_lite.db` (최근 365일 + 타깃 종목 + paper 스키마만). 결과 ~20MB |
| `deploy/roll_lite_db.py` | 경량 DB에 증분 수집 후 365일 밖 삭제 + VACUUM. `--skip-collect` 로 프루닝만 |
| `Dockerfile` | `requirements-web.txt` 설치 → <span style="color:red">`LITE_DB_URL`(기본값=공개 Release URL)</span>로 Release에서 경량 DB 취득 → `gunicorn app:app` |
| `.github/workflows/roll-lite-db.yml` | 평일 cron: Release 경량 DB 내려받기 → roll → Release 업로드 → <span style="color:red">Render deploy 훅</span> → Discord 알림 |
| `deploy/requirements-web.txt` | 서빙 전용 경량 의존성(fastapi/uvicorn/pykrx/FDR/psycopg2 제외) |

## 최초 배포 순서

1. 로컬: `python deploy/build_lite_db.py` → `data/app_lite.db` 생성.
2. GitHub: `lite-db` 태그로 Release 생성, `app_lite.db` 를 자산으로 업로드.
3. GitHub Secrets 등록: `DISCORD_WEBHOOK_URL`, <span style="color:red">`RENDER_DEPLOY_HOOK_URL`</span>
   (수집 활성화 시 `KRX_ID`/`KRX_PW`).
4. <span style="color:red">Render: New → Web Service → GitHub 저장소 연결 → Language=**Docker**,
   Branch=`master`, Region=Singapore, Instance=**Free**. `Dockerfile` 의 `LITE_DB_URL` 기본값이
   공개 Release URL이라 빌드 인자 입력은 불필요.
   환경변수: `APP_PROFILE=web`, `READONLY=1`, `FLASK_DEBUG=False`,
   `DATABASE_URL=sqlite:///./data/app_lite.db`, `PAPER_DATABASE_URL=<Turso>` (`PORT` 는 넣지 않음).</span>
5. Health check 경로: `/proposal-mobile`.
6. <span style="color:red">Render 서비스 Settings → Deploy Hook URL 생성 → GitHub Secret `RENDER_DEPLOY_HOOK_URL` 등록.</span>
7. Actions `roll-lite-db` 를 `workflow_dispatch` 로 1회 수동 실행해 파이프라인 검증.

## 미결/주의

- PWA 아이콘 미포함: `static/manifest.webmanifest` 에 `icons` 없음. 필요 시 `static/`에
  `icon-192.png`/`icon-512.png` 추가 후 매니페스트에 `icons` 배열 기입.
- `roll-lite-db.yml` 은 현재 `--skip-collect`(프루닝만). CI에서 KRX 수집이 확인되면 플래그 제거.
- <span style="color:red">Turso 드라이버 `sqlalchemy-libsql` 는 `requirements-web.txt` 에서 활성화됨. `libsql-experimental`
  은 cp312 manylinux 휠만 존재 → Render 이미지(`python:3.12-slim`)에서만 컴파일 없이 설치. 로컬
  Windows/Python 3.14 에서는 설치 불가(로컬 `prop` 공유가 필요하면 Python 3.12 venv 사용).</span>
- <span style="color:red">Render 무료 인스턴스는 15분 유휴 시 슬립 → 첫 접속 콜드스타트(~50초). 상시 가동이 필요하면
  외부 uptime 핑 또는 유료 인스턴스.</span>
