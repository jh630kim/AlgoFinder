"""
[07번 테스트] 8개 퀀트 매매 전략 모듈 전수 검증 및 StockInfo 원본 1:1 대조 테스트.

D:\\Projects\\AntiGravity\\AlgoFinder\\backend\\tests\\fixtures\\test_07_strategy_engin_data_gen_truth.json
독립 정답지 파일에 수록된 StockInfo 레거시 엔진의 연산 결과(expected_results)와
신규 AlgoFinder 8개 퀀트 전략(S1~S5)의 연산 결과를 1:1로 비교 대조(Expected vs Actual)하여 검증하고,
결과를 D:\\Projects\\AntiGravity\\AlgoFinder\\backend\\tests\\fixtures\\test_07_strategy_engine_results.csv 파일로 자동 추출합니다.
"""

import os
import json
import sqlite3
import inspect
import unittest
import pandas as pd
import numpy as np

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "test_07_strategy_engine_data.json"
)

GROUND_TRUTH_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "test_07_strategy_engin_data_gen_truth.json"
)

CSV_OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "test_07_strategy_engine_results.csv"
)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "app.db"
)

from backend.app.services.strategies.s1_ma_cross import S1MACrossStrategy
from backend.app.services.strategies.s1a_ma_cross_volume import S1aMACrossVolumeStrategy
from backend.app.services.strategies.s1b_ma_cross_legacy import S1bMACrossLegacyStrategy
from backend.app.services.strategies.s1c_ma_cross_adaptive import S1cMACrossAdaptiveStrategy
from backend.app.services.strategies.s2_breakout import S2BreakoutStrategy
from backend.app.services.strategies.s3_bollinger import S3BollingerStrategy
from backend.app.services.strategies.s4_rsi_overbought import S4RSIStrategy
from backend.app.services.strategies.s5_candle_patterns import S5CandlePatternsStrategy


class Test07StrategyEngine(unittest.TestCase):
    """
    07번 테스트: StockInfo 원본 독립 정답지(test_07_strategy_engin_data_gen_truth.json) 1:1 대조 및 CSV 저장 클래스.
    """

    all_signal_records = []
    expected_dict = {}

    @classmethod
    def tearDownClass(cls) -> None:
        """모든 테스트 종료 후 8개 전략의 매수 및 매도 신호 내역을 CSV 파일로 일괄 저장."""
        if cls.all_signal_records:
            res_df = pd.DataFrame(cls.all_signal_records)
            output_dir = os.path.dirname(CSV_OUTPUT_PATH)
            os.makedirs(output_dir, exist_ok=True)
            res_df.to_csv(CSV_OUTPUT_PATH, index=False, encoding="utf-8-sig")
            buy_cnt = len(res_df[res_df['signal_type'] == '매수'])
            sell_cnt = len(res_df[res_df['signal_type'] == '매도'])
            print(f"\n==================================================")
            print(f" [CSV 저장 완료] StockInfo 원본 대조 결과 저장 완료:")
            print(f"    - 파일 경로: {CSV_OUTPUT_PATH}")
            print(f"    - 총 포착 신호: {len(res_df)}건 (매수: {buy_cnt}건 | 매도: {sell_cnt}건)")
            print(f"==================================================")

    def setUp(self) -> None:
        """fixtures JSON 주가 파일 및 test_07_strategy_engin_data_gen_truth.json 정답지 로딩."""
        # 1. 120일 시계열 주가 로딩
        if os.path.exists(FIXTURE_PATH):
            with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            records = data.get("records", [])
            self.df_test = pd.DataFrame(records)

        # 2. StockInfo 독립 정답지 파일 로딩
        if os.path.exists(GROUND_TRUTH_PATH):
            with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
                gt_data = json.load(f)
            self.expected_dict = gt_data.get("expected_results", {})

    def assert_parameters_complete(self, func, input_dict: dict) -> None:
        """inspect 모듈 매개변수 완전성 검증."""
        sig = inspect.signature(func)
        required_params = [
            p.name for p in sig.parameters.values() if p.name != "self"
        ]
        for param in required_params:
            self.assertIn(
                param, input_dict,
                f"매개변수 누락 오류: '{param}' 항목이 input 데이터에 명시되지 않았습니다."
            )

    def _verify_expected_vs_actual(self, strategy_name: str, res_df: pd.DataFrame) -> None:
        """StockInfo 원본 정답지(Expected)와 AlgoFinder 연산 결과(Actual) 1:1 대조 출력 및 검증."""
        exp_info = self.expected_dict.get(strategy_name, {})
        exp_buy_dates = exp_info.get("expected_buy_dates", [])
        exp_sell_dates = exp_info.get("expected_sell_dates", [])

        buy_df = res_df[res_df['signal_buy'] == True]
        sell_df = res_df[res_df['signal_sell'] == True]

        actual_buy_dates = [
            f"{str(d)[:4]}-{str(d)[4:6]}-{str(d)[6:]}" if len(str(d)) == 8 else str(d)
            for d in buy_df['date'].tolist()
        ]
        actual_sell_dates = [
            f"{str(d)[:4]}-{str(d)[4:6]}-{str(d)[6:]}" if len(str(d)) == 8 else str(d)
            for d in sell_df['date'].tolist()
        ]

        print(f"\n==================================================")
        print(f" [전략명: {strategy_name}] StockInfo 원본 정답지 1:1 대조")
        print(f"--------------------------------------------------")
        print(f"    - [매수신호일 대조]")
        print(f"      - StockInfo 정답 (Expected) : {exp_buy_dates}")
        print(f"      - AlgoFinder 실제 (Actual)   : {actual_buy_dates}")

        print(f"    - [매도신호일 대조]")
        print(f"      - StockInfo 정답 (Expected) : {exp_sell_dates}")
        print(f"      - AlgoFinder 실제 (Actual)   : {actual_sell_dates}")

        # 신호 내역 CSV 기록 누적
        sig_df = res_df[(res_df['signal_buy'] == True) | (res_df['signal_sell'] == True)]
        for idx, row in sig_df.iterrows():
            date_str = str(row['date'])
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if len(date_str) == 8 else date_str
            prob = float(row['prob_up'])
            close_p = float(row['close_price'])
            symbol = str(row.get('symbol', '005930'))
            name = str(row.get('name', '삼성전자'))
            signal_type = "매수" if bool(row.get('signal_buy', False)) else "매도"

            self.all_signal_records.append({
                "strategy_name": strategy_name,
                "symbol": symbol,
                "name": name,
                "date": date_fmt,
                "signal_type": signal_type,
                "close_price": int(close_p),
                "prob_up": prob
            })
        print(f"==================================================")

        # StockInfo 원본 정답지와 1:1 Assert 대조 검증
        self.assertEqual(exp_buy_dates, actual_buy_dates, f"[{strategy_name}] StockInfo 원본 매수신호 정답 불일치!")
        self.assertEqual(exp_sell_dates, actual_sell_dates, f"[{strategy_name}] StockInfo 원본 매도신호 정답 불일치!")

    def test_01_s1_ma_cross(self) -> None:
        """[7-1번 테스트] S1 이평선 골든크로스 전략 1:1 대조 검증."""
        strat = S1MACrossStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("signal_buy", res_df.columns)
        self.assertIn("signal_sell", res_df.columns)
        self.assertIn("prob_up", res_df.columns)
        self._verify_expected_vs_actual("S1_MA_Cross", res_df)

    def test_02_s1a_ma_cross_volume(self) -> None:
        """[7-2번 테스트] S1a 거래량 150% 동반 이평 돌파 전략 1:1 대조 검증."""
        strat = S1aMACrossVolumeStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("signal_buy", res_df.columns)
        self._verify_expected_vs_actual("S1a_MA_Cross_Volume", res_df)

    def test_03_s1b_ma_cross_legacy(self) -> None:
        """[7-3번 테스트] S1b 상승확률 55% 이상 필터 전략 1:1 대조 검증."""
        strat = S1bMACrossLegacyStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("signal_buy", res_df.columns)
        self._verify_expected_vs_actual("S1b_MA_Cross_Legacy", res_df)

    def test_04_s1c_ma_cross_adaptive(self) -> None:
        """[7-4번 테스트] S1c 20일선 추세 적응형 듀얼 전략 1:1 대조 검증."""
        strat = S1cMACrossAdaptiveStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("signal_buy", res_df.columns)
        self._verify_expected_vs_actual("S1c_MA_Cross_Adaptive", res_df)

    def test_05_s2_breakout(self) -> None:
        """[7-5번 테스트] S2 RSI Signal 크로스 & 눌림목 반등 전략 1:1 대조 검증."""
        strat = S2BreakoutStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("rsi", res_df.columns)
        self._verify_expected_vs_actual("S2_Breakout", res_df)

    def test_06_s3_bollinger(self) -> None:
        """[7-6번 테스트] S3 볼린저 밴드 스퀴즈 돌파 & 하한선 반등 전략 1:1 대조 검증."""
        strat = S3BollingerStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("bb_ub", res_df.columns)
        self._verify_expected_vs_actual("S3_Bollinger", res_df)

    def test_07_s4_rsi_overbought(self) -> None:
        """[7-7번 테스트] S4 RSI 30% 이하 과매도 탈출 전략 1:1 대조 검증."""
        strat = S4RSIStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("rsi14", res_df.columns)
        self._verify_expected_vs_actual("S4_RSI_Overbought", res_df)

    def test_08_s5_candle_patterns(self) -> None:
        """[7-8번 테스트] S5 캔들 패턴(망치형/장대양봉) 전략 1:1 대조 검증."""
        strat = S5CandlePatternsStrategy()
        self.assert_parameters_complete(strat.calculate_indicators, {"df": self.df_test})
        res_df = strat.calculate_indicators(self.df_test)
        self.assertIn("signal_buy", res_df.columns)
        self._verify_expected_vs_actual("S5_Candle_Patterns", res_df)


if __name__ == "__main__":
    unittest.main()
