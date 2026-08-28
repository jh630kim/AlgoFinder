"""
MarketIndicesDaily 데이터베이스 연산 전담 Repository 클래스 모듈.

코스피, 코스닥, S&P500 지수 및 원/달러 환율 데이터를 조회하고 대량 Upsert(등록/수정)하는
MarketIndicesRepository 클래스를 정의합니다.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.app.models.market_indices_daily import MarketIndicesDaily


class MarketIndicesRepository:
    """
    MarketIndicesDaily 데이터베이스 연산 전담 Repository 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        MarketIndicesRepository 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session

    def get_by_date(self, date_str: str) -> Optional[MarketIndicesDaily]:
        """
        일자(YYYYMMDD)로 주요 지수 및 환율 데이터를 조회합니다.

        :param date_str: 일자 (YYYYMMDD)
        :return: MarketIndicesDaily 객체 또는 None
        """
        return self.session.query(MarketIndicesDaily).filter(
            MarketIndicesDaily.date == date_str
        ).first()

    def get_max_date(self) -> Optional[str]:
        """
        DB에 적재된 가장 최근 지수/환율 일자(YYYYMMDD)를 조회합니다.

        :return: 최근 일자 문자열 또는 None
        """
        return self.session.query(func.max(MarketIndicesDaily.date)).scalar()

    def get_kospi_series(self, end_date: str, limit: int) -> List[Dict[str, Any]]:
        """
        기준일(YYYYMMDD) 이하 코스피 종가 시계열을 최신순 limit개 조회해
        과거→현재(오름차순)로 정렬하여 반환합니다. 종가가 없는(None) 행은 제외합니다.

        :param end_date: 조회 종료 일자 (YYYYMMDD, 이 일자 포함)
        :param limit: 최신순으로 가져올 최대 거래일 수
        :return: [{"date": "YYYYMMDD", "kospi_close": float}, ...] (오름차순)
        """
        rows = (
            self.session.query(MarketIndicesDaily.date, MarketIndicesDaily.kospi_close)
            .filter(
                MarketIndicesDaily.date <= end_date,
                MarketIndicesDaily.kospi_close.isnot(None),
            )
            .order_by(MarketIndicesDaily.date.desc())
            .limit(limit)
            .all()
        )
        return [{"date": d, "kospi_close": float(c)} for d, c in reversed(rows)]

    def bulk_upsert(self, items: List[Dict[str, Any]]) -> int:
        """
        주요 지수 및 환율 데이터를 대량 Upsert(등록/수정)합니다.

        :param items: 데이터 딕셔너리 리스트
        :return: 처리된 레코드 수
        """
        if not items:
            return 0

        saved_count = 0
        for item in items:
            date_str = item.get("date")
            if not date_str:
                continue

            existing = self.get_by_date(date_str)
            if existing:
                existing.kospi_close = item.get("kospi_close", existing.kospi_close)
                existing.kosdaq_close = item.get("kosdaq_close", existing.kosdaq_close)
                existing.sp500_close = item.get("sp500_close", existing.sp500_close)
                existing.usdkrw_rate = item.get("usdkrw_rate", existing.usdkrw_rate)
            else:
                new_record = MarketIndicesDaily(
                    date=date_str,
                    kospi_close=item.get("kospi_close"),
                    kosdaq_close=item.get("kosdaq_close"),
                    sp500_close=item.get("sp500_close"),
                    usdkrw_rate=item.get("usdkrw_rate")
                )
                self.session.add(new_record)
            saved_count += 1

        self.session.commit()
        return saved_count
