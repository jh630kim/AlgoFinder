"""
백테스트 매매일지 및 체결 로그 리포지토리 모듈.

StrategyTradeLogs ORM 모델과 연동하여 개별 체결 내역(매수/매도, 체결단가, 수량, 평가자산 등)의
일괄 저장(Bulk Insert) 및 조회를 전담하는 StrategyTradeLogsRepository 클래스를 정의합니다.
"""

import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.strategy_trade_logs import StrategyTradeLogs

logger = logging.getLogger(__name__)


class StrategyTradeLogsRepository:
    """
    StrategyTradeLogs 데이터베이스 CRUD 전담 리포지토리 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        StrategyTradeLogsRepository 초기화.

        :param session: SQLAlchemy DB 세션 객체
        """
        self.session = session

    def bulk_insert_trade_logs(self, logs_list: List[Dict[str, Any]]) -> int:
        """
        여러 건의 매매 체결 로그 데이터를 대량(Bulk) 적재합니다.

        :param logs_list: 체결 로그 딕셔너리 리스트
        :return: 저장된 로그 건수
        """
        if not logs_list:
            return 0

        objects = [
            StrategyTradeLogs(
                combo_id=item["combo_id"],
                trade_date=item["trade_date"],
                symbol=item["symbol"],
                name=item.get("name"),
                trade_type=item["trade_type"],
                holding_days=item.get("holding_days", 0),
                shares=item.get("shares", 0),
                unit_price=item.get("unit_price", 0.0),
                total_amount=item.get("total_amount", 0.0),
                equity_after_trade=item.get("equity_after_trade", 0.0),
                cum_return_pct=item.get("cum_return_pct", 0.0),
                profit_pct=item.get("profit_pct", 0.0),
                profit_krw=item.get("profit_krw", 0.0),
                prob_up=item.get("prob_up", 0.0),
                strategy_tag=item.get("strategy_tag")
            )
            for item in logs_list
        ]
        self.session.bulk_save_objects(objects)
        self.session.commit()
        return len(objects)

    def get_logs_by_combo(self, combo_id: int) -> List[StrategyTradeLogs]:
        """
        특정 전략 조합 ID의 전체 체결 로그를 일자순으로 조회합니다.

        :param combo_id: 전략 조합 ID
        :return: StrategyTradeLogs 리스트
        """
        return self.session.query(StrategyTradeLogs).filter_by(
            combo_id=combo_id
        ).order_by(StrategyTradeLogs.trade_date.asc(), StrategyTradeLogs.id.asc()).all()

    def clear_logs_by_combo(self, combo_id: int) -> int:
        """
        특정 전략 조합 ID의 기존 체결 로그를 삭제합니다.

        :param combo_id: 전략 조합 ID
        :return: 삭제된 로그 건수
        """
        deleted_count = self.session.query(StrategyTradeLogs).filter_by(combo_id=combo_id).delete()
        self.session.commit()
        return deleted_count
