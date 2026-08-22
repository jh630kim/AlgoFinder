"""
S2: RSI 및 이격도 돌파 전략 모듈.

14일 RSI 지표가 9일 Signal 이평을 상향 돌파(골든크로스)하고,
최근 5일간 최저 RSI가 35% 이하(눌림목) 형성 후 반등할 때 매수합니다.
"""

import pandas as pd
import numpy as np
from backend.app.services.strategies.base_strategy import BaseStrategy


class S2BreakoutStrategy(BaseStrategy):
    """
    S2_Breakout 퀀트 매매 전략 클래스.
    """

    def __init__(self, rsi_period: int = 14, signal_period: int = 9) -> None:
        """
        S2BreakoutStrategy 초기화.

        :param rsi_period: RSI 산출 기간 (기본 14일)
        :param signal_period: Signal 이평 기간 (기본 9일)
        """
        self.rsi_period = rsi_period
        self.signal_period = signal_period

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S2 전략 전용 RSI 핀포인트 지표 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        df = df.copy()

        # 1. BaseStrategy 헬퍼에서 RSI 관련 핀포인트 계산 (이평선, 볼린저 연산 무시)
        rsi, signal, rsi_min5, rsi_max5 = self.calc_rsi(df, self.rsi_period, self.signal_period)
        df['rsi'] = rsi
        df['signal'] = signal
        df['rsi_min5'] = rsi_min5
        df['rsi_max5'] = rsi_max5

        df['rsi_prev'] = df.groupby('symbol')['rsi'].shift(1)
        df['signal_prev'] = df.groupby('symbol')['signal'].shift(1)

        # 2. 🟢 매수 신호: RSI ↔ Signal 골든크로스 AND 최근 5일 내 RSI <= 35/30 눌림목 형성 후 반등
        rsi_golden_cross = (df['rsi'] > df['signal']) & (df['rsi_prev'] <= df['signal_prev'])
        oversold_pullback = (df['rsi_prev'] <= 35) | (df['rsi_min5'] <= 30)
        df['signal_buy'] = rsi_golden_cross & oversold_pullback

        # 3. 🔴 매도 신호: 과매수(65/70 이상) 진입 후 RSI ↔ Signal 데드크로스 하향 이탈
        rsi_dead_cross = (df['rsi'] < df['signal']) & (df['rsi_prev'] >= df['signal_prev'])
        overbought_exit = (df['rsi_prev'] >= 65) | (df['rsi_max5'] >= 70)
        df['signal_sell'] = rsi_dead_cross & overbought_exit

        # 4. 수급 팩터 + 시그모이드 S자 AI 확신 확률 (prob_up) 계산
        z_core = (df['rsi'] - 50.0) / 15.0
        z_investor = self.calc_investor_z_score(df)
        signal_bonus = np.where(df['signal_buy'], 1.2, 0.0)

        df['prob_up'] = self.calc_sigmoid_prob(z_core, pd.Series(z_investor, index=df.index), signal_bonus)
        return df
