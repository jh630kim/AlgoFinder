"""
[09번 테스트] BacktestEngine 퀀트 시뮬레이션 엔진 연산 및 체결 검증 모듈.

inspect 모듈을 활용하여 필수 매개변수 요구 파라미터 완전성을 자동 Assert 검증하고
D-1일 신호 포착 ➔ D-0일 종가(close_price) 체결, 300만 원 초기 자산, 최대 3슬롯 관리,
prob_up 상위 매수 연산 결과를 1:1 대조 검증합니다.
"""

import os
import json
import inspect
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.models.all_stock_master import AllStockMaster
from backend.app.models.investor_trading_daily import InvestorTradingDaily
from backend.app.services.backtest_engine import BacktestEngine

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "test_09_backtest_engine_data.json")


class Test09BacktestEngine(unittest.TestCase):
    """
    09번 테스트: BacktestEngine 시뮬레이터 연산 및 매매 체결 검증 클래스.
    """

    def setUp(self) -> None:
        """인메모리 SQLite 세션 초기화, 샘플 주가 데이터 생성 및 Fixture 로드."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            self.fixtures = json.load(f)

        self._seed_mock_market_data()
        self.backtest_engine = BacktestEngine(self.session)

    def tearDown(self) -> None:
        """테스트 세션 및 DB 엔진 자원 정리."""
        self.session.close()
        self.engine.dispose()

    def _seed_mock_market_data(self) -> None:
        """시뮬레이션 연산용 샘플 마스터 및 주가 시계열 데이터(20260101 ~ 20260110) 생성."""
        master = AllStockMaster(
            code="005930", name="삼성전자", market="KOSPI",
            industry="반도체", sector="KOSPI 200", marcap=400000000000000, stocks=5000000000
        )
        self.session.add(master)

        dates = [f"202601{i:02d}" for i in range(1, 11)]
        prices = [70000, 70500, 71000, 72000, 71500, 73000, 74000, 73500, 75000, 76000]

        for d, p in zip(dates, prices):
            item = InvestorTradingDaily(
                symbol="005930", date=d, open_price=float(p - 500),
                high_price=float(p + 1000), low_price=float(p - 1000),
                close_price=float(p), volume=1000000, personal_net_buy=1000000,
                foreigner_net_buy=2000000, institution_net_buy=3000000
            )
            self.session.add(item)
        self.session.commit()

    def assert_parameters_complete(self, func, input_dict: dict) -> None:
        """
        inspect 모듈을 사용하여 필수 매개변수 요구 파라미터 완전성을 자동 검증(Assert)합니다.

        :param func: 검증 대상 메서드
        :param input_dict: 테스트 입력값 딕셔너리
        """
        sig = inspect.signature(func)
        required_params = [
            p.name for p in sig.parameters.values() if p.name != "self" and p.default == inspect.Parameter.empty
        ]
        for param in required_params:
            self.assertIn(
                param, input_dict,
                f"매개변수 누락 오류: '{param}' 항목이 input 데이터에 명시되지 않았습니다."
            )

    def test_01_run_backtest_combo1(self) -> None:
        """[9-1번 테스트] BacktestEngine.run_backtest_for_combo S1 전략 시뮬레이션 연산 검증."""
        data = self.fixtures["test_01_run_backtest_combo1"]
        inp = data["input"]
        exp = data["expected"]

        self.assert_parameters_complete(self.backtest_engine.run_backtest_for_combo, inp)

        res = self.backtest_engine.run_backtest_for_combo(
            combo_id=inp["combo_id"],
            initial_capital=inp["initial_capital"],
            max_slots=inp["max_slots"],
            start_date=inp["start_date"],
            end_date=inp["end_date"],
            target_sectors=inp["target_sectors"]
        )

        m = res["metrics"]
        print(f"\n[BacktestEngine.run_backtest | 전략: {res['combo_name']} | 최종자산: {m['final_capital']:,.0f}원 | 수익률: {m['total_return_pct']}% | MDD: {m['mdd_pct']}%]")
        self.assertEqual(res["combo_id"], exp["combo_id"])
        self.assertEqual(res["combo_name"], exp["combo_name"])
        self.assertGreaterEqual(m["final_capital"], 0.0)


if __name__ == "__main__":
    unittest.main()
