"""
전략별 일별 누적자산(Equity Curve) 리포지토리 모듈.

StrategyDailyEquity ORM 모델과 연동하여 일별 평가자산 시계열의
일괄 저장(Bulk Insert) 및 조회를 전담하는 StrategyDailyEquityRepository 클래스를 정의합니다.
"""

import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.strategy_daily_equity import StrategyDailyEquity

logger = logging.getLogger(__name__)


class StrategyDailyEquityRepository:
    """
    StrategyDailyEquity 데이터베이스 CRUD 전담 리포지토리 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        StrategyDailyEquityRepository 초기화.

        :param session: SQLAlchemy DB 세션 객체
        """
        self.session = session

    def bulk_insert_daily_equity(self, equity_list: List[Dict[str, Any]]) -> int:
        """
        여러 건의 일별 누적자산 데이터를 대량(Bulk) 적재합니다.

        :param equity_list: 일별 자산 딕셔너리 리스트 (combo_id, trade_date, equity_amount)
        :return: 저장된 데이터 건수
        """
        if not equity_list:
            return 0

        objects = [
            StrategyDailyEquity(
                combo_id=item["combo_id"],
                trade_date=item["trade_date"],
                equity_amount=item["equity_amount"]
            )
            for item in equity_list
        ]
        self.session.bulk_save_objects(objects)
        self.session.commit()
        return len(objects)

    def get_equity_by_combo(self, combo_id: int) -> List[StrategyDailyEquity]:
        """
        특정 전략 조합 ID의 전체 일별 평가자산을 일자순으로 조회합니다.

        :param combo_id: 전략 조합 ID
        :return: StrategyDailyEquity 리스트
        """
        return self.session.query(StrategyDailyEquity).filter_by(
            combo_id=combo_id
        ).order_by(StrategyDailyEquity.trade_date.asc()).all()

    def clear_equity_by_combo(self, combo_id: int) -> int:
        """
        특정 전략 조합 ID의 기존 일별 평가자산을 삭제합니다.

        :param combo_id: 전략 조합 ID
        :return: 삭제된 데이터 건수
        """
        deleted_count = self.session.query(StrategyDailyEquity).filter_by(combo_id=combo_id).delete()
        self.session.commit()
        return deleted_count
