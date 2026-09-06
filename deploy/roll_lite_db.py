"""
경량 DB 롤링 증분 갱신 스크립트 (deploy/roll_lite_db.py).

보관된 경량 SQLite(`data/app_lite.db`)를 대상으로:
  1) 새 거래일 증분 수집 (`run_data_collection.run_pipeline(mode="incremental", stage="ohlcv-only")`)
     - Stage 1(마스터/타깃 목록) 미실행: PC 업로드분 유지(목록 드리프트·풀백필 방지)
     - Stage 2(지수, FDR) + Stage 3(FDR OHLCV만, 수급 컬럼 NULL)
  2) 롤링 창(기본 730일 = 2년) 밖으로 밀려난 날짜 삭제
  3) VACUUM 후 결과 보고

CI(GitHub Actions)는 KRX 로그인·네이버 스크래핑이 막혀 있으므로 `ohlcv-only`로만 수집한다.
수집이 실패하거나, 새 거래일도 없고 최신일 결손 백필(행 수 증가)도 없으면 **비정상 종료(exit 1)** 한다 —
워크플로가 이를 감지해 Release 업로드·재배포를 건너뛰고 Discord 경고를 보낸다.
(같은 날짜라도 종목이 채워지면 행 수가 늘어나므로 업로드·재배포가 진행된다.)

사용법:
    python deploy/roll_lite_db.py [--db data/app_lite.db] [--days 730]
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta


def _investor_stats(db: str) -> tuple:
    """(최신 날짜 YYYYMMDD 또는 '', investor_trading_daily 전체 행 수)를 반환합니다."""
    conn = sqlite3.connect(db)
    try:
        d = conn.execute("SELECT max(date) FROM investor_trading_daily").fetchone()[0] or ""
        n = conn.execute("SELECT count(*) FROM investor_trading_daily").fetchone()[0]
        return d, n
    finally:
        conn.close()


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


def _prune_etf(db: str) -> None:
    """웹(lite) 수집 대상에서 미국 ETF(sector='ETF_USA')를 제거합니다(첫 실행 후엔 no-op).

    투자제안은 KOSPI200/KOSDAQ150만 쓰므로 ETF 는 웹에서 불필요하고 FDR 수집 부하만 크다.
    build_lite_db.py 로 재빌드하지 않아도, 이 스텝이 배포된 lite DB 에서 ETF 를 자동으로 뺀다.
    """
    conn = sqlite3.connect(db)
    try:
        etf = [r[0] for r in conn.execute(
            "SELECT code FROM all_stock_master WHERE sector = 'ETF_USA'")]
        if not etf:
            return
        ph = ",".join("?" * len(etf))
        n1 = conn.execute(
            f"DELETE FROM investor_trading_daily WHERE symbol IN ({ph})", etf).rowcount
        n2 = conn.execute(
            f"DELETE FROM target_stocks WHERE symbol IN ({ph})", etf).rowcount
        conn.commit()
        if n1 or n2:
            print(f"ETF 제외: target_stocks -{n2}, investor_trading_daily -{n1:,}")
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/app_lite.db")
    ap.add_argument("--days", type=int, default=730)  # 2년치 (합성 점수 장기 팩터용)
    args = ap.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"경량 DB가 없습니다: {args.db} (먼저 build_lite_db.py 실행)")

    # 파이프라인이 경량 DB를 바라보도록 강제
    os.environ["DATABASE_URL"] = f"sqlite:///./{args.db.replace(os.sep, '/')}"
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    _prune_etf(args.db)  # 배포된 lite DB 에서 미국 ETF 자동 제거(첫 실행 후 no-op)
    before_max, before_cnt = _investor_stats(args.db)
    print(f"증분 수집 시작 (mode=incremental, stage=ohlcv-only) ... "
          f"현재 최신일 {before_max or '(없음)'}, 행 {before_cnt:,}")
    try:
        from run_data_collection import run_pipeline
        run_pipeline(mode="incremental", stage="ohlcv-only")
    except Exception as exc:  # noqa: BLE001 - 수집 실패 시 비정상 종료로 워크플로에 알림
        raise SystemExit(f"⚠️ 증분 수집 중 예외 발생 — 롤링 중단: {exc}")

    after_max, after_cnt = _investor_stats(args.db)
    # 새 거래일 OR 최신일 결손 백필(행 수 증가) 둘 중 하나라도 있으면 진행.
    if not after_max or (after_max <= before_max and after_cnt <= before_cnt):
        raise SystemExit(
            f"⚠️ 신규/백필 데이터가 없습니다 (최신일 {before_max or '없음'} → {after_max or '없음'}, "
            f"행 {before_cnt:,} → {after_cnt:,}). 롤링 중단 — 기존 Release 자산 보존."
        )
    print(f"신규/백필 확인: 최신일 {before_max or '없음'} → {after_max}, 행 {before_cnt:,} → {after_cnt:,}")

    print(f"롤링 프루닝 ({args.days}일) ...")
    cutoff = _prune(args.db, args.days)
    print(f"완료. 컷오프(포함) {cutoff}, 파일 {os.path.getsize(args.db) / 1_000_000:.1f} MB")


if __name__ == "__main__":
    main()
