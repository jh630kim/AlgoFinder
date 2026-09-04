"""
[10번 테스트] PureRuleEngine 순수관행(횡단면 합성 점수) 시뮬레이션 엔진 검증 모듈.

inspect 모듈로 run_backtest 매개변수 완전성을 Assert 검증하고,
다종목·다기간 시세를 시드해 시뮬레이션이 예외 없이 완주하며 combo_id=22 결과를
반환하는지 확인한다. 또한 신호일 합성 랭킹이 결측(pd.NA)인 보유 종목을 청산 판정할 때
TypeError 없이 "랭킹이탈"로 처리되는 회귀 케이스를 고정한다.
"""

import inspect
import unittest

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.all_stock_master import AllStockMaster
from backend.app.models.investor_trading_daily import InvestorTradingDaily
from backend.app.models.market_indices_daily import MarketIndicesDaily
from backend.app.models.target_stocks import TargetStocks
from backend.app.services.purerule_engine import COMBO_ID, COMBO_NAME, PureRuleEngine


class Test10PureRuleEngine(unittest.TestCase):
    """10번 테스트: PureRuleEngine 순수관행 시뮬레이션 엔진 검증 클래스."""

    def setUp(self) -> None:
        """인메모리 SQLite 세션 초기화 및 다종목 시세/지수 시드."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self._seed_market_data()
        self.purerule_engine = PureRuleEngine(self.session)

    def tearDown(self) -> None:
        """테스트 세션 및 DB 엔진 자원 정리."""
        self.session.close()
        self.engine.dispose()

    def _seed_market_data(self) -> None:
        """8개 종목 × 60거래일(20260101~) 시세와 동일 구간 지수 데이터를 생성한다."""
        dates = [d.strftime("%Y%m%d")
                 for d in pd.bdate_range("2026-01-02", periods=60)]

        for idx in range(8):
            code = f"00{idx}930"
            self.session.add(AllStockMaster(
                code=code, name=f"테스트{idx}", market="KOSPI",
                industry="반도체", sector="KOSPI 200",
                marcap=400000000000000, stocks=5000000000,
            ))
            self.session.add(TargetStocks(symbol=code))
            # 종목마다 상승 기울기를 달리해 횡단면 랭킹이 갈리도록 한다.
            base, slope = 50000 + idx * 1000, 40 + idx * 25
            for step, d in enumerate(dates):
                price = float(base + slope * step)
                self.session.add(InvestorTradingDaily(
                    symbol=code, date=d, open_price=price - 300.0,
                    high_price=price + 600.0, low_price=price - 600.0,
                    close_price=price, volume=1_000_000, is_suspended=0,
                    personal_net_buy=None, foreigner_net_buy=None,
                    institution_net_buy=None,
                ))

        for step, d in enumerate(dates):
            self.session.add(MarketIndicesDaily(
                date=d, kospi_close=2500.0 + step, kosdaq_close=850.0 + step,
                sp500_close=5000.0 + step, usdkrw_rate=1350.0,
            ))
        self.session.commit()

    def test_01_run_backtest_parameters_and_result(self) -> None:
        """[10-1번 테스트] 매개변수 완전성 검증 + 시뮬레이션 완주/결과 스키마 확인."""
        inp = {
            "initial_capital": 10_000_000.0, "max_slots": 3,
            "start_date": "20260101", "end_date": "20260320",
            "target_sectors": ["KOSPI 200"],
        }
        sig = inspect.signature(self.purerule_engine.run_backtest)
        required = [
            p.name for p in sig.parameters.values()
            if p.name != "self" and p.default is inspect.Parameter.empty
        ]
        for name in required:
            self.assertIn(name, inp, f"매개변수 누락 오류: '{name}'")

        res = self.purerule_engine.run_backtest(**inp)

        print(f"\n[PureRuleEngine.run_backtest | {res['combo_name']} | "
              f"체결 {res['log_count']}건 | 지표 {res['metrics']}]")
        self.assertEqual(res["combo_id"], COMBO_ID)
        self.assertEqual(res["combo_name"], COMBO_NAME)
        self.assertIn("final_capital", res["metrics"])
        self.assertGreaterEqual(res["metrics"]["final_capital"], 0.0)

    def test_02_exit_reason_handles_na_rank(self) -> None:
        """[10-2번 테스트] 신호일 합성 랭킹이 pd.NA 인 보유 종목도 예외 없이 청산 판정."""
        pos = {"buy": 10000.0, "hold": 1, "sh": 10, "pct": 50.0, "name": "테스트"}
        rank = {("000930", "20260110"): (pd.NA, pd.NA)}
        atr = {("000930", "20260110"): 100.0}

        reason = PureRuleEngine._exit_reason(
            "000930", "20260110", 10500.0, pos, rank, atr,
            n_slots=3, is_rebal=False, top_by_date={},
        )
        self.assertEqual(reason, "랭킹이탈")

    def test_03_exit_reason_missing_key_is_kept(self) -> None:
        """[10-3번 테스트] 랭킹 맵에 아예 없는 (심볼,일자)는 청산 사유 없음(보유 유지)."""
        pos = {"buy": 10000.0, "hold": 1, "sh": 10, "pct": 50.0, "name": "테스트"}
        reason = PureRuleEngine._exit_reason(
            "999999", "20260110", 10500.0, pos, {}, {},
            n_slots=3, is_rebal=False, top_by_date={"20260110": ["999999"]},
        )
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
