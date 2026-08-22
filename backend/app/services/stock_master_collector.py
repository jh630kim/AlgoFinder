"""
전 증시 종목 마스터 수집 및 동기화 서비스 모듈.

FinanceDataReader 및 pykrx를 활용하여 KOSPI 200, KOSDAQ 150, 미국 ETF 등
전 증시 종목 마스터(4,000개+)를 수집하고 AllStockMaster 및 TargetStocks 테이블에 동기화합니다.
"""

from typing import List, Dict, Any, Set
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
import FinanceDataReader as fdr
from pykrx import stock
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

    def fetch_master_dataframe(self, market_code: str = "KRX") -> List[Dict[str, Any]]:
        """
        FinanceDataReader를 이용해 일반 주식(KRX-DESC 2,870개+)과 ETF(ETF/KR 1,160개+) 목록을 모두 수집합니다.

        :param market_code: 시장 코드 ('KRX' 등)
        :return: 정제된 종목 딕셔너리 리스트 (총 4,000개 이상)
        """
        items: List[Dict[str, Any]] = []
        code_set: Set[str] = set()

        # 1. 일반 주식 수집 (KRX-DESC)
        try:
            df_krx = fdr.StockListing("KRX-DESC")
            for _, row in df_krx.iterrows():
                code = str(row.get("Code", row.get("Symbol", ""))).zfill(6)
                if not code or code in code_set:
                    continue

                name = str(row.get("Name", ""))
                mkt = str(row.get("Market", market_code))
                industry = str(row.get("Industry", row.get("Sector", ""))) if "Industry" in row or "Sector" in row else None

                raw_marcap = row.get("Marcap", 0)
                marcap = int(raw_marcap) if raw_marcap is not None and str(raw_marcap).isdigit() else 0

                raw_stocks = row.get("Stocks", 0)
                stocks = int(raw_stocks) if raw_stocks is not None and str(raw_stocks).isdigit() else 0

                items.append({
                    "code": code,
                    "name": name,
                    "market": mkt,
                    "industry": industry,
                    "sector": "일반",
                    "marcap": marcap,
                    "stocks": stocks,
                })
                code_set.add(code)
        except Exception as exc:
            logger.error("일반 주식 마스터 수집 중 오류 발생: %s", exc)

        # 2. ETF 상장 목록 수집 (ETF/KR)
        try:
            df_etf = fdr.StockListing("ETF/KR")
            for _, row in df_etf.iterrows():
                code = str(row.get("Symbol", row.get("Code", ""))).zfill(6)
                if not code or code in code_set:
                    continue

                name = str(row.get("Name", ""))
                category = str(row.get("Category", "ETF"))

                raw_marcap = row.get("MarCap", row.get("Marcap", 0))
                marcap = int(raw_marcap) if raw_marcap is not None and str(raw_marcap).isdigit() else 0

                items.append({
                    "code": code,
                    "name": name,
                    "market": "ETF",
                    "industry": category,
                    "sector": "일반",
                    "marcap": marcap,
                    "stocks": 0,
                })
                code_set.add(code)
        except Exception as exc:
            logger.error("ETF 마스터 수집 중 오류 발생: %s", exc)

        return items

    def _fetch_index_constituents(self, ticker: str) -> List[str]:
        """
        pykrx를 활용해 지정된 지수 티커의 구성 종목 목록을 수집합니다.
        주말/휴일/장개장 전 데이터를 고려하여 최근 7일간의 날짜를 역순으로 소급 조회합니다.

        :param ticker: 지수 티커 (예: '1028' - KOSPI 200, '2203' - KOSDAQ 150)
        :return: 6자리 종목코드 문자열 리스트
        """
        now = datetime.now()
        for i in range(7):
            target_date = (now - timedelta(days=i)).strftime("%Y%m%d")
            try:
                codes = stock.get_index_portfolio_deposit_file(ticker, target_date)
                if codes is not None and len(codes) > 0:
                    return [str(c).zfill(6) for c in codes]
            except Exception:
                continue

        logger.error("지수 티커 %s (pykrx) 최근 7일 소급 수집 실패", ticker)
        return []

    def filter_target_symbols(self, items: List[Dict[str, Any]]) -> List[str]:
        """
        pykrx 지수 편입 종목(KOSPI 200, KOSDAQ 150)과 미국 ETF를 타깃 종목으로 추출합니다.

        :param items: 전체 종목 데이터 딕셔너리 리스트
        :return: 타깃 종목코드 리스트 (약 350개 이상)
        """
        target_codes: Set[str] = set()
        item_dict = {i["code"]: i for i in items}

        # 1. KOSPI 200 수집 (pykrx 지수 티커: '1028')
        kospi200_codes = set(self._fetch_index_constituents("1028"))
        if kospi200_codes:
            for code in kospi200_codes:
                if code in item_dict:
                    item_dict[code]["sector"] = "KOSPI 200"
                target_codes.add(code)
        else:
            logger.warning("pykrx KOSPI 200 수집 실패로 FDR 시총 상위 200개 폴백 적용")
            kospi_items = [i for i in items if i.get("market") == "KOSPI"]
            kospi_sorted = sorted(kospi_items, key=lambda x: x.get("marcap") or 0, reverse=True)
            for item in kospi_sorted[:200]:
                item["sector"] = "KOSPI 200"
                target_codes.add(item["code"])

        # 2. KOSDAQ 150 수집 (pykrx 지수 티커: '2203')
        kosdaq150_codes = set(self._fetch_index_constituents("2203"))
        if kosdaq150_codes:
            for code in kosdaq150_codes:
                if code in item_dict:
                    item_dict[code]["sector"] = "KOSDAQ 150"
                target_codes.add(code)
        else:
            logger.warning("pykrx KOSDAQ 150 수집 실패로 FDR 시총 상위 150개 폴백 적용")
            kosdaq_items = [i for i in items if i.get("market") == "KOSDAQ"]
            kosdaq_sorted = sorted(kosdaq_items, key=lambda x: x.get("marcap") or 0, reverse=True)
            for item in kosdaq_sorted[:150]:
                item["sector"] = "KOSDAQ 150"
                target_codes.add(item["code"])

        # 3. 미국 ETF (종목명에 '미국' 포함된 ETF)
        for item in items:
            name = str(item.get("name") or "")
            mkt = str(item.get("market") or "")

            if mkt == "ETF" and "미국" in name:
                item["sector"] = "ETF_USA"
                target_codes.add(item["code"])

        return sorted(list(target_codes))

    def run_sync(self) -> Dict[str, Any]:
        """
        전 증시 종목 마스터 수집 및 타깃 종목 동기화 파이프라인을 실행합니다.

        :return: 동기화 결과 요약 딕셔너리
        """
        all_items = self.fetch_master_dataframe("KRX")
        target_symbols = self.filter_target_symbols(all_items)

        # sector(지수구분)가 갱신된 all_items를 DB에 적재
        saved_count = self.master_repo.bulk_upsert(all_items)
        target_count = self.target_repo.sync_targets(target_symbols)

        return {
            "total_fetched": len(all_items),
            "master_saved": saved_count,
            "targets_saved": target_count,
        }

