"""
일자별 주체별 수급 및 OHLCV 데이터 Repository 모듈.

InvestorTradingDaily 테이블에 대한 CRUD 및 Bulk Upsert 연산을 전담하는
MarketDataRepository 클래스를 정의합니다.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.investor_trading_daily import InvestorTradingDaily


class MarketDataRepository:
    """
    InvestorTradingDaily 데이터베이스 연산 전담 Repository 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        MarketDataRepository 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session

    def get_by_symbol_and_date(self, symbol: str, date_str: str) -> Optional[InvestorTradingDaily]:
        """
        종목코드와 일자로 일별 수급/OHLCV 데이터를 조회합니다.

        :param symbol: 종목코드
        :param date_str: 일자 (YYYYMMDD)
        :return: InvestorTradingDaily 객체 또는 None
        """
        return self.session.query(InvestorTradingDaily).filter(
            InvestorTradingDaily.symbol == symbol,
            InvestorTradingDaily.date == date_str
        ).first()

    def bulk_upsert(self, items: List[Dict[str, Any]]) -> int:
        """
        일별 수급/OHLCV 데이터를 대량 Upsert(등록/수정)합니다.

        :param items: 데이터 딕셔너리 리스트
        :return: 처리된 레코드 수
        """
        if not items:
            return 0

        for item in items:
            symbol = item.get("symbol")
            date_str = item.get("date")
            existing = self.get_by_symbol_and_date(symbol, date_str)
            if existing:
                for key, val in item.items():
                    setattr(existing, key, val)
            else:
                new_obj = InvestorTradingDaily(**item)
                self.session.add(new_obj)

        self.session.commit()
        return len(items)
