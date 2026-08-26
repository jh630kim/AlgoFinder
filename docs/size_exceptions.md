# 규칙 3 예외 기록 — 200줄 초과 파일

CLAUDE.md 규칙 3(단일 파일 200줄 원칙)을 초과한 파일과 사유입니다. 사용자 검토 대상입니다.

## backend/app/repositories/web_repository.py (380줄)
- `WebRepository` 단일 클래스가 웹 대시보드 조회(종목 자동완성, 차트, TOP 수급 랭킹, 지수 summary,
  업종/종목 필터링 등)만 전담하는 단일 책임 안에서, 조회 메서드 개수 자체가 많아 줄 수가 늘어남.
- 메서드별로 별도 파일로 쪼개면 서로 연관된 대시보드 쿼리가 여러 파일에 흩어져 오히려 탐색성이 떨어짐.

## backend/app/api/routes_paper.py (372줄)
- 모의투자/투자제안 계좌유형(`account_type`)별 자산 관리 API 8개(backtest, portfolio, reset,
  manual-buy 등)가 하나의 Blueprint(`paper_api_bp`)에 묶여 있어 엔드포인트 수만큼 길어짐.
- 각 라우트 함수 자체는 요청/응답 바인딩 위주로 짧으며, 복잡한 로직은 이미 레포지토리/서비스로 위임됨.

## backend/app/services/backtest_engine.py (340줄)
- `BacktestEngine._simulate_trading` 메서드(139~326줄, 약 190줄)가 슬롯 관리·매수/매도 조건·
  보유 종목 갱신이 서로 얽힌 단일 시뮬레이션 알고리즘이라 응집도가 높아 분리 시 로직 추적이 어려워짐.

## backend/app/services/market_data_collector.py (336줄)
- PyKRX/FinanceDataReader/Naver 등 복수 외부 데이터 소스에 대한 재시도·폴백 로직을 포함한
  수집 파이프라인이라, 외부 연동 특유의 예외 처리 분기가 많아 줄 수가 늘어남.

---
위 4개 파일은 현재 구조 유지를 제안드립니다. 특정 파일을 실제로 분리하길 원하시면 말씀해 주세요.
