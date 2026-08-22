"""
AllStockMaster 데이터베이스 연산 전담 Repository 클래스 모듈.

전 증시 종목 마스터 데이터를 조회하고 대량 Upsert(등록/수정)하는
StockMasterRepository 클래스를 정의합니다.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.all_stock_master import AllStockMaster


class StockMasterRepository:
    """
    AllStockMaster 데이터베이스 연산 전담 Repository 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        StockMasterRepository 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session

    def get_by_code(self, code: str) -> Optional[AllStockMaster]:
        """
        종목코드로 종목 마스터 정보를 조회합니다.

        :param code: 종목코드
        :return: AllStockMaster 객체 또는 None
        """
        return self.session.query(AllStockMaster).filter(AllStockMaster.code == code).first()

    def get_all(self) -> List[AllStockMaster]:
        """
        전체 종목 마스터 리스트를 조회합니다.

        :return: AllStockMaster 리스트
        """
        return self.session.query(AllStockMaster).all()

    def bulk_upsert(self, items: List[Dict[str, Any]]) -> int:
        """
        종목 마스터 데이터를 대량 Upsert(등록/수정)합니다.

        :param items: 종목 데이터 딕셔너리 리스트
        :return: 처리된 레코드 수
        """
        if not items:
            return 0

        saved_count = 0
        for item in items:
            code = item.get("code")
            if not code:
                continue

            existing = self.get_by_code(code)
            if existing:
                existing.name = item.get("name", existing.name)
                existing.market = item.get("market", existing.market)
                existing.industry = item.get("industry", existing.industry)
                existing.sector = item.get("sector", existing.sector)
                existing.marcap = item.get("marcap", existing.marcap)
                existing.stocks = item.get("stocks", existing.stocks)
            else:
                new_stock = AllStockMaster(
                    code=code,
                    name=item.get("name"),
                    market=item.get("market"),
                    industry=item.get("industry"),
                    sector=item.get("sector"),
                    marcap=item.get("marcap"),
                    stocks=item.get("stocks"),
                )
                self.session.add(new_stock)
            saved_count += 1

        self.session.commit()
        return saved_count
