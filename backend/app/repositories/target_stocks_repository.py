"""
수집 대상 타깃 종목 Repository 모듈.

TargetStocks 테이블에 대한 조회, 등록 및 초기화 연산을 전담하는
TargetStocksRepository 클래스를 정의합니다.
"""

from typing import List
from sqlalchemy.orm import Session
from backend.app.models.target_stocks import TargetStocks


class TargetStocksRepository:
    """
    TargetStocks 데이터베이스 연산 전담 Repository 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        TargetStocksRepository 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session

    def get_all_symbols(self) -> List[str]:
        """
        등록된 모든 타깃 종목코드 리스트를 조회합니다.

        :return: 종목코드 문자열 리스트
        """
        records = self.session.query(TargetStocks.symbol).all()
        return [r.symbol for r in records]

    def sync_targets(self, symbols: List[str]) -> int:
        """
        타깃 종목 목록을 동기화(초기화 후 재등록)합니다.

        :param symbols: 타깃 종목코드 리스트
        :return: 등록된 종목 수
        """
        # 기존 목록 삭제
        self.session.query(TargetStocks).delete()
        
        # 신규 목록 추가
        for sym in set(symbols):
            self.session.add(TargetStocks(symbol=sym))

        self.session.commit()
        return len(symbols)
