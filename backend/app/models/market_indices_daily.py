"""
주요 지수 및 환율 일별 데이터 ORM 모델 모듈.

코스피, 코스닥, S&P500 지수 및 원/달러 환율의 일별 데이터를
저장 및 관리하는 MarketIndicesDaily 클래스를 정의합니다.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime
from backend.app.core.database import Base


class MarketIndicesDaily(Base):
    """
    주요 지수 및 환율 일별 데이터 ORM 모델 클래스.
    """
    __tablename__ = "market_indices_daily"

    # 일자 (YYYYMMDD 또는 YYYY-MM-DD) - Primary Key
    date = Column(String(10), primary_key=True, comment="일자")

    # 코스피 지수 종가 (x100 소수점 처리 등)
    kospi_close = Column(Float, nullable=True, comment="코스피 종가")
    # 코스닥 지수 종가
    kosdaq_close = Column(Float, nullable=True, comment="코스닥 종가")
    # S&P500 지수 종가
    sp500_close = Column(Float, nullable=True, comment="S&P500 종가")
    # 원/달러 환율
    usdkrw_rate = Column(Float, nullable=True, comment="원/달러 환율")

    # 수정 일시
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="수정일시")

    def __repr__(self) -> str:
        """MarketIndicesDaily 객체의 문자열 표현을 반환합니다."""
        return f"<MarketIndicesDaily(date='{self.date}', kospi={self.kospi_close}, usdkrw={self.usdkrw_rate})>"
