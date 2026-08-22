"""
백테스트 전략 성과 리더보드 ORM 모델 모듈.

31개 퀀트 전략 백테스트 성과 지표(최종 자산, 누적 수익률, 승률, MDD 등)를
저장 및 관리하는 StrategyLeaderboard 클래스를 정의합니다.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime
from backend.app.core.database import Base


class StrategyLeaderboard(Base):
    """
    백테스트 전략 성과 리더보드 ORM 모델 클래스.
    """
    __tablename__ = "strategy_leaderboard"

    # 전략 조합 ID (1 ~ 31) - Primary Key
    combo_id = Column(Integer, primary_key=True, comment="전략 조합 ID")
    # 전략 조합 명칭 (예: S5, S1+S2 등)
    combo_name = Column(String(100), nullable=False, comment="전략 조합 명칭")

    # 최종 자산 금액 (원)
    final_capital = Column(Float, nullable=False, default=0.0, comment="최종 자산(원)")
    # 누적 수익률 (%)
    total_return_pct = Column(Float, nullable=False, default=0.0, comment="누적 수익률(%)")
    # 매매 승률 (%)
    win_rate_pct = Column(Float, nullable=False, default=0.0, comment="승률(%)")
    # 최대 낙폭 MDD (%)
    mdd_pct = Column(Float, nullable=False, default=0.0, comment="최대 낙폭(%)")
    # 총 거래 횟수
    total_trades = Column(Integer, nullable=False, default=0, comment="총 거래 횟수")

    # 수정 일시
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="수정일시")

    def __repr__(self) -> str:
        """StrategyLeaderboard 객체의 문자열 표현을 반환합니다."""
        return f"<StrategyLeaderboard(combo_id={self.combo_id}, name='{self.combo_name}', return={self.total_return_pct}%)>"
