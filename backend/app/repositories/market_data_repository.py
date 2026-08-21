"""
InvestorTradingDaily 데이터베이스 연산 전담 Repository 클래스 모듈.

종목별 일별 수급 및 시세 데이터를 조회/적재하고 가장 최근 수집 일자를 구하는
MarketDataRepository 클래스를 정의합니다.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import func
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

    def get_max_date(self, symbol: str) -> Optional[str]:
        """
        해당 종목의 DB에 적재된 가장 최근 일자(YYYYMMDD)를 조회합니다.

        :param symbol: 종목코드
        :return: 최근 일자 문자열 또는 None
        """
        return self.session.query(func.max(InvestorTradingDaily.date)).filter(
            InvestorTradingDaily.symbol == symbol
        ).scalar()

    def bulk_upsert(self, items: List[Dict[str, Any]]) -> int:
        """
        일별 수급/OHLCV 데이터를 대량 Upsert(등록/수정)합니다.

        :param items: 데이터 딕셔너리 리스트
        :return: 처리된 레코드 수
        """
        if not items:
            return 0

        saved_count = 0
        for item in items:
            sym = item.get("symbol")
            date_str = item.get("date")
            if not sym or not date_str:
                continue

            existing = self.get_by_symbol_and_date(sym, date_str)
            if existing:
                existing.open_price = item.get("open_price", existing.open_price)
                existing.high_price = item.get("high_price", existing.high_price)
                existing.low_price = item.get("low_price", existing.low_price)
                existing.close_price = item.get("close_price", existing.close_price)
                existing.volume = item.get("volume", existing.volume)
                existing.personal_net_buy = item.get("personal_net_buy", existing.personal_net_buy)
                existing.foreigner_net_buy = item.get("foreigner_net_buy", existing.foreigner_net_buy)
                existing.institution_net_buy = item.get("institution_net_buy", existing.institution_net_buy)
                existing.pension_net_buy = item.get("pension_net_buy", existing.pension_net_buy)
                existing.financial_net_buy = item.get("financial_net_buy", existing.financial_net_buy)
                existing.other_corp_net_buy = item.get("other_corp_net_buy", existing.other_corp_net_buy)
            else:
                new_record = InvestorTradingDaily(
                    symbol=sym,
                    date=date_str,
                    open_price=item.get("open_price"),
                    high_price=item.get("high_price"),
                    low_price=item.get("low_price"),
                    close_price=item.get("close_price"),
                    volume=item.get("volume"),
                    personal_net_buy=item.get("personal_net_buy"),
                    foreigner_net_buy=item.get("foreigner_net_buy"),
                    institution_net_buy=item.get("institution_net_buy"),
                    pension_net_buy=item.get("pension_net_buy"),
                    financial_net_buy=item.get("financial_net_buy"),
                    other_corp_net_buy=item.get("other_corp_net_buy")
                )
                self.session.add(new_record)
            saved_count += 1

        self.session.commit()
        return saved_count
