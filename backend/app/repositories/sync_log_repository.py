"""
데이터 수집 동기화 로그 Repository 모듈.

SyncLogs 테이블에 대한 실행 기록 저장 및 조회를 전담하는
SyncLogRepository 클래스를 정의합니다.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.sync_logs import SyncLogs


class SyncLogRepository:
    """
    SyncLogs 데이터베이스 연산 전담 Repository 클래스.
    """

    def __init__(self, session: Session) -> None:
        """
        SyncLogRepository 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.session = session

    def create_log(self, log_data: Dict[str, Any]) -> SyncLogs:
        """
        새 동기화 실행 로그를 생성하여 DB에 저장합니다.

        :param log_data: 로그 필드 딕셔너리
        :return: 생성된 SyncLogs 객체
        """
        new_log = SyncLogs(**log_data)
        self.session.add(new_log)
        self.session.commit()
        self.session.refresh(new_log)
        return new_log

    def get_latest_log(self) -> Optional[SyncLogs]:
        """최신 동기화 실행 로그를 조회합니다."""
        return self.session.query(SyncLogs).order_by(SyncLogs.id.desc()).first()
