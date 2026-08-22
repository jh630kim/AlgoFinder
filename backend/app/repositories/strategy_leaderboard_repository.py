"""
백테스트 전략 성과 리더보드 리포지토리 모듈.

StrategyLeaderboard ORM 모델과 연동하여 전략 성과 지표(최종자산, 누적수익률, 승률, MDD 등)의
생성, 수정 및 성과 순위 조회를 전담하는 StrategyLeaderboardRepository 클래스를 정의합니다.
"""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.strategy_leaderboard import StrategyLeaderboard

logger = logging.getLogger(__name__)


class StrategyLeaderboardRepository:
    """
    StrategyLeaderboard 데이터베이스 CRUD 전담 리포지토리 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        StrategyLeaderboardRepository 초기화.

        :param session: SQLAlchemy DB 세션 객체
        """
        self.session = session

    def upsert_leaderboard_entry(self, entry_dict: Dict[str, Any]) -> StrategyLeaderboard:
        """
        전략 성과 지표 데이터를 생성하거나 이미 존재하면 업데이트(Upsert)합니다.

        :param entry_dict: combo_id, combo_name, final_capital, total_return_pct, win_rate_pct, mdd_pct, total_trades
        :return: 저장되거나 업데이트된 StrategyLeaderboard 객체
        """
        combo_id = entry_dict["combo_id"]
        entry = self.session.query(StrategyLeaderboard).filter_by(combo_id=combo_id).first()

        if not entry:
            entry = StrategyLeaderboard(
                combo_id=combo_id,
                combo_name=entry_dict["combo_name"],
                final_capital=float(entry_dict.get("final_capital", 0.0)),
                total_return_pct=float(entry_dict.get("total_return_pct", 0.0)),
                win_rate_pct=float(entry_dict.get("win_rate_pct", 0.0)),
                mdd_pct=float(entry_dict.get("mdd_pct", 0.0)),
                total_trades=int(entry_dict.get("total_trades", 0))
            )
            self.session.add(entry)
        else:
            entry.combo_name = entry_dict["combo_name"]
            entry.final_capital = float(entry_dict.get("final_capital", 0.0))
            entry.total_return_pct = float(entry_dict.get("total_return_pct", 0.0))
            entry.win_rate_pct = float(entry_dict.get("win_rate_pct", 0.0))
            entry.mdd_pct = float(entry_dict.get("mdd_pct", 0.0))
            entry.total_trades = int(entry_dict.get("total_trades", 0))

        self.session.commit()
        self.session.refresh(entry)
        return entry

    def get_by_combo_id(self, combo_id: int) -> Optional[StrategyLeaderboard]:
        """
        특정 전략 조합 ID의 성과 지표 데이터를 조회합니다.

        :param combo_id: 전략 조합 ID (1 ~ 31)
        :return: StrategyLeaderboard 객체 또는 None
        """
        return self.session.query(StrategyLeaderboard).filter_by(combo_id=combo_id).first()

    def get_all_ordered_by_return(self) -> List[StrategyLeaderboard]:
        """
        누적 수익률(total_return_pct) 내림차순 정렬로 전체 전략 리더보드를 조회합니다.

        :return: StrategyLeaderboard 리스트
        """
        return self.session.query(StrategyLeaderboard).order_by(
            StrategyLeaderboard.total_return_pct.desc()
        ).all()
