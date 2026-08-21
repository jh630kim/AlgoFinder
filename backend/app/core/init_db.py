"""
데이터베이스 스키마 및 테이블 최초 생성 또는 테이블/컬럼 추가 모듈
* 초기화를 위해서는 app.db를 지우고 init_db.py를 재실행해야 함

SQLAlchemy ORM 모델 기반으로 로컬 SQLite DB(data/app.db)에
모든 데이터베이스 테이블을 자동 생성하는 DatabaseInitializer 클래스를 정의합니다.
"""

import os
import logging
from backend.app.core.database import db_manager, Base
import backend.app.models  # noqa: F401 모델 등록용 임포트

logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """
    데이터베이스 스키마 초기화 및 테이블 생성 전담 클래스.
    """

    def __init__(self) -> None:
        """DatabaseInitializer 초기화 및 data 디렉토리 생성."""
        os.makedirs("data", exist_ok=True)

    def initialize_database(self) -> None:
        """
        등록된 모든 ORM 모델 기반으로 DB 테이블을 생성합니다.
        """
        logger.info("데이터베이스 스키마 생성 시작...")
        db_manager.create_all_tables()
        logger.info("모든 데이터베이스 테이블 생성이 완료되었습니다.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initializer = DatabaseInitializer()
    initializer.initialize_database()
