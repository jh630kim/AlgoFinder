"""
백테스트 매매일지 및 개별 체결 로그 ORM 모델 모듈.

백테스팅 시뮬레이션 중 발생하는 매수/매도 내역 및 상세 트레이드 로그를
저장하고 관리하는 StrategyTradeLogs 클래스를 정의합니다.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime
from backend.app.core.database import Base


class StrategyTradeLogs(Base):
    """
    백테스트 매매일지 및 개별 체결 로그 ORM 모델 클래스.
    """
    __tablename__ = "strategy_trade_logs"

    # 체결 로그 ID - Primary Key AutoIncrement
    id = Column(Integer, primary_key=True, autoincrement=True, comment="로그 ID")
    # 전략 조합 ID (1 ~ 31)
    combo_id = Column(Integer, nullable=False, index=True, comment="전략 조합 ID")
    # 체결 일자 (YYYYMMDD 또는 YYYY-MM-DD)
    trade_date = Column(String(10), nullable=False, index=True, comment="매매 일자")

    # 종목 정보
    symbol = Column(String(20), nullable=False, index=True, comment="종목코드")
    name = Column(String(100), nullable=True, comment="종목명")

    # 매매 구분 (BUY / SELL)
    trade_type = Column(String(10), nullable=False, comment="매매구분(BUY/SELL)")
    # 보유 일수
    holding_days = Column(Integer, default=0, comment="보유 일수")

    # 체결 수량 및 가격
    shares = Column(Integer, nullable=False, default=0, comment="체결 수량")
    unit_price = Column(Float, nullable=False, default=0.0, comment="체결 단가(원)")
    total_amount = Column(Float, nullable=False, default=0.0, comment="총 거래금액(원)")

    # 거래 후 성과 지표
    equity_after_trade = Column(Float, nullable=False, default=0.0, comment="거래후 평가자산")
    cum_return_pct = Column(Float, default=0.0, comment="누적 수익률(%)")
    profit_pct = Column(Float, default=0.0, comment="손익률(%)")
    profit_krw = Column(Float, default=0.0, comment="손익금액(원)")

    # AI 상승확률 및 전략 태그
    prob_up = Column(Float, default=0.0, comment="AI 상승확률(%)")
    strategy_tag = Column(String(20), nullable=True, comment="전략 태그(S1~S5)")

    # 등록 일시
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="등록일시")

    def __repr__(self) -> str:
        """StrategyTradeLogs 객체의 문자열 표현을 반환합니다."""
        return f"<StrategyTradeLogs(id={self.id}, combo_id={self.combo_id}, symbol='{self.symbol}', type='{self.trade_type}')>"
