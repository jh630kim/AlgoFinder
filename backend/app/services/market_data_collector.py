"""
일별 수급 및 OHLCV 데이터 수집 파이프라인 모듈.

PyKRX 및 FinanceDataReader/Naver API를 활용하여 타깃 종목의
일별 수급 및 가격 데이터를 수집하고 SyncLogs를 자동 기록하는 MarketDataCollector 클래스를 정의합니다.
"""

from typing import List, Dict, Any
import time
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from pykrx import stock
from backend.app.repositories.market_data_repository import MarketDataRepository
from backend.app.repositories.target_stocks_repository import TargetStocksRepository
from backend.app.repositories.sync_log_repository import SyncLogRepository

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """
    일별 수급 및 OHLCV 수집 및 파이프라인 제어 전담 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        MarketDataCollector 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session
        self.market_repo = MarketDataRepository(session)
        self.target_repo = TargetStocksRepository(session)
        self.sync_log_repo = SyncLogRepository(session)

    def fetch_trading_data_with_retry(
        self, symbol: str, start_date: str, end_date: str, max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        PyKRX를 이용하여 단일 종목의 일별 수급/OHLCV 데이터를 지연 재시도로 수집합니다.

        :param symbol: 종목코드
        :param start_date: 시작일자 (YYYYMMDD)
        :param end_date: 종료일자 (YYYYMMDD)
        :param max_retries: 최대 재시도 횟수
        :return: 정제된 수급/OHLCV 데이터 딕셔너리 리스트
        """
        for attempt in range(1, max_retries + 1):
            try:
                # PyKRX 거래실적 및 가격 데이터 수집
                df_trading = stock.get_market_trading_value_by_date(start_date, end_date, symbol)
                df_price = stock.get_market_ohlcv_by_date(start_date, end_date, symbol)

                items: List[Dict[str, Any]] = []
                for idx, row in df_price.iterrows():
                    date_str = idx.strftime("%Y%m%d")
                    t_row = df_trading.loc[idx] if idx in df_trading.index else {}

                    items.append({
                        "symbol": symbol,
                        "date": date_str,
                        "open_price": float(row.get("시가", 0)),
                        "high_price": float(row.get("고가", 0)),
                        "low_price": float(row.get("저가", 0)),
                        "close_price": float(row.get("종가", 0)),
                        "volume": int(row.get("거래량", 0)),
                        "personal_net_buy": int(t_row.get("개인", 0)),
                        "foreigner_net_buy": int(t_row.get("외국인합계", t_row.get("외국인", 0))),
                        "institution_net_buy": int(t_row.get("기관합계", 0)),
                        "pension_net_buy": int(t_row.get("연기금", 0)),
                        "financial_net_buy": int(t_row.get("금융투자", 0)),
                        "other_corp_net_buy": int(t_row.get("기타법인", 0)),
                    })
                return items
            except Exception as exc:
                logger.warning("수집 재시도 (%d/%d) - 종목: %s, 에러: %s", attempt, max_retries, symbol, exc)
                time.sleep(1.0 * (2 ** (attempt - 1)))  # Exponential Backoff

        return []

    def collect_target_market_data(
        self, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        모든 타깃 종목에 대해 수급/OHLCV 데이터를 수집하고 SyncLogs에 기록합니다.

        :param start_date: 시작일자 (YYYYMMDD)
        :param end_date: 종료일자 (YYYYMMDD)
        :return: 수집 결과 요약 딕셔너리
        """
        symbols = self.target_repo.get_all_symbols()
        total_records = 0

        for sym in symbols:
            items = self.fetch_trading_data_with_retry(sym, start_date, end_date)
            if items:
                saved = self.market_repo.bulk_upsert(items)
                total_records += saved
            time.sleep(0.1)  # Rate limiting

        # SyncLogs 기록 생성
        log_entry = self.sync_log_repo.create_log({
            "sync_date": end_date,
            "total_count": total_records,
            "kospi_count": len(symbols),
            "status": "SUCCESS",
        })

        return {
            "target_symbols_count": len(symbols),
            "total_records_saved": total_records,
            "log_id": log_entry.id,
        }
