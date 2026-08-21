"""
전 증시 종목 마스터 수집 및 동기화 서비스 모듈.

FinanceDataReader를 활용하여 KOSPI, KOSDAQ, ETF 등 전체 종목 마스터를 수집하고
AllStockMaster 및 TargetStocks 테이블에 동기화하는 StockMasterCollector 클래스를 정의합니다.
"""

from typing import List, Dict, Any
import logging
from sqlalchemy.orm import Session
import FinanceDataReader as fdr
from backend.app.repositories.stock_master_repository import StockMasterRepository
from backend.app.repositories.target_stocks_repository import TargetStocksRepository

logger = logging.getLogger(__name__)


class StockMasterCollector:
    """
    종목 마스터 데이터 수집 및 타깃 필터링 전담 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        StockMasterCollector 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session
        self.master_repo = StockMasterRepository(session)
        self.target_repo = TargetStocksRepository(session)

    def fetch_master_dataframe(self, market_code: str) -> List[Dict[str, Any]]:
        """
        FinanceDataReader를 이용하여 지정 시장의 종목 목록을 수집합니다.

        :param market_code: 시장 코드 ('KRX', 'KOSPI', 'KOSDAQ', 'ETF' 등)
        :return: 정제된 종목 딕셔너리 리스트
        """
        try:
            df = fdr.StockListing(market_code)
            items: List[Dict[str, Any]] = []

            for _, row in df.iterrows():
                code = str(row.get("Code", row.get("Symbol", ""))).zfill(6)
                name = str(row.get("Name", ""))
                mkt = str(row.get("Market", market_code))
                dept = str(row.get("Dept", "")) if "Dept" in row else None
                sector = str(row.get("Sector", "")) if "Sector" in row else None
                marcap = int(row["Marcap"]) if "Marcap" in row and str(row["Marcap"]).isdigit() else None
                stocks = int(row["Stocks"]) if "Stocks" in row and str(row["Stocks"]).isdigit() else None

                items.append({
                    "code": code,
                    "name": name,
                    "market": mkt,
                    "dept": dept,
                    "sector": sector,
                    "marcap": marcap,
                    "stocks": stocks,
                })
            return items
        except Exception as exc:
            logger.error("종목 마스터 수집 중 오류 발생 (%s): %s", market_code, exc)
            return []

    def filter_target_symbols(self, items: List[Dict[str, Any]]) -> List[str]:
        """
        수집 항목 중 KOSPI 200, KOSDAQ 150, 미국 관련 ETF 타깃 종목을 추출합니다.

        :param items: 전체 종목 데이터 딕셔너리 리스트
        :return: 타깃 종목코드 리스트
        """
        target_symbols: List[str] = []
        for item in items:
            sector = str(item.get("sector") or "")
            name = str(item.get("name") or "")
            mkt = str(item.get("market") or "")

            # KOSPI 200, KOSDAQ 150, 또는 종목명에 '미국' 포함된 ETF
            if "KOSPI 200" in sector or "KOSDAQ 150" in sector or ("ETF" in mkt and "미국" in name):
                target_symbols.append(item["code"])

        return target_symbols

    def run_sync(self) -> Dict[str, Any]:
        """
        전 증시 종목 마스터 수집 및 타깃 종목 동기화 파이프라인을 실행합니다.

        :return: 동기화 결과 요약 딕셔너리
        """
        all_items = self.fetch_master_dataframe("KRX")
        saved_count = self.master_repo.bulk_upsert(all_items)
        
        target_symbols = self.filter_target_symbols(all_items)
        target_count = self.target_repo.sync_targets(target_symbols)

        return {
            "total_fetched": len(all_items),
            "master_saved": saved_count,
            "targets_saved": target_count,
        }
