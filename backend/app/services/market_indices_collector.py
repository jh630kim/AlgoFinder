"""
주요 시장 지수 및 환율 데이터 수집 파이프라인 모듈.

FinanceDataReader를 활용하여 KOSPI, KOSDAQ, S&P500 지수 및 USD/KRW 환율 일자별 데이터를 수집하고
MarketIndicesDaily 테이블에 적재하는 MarketIndicesCollector 클래스를 정의합니다.
"""

from typing import List, Dict, Any
import logging
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy.orm import Session
from backend.app.repositories.market_indices_repository import MarketIndicesRepository

logger = logging.getLogger(__name__)


class MarketIndicesCollector:
    """
    주요 시장 지수 및 환율 일별 데이터 수집 전담 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        MarketIndicesCollector 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session
        self.indices_repo = MarketIndicesRepository(session)

    def fetch_indices_and_rate(
        self, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        지정 기간 동안의 KOSPI 개장일 기준으로 KOSPI, KOSDAQ, S&P500, USD/KRW 일별 데이터를 수집하여 병합합니다.

        :param start_date: 시작일자 (YYYYMMDD)
        :param end_date: 종료일자 (YYYYMMDD)
        :return: 일자별 지수/환율 딕셔너리 리스트
        """
        # FinanceDataReader 는 웹 서빙(requirements-web) 대상이 아니라 지연 import 한다.
        import FinanceDataReader as fdr

        try:
            kospi_df = fdr.DataReader("KS11", start_date, end_date)
            kosdaq_df = fdr.DataReader("KQ11", start_date, end_date)
            sp500_df = fdr.DataReader("US500", start_date, end_date)
            usdkrw_df = fdr.DataReader("USD/KRW", start_date, end_date)

            if kospi_df.empty:
                return []

            # KOSPI 종가가 존재하는 한국 증시 개장일(영업일)만 추출
            valid_kospi_df = kospi_df.dropna(subset=["Close"]) if "Close" in kospi_df.columns else kospi_df
            sorted_dates = sorted([d.strftime("%Y%m%d") for d in valid_kospi_df.index])
            records = []

            for d_str in sorted_dates:
                dt_key = pd.to_datetime(d_str)

                kospi_val = float(kospi_df.loc[dt_key, "Close"]) if dt_key in kospi_df.index and "Close" in kospi_df.columns and pd.notna(kospi_df.loc[dt_key, "Close"]) else None
                kosdaq_val = float(kosdaq_df.loc[dt_key, "Close"]) if dt_key in kosdaq_df.index and "Close" in kosdaq_df.columns and pd.notna(kosdaq_df.loc[dt_key, "Close"]) else None
                sp500_val = float(sp500_df.loc[dt_key, "Close"]) if dt_key in sp500_df.index and "Close" in sp500_df.columns and pd.notna(sp500_df.loc[dt_key, "Close"]) else None
                usdkrw_val = float(usdkrw_df.loc[dt_key, "Close"]) if dt_key in usdkrw_df.index and "Close" in usdkrw_df.columns and pd.notna(usdkrw_df.loc[dt_key, "Close"]) else None

                if kospi_val is not None:
                    records.append({
                        "date": d_str,
                        "kospi_close": kospi_val,
                        "kosdaq_close": kosdaq_val,
                        "sp500_close": sp500_val,
                        "usdkrw_rate": usdkrw_val
                    })

            return records
        except Exception as e:
            logger.error(f"지수/환율 수집 오류: {e}")
            return []

    def collect_market_indices(
        self, start_date: str = None, end_date: str = None, incremental: bool = True
    ) -> Dict[str, Any]:
        """
        지수 및 환율 수집 파이프라인을 스마트 증분(Incremental) 또는 전체(Full) 모드로 실행합니다.

        :param start_date: 시작일자 (YYYYMMDD, None시 기본값 1년전)
        :param end_date: 종료일자 (YYYYMMDD, None시 오늘)
        :param incremental: 증분 수집 여부 (True: 미수집 신규 일자만, False: 전체 덮어쓰기)
        :return: 수집 결과 요약 딕셔너리
        """
        today_str = datetime.now().strftime("%Y%m%d")
        actual_end = end_date if end_date else today_str
        target_start = start_date if start_date else (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        if incremental:
            max_date = self.indices_repo.get_max_date()
            if max_date:
                next_day_dt = datetime.strptime(max_date, "%Y%m%d") + timedelta(days=1)
                next_day_str = next_day_dt.strftime("%Y%m%d")
                if next_day_str > actual_end:
                    logger.info(f"  └─ ➔ 지수/환율 최신({max_date}) 데이터 적재 완료 상태 (건너뜀)")
                    return {
                        "start_date": target_start,
                        "end_date": actual_end,
                        "fetched_count": 0,
                        "saved_count": 0,
                        "skipped": True
                    }
                else:
                    target_start = next_day_str

        items = self.fetch_indices_and_rate(target_start, actual_end)
        saved_count = self.indices_repo.bulk_upsert(items)
        return {
            "start_date": target_start,
            "end_date": actual_end,
            "fetched_count": len(items),
            "saved_count": saved_count,
            "skipped": False
        }
