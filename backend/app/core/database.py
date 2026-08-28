"""
데이터베이스 엔진 및 세션 관리 모듈.

이 모듈은 SQLAlchemy를 이용한 데이터베이스 연결 엔진 생성,
세션 팩토리 관리 및 세션 의존성 주입 함수를 제공합니다.
"""

from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from backend.app.core.config import settings

# ORM 모델 상속용 기본 Base 클래스
Base = declarative_base()


class DatabaseManager:
    """
    데이터베이스 엔진 및 세션을 전담 관리하는 메인 클래스.
    """

    def __init__(self, db_url: str = settings.DATABASE_URL) -> None:
        """
        DatabaseManager 초기화 메서드.

        :param db_url: 데이터베이스 접속 URL 문자열
        """
        connect_args = {}
        # SQLite 연결 시 멀티스레드 세션 공유 허용
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self.engine = create_engine(db_url, connect_args=connect_args)
        self.session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def create_all_tables(self) -> None:
        """등록된 모든 SQLAlchemy ORM 모델 테이블을 DB에 생성 및 안전 마이그레이션합니다."""
        Base.metadata.create_all(bind=self.engine)
        # paper_* 테이블에 account_type 컬럼 마이그레이션 안전 처리
        with self.engine.begin() as conn:
            for tbl in ["paper_portfolios", "paper_positions", "paper_trade_histories"]:
                try:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN account_type VARCHAR(20) DEFAULT 'rec'"))
                except Exception:
                    pass  # 이미 컬럼이 존재하는 경우 예외 무시

            # investor_trading_daily 거래정지 플래그 컬럼 마이그레이션 안전 처리
            try:
                conn.execute(text("ALTER TABLE investor_trading_daily ADD COLUMN is_suspended INTEGER NOT NULL DEFAULT 0"))
            except Exception:
                pass  # 이미 컬럼이 존재하는 경우 예외 무시
            # 기존 적재분 일회성 백필: 거래량 0 + 고가=저가 → 거래정지로 표시
            try:
                conn.execute(text(
                    "UPDATE investor_trading_daily SET is_suspended = 1 "
                    "WHERE is_suspended = 0 AND volume = 0 AND high_price = low_price"
                ))
            except Exception:
                pass

    def get_session(self) -> Generator[Session, None, None]:
        """
        API 요청 처리용 데이터베이스 세션을 생성하고 반환합니다.

        :yield: SQLAlchemy Session 객체
        """
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()


# 전역 DatabaseManager 인스턴스 생성
db_manager = DatabaseManager()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 의존성 주입용 DB 세션 제너레이터 함수.

    :yield: SQLAlchemy Session 객체
    """
    yield from db_manager.get_session()
