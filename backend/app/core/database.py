"""
데이터베이스 엔진 및 세션 관리 모듈.

이 모듈은 SQLAlchemy를 이용한 데이터베이스 연결 엔진 생성,
세션 팩토리 관리 및 세션 의존성 주입 함수를 제공합니다.
"""

from typing import Generator
from sqlalchemy import create_engine, text, make_url
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from backend.app.core.config import settings

# ORM 모델 상속용 기본 Base 클래스
Base = declarative_base()


class DatabaseManager:
    """
    데이터베이스 엔진 및 세션을 전담 관리하는 메인 클래스.
    """

    def __init__(self, db_url: str = None, paper_db_url: str = None) -> None:
        """
        DatabaseManager 초기화 메서드.

        :param db_url: 메인(시세·rec) DB 접속 URL. None이면 settings.DATABASE_URL.
        :param paper_db_url: 투자제안 가상매매(prop) 전용 DB URL. None이면 settings.PAPER_DATABASE_URL.
                             비어 있으면 prop도 메인 엔진으로 폴백한다.
        """
        db_url = db_url if db_url is not None else settings.DATABASE_URL
        paper_db_url = paper_db_url if paper_db_url is not None else settings.PAPER_DATABASE_URL

        self.engine = self._make_engine(db_url)
        self.session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

        # prop 전용 엔진(선택). 미설정 시 메인 세션 팩토리를 그대로 재사용
        self.paper_engine = self._make_engine(paper_db_url) if paper_db_url else None
        self.paper_session_factory = (
            sessionmaker(autocommit=False, autoflush=False, bind=self.paper_engine)
            if self.paper_engine else self.session_factory
        )

    @staticmethod
    def _make_engine(db_url: str):
        """DB 접속 엔진을 생성합니다.

        - `sqlite+libsql://`(Turso 원격): 인증 토큰은 URL 쿼리(`authToken`)로는 드라이버에
          전달되지 않으므로, 쿼리에서 분리해 `connect_args["auth_token"]` 로 넘긴다.
          `secure` 등 나머지 쿼리는 URL에 유지한다.
        - 순수 `sqlite:`: 멀티스레드 허용(`check_same_thread=False`).
        """
        connect_args = {}
        if db_url.startswith("sqlite+libsql"):
            url = make_url(db_url)
            query = dict(url.query)
            token = query.pop("authToken", None) or query.pop("auth_token", None)
            if token:
                connect_args["auth_token"] = token
            # '/' 만 남아 빈 database 인 경우 제거 → 원격 전용 형태로 정규화
            url = url.set(query=query, database=url.database or None)
            try:
                return create_engine(url, connect_args=connect_args)
            except Exception:
                # 로컬(Windows)은 sqlalchemy-libsql 휠이 없어 드라이버 로드 실패 →
                # paper 엔진 없이 동작(prop 은 메인 DB 폴백). Turso 동기화는 HTTP 클라이언트가 담당.
                return None
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        return create_engine(db_url, connect_args=connect_args)

    def create_all_tables(self) -> None:
        """등록된 모든 SQLAlchemy ORM 모델 테이블을 DB에 생성 및 안전 마이그레이션합니다."""
        Base.metadata.create_all(bind=self.engine)
        self._migrate_paper_columns(self.engine)

        with self.engine.begin() as conn:
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

        # prop 전용 엔진이 별도면(Turso 등) paper_* 3개 테이블만 보장한다.
        # 시세/전략 테이블은 Turso에 두지 않는다. 또한 libSQL 원격은 create_all 의
        # 존재 프리체크가 불안정해, 테이블별로 개별 생성하고 중복 예외는 무시한다.
        if self.paper_engine is not None:
            for name in ("paper_portfolios", "paper_positions", "paper_trade_histories"):
                table = Base.metadata.tables.get(name)
                if table is None:
                    continue
                try:
                    table.create(bind=self.paper_engine, checkfirst=True)
                except Exception:
                    pass  # 이미 존재(원격 프리체크 실패 포함)하면 무시
            self._migrate_paper_columns(self.paper_engine)

    @staticmethod
    def _migrate_paper_columns(engine) -> None:
        """paper_* 테이블에 account_type 컬럼을 안전하게 추가합니다(이미 있으면 무시).

        libSQL/Turso 에서도 `ALTER TABLE ADD COLUMN` 은 동일하게 동작하며,
        중복 추가 예외는 무시하므로 매 기동 호출해도 무해하다.
        """
        with engine.begin() as conn:
            for tbl in ["paper_portfolios", "paper_positions", "paper_trade_histories"]:
                try:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN account_type VARCHAR(20) DEFAULT 'rec'"))
                except Exception:
                    pass  # 이미 컬럼이 존재하는 경우 예외 무시

    def get_session(self) -> Generator[Session, None, None]:
        """
        API 요청 처리용 (메인=시세·rec) 데이터베이스 세션을 생성하고 반환합니다.

        :yield: SQLAlchemy Session 객체
        """
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def get_paper_session(self, account_type: str = "rec") -> Generator[Session, None, None]:
        """가상매매 계좌유형별 세션을 반환합니다.

        - account_type == 'prop' 이고 PAPER_DATABASE_URL 이 설정돼 있으면 그 전용 엔진.
        - 그 외(rec 포함) 또는 미설정 시 메인 엔진으로 폴백.

        :param account_type: 'rec'(모의투자) 또는 'prop'(투자제안)
        :yield: SQLAlchemy Session 객체
        """
        use_paper = account_type == "prop" and self.paper_engine is not None
        factory = self.paper_session_factory if use_paper else self.session_factory
        session = factory()
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
