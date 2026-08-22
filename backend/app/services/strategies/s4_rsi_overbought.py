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

        # 1. BaseStrategy 헬퍼에서 RSI(14) 단 1개 지표만 핀포인트 계산 (이평선, 볼린저 연산 무시)
        rsi, _, _, _ = self.calc_rsi(df, self.window)
        df['rsi14'] = rsi
        df['rsi14_prev'] = df.groupby('symbol')['rsi14'].shift(1)

        # 2. 🟢 매수 신호: 전일 RSI 30% 이하 ➔ 금일 RSI 30% 상향 탈출 AND 금일 양봉
        rsi_exit_oversold = (df['rsi14_prev'] <= self.oversold) & (df['rsi14'] > self.oversold)
        is_bullish = df['close_price'] >= df['open_price']
        df['signal_buy'] = rsi_exit_oversold & is_bullish

        # 3. 🔴 매도 신호: RSI 70% 이상 과매수 진입시
        df['signal_sell'] = df['rsi14'] >= self.overbought

        # 4. 수급 팩터 + 시그모이드 S자 AI 확신 확률 (prob_up) 계산
        z_core = (self.oversold - df['rsi14']) / 15.0
        z_investor = self.calc_investor_z_score(df)
        signal_bonus = np.where(df['signal_buy'], 1.0, 0.0)

        df['prob_up'] = self.calc_sigmoid_prob(z_core, pd.Series(z_investor, index=df.index), signal_bonus)
        return df
