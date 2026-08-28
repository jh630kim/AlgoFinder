"""
일자별 주체별 수급 및 OHLCV 가격 데이터 ORM 모델 모듈.

종목별 일자별 개인, 외국인, 기관 등 수급 내역 및
시가/고가/저가/종가/거래량 데이터를 관리하는 InvestorTradingDaily 클래스를 정의합니다.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, BigInteger, Float, DateTime, Integer
from backend.app.core.database import Base


class InvestorTradingDaily(Base):
    """
    일자별 주체별 수급 및 OHLCV 가격 데이터 ORM 모델 클래스.
    """
    __tablename__ = "investor_trading_daily"

    # 종목코드 (Composite PK)
    symbol = Column(String(20), primary_key=True, comment="종목코드")
    # 일자 (YYYYMMDD 또는 YYYY-MM-DD) (Composite PK)
    date = Column(String(10), primary_key=True, index=True, comment="일자")

    # 주체별 순매수 금액 (원) - 수급 미제공 시 NULL 적재 지원
    personal_net_buy = Column(BigInteger, nullable=True, default=None, comment="개인 순매수(원)")
    foreigner_net_buy = Column(BigInteger, nullable=True, default=None, comment="외국인 순매수(원)")
    institution_net_buy = Column(BigInteger, nullable=True, default=None, comment="기관 순매수(원)")
    pension_net_buy = Column(BigInteger, nullable=True, default=None, comment="연기금 순매수(원)")
    financial_net_buy = Column(BigInteger, nullable=True, default=None, comment="금융투자 순매수(원)")
    other_corp_net_buy = Column(BigInteger, nullable=True, default=None, comment="기타법인 순매수(원)")

    # OHLCV 가격 및 거래량
    close_price = Column(Float, nullable=False, comment="종가(원)")
    open_price = Column(Float, nullable=False, comment="시가(원)")
    high_price = Column(Float, nullable=False, comment="고가(원)")
    low_price = Column(Float, nullable=False, comment="저가(원)")
    volume = Column(BigInteger, nullable=False, comment="거래량(주)")

    # 거래정지 여부 (1=거래정지일). 네이버가 종가 동결·거래량 0으로 표시하는 구간을
    # 지표/전략 연산에서 제외하기 위한 플래그. 판별식: volume=0 AND high_price=low_price
    is_suspended = Column(Integer, nullable=False, default=0, server_default="0", comment="거래정지 여부(1=정지)")

    # 수정 일시
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="수정일시")

    def __repr__(self) -> str:
        """InvestorTradingDaily 객체의 문자열 표현을 반환합니다."""
        return f"<InvestorTradingDaily(symbol='{self.symbol}', date='{self.date}', close={self.close_price})>"
