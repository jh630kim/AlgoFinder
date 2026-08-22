"""
통합 퀀트 전략 백테스팅 실행 모듈 (run_backtest.py).

21개 퀀트 전략 조합(단독 8개 + 복합 13개)에 대하여
초기 자산 300만 원 / 최대 3슬롯(총자산 1/3) 운영 / D-1일 신호 포착 ➔ D-0일 종가 체결 /
prob_up 상위 정렬 / 가변 기간 및 투자 대상 군 다중 선택 필터링 백테스트를 실행하고 DB에 저장합니다.
"""

import sys
import argparse
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from backend.app.core.database import db_manager
from backend.app.services.backtest_engine import BacktestEngine, STRATEGY_COMBOS
from backend.app.repositories.strategy_leaderboard_repository import StrategyLeaderboardRepository

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("run_backtest")


def main() -> None:
    """CLI 인자를 파싱하고 21개 백테스트 시뮬레이션을 구동하여 DB에 결과를 적재합니다."""
    parser = argparse.ArgumentParser(description="AlgoFinder 21개 퀀트 전략 백테스트 구동 스크립트")
    parser.add_argument(
        "--combo",
        default="all",
        help="실행할 전략 조합 ID (1~21 지정 또는 'all', 기본값: all)"
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=3000000.0,
        help="초기 자본금 (원, 기본값: 3,000,000)"
    )
    parser.add_argument(
        "--target",
        default="ALL",
        help="투자 대상 군 선택 (콤마 구분: KOSPI200,KOSDAQ150,ETF_USA 또는 ALL, 기본값: ALL)"
    )
    parser.add_argument("--start", help="시뮬레이션 시작일자 (YYYYMMDD, 미지정 시 최근 1년)")
    parser.add_argument("--end", help="시뮬레이션 종료일자 (YYYYMMDD, 미지정 시 오늘)")

    args = parser.parse_args()

    # 투자 대상 군 파싱
    target_str = args.target.upper()
    if target_str == "ALL":
        target_sectors = ["KOSPI 200", "KOSDAQ 150", "ETF_USA"]
    else:
        raw_targets = [t.strip() for t in target_str.split(",") if t.strip()]
        target_sectors = []
        for t in raw_targets:
            if "KOSPI" in t:
                target_sectors.append("KOSPI 200")
            elif "KOSDAQ" in t:
                target_sectors.append("KOSDAQ 150")
            elif "ETF" in t:
                target_sectors.append("ETF_USA")

    today_dt = datetime.now()
    end_date = args.end if args.end else today_dt.strftime("%Y%m%d")
    start_date = args.start if args.start else (today_dt - timedelta(days=365)).strftime("%Y%m%d")

    logger.info("==================================================")
    logger.info(f"🚀 AlgoFinder 21개 퀀트 전략 백테스팅 엔진 구동")
    logger.info(f"⚙️ 옵션: 초기자금={args.initial_capital:,.0f}원 | 3슬롯 관리(1/3 분할)")
    logger.info(f"⚙️ 대상군: {target_sectors} | 기간: {start_date} ~ {end_date}")
    logger.info("==================================================")

    db_manager.create_all_tables()
    session = next(db_manager.get_session())

    try:
        engine = BacktestEngine(session)

        if args.combo.lower() == "all":
            combo_ids = list(STRATEGY_COMBOS.keys())
        else:
            combo_ids = [int(c.strip()) for c in args.combo.split(",") if c.strip()]

        for c_id in combo_ids:
            logger.info(f" -> [Combo {c_id:02d}] 백테스팅 시뮬레이션 연산 중...")
            res = engine.run_backtest_for_combo(
                combo_id=c_id,
                initial_capital=args.initial_capital,
                start_date=start_date,
                end_date=end_date,
                target_sectors=target_sectors
            )
            m = res["metrics"]
            logger.info(
                f"    └─ ✅ [{res['combo_name']}] 수익률: {m['total_return_pct']:+.2f}% | "
                f"승률: {m['win_rate_pct']:.1f}% | MDD: {m['mdd_pct']:.1f}% | "
                f"최종자산: {m['final_capital']:,.0f}원 (거래건수: {m['total_trades']}건)"
            )

        logger.info("\n==================================================")
        logger.info("🏆 21개 전략 성과 리더보드 (누적 수익률 상위 5개)")
        logger.info("==================================================")

        leaderboard_repo = StrategyLeaderboardRepository(session)
        top_entries = leaderboard_repo.get_all_ordered_by_return()[:5]
        for idx, entry in enumerate(top_entries, 1):
            logger.info(
                f" [{idx}위] {entry.combo_name:<15} | 수익률: {entry.total_return_pct:+.2f}% | "
                f"승률: {entry.win_rate_pct:.1f}% | MDD: {entry.mdd_pct:.1f}% | "
                f"최종자산: {entry.final_capital:,.0f}원"
            )
        logger.info("==================================================")

    except Exception as e:
        logger.error(f"❌ 백테스팅 중 오류 발생: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    main()
