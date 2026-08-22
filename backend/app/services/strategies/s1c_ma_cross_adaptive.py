"""
S1c: 20일선 추세 적응형 듀얼 전략 모듈.

20일 이동평균선(sma20)이 3일 전 대비 상승 추세이면 S1b(확률 필터 방식)를 적용하고,
횡보 및 하락 추세이면 S1a(거래량 필터 방식)를 적응형으로 스위칭하여 매매합니다.
"""

import pandas as pd
import numpy as np
from backend.app.services.strategies.base_strategy import BaseStrategy
from backend.app.services.strategies.s1a_ma_cross_volume import S1aMACrossVolumeStrategy
from backend.app.services.strategies.s1b_ma_cross_legacy import S1bMACrossLegacyStrategy


class S1cMACrossAdaptiveStrategy(BaseStrategy):
    """
    S1c_MA_Cross_Adaptive 퀀트 매매 전략 클래스.
    """

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        """
        S1cMACrossAdaptiveStrategy 초기화.

        :param short_window: 단기 이평 기간 (기본 5일)
        :param long_window: 장기 이평 기간 (기본 20일)
        """
        self.short_window = short_window
        self.long_window = long_window
        self.s1a_engine = S1aMACrossVolumeStrategy(short_window=short_window, long_window=long_window)
        self.s1b_engine = S1bMACrossLegacyStrategy(short_window=short_window, long_window=long_window)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S1c 전략 전용 적응형 듀얼 지표 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        df_s1a = self.s1a_engine.calculate_indicators(df)
        df_s1b = self.s1b_engine.calculate_indicators(df)

        df_res = df_s1a.copy()

        # 20일선 기울기 판단 (3일 전 대비 상승 여부)
        sma20_prev3 = df_res.groupby('symbol')['sma20'].shift(3)
        is_uptrend = df_res['sma20'] > sma20_prev3

        # 🟢 매수 신호: 상승 추세 ➔ S1b 매수, 횡보/하락 추세 ➔ S1a 매수
        df_res['signal_buy'] = np.where(is_uptrend, df_s1b['signal_buy'], df_s1a['signal_buy'])

        # 🔴 매도 신호: 상승 추세 ➔ S1b 매도, 횡보/하락 추세 ➔ S1a 매도
        df_res['signal_sell'] = np.where(is_uptrend, df_s1b['signal_sell'], df_s1a['signal_sell'])

        # AI 확신 확률: 상승 추세시 S1b prob_up, 횡보시 S1a prob_up
        df_res['prob_up'] = np.where(is_uptrend, df_s1b['prob_up'], df_s1a['prob_up'])

        return df_res
