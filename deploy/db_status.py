"""
DB 상태 점검 스크립트 (deploy/db_status.py).

`data/app.db` 와 `data/app_lite.db` 의 최신 거래일·8월28일 종목수·지수 최신일·
paper_positions 의 entry_strategy 컬럼 유무·파일 크기를 한 번에 출력한다.

사용법:
    python deploy/db_status.py
    python deploy/db_status.py 20260828    # 특정 날짜 종목수 확인
"""

import os
import sqlite3
import sys


def report(path: str, check_date: str) -> None:
    """단일 SQLite 파일의 상태를 출력합니다."""
    if not os.path.exists(path):
        print(f"[{path}] 파일 없음")
        return
    conn = sqlite3.connect(path)
    try:
        q = conn.execute
        ohlcv_max = q("SELECT max(date) FROM investor_trading_daily").fetchone()[0]
        day_cnt = q(
            "SELECT count(*) FROM investor_trading_daily WHERE date = ?", (check_date,)
        ).fetchone()[0]
        idx_max = q("SELECT max(date) FROM market_indices_daily").fetchone()[0]
        cols = [r[1] for r in q("PRAGMA table_info(paper_positions)")]
        has_entry = "entry_strategy" in cols
        size_mb = round(os.path.getsize(path) / 1_000_000, 1)
        print(f"[{path}]")
        print(f"  OHLCV 최신일   : {ohlcv_max}")
        print(f"  {check_date} 종목수 : {day_cnt}")
        print(f"  지수 최신일     : {idx_max}")
        print(f"  entry_strategy : {has_entry}")
        print(f"  파일 크기       : {size_mb} MB")
    finally:
        conn.close()


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "20260828"
    for p in ("data/app.db", "data/app_lite.db"):
        report(p, d)
        print()
