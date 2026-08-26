"""
전략별 일별 누적자산(Equity Curve) 저장 ORM 모델 모듈.

각 전략(combo_id)이 각 거래일(trade_date)마다 보유한 총 평가자산(equity_amount)을
저장 및 관리하는 StrategyDailyEquity 클래스를 정의합니다.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime
from backend.app.core.database import Base


class StrategyDailyEquity(Base):
    """
    전략별 일별 누적자산 저장 ORM 모델 클래스.
    """
    __tablename__ = "strategy_daily_equity"

    # 기본 키 (Auto Increment)
    id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="고유 ID")
    
    # 전략 조합 ID (1 ~ 31) - 인덱스
    combo_id = Column(Integer, index=True, nullable=False, comment="전략 조합 ID")
    
    # 거래 일자 (YYYYMMDD 형식)
    trade_date = Column(String(8), index=True, nullable=False, comment="거래 일자(YYYYMMDD)")
    
    # 당일 총 평가자산 금액 (원)
    equity_amount = Column(Float, nullable=False, default=0.0, comment="당일 총 평가자산(원)")

    # 생성 일시
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="생성일시")

    def __repr__(self) -> str:
        """StrategyDailyEquity 객체의 문자열 표현을 반환합니다."""
        return f"<StrategyDailyEquity(combo_id={self.combo_id}, date='{self.trade_date}', equity={self.equity_amount})>"
