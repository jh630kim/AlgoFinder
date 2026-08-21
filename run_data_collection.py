"""
통합 데이터 수집 실행 모듈 (run_data_collection.py).

전체 데이터 수집 파이프라인을 스마트 증분(Incremental) 또는 전체(Full) 모드로 선택 실행합니다:
1단계: StockMasterCollector ➔ 전 증시 종목 마스터(all_stock_master) 및 타깃 종목(target_stocks) 동기화
2단계: MarketIndicesCollector ➔ 주요 시장 지수 및 환율(market_indices_daily: KOSPI, KOSDAQ, S&P500, USD/KRW) 적재
3단계: MarketDataCollector ➔ 타깃 종목 일별 수급/OHLCV(investor_trading_daily) 적재 및 실행 로그(sync_logs) 저장
"""

import sys
import argparse
import logging
from datetime import datetime, timedelta
from backend.app.core.database import db_manager
from backend.app.services.stock_master_collector import StockMasterCollector
from backend.app.services.market_indices_collector import MarketIndicesCollector
from backend.app.services.market_data_collector import MarketDataCollector

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("run_data_collection")


def run_pipeline(mode: str = "incremental", start_date: str = None, end_date: str = None) -> None:
    """
    1단계~3단계 통합 데이터 수집 파이프라인을 지정된 모드로 실행합니다.

    :param mode: 수집 모드 ('incremental': 미수집 신규 일자만 스마트 수집, 'full': 전체 기간 덮어쓰기)
    :param start_date: 수집 시작일자 (YYYYMMDD)
    :param end_date: 수집 종료일자 (YYYYMMDD)
    """
    is_incremental = (mode.lower() == "incremental")
    today_dt = datetime.now()
    if not end_date:
        end_date = today_dt.strftime("%Y%m%d")

    logger.info("==================================================")
    logger.info(f"🚀 AlgoFinder 통합 데이터 수집 파이프라인 시작 [{mode.upper()} 모드]")
    logger.info(f"⚙️ 옵션: 증분수집={is_incremental}, 기간={start_date or 'DB최신/1년전'} ~ {end_date}")
    logger.info("==================================================")

    # DB 테이블 생성 보장
    db_manager.create_all_tables()
    session = next(db_manager.get_session())

    try:
        # ----------------------------------------------------
        # 1단계: 종목 마스터 및 타깃 종목 목록 동기화
        # ----------------------------------------------------
        logger.info("\n[1단계] 종목 마스터 & 타깃 종목 수집 시작...")
        master_collector = StockMasterCollector(session)
        stage1_res = master_collector.run_sync()
        logger.info(
            f"  └─ ✅ [1단계 완료] KRX 전 종목 마스터 {stage1_res.get('total_fetched')}개 수집 "
            f"(마스터 {stage1_res.get('master_saved')}건 적재, 타깃 종목 {stage1_res.get('targets_saved')}개 동기화 완료)"
        )

        # ----------------------------------------------------
        # 2단계: 주요 지수 및 환율 데이터 적재
        # ----------------------------------------------------
        logger.info(f"\n[2단계] 주요 시장 지수 및 환율 수집 시작 [{mode.upper()} 모드]...")
        indices_collector = MarketIndicesCollector(session)
        stage2_res = indices_collector.collect_market_indices(
            start_date=start_date,
            end_date=end_date,
            incremental=is_incremental
        )
        if stage2_res.get("skipped"):
            logger.info("  └─ ➔ 지수/환율 데이터가 이미 최신 상태이므로 수집을 건너뛰었습니다.")
        else:
            logger.info(
                f"  └─ ✅ [2단계 완료] 지수/환율 수집 완료 "
                f"({stage2_res.get('fetched_count')}일 치 {stage2_res.get('saved_count')}건 DB 적재 완료)"
            )

        # ----------------------------------------------------
        # 3단계: 타깃 종목 일별 수급/OHLCV 및 SyncLogs 적재
        # ----------------------------------------------------
        logger.info(f"\n[3단계] 타깃 종목 일별 수급 및 OHLCV 데이터 수집 시작 [{mode.upper()} 모드]...")
        market_data_collector = MarketDataCollector(session)
        stage3_res = market_data_collector.collect_target_market_data(
            start_date=start_date,
            end_date=end_date,
            incremental=is_incremental
        )

        logger.info("\n==================================================")
        logger.info(f"🎉 전체 3단계 수집 파이프라인 완료 [{mode.upper()} 모드]")
        logger.info(
            f"📊 통계: 총 타깃 {stage3_res.get('target_symbols_count')}개 종목 중 "
            f"적재 {stage3_res.get('total_records_saved')}건, 이미 최신이라 건너뀀 {stage3_res.get('skipped_symbols_count')}개 종목"
        )
        logger.info("==================================================")

    except Exception as e:
        logger.error(f"❌ 수집 파이프라인 실행 중 오류 발생: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlgoFinder 통합 데이터 수집 스크립트")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="수집 모드 선택 ('incremental': 스마트 증분 수집, 'full': 전체 기간 덮어쓰기)"
    )
    parser.add_argument("--start", help="시작일자 (YYYYMMDD)")
    parser.add_argument("--end", help="종료일자 (YYYYMMDD)")

    args = parser.parse_args()
    run_pipeline(mode=args.mode, start_date=args.start, end_date=args.end)
