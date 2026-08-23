"""
S4: RSI 과매도 탈출 전략 모듈.

RSI(14) 수치가 30% 이하 과매도 구간에 진입했다가 30% 선을 위로 상향 탈출할 때 매수하고,
RSI(14)가 70% 이상 과매수 구간에 진입할 때 매도합니다.
"""

import pandas as pd
import numpy as np
from backend.app.services.strategies.base_strategy import BaseStrategy


class S4RSIStrategy(BaseStrategy):
    """
    S4_RSI_Overbought 퀀트 매매 전략 클래스.
    """

    def __init__(self, window: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> None:
        """
        S4RSIStrategy 초기화.

        :param window: RSI 산출 기간 (기본 14일)
        :param oversold: 과매도 매수 기준선 (기본 30.0%)
        :param overbought: 과매수 매도 기준선 (기본 70.0%)
        """
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S4 전략 전용 RSI(14) 핀포인트 지표 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        df = df.copy()

        # 1. BaseStrategy 헬퍼에서 RSI(14) 및 Signal(9일 이평) 핀포인트 계산
        rsi, signal, rsi_min5, rsi_max5 = self.calc_rsi(df, self.window, 9)
        df['rsi14'] = rsi
        df['signal'] = signal
        df['rsi14_prev'] = df.groupby('symbol')['rsi14'].shift(1)
        df['signal_prev'] = df.groupby('symbol')['signal'].shift(1)

        # 2. 💙 S4 표준 전략: 30% 과매도선 상향 탈출 매수 / 70% 과매수 영역 진입 매도
        rsi_exit_oversold = (df['rsi14_prev'] <= self.oversold) & (df['rsi14'] > self.oversold)
        is_bullish = df['close_price'] >= df['open_price']
        df['signal_buy'] = rsi_exit_oversold & is_bullish

        rsi_enter_overbought = (df['rsi14_prev'] < self.overbought) & (df['rsi14'] >= self.overbought)
        df['signal_sell'] = rsi_enter_overbought

        # 3. ⚡ S4a Signal 교차 전략: 과매도(30/35% 이하) 후 9일선 1.5%p 상향 돌파 / 과매수 후 9일선 하향 이탈
        rsi_diff = df['rsi14'] - df['signal']
        rsi_golden_cross = (rsi_diff >= 1.5) & (df['rsi14_prev'] <= df['signal_prev'])
        oversold_pullback = (df['rsi14_prev'] <= 35.0) | (rsi_min5 <= 30.0)
        df['signal_buy_s4a'] = rsi_golden_cross & oversold_pullback

        rsi_dead_cross = (df['rsi14'] < df['signal']) & (df['rsi14_prev'] >= df['signal_prev'])
        overbought_exit = (df['rsi14_prev'] >= 65.0) | (rsi_max5 >= 70.0)
        df['signal_sell_s4a'] = rsi_dead_cross & overbought_exit

        # 4. 수급 팩터 + 시그모이드 S자 AI 확신 확률 (prob_up) 계산
        z_core = (self.oversold - df['rsi14']) / 15.0
        z_investor = self.calc_investor_z_score(df)
        signal_bonus = np.where(df['signal_buy'], 1.0, 0.0)

        df['prob_up'] = self.calc_sigmoid_prob(z_core, pd.Series(z_investor, index=df.index), signal_bonus)
        return df
