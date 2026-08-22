"""
[StockInfo 원본 정답지 생성 전용 프로그램]

D:\\Projects\\AntiGravity\\StockInfo\\Strategy 내의 8개 레거시 전략 모듈(strategy.py)을
동적으로 임포트하여 삼성전자 120일 시계열 데이터에 투입하고,
StockInfo 원본 엔진이 연산한 매수/매도 신호 발생 일자를 추출하여
D:\\Projects\\AntiGravity\\AlgoFinder\\backend\\tests\\fixtures\\test_07_strategy_engin_data_gen_truth.json 파일로 저장합니다.
"""

import os
import sys
import json
import importlib.util
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

STOCKINFO_STRATEGY_DIR = r"D:\Projects\AntiGravity\StockInfo\Strategy"
FIXTURE_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "test_07_strategy_engine_data.json"
)
GROUND_TRUTH_OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "test_07_strategy_engin_data_gen_truth.json"
)

# StockInfo 폴더별 전략 클래스명 매핑
STRATEGY_MAP = {
    "S1_MA_Cross": ("S1_MA_Cross", "S1MACrossStrategy"),
    "S1a_MA_Cross_Volume": ("S1a_MA_Cross_Volume", "S1aMACrossVolumeStrategy"),
    "S1b_MA_Cross_Legacy": ("S1b_MA_Cross_Legacy", "S1bMACrossLegacyStrategy"),
    "S1c_MA_Cross_Adaptive": ("S1c_MA_Cross_Adaptive", "S1cMACrossAdaptiveStrategy"),
    "S2_Breakout": ("S2_Breakout", "S2BreakoutStrategy"),
    "S3_Bollinger": ("S3_Bollinger", "S3BollingerStrategy"),
    "S4_RSI_Overbought": ("S4_RSI_Overbought", "S4RSIStrategy"),
    "S5_Candle_Patterns": ("S5_Candle_Patterns", "S5CandlePatternsStrategy")
}


def load_legacy_strategy_module(folder_name: str, class_name: str):
    """StockInfo/Strategy/<folder_name>/strategy.py 동적 임포트 헬퍼"""
    module_path = os.path.join(STOCKINFO_STRATEGY_DIR, folder_name, "strategy.py")
    if not os.path.exists(module_path):
        raise FileNotFoundError(f"StockInfo 전략 모듈을 찾을 수 없습니다: {module_path}")

    spec = importlib.util.spec_from_file_location(f"legacy_{folder_name}", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"legacy_{folder_name}"] = module
    spec.loader.exec_module(module)

    strategy_cls = getattr(module, class_name)
    return strategy_cls()


def generate_ground_truth():
    print(f"[StockInfo 정답지 생성기] 동적 임포트 연산 시작...")
    if not os.path.exists(FIXTURE_DATA_PATH):
        raise FileNotFoundError(f"픽스처 주가 데이터가 없습니다: {FIXTURE_DATA_PATH}")

    with open(FIXTURE_DATA_PATH, "r", encoding="utf-8") as f:
        fixture_json = json.load(f)

    records = fixture_json.get("records", [])
    df_input = pd.DataFrame(records)

    expected_results = {}

    for strat_key, (folder_name, class_name) in STRATEGY_MAP.items():
        print(f" -> StockInfo 원본 [{folder_name}] 레거시 모듈 계산 중...")
        try:
            legacy_strat = load_legacy_strategy_module(folder_name, class_name)
            res_df = legacy_strat.calculate_indicators(df_input)

            buy_df = res_df[res_df['signal_buy'] == True] if 'signal_buy' in res_df.columns else pd.DataFrame()
            sell_df = res_df[res_df['signal_sell'] == True] if 'signal_sell' in res_df.columns else pd.DataFrame()

            buy_dates = [
                f"{str(d)[:4]}-{str(d)[4:6]}-{str(d)[6:]}" if len(str(d)) == 8 else str(d)
                for d in buy_df['date'].tolist()
            ] if not buy_df.empty else []

            sell_dates = [
                f"{str(d)[:4]}-{str(d)[4:6]}-{str(d)[6:]}" if len(str(d)) == 8 else str(d)
                for d in sell_df['date'].tolist()
            ] if not sell_df.empty else []

            expected_results[strat_key] = {
                "expected_buy_dates": buy_dates,
                "expected_sell_dates": sell_dates
            }
            print(f"    - [원본 매수신호]: {buy_dates}")
            print(f"    - [원본 매도신호]: {sell_dates}")
        except Exception as e:
            print(f"    - [{strat_key}] StockInfo 원본 계산 오류: {e}")
            expected_results[strat_key] = {
                "expected_buy_dates": [],
                "expected_sell_dates": []
            }

    ground_truth_json = {
        "source": "StockInfo Legacy Strategy Engine Direct Execution",
        "symbol": fixture_json.get("symbol", "005930"),
        "name": fixture_json.get("name", "삼성전자"),
        "expected_results": expected_results
    }

    with open(GROUND_TRUTH_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(ground_truth_json, f, ensure_ascii=False, indent=2)

    print(f"\n==================================================")
    print(f" [StockInfo 정답지 생성을 완료하였습니다!]")
    print(f"   - 정답지 파일 경로: {GROUND_TRUTH_OUTPUT_PATH}")
    print(f"==================================================")


if __name__ == "__main__":
    generate_ground_truth()
