# 규칙 3 예외 기록 — 200줄 초과 파일

CLAUDE.md 규칙 3(단일 파일 200줄 원칙)을 초과한 파일과 사유입니다. 사용자 검토 대상입니다.

## app.py (244줄)
- Flask 앱 팩토리 단일 진입점 — 앱 생성·블루프린트 등록·5개 페이지 라우트·프로필/읽기전용
  게이트·SSR 주입 헬퍼가 한 파일에 모임. 라우트 함수 자체는 짧고 연산은 전부 서비스로 위임됨.
- (2026-09-05) 기동 시 투자제안 추천 캐시 백그라운드 예열(`_warm_proposal_cache`) +
  web 프로필에서 매 요청을 계기로 `roll-lite-db` 워크플로를 조건부 원격 발동
  (`WorkflowDispatcher` 호출, GitHub schedule 지연 우회). 약 198 → 244줄.

## backend/app/repositories/web_repository.py (393줄)
- `WebRepository` 단일 클래스가 웹 대시보드 조회(종목 자동완성, 차트, TOP 수급 랭킹, 지수 summary,
  업종/종목 필터링 등)만 전담하는 단일 책임 안에서, 조회 메서드 개수 자체가 많아 줄 수가 늘어남.
- 메서드별로 별도 파일로 쪼개면 서로 연관된 대시보드 쿼리가 여러 파일에 흩어져 오히려 탐색성이 떨어짐.
- (2026-08-29) `get_stock_chart_data`에 `end_date`(기준일) 선택 인자 추가 —
  보조 차트를 화면 기준일까지만 그리기 위한 끝 날짜 제한. 미지정 시 기존과 동일. 약 380 → 393줄.

## backend/app/api/routes_paper.py (<span style="color:red">628줄</span>)
- 모의투자/투자제안 계좌유형(`account_type`)별 자산 관리 API(backtest, portfolio, reset,
  manual-buy, sell, stock-info, recommended-stocks 등)가 하나의 Blueprint(`paper_api_bp`)에
  묶여 있어 엔드포인트 수만큼 길어짐.
- 각 라우트 함수 자체는 요청/응답 바인딩 위주로 짧으며, 복잡한 로직은 이미 레포지토리/서비스로 위임됨.
- (2026-08-27) `backtest_run`에 결과 3개 테이블 `clear_all()` 초기화·단일 전략 8종 제한·렌더 payload
  파일 캐시 기록 로직 추가. 리더보드 조립 로직은 `BacktestLeaderboardBuilder` 서비스로 이관.
- (2026-08-27) 투자제안 창 배선: recommended-stocks 실연산 교체, portfolio 기준일 평가·매도신호,
  manual-buy 슬롯/중복 가드 + 포지션 생성, sell/stock-info 엔드포인트 신설(신호·평가 연산은
  `ProposalAdvisor` 서비스로 위임). 약 261 → 359줄.
- (2026-08-28) 모의투자 창 배선: `next-trading-date` 엔드포인트 신설,
  recommended-stocks·portfolio에 `mode`(advice/sim) 파라미터, manual-buy·sell에 `rec` 계좌용
  기준일 종가 기본값·자동 수량 산정, `_dash`/`_close_on_or_before` 헬퍼 추가. 약 359 → 457줄.
- (2026-08-29) 디스코드 전달(`notify-recommendations`), 가상매매 JSON
  `export`/`import` 엔드포인트, paper 라우트 5개의 (메인/psession) 2세션 분리(`_paper_session`
  헬퍼). 약 457 → 549줄.
- (2026-08-29) `sync-turso` 엔드포인트(로컬↔Turso HTTP 동기화, push/pull).
  약 549 → 593줄. 실제 HTTP·SQL 로직은 `services/turso_http_client.py`(신규, 171줄)로 위임.
- (2026-08-30 Phase 1·2) `backtest_run` 재연산 대상을 combo_id 리스트로 축소(S1b/S1c 폐기) +
  순수관행 엔트리(combo_id=22) 실행 호출, `max_slots` 5, `manual-buy`에 `entry_strategy` 태그 저장.
  약 593 → 612줄.
- (2026-08-30) 순수관행 엔트리 `except` 블록을 `logger.exception` + 진행 메시지 표기로
  변경(엔트리 실패가 조용히 묻히던 것을 표면화). 약 612 → 617줄.
- (2026-08-30) `backtest_run` 부분 실패 보고 — combo 루프·순수관행 엔트리의 `except` 를
  모두 `logger.exception` + `failed_entries` 수집으로 통일하고, 종료 시 실패가 있으면
  진행 메시지·응답 JSON(`failed`)에 실패 항목을 남긴다. 약 617 → 628줄.

## backend/app/services/proposal_advisor.py (285줄)
- 투자제안/모의투자 화면 데이터 조립(추천·매도신호·포트폴리오 평가)을 담당하는
  단일 클래스 `ProposalAdvisor`. 메서드 개수(로딩·지표캐시·추천·매도행·포트폴리오뷰)만큼 길어짐.
- (2026-08-28) 모의투자용 D-1 판단 모드(`mode`/`_signal_offset`/`_signal_date`/
  `_eff_close_map`) 추가로 약 186 → 211줄.
- (2026-08-29) 성능 A+C: 기준일마다 재로딩하던 것을 넓은 창(워밍업+FORWARD)
  1회 로드·1회 지표 계산 후 창 내 슬라이스로 처리하도록 `_load` 재구성 + `_covers`/`_resolve_dates`
  헬퍼 추가. 약 211 → 254줄. 캐시 키는 `(모드, 데이터버전)`으로 축소(`proposal_advisor_cache.py`).
- (2026-08-30 Phase 2) `_composite_map` 헬퍼(합성 점수 창 캐시) 추가, `get_recommendations`가
  합성 점수순 정렬·전략별 top_n 제한·`composite_pct/rank` 노출, `build_portfolio_view` 매도 시그널에
  `entry_strategy`+합성 점수 병기. 약 254 → 285줄.

## backend/app/services/backtest_engine.py (462줄)
- `BacktestEngine._simulate_trading` 메서드가 슬롯 관리·매수/매도 조건·보유 종목 갱신이 서로
  얽힌 단일 시뮬레이션 알고리즘이라 응집도가 높아 분리 시 로직 추적이 어려워짐.
- (2026-08-27) 성능 개선으로 `load_market_dataframe` 기간 제한(워밍업 버퍼) + 전략별 지표/딕셔너리
  캐싱 헬퍼(`_get_processed_df`, `_get_dict_map`) 및 체결 시점 자산 평가 헬퍼(`_portfolio_equity`)가
  추가되어 약 60줄 증가. `load_market_dataframe`은 기간 버퍼 계산·캐시 무효화 처리로 약 40줄(30줄 초과).
- (2026-08-29) `load_market_dataframe`에 `warmup_days` 선택 인자 추가(기본 200,
  기존 호출부 불변). ProposalAdvisor가 창 시작에 워밍업을 이미 반영하고 `warmup_days=0`으로 호출.
- (2026-08-30 Phase 1·2) `_simulate_trading` 청산 판정에 -5%/+10% 추가, 매수 후보 정렬을
  합성 점수로(`_get_composite_map` 헬퍼 추가), STOP/TARGET 상수 정의, S1b/S1c 제거. 약 417 → 462줄.

## backend/app/services/purerule_engine.py (218줄)
- 순수관행 백테스트 엔트리(combo_id=22) 전담 클래스 `PureRuleEngine`. 합성 점수 로드 →
  주간(ISO week) 리밸런싱 · 균등비중 top-5 · ATR 하드스톱 · 랭킹 이탈 · 최대 보유일 청산 →
  strategy_trade_logs 스키마로 매매일지 조립까지, 하나의 시뮬레이션 알고리즘이 응집되어 있어
  분리 시 추적이 어려움. 정적 헬퍼 6개로 이미 분할. 후속 축소 대상.
- (2026-08-30) `_exit_reason`의 `composite_rank` NA 처리 버그 수정 —
  `pd.NA` 를 bool 로 평가해 `TypeError` 가 나던 것을 `_MISSING` 센티넬로 (키 없음 / NA / 정상 정수)
  3분기 처리. 매수 편입부의 `float(cpct or 50.0)` 도 `pd.notna` 가드로 교체. 약 206 → 218줄.

## backend/app/services/market_data_collector.py (<span style="color:red">403줄</span>)
- PyKRX/FinanceDataReader/Naver 등 복수 외부 데이터 소스에 대한 재시도·폴백 로직을 포함한
  수집 파이프라인이라, 외부 연동 특유의 예외 처리 분기가 많아 줄 수가 늘어남.
- (2026-08-27) `collect_target_market_data`에 웹 진행바용 `progress_callback` 선택 인자 및
  종목 루프 내 호출부가 추가되어 약 5줄 증가.
- (2026-08-30 Phase 0) `collect_target_market_data(ohlcv_only=)` 분기 —
  네이버/KRX 수급 스크래핑 없이 FDR OHLCV 폴백을 정식 경로로(CI용). 약 342 → 349줄.
- (2026-09-06) `_fetch_fdr_fallback` 이 `fdr.DataReader` 직접 호출 대신 `fdr_safe.read_fdr`
  (강제 타임아웃 wrapper, 신규 33줄)를 사용하도록 교체 — 무응답 호출 무한 대기 방지.
  약 349 → 364줄(그간 미기록 증가분 포함).
- <span style="color:red">(2026-09-06) `_write_progress` 정적 메서드 + 종목 루프 진행 카운터(attempted/with_data/
  failed_sample) 추가 — 타임아웃 강제종료 시에도 `data/roll_progress.json` 에 마지막 카운트가
  남아 커버리지 리포트가 "성공/시도"를 보고. 약 364 → 403줄.</span>

---
위 <span style="color:red">7개</span> 파일은 현재 구조 유지를 제안드립니다. 특정 파일을 실제로 분리하길 원하시면 말씀해 주세요.
