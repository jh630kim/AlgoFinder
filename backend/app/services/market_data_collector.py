"""
일별 수급 및 OHLCV 데이터 수집 파이프라인 모듈.

PyKRX 및 FinanceDataReader/Naver API를 활용하여 타깃 종목의
일별 수급 및 가격 데이터를 수집하고 SyncLogs를 자동 기록하는 MarketDataCollector 클래스를 정의합니다.
"""

from typing import List, Dict, Any, Optional
import time
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from pykrx import stock
from backend.app.repositories.market_data_repository import MarketDataRepository
from backend.app.repositories.target_stocks_repository import TargetStocksRepository
from backend.app.repositories.sync_log_repository import SyncLogRepository
from backend.app.repositories.stock_master_repository import StockMasterRepository

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
        self.master_repo = StockMasterRepository(session)

    def fetch_trading_data_with_retry(
        self, symbol: str, start_date: str, end_date: str, max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        단일 종목의 일별 수급 및 시세를 지연 재시도(Exponential Backoff)를 적용하여 수집합니다.

        :param symbol: 종목코드
        :param start_date: 시작일자 (YYYYMMDD)
        :param end_date: 종료일자 (YYYYMMDD)
        :param max_retries: 최대 재시도 횟수
        :return: 데이터 딕셔너리 리스트
        """
        for attempt in range(1, max_retries + 1):
            try:
                # PyKRX 주체별 거래실적 추이 수집
                df = stock.get_market_trading_value_by_date(start_date, end_date, symbol)
                if df.empty:
                    return []

                # OHLCV 데이터 수집
                ohlcv_df = stock.get_market_ohlcv_by_date(start_date, end_date, symbol)

                records = []
                for idx_dt, row in df.iterrows():
                    d_str = idx_dt.strftime("%Y%m%d")
                    ohlcv_row = ohlcv_df.loc[idx_dt] if idx_dt in ohlcv_df.index else {}

                    records.append({
                        "symbol": symbol,
                        "date": d_str,
                        "open_price": float(ohlcv_row.get("시가", 0.0)),
                        "high_price": float(ohlcv_row.get("고가", 0.0)),
                        "low_price": float(ohlcv_row.get("저가", 0.0)),
                        "close_price": float(ohlcv_row.get("종가", 0.0)),
                        "volume": int(ohlcv_row.get("거래량", 0)),
                        "personal_net_buy": float(row.get("개인", 0.0)),
                        "foreigner_net_buy": float(row.get("외국인합계", 0.0)),
                        "institution_net_buy": float(row.get("기관합계", 0.0)),
                        "pension_net_buy": float(row.get("연기금", 0.0)),
                        "financial_net_buy": float(row.get("금융투자", 0.0)),
                        "other_corp_net_buy": float(row.get("기타법인", 0.0))
                    })
                return records
            except Exception as e:
                logger.warning(f"[{symbol}] 수집 시도 {attempt}/{max_retries} 실패: {e}")
                if attempt == max_retries:
                    logger.error(f"[{symbol}] 수집 최종 실패")
                    return []
                time.sleep(1.0 * (2 ** (attempt - 1)))  # Exponential Backoff

        return []

    def collect_target_market_data(
        self, start_date: str = None, end_date: str = None, incremental: bool = True
    ) -> Dict[str, Any]:
        """
        모든 타깃 종목에 대해 수급/OHLCV 데이터를 스마트 증분(Incremental) 또는 전체(Full) 모드로 수집합니다.

        :param start_date: 시작일자 (YYYYMMDD, None시 기본값 1년전)
        :param end_date: 종료일자 (YYYYMMDD, None시 오늘)
        :param incremental: 증분 수집 여부 (True: 미수집 신규 일자만, False: 전체 덮어쓰기)
        :return: 수집 결과 요약 딕셔너리
        """
        today_str = datetime.now().strftime("%Y%m%d")
        actual_end = end_date if end_date else today_str
        default_start = start_date if start_date else (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        symbols = self.target_repo.get_all_symbols()
        total_symbols = len(symbols)
        total_records = 0
        skipped_count = 0

        mode_str = "스마트 증분(Incremental)" if incremental else "전체(Full)"
        logger.info(f"총 {total_symbols}개 타깃 종목 수집 시작 [{mode_str} 모드]...")

        for idx, sym in enumerate(symbols, 1):
            stock_obj = self.master_repo.get_by_code(sym)
            stock_name = stock_obj.name if stock_obj else sym
            pct = (idx / total_symbols) * 100 if total_symbols > 0 else 100

            target_start = default_start

            if incremental:
                max_date = self.market_repo.get_max_date(sym)
                if max_date:
                    next_day_dt = datetime.strptime(max_date, "%Y%m%d") + timedelta(days=1)
                    next_day_str = next_day_dt.strftime("%Y%m%d")
                    if next_day_str > actual_end:
                        logger.info(f"  ├─ [{idx:3d}/{total_symbols:3d}] ({pct:5.1f}%) {sym} {stock_name} ➔ 최신({max_date}) 데이터 적재됨 (건너뜀)")
                        skipped_count += 1
                        continue
                    else:
                        target_start = next_day_str

            items = self.fetch_trading_data_with_retry(sym, target_start, actual_end)
            saved = 0
            if items:
                saved = self.market_repo.bulk_upsert(items)
                total_records += saved

            logger.info(f"  ├─ [{idx:3d}/{total_symbols:3d}] ({pct:5.1f}%) {sym} {stock_name} 수집 완료 ({target_start}~{actual_end}, {saved}건 적재)")
            time.sleep(0.1)  # Rate limiting

        # SyncLogs 기록 생성
        log_entry = self.sync_log_repo.create_log({
            "sync_date": actual_end,
            "total_count": total_records,
            "kospi_count": total_symbols,
            "status": "SUCCESS",
        })

        logger.info(f"  └─ ✅ 수집 완료 (적재: {total_records}건, 건너뜀: {skipped_count}개 종목)")

        return {
            "target_symbols_count": total_symbols,
            "total_records_saved": total_records,
            "skipped_symbols_count": skipped_count,
            "log_id": log_entry.id,
        }
