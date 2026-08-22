"""
S5: 캔들 패턴 및 거래량 수급 전략 모듈.

아랫꼬리가 긴 망치형 캔들(Hammer) 또는 180% 이상 거래량이 폭발한 대량거래 장대양봉을 포착하여 매수하고,
유성형 캔들 또는 거래량 폭발 장대음봉 발생 시 매도합니다.
"""

import pandas as pd
import numpy as np
from backend.app.services.strategies.base_strategy import BaseStrategy


class S5CandlePatternsStrategy(BaseStrategy):
    """
    S5_Candle_Patterns 퀀트 매매 전략 클래스.
    """

    def __init__(self, window: int = 20) -> None:
        """
        S5CandlePatternsStrategy 초기화.

        :param window: 거래량 이평 기간 (기본 20일)
        """
        self.window = window

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S5 전략 전용 캔들 패턴 핀포인트 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        df = df.copy()

        # 1. 거래량 20일 이평 핀포인트 연산
        df['vma20'] = self.calc_volume_sma(df, self.window)

        open_p = df['open_price']
        close_p = df['close_price']
        high_p = df['high_price']
        low_p = df['low_price']

        body = (close_p - open_p).abs()
        body = np.where(body <= 0, 1.0, body)
        lower_wick = np.minimum(open_p, close_p) - low_p
        upper_wick = high_p - np.maximum(open_p, close_p)

        # 2. 🟢 매수 신호 (망치형 캔들 OR 거래량 1.8배 동반 장대양봉)
        is_hammer = (lower_wick >= 1.8 * body) & (upper_wick <= 0.4 * body) & (close_p >= open_p)
        is_bull_spike = ((close_p - open_p) / open_p >= 0.025) & (df['volume'] >= 1.8 * df['vma20'])
        df['signal_buy'] = is_hammer | is_bull_spike

        # 3. 🔴 매도 신호 (유성형 캔들 OR 거래량 급증 장대음봉)
        is_shooting_star = (upper_wick >= 1.8 * body) & (lower_wick <= 0.4 * body) & (open_p >= close_p)
        is_bear_spike = ((open_p - close_p) / open_p >= 0.025) & (df['volume'] >= 1.5 * df['vma20'])
        df['signal_sell'] = is_shooting_star | is_bear_spike

        # 4. 수급 팩터 + 시그모이드 S자 AI 확신 확률 (prob_up) 계산
        vol_ratio = df['volume'] / (df['vma20'] + 1e-6)
        z_core = (vol_ratio - 1.0) / 0.6
        z_investor = self.calc_investor_z_score(df)
        signal_bonus = np.where(is_hammer, 1.3, np.where(is_bull_spike, 1.5, 0.0))

        df['prob_up'] = self.calc_sigmoid_prob(z_core, pd.Series(z_investor, index=df.index), signal_bonus)
        return df
