"""
전 증시 종목 마스터 Repository 모듈.

AllStockMaster 테이블에 대한 CRUD 및 Bulk Upsert 연산을 전담하는
StockMasterRepository 클래스를 정의합니다.
"""

from typing import List, Optional, Dict, Any
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
        종목코드로 마스터 정보를 조회합니다.

        :param code: 종목코드
        :return: AllStockMaster 객체 또는 None
        """
        return self.session.query(AllStockMaster).filter(AllStockMaster.code == code).first()

    def get_all(self) -> List[AllStockMaster]:
        """전체 종목 마스터 목록을 조회합니다."""
        return self.session.query(AllStockMaster).all()

    def bulk_upsert(self, items: List[Dict[str, Any]]) -> int:
        """
        종목 마스터 데이터를 대량 Upsert(등록/수정)합니다.

        :param items: 종목 데이터 딕셔너리 리스트
        :return: 처리된 레코드 수
        """
        if not items:
            return 0

        for item in items:
            code = item.get("code")
            existing = self.get_by_code(code)
            if existing:
                for key, val in item.items():
                    setattr(existing, key, val)
            else:
                new_obj = AllStockMaster(**item)
                self.session.add(new_obj)

        self.session.commit()
        return len(items)
