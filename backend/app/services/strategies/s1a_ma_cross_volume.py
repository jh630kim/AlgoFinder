"""
S1a: 거래량 150% 동반 이평 돌파 전략 모듈.

S1 이동평균선 골든크로스 신호에 당일 거래량이 5일 거래량 이평선(vol_sma5)의 150% 이상
동반 폭발할 때 매수하고, 데드크로스 또는 음봉 거래량 폭발 시 매도합니다.
"""

import pandas as pd
import numpy as np
from backend.app.services.strategies.s1_ma_cross import S1MACrossStrategy


class S1aMACrossVolumeStrategy(S1MACrossStrategy):
    """
    S1a_MA_Cross_Volume 퀀트 매매 전략 클래스.
    """

    def __init__(self, short_window: int = 5, long_window: int = 20, vol_mult: float = 1.5) -> None:
        """
        S1aMACrossVolumeStrategy 초기화.

        :param short_window: 단기 이평 기간 (기본 5일)
        :param long_window: 장기 이평 기간 (기본 20일)
        :param vol_mult: 거래량 폭발 기준 배수 (기본 1.5배)
        """
        super().__init__(short_window=short_window, long_window=long_window)
        self.vol_mult = vol_mult

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S1a 전략 전용 거래량 동반 이평선 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        # 1. S1 이평선 지표 렌더링
        df = super().calculate_indicators(df)

        # 2. 거래량 5일 이평 및 거래량 비율 계산 (핀포인트 연산)
        df['vol_sma5'] = self.calc_volume_sma(df, 5)
        df['vol_ratio'] = df['volume'] / (df['vol_sma5'] + 1e-6)

        # 3. 🟢 매수 신호: S1 매수 신호 AND 거래량 150% 이상 폭발
        volume_spike = df['volume'] >= (df['vol_sma5'] * self.vol_mult)
        df['signal_buy'] = df['signal_buy'] & volume_spike

        # 4. 🔴 매도 신호: S1 매도 신호 OR (당일 음봉 AND 거래량 150% 이상 폭발)
        bearish_volume_spike = (df['close_price'] < df['open_price']) & volume_spike
        df['signal_sell'] = df['signal_sell'] | bearish_volume_spike

        # 5. 거래량 폭발 가산점이 반영된 시그모이드 S자 prob_up
        diff_pct = (df['sma5'] - df['sma20']) / (df['sma20'] + 1e-6) * 100.0
        z_core = (diff_pct / 1.5) + ((df['vol_ratio'] - 1.0) / 0.5)
        z_investor = self.calc_investor_z_score(df)
        signal_bonus = np.where(df['signal_buy'], 1.2, 0.0)

        df['prob_up'] = self.calc_sigmoid_prob(z_core, pd.Series(z_investor, index=df.index), signal_bonus)
        return df
