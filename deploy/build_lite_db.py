"""
경량(웹 배포용) SQLite 생성 스크립트 (deploy/build_lite_db.py).

전체 20년치 `data/app.db` 에서 웹(투자제안 모바일)에 필요한 최소 데이터만 남긴
`data/app_lite.db` 를 만든다.

포함: all_stock_master(전체), target_stocks(전체),
      investor_trading_daily(최근 N일 + 타깃 종목만), market_indices_daily(최근 N일),
      paper_* (스키마만, 데이터 제외)
제외: strategy_leaderboard / strategy_trade_logs / strategy_daily_equity / sync_logs

사용법:
    python deploy/build_lite_db.py [--src data/app.db] [--dst data/app_lite.db] [--days 365]
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ORM 테이블 등록(모델 import 만으로 Base.metadata 에 등록됨)
from backend.app.core.database import Base  # noqa: E402
import backend.app.models.all_stock_master  # noqa: F401,E402
import backend.app.models.target_stocks  # noqa: F401,E402
import backend.app.models.investor_trading_daily  # noqa: F401,E402
import backend.app.models.market_indices_daily  # noqa: F401,E402
import backend.app.models.paper_trading  # noqa: F401,E402

# 경량 DB에 유지할 테이블
KEEP_ALL = ["all_stock_master", "target_stocks"]
KEEP_ROLLING = ["investor_trading_daily", "market_indices_daily"]
SCHEMA_ONLY = ["paper_portfolios", "paper_positions", "paper_trade_histories"]


def _common_columns(conn: sqlite3.Connection, table: str) -> list:
    """대상 테이블에서 (경량 스키마 ∩ 원본 스키마) 공통 컬럼명을 순서대로 반환합니다."""
    lite_cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    full_cols = {r[1] for r in conn.execute(f"PRAGMA full.table_info({table})")}
    return [c for c in lite_cols if c in full_cols]


def build(src: str, dst: str, days: int) -> None:
    """경량 DB를 생성합니다."""
    if not os.path.exists(src):
        raise SystemExit(f"원본 DB가 없습니다: {src}")
    if os.path.exists(dst):
        os.remove(dst)

    # 1) ORM 스키마로 빈 경량 DB 생성 + 안전 마이그레이션(is_suspended / account_type)
    from sqlalchemy import create_engine, text
    engine = create_engine(f"sqlite:///{dst}")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as c:
        for tbl in SCHEMA_ONLY:
            try:
                c.execute(text(f"ALTER TABLE {tbl} ADD COLUMN account_type VARCHAR(20) DEFAULT 'rec'"))
            except Exception:
                pass
        try:
            c.execute(text("ALTER TABLE investor_trading_daily ADD COLUMN is_suspended INTEGER NOT NULL DEFAULT 0"))
        except Exception:
            pass
    engine.dispose()

    # 2) 원본에서 필터 복사
    conn = sqlite3.connect(dst)
    try:
        conn.execute(f"ATTACH DATABASE '{src}' AS full")
        cutoff = (
            datetime.strptime(conn.execute("SELECT max(date) FROM full.investor_trading_daily").fetchone()[0], "%Y%m%d")
            - timedelta(days=days)
        ).strftime("%Y%m%d")
        print(f"롤링 컷오프(포함): {cutoff}  (최근 {days}일)")

        for table in KEEP_ALL:
            cols = _common_columns(conn, table)
            col_sql = ", ".join(cols)
            conn.execute(f"INSERT INTO {table} ({col_sql}) SELECT {col_sql} FROM full.{table}")

        cols = _common_columns(conn, "investor_trading_daily")
        col_sql = ", ".join(cols)
        conn.execute(
            f"INSERT INTO investor_trading_daily ({col_sql}) "
            f"SELECT {col_sql} FROM full.investor_trading_daily "
            f"WHERE date >= ? AND symbol IN (SELECT symbol FROM target_stocks)",
            (cutoff,),
        )

        cols = _common_columns(conn, "market_indices_daily")
        col_sql = ", ".join(cols)
        conn.execute(
            f"INSERT INTO market_indices_daily ({col_sql}) "
            f"SELECT {col_sql} FROM full.market_indices_daily WHERE date >= ?",
            (cutoff,),
        )

        conn.commit()
        conn.execute("DETACH DATABASE full")
        conn.execute("VACUUM")
        conn.commit()

        for t in KEEP_ALL + KEEP_ROLLING + SCHEMA_ONLY:
            n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"  {t:26s} rows={n:,}")
    finally:
        conn.close()

    print(f"완료: {dst}  ({os.path.getsize(dst) / 1_000_000:.1f} MB)  / 원본 {os.path.getsize(src) / 1_000_000:.1f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/app.db")
    ap.add_argument("--dst", default="data/app_lite.db")
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()
    build(args.src, args.dst, args.days)
