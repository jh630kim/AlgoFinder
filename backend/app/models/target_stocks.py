"""
수집 대상 타깃 종목 ORM 모델 모듈.

KOSPI 200, KOSDAQ 150, 미국 ETF 등 수집 타깃 종목 목록을
저장 및 관리하는 TargetStocks 클래스를 정의합니다.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from backend.app.core.database import Base


class TargetStocks(Base):
    """
    수집 대상 타깃 종목 ORM 모델 클래스.
    """
    __tablename__ = "target_stocks"

    # 타깃 종목 코드 - Primary Key
    symbol = Column(String(20), primary_key=True, comment="타깃 종목코드")
    # 등록 일시
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="등록일시")

    def __repr__(self) -> str:
        """TargetStocks 객체의 문자열 표현을 반환합니다."""
        return f"<TargetStocks(symbol='{self.symbol}')>"
