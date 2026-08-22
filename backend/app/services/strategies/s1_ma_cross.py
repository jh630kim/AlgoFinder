"""
S1: 이동평균선 골든크로스 & 60일선 정배열 추세 전략 모듈.

5일 종가 이평선(sma5)이 20일 종가 이평선(sma20)을 상향 돌파(골든크로스)하고
주가가 60일 이평선(sma60) 상단에 위치한 정배열 추세 종목을 포착합니다.
"""

import pandas as pd
import numpy as np
from backend.app.services.strategies.base_strategy import BaseStrategy


class S1MACrossStrategy(BaseStrategy):
    """
    S1_MA_Cross 퀀트 매매 전략 클래스.
    """

    def __init__(self, short_window: int = 5, long_window: int = 20, trend_window: int = 60) -> None:
        """
        S1MACrossStrategy 초기화.

        :param short_window: 단기 이평 기간 (기본 5일)
        :param long_window: 장기 이평 기간 (기본 20일)
        :param trend_window: 추세 판단 이평 기간 (기본 60일)
        """
        self.short_window = short_window
        self.long_window = long_window
        self.trend_window = trend_window

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S1 전략 전용 이평선 핀포인트 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        df = df.copy()

        # 1. BaseStrategy 지표 헬퍼로부터 필요한 이평선만 핀포인트 계산 (RSI, 볼린저 연산 무시)
        df['sma5'] = self.calc_sma(df, self.short_window)
        df['sma20'] = self.calc_sma(df, self.long_window)
        df['sma60'] = self.calc_sma(df, self.trend_window)

        df['sma5_prev'] = df.groupby('symbol')['sma5'].shift(1)
        df['sma20_prev'] = df.groupby('symbol')['sma20'].shift(1)

        # 2. 🟢 골든크로스 매수 신호 (sma5 > sma20 및 전일 sma5 <= sma20) AND 60일선 상단 정배열
        golden_cross = (df['sma5'] > df['sma20']) & (df['sma5_prev'] <= df['sma20_prev'])
        uptrend_60d = df['close_price'] > df['sma60']
        df['signal_buy'] = golden_cross & uptrend_60d

        # 3. 🔴 데드크로스 매도 신호 (sma5 < sma20 및 전일 sma5 >= sma20)
        dead_cross = (df['sma5'] < df['sma20']) & (df['sma5_prev'] >= df['sma20_prev'])
        df['signal_sell'] = dead_cross

        # 4. 수급 팩터 + 시그모이드 S자 AI 확신 확률 (prob_up) 계산
        diff_pct = (df['sma5'] - df['sma20']) / (df['sma20'] + 1e-6) * 100.0
        z_core = diff_pct / 1.5
        z_investor = self.calc_investor_z_score(df)
        signal_bonus = np.where(df['signal_buy'], 1.0, 0.0)

        df['prob_up'] = self.calc_sigmoid_prob(z_core, pd.Series(z_investor, index=df.index), signal_bonus)
        return df
