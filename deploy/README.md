# 배포 (Koyeb + 경량 1년치 DB)

전체 설계는 [`../docs/web_deploy_plan.md`](../docs/web_deploy_plan.md) 참고. 이 문서는 실행 요약이다.

## 환경변수

| 변수 | 로컬(full) | Koyeb(web) | 설명 |
|---|---|---|---|
| `APP_PROFILE` | 미설정 또는 `full` | `web` | `web`이면 `/`,`/backtest`,`/recommendation`,`/proposal` → `/proposal-mobile` 302 |
| `READONLY` | `0`(기본) | `1` | `/api/sync*` 403 차단. 가상매매(paper) 쓰기는 영향 없음 |
| `DATABASE_URL` | 미설정(→`sqlite:///./data/app.db`) | `sqlite:///./data/app_lite.db` | 시세 DB 위치 |
| `PAPER_DATABASE_URL` | 선택(Turso 주소) | Turso 주소 | `prop` 가상매매 저장소. 미설정 시 `prop`도 `DATABASE_URL` 폴백 |
| `FLASK_DEBUG` | `True` | `False` | — |
| `DISCORD_WEBHOOK_URL` | 선택 | 선택 | 추천종목 전달 / 배치 알림 |
| `KRX_ID` / `KRX_PW` | 수집 시 필요 | 불필요 | 롤링 증분 수집(Actions)에서 사용 |

로컬은 `.env` 를 비워두면 지금과 100% 동일하게 동작한다.

## 스크립트

| 스크립트 | 역할 |
|---|---|
| `deploy/build_lite_db.py` | `data/app.db` → `data/app_lite.db` (최근 365일 + 타깃 종목 + paper 스키마만). 결과 ~20MB |
| `deploy/roll_lite_db.py` | 경량 DB에 증분 수집 후 365일 밖 삭제 + VACUUM. `--skip-collect` 로 프루닝만 |
| `Dockerfile` | `requirements-web.txt` 설치 → 빌드 인자 `LITE_DB_URL` 로 Release에서 경량 DB 취득 → `gunicorn app:app` |
| `.github/workflows/roll-lite-db.yml` | 평일 cron: Release 경량 DB 내려받기 → roll → Release 업로드 → Koyeb redeploy 훅 → Discord 알림 |
| `deploy/requirements-web.txt` | 서빙 전용 경량 의존성(fastapi/uvicorn/pykrx/FDR/psycopg2 제외) |

## 최초 배포 순서

1. 로컬: `python deploy/build_lite_db.py` → `data/app_lite.db` 생성.
2. GitHub: `lite-db` 태그로 Release 생성, `app_lite.db` 를 자산으로 업로드.
3. GitHub Secrets 등록: `KRX_ID`, `KRX_PW`, `KOYEB_DEPLOY_HOOK_URL`, `DISCORD_WEBHOOK_URL`,
   (Turso 사용 시) `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.
4. Koyeb: GitHub 저장소 연결(Dockerfile 빌더), 빌드 인자
   `LITE_DB_URL=https://github.com/<owner>/<repo>/releases/download/lite-db/app_lite.db`,
   환경변수(`APP_PROFILE=web`, `READONLY=1`, `FLASK_DEBUG=False`,
   `DATABASE_URL=sqlite:///./data/app_lite.db`, 필요 시 `PAPER_DATABASE_URL`).
5. Health check 경로: `/proposal-mobile`.
6. Actions `roll-lite-db` 를 `workflow_dispatch` 로 1회 수동 실행해 파이프라인 검증.

## 미결/주의

- PWA 아이콘 미포함: `static/manifest.webmanifest` 에 `icons` 없음. 필요 시 `static/`에
  `icon-192.png`/`icon-512.png` 추가 후 매니페스트에 `icons` 배열 기입.
- `roll-lite-db.yml` 은 현재 `--skip-collect`(프루닝만). CI에서 KRX 수집이 확인되면 플래그 제거.
- Turso(libSQL) 연결 시 `deploy/requirements-web.txt` 의 `sqlalchemy-libsql` 주석 해제 필요.
