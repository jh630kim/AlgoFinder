"""
데이터 수집 및 동기화 로그 ORM 모델 모듈.

수집 파이프라인의 동기화 실행 이력, 수집 건수 및 성공/실패 상태를
저장하고 관리하는 SyncLogs 클래스를 정의합니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from backend.app.core.database import Base


class SyncLogs(Base):
    """
    데이터 수집 및 동기화 로그 ORM 모델 클래스.
    """
    __tablename__ = "sync_logs"

    # 기본키 ID
    id = Column(Integer, primary_key=True, autoincrement=True, comment="로그 ID")
    # 동기화 처리 일자 (YYYYMMDD)
    sync_date = Column(String(10), nullable=False, index=True, comment="동기화 일자")

    # 시장별 처리 수집 건수
    total_count = Column(Integer, default=0, comment="전체 처리 건수")
    kospi_count = Column(Integer, default=0, comment="코스피 처리 건수")
    kosdaq_count = Column(Integer, default=0, comment="코스닥 처리 건수")
    etf_count = Column(Integer, default=0, comment="ETF 처리 건수")
    etn_count = Column(Integer, default=0, comment="ETN 처리 건수")

    # 실행 상태 (SUCCESS / FAILED)
    status = Column(String(20), nullable=False, default="SUCCESS", comment="상태")
    # 등록 일시
    created_at = Column(DateTime, default=datetime.utcnow, comment="등록일시")

    def __repr__(self) -> str:
        """SyncLogs 객체의 문자열 표현을 반환합니다."""
        return f"<SyncLogs(id={self.id}, sync_date='{self.sync_date}', status='{self.status}')>"
