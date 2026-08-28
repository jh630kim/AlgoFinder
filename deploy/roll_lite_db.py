"""
경량 DB 롤링 증분 갱신 스크립트 (deploy/roll_lite_db.py).

보관된 경량 SQLite(`data/app_lite.db`)를 대상으로:
  1) 새 거래일 증분 수집 (`run_data_collection.run_pipeline(mode="incremental")`)
  2) 롤링 창(기본 365일) 밖으로 밀려난 날짜 삭제
  3) VACUUM 후 결과 보고

증분 수집은 KRX 로그인·네트워크가 필요하므로 CI(GitHub Actions)에서 실행한다.
파생 캐시(kospi_regime / proposal_advisor_cache)는 요청 시점에 재계산되는 값이라
별도 산출물이 없다(백테스트용 `data/backtest_render_cache.json` 은 웹 배포 대상 아님).

사용법:
    python deploy/roll_lite_db.py [--db data/app_lite.db] [--days 365] [--skip-collect]
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta


def _prune(db: str, days: int) -> str:
    """롤링 창 밖 날짜를 삭제하고 VACUUM 합니다. 적용된 컷오프를 반환."""
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT max(date) FROM investor_trading_daily").fetchone()
        if not row or not row[0]:
            raise SystemExit("investor_trading_daily 가 비어 있습니다.")
        cutoff = (datetime.strptime(row[0], "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")
        before = {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in ("investor_trading_daily", "market_indices_daily")
        }
        conn.execute("DELETE FROM investor_trading_daily WHERE date < ?", (cutoff,))
        conn.execute("DELETE FROM market_indices_daily WHERE date < ?", (cutoff,))
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
        for t, n0 in before.items():
            n1 = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"  {t:26s} {n0:,} -> {n1:,}  (삭제 {n0 - n1:,})")
        return cutoff
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/app_lite.db")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--skip-collect", action="store_true", help="증분 수집 없이 프루닝/VACUUM만 수행")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"경량 DB가 없습니다: {args.db} (먼저 build_lite_db.py 실행)")

    # 파이프라인이 경량 DB를 바라보도록 강제
    os.environ["DATABASE_URL"] = f"sqlite:///./{args.db.replace(os.sep, '/')}"
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not args.skip_collect:
        print("증분 수집 시작 (mode=incremental, stage=all) ...")
        from run_data_collection import run_pipeline
        run_pipeline(mode="incremental", stage="all")
    else:
        print("증분 수집 생략(--skip-collect).")

    print(f"롤링 프루닝 ({args.days}일) ...")
    cutoff = _prune(args.db, args.days)
    print(f"완료. 컷오프(포함) {cutoff}, 파일 {os.path.getsize(args.db) / 1_000_000:.1f} MB")


if __name__ == "__main__":
    main()
