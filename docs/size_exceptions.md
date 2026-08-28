# 규칙 3 예외 기록 — 200줄 초과 파일

CLAUDE.md 규칙 3(단일 파일 200줄 원칙)을 초과한 파일과 사유입니다. 사용자 검토 대상입니다.

## backend/app/repositories/web_repository.py (380줄)
- `WebRepository` 단일 클래스가 웹 대시보드 조회(종목 자동완성, 차트, TOP 수급 랭킹, 지수 summary,
  업종/종목 필터링 등)만 전담하는 단일 책임 안에서, 조회 메서드 개수 자체가 많아 줄 수가 늘어남.
- 메서드별로 별도 파일로 쪼개면 서로 연관된 대시보드 쿼리가 여러 파일에 흩어져 오히려 탐색성이 떨어짐.

## backend/app/api/routes_paper.py (<span style="color:red">549줄</span>)
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
- <span style="color:red">(2026-08-29) 디스코드 전달(`notify-recommendations`), 가상매매 JSON
  `export`/`import` 엔드포인트, paper 라우트 5개의 (메인/psession) 2세션 분리(`_paper_session`
  헬퍼). 약 457 → 549줄.</span>

## backend/app/services/proposal_advisor.py (254줄)
- 투자제안/모의투자 화면 데이터 조립(추천·매도신호·포트폴리오 평가)을 담당하는
  단일 클래스 `ProposalAdvisor`. 메서드 개수(로딩·지표캐시·추천·매도행·포트폴리오뷰)만큼 길어짐.
- (2026-08-28) 모의투자용 D-1 판단 모드(`mode`/`_signal_offset`/`_signal_date`/
  `_eff_close_map`) 추가로 약 186 → 211줄.
- (2026-08-29) 성능 A+C: 기준일마다 재로딩하던 것을 넓은 창(워밍업+FORWARD)
  1회 로드·1회 지표 계산 후 창 내 슬라이스로 처리하도록 `_load` 재구성 + `_covers`/`_resolve_dates`
  헬퍼 추가. 약 211 → 254줄. 캐시 키는 `(모드, 데이터버전)`으로 축소(`proposal_advisor_cache.py`).

## backend/app/services/backtest_engine.py (413줄)
- `BacktestEngine._simulate_trading` 메서드가 슬롯 관리·매수/매도 조건·보유 종목 갱신이 서로
  얽힌 단일 시뮬레이션 알고리즘이라 응집도가 높아 분리 시 로직 추적이 어려워짐.
- (2026-08-27) 성능 개선으로 `load_market_dataframe` 기간 제한(워밍업 버퍼) + 전략별 지표/딕셔너리
  캐싱 헬퍼(`_get_processed_df`, `_get_dict_map`) 및 체결 시점 자산 평가 헬퍼(`_portfolio_equity`)가
  추가되어 약 60줄 증가. `load_market_dataframe`은 기간 버퍼 계산·캐시 무효화 처리로 약 40줄(30줄 초과).
- (2026-08-29) `load_market_dataframe`에 `warmup_days` 선택 인자 추가(기본 200,
  기존 호출부 불변). ProposalAdvisor가 창 시작에 워밍업을 이미 반영하고 `warmup_days=0`으로 호출.

## backend/app/services/market_data_collector.py (342줄)
- PyKRX/FinanceDataReader/Naver 등 복수 외부 데이터 소스에 대한 재시도·폴백 로직을 포함한
  수집 파이프라인이라, 외부 연동 특유의 예외 처리 분기가 많아 줄 수가 늘어남.
- (2026-08-27) `collect_target_market_data`에 웹 진행바용 `progress_callback` 선택 인자 및
  종목 루프 내 호출부가 추가되어 약 5줄 증가.

---
위 5개 파일은 현재 구조 유지를 제안드립니다. 특정 파일을 실제로 분리하길 원하시면 말씀해 주세요.
