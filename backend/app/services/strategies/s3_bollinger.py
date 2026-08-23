"""
S3: 볼린저 밴드 반등 & 스퀴즈 돌파 전략 모듈.

볼린저 밴드(20, 2.0) 밴드폭이 0.14 이하로 극심하게 수축(스퀴즈) 후 상한선 폭발 돌파 시 매수하거나,
하한선(LB) 터치 후 양봉 반등 시 매수하고 상한선 도달 시 매도합니다.
"""

import pandas as pd
import numpy as np
from backend.app.services.strategies.base_strategy import BaseStrategy


class S3BollingerStrategy(BaseStrategy):
    """
    S3_Bollinger 퀀트 매매 전략 클래스.
    """

    def __init__(self, window: int = 20, num_std: float = 2.0) -> None:
        """
        S3BollingerStrategy 초기화.

        :param window: 볼린저 밴드 중심선 기간 (기본 20일)
        :param num_std: 표준편차 승수 (기본 2.0)
        """
        self.window = window
        self.num_std = num_std

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S3 전략 전용 볼린저 밴드 핀포인트 지표 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        df = df.copy()

        # 1. BaseStrategy 헬퍼에서 볼린저 밴드 핀포인트 계산 (RSI, 60일 이평 연산 무시)
        mb, ub, lb, bandwidth, min_bw20 = self.calc_bollinger(df, self.window, self.num_std)
        df['bb_mb'] = mb
        df['bb_ub'] = ub
        df['bb_lb'] = lb
        df['bandwidth'] = bandwidth
        df['min_bandwidth_20d'] = min_bw20

        df['close_prev'] = df.groupby('symbol')['close_price'].shift(1)
        df['bb_ub_prev'] = df.groupby('symbol')['bb_ub'].shift(1)
        df['bb_lb_prev'] = df.groupby('symbol')['bb_lb'].shift(1)

        # 2. 🌸 S3 일반 반등 매수/매도 (표준 평균회귀: 하한선 이탈 후 복귀 양봉 / 상한선 진입 후 복귀 음봉)
        lower_rebound = (df['close_prev'] <= df['bb_lb_prev']) & (df['close_price'] > df['bb_lb']) & (df['close_price'] > df['close_prev'])
        upper_reversal = (df['close_prev'] >= df['bb_ub_prev']) & (df['close_price'] < df['bb_ub']) & (df['close_price'] < df['close_prev'])

        df['signal_buy'] = lower_rebound
        df['signal_sell'] = upper_reversal

        # 3. 💥 S3a 스퀴즈 폭발 돌파 매수/매도 (20일 최저 밴드폭 0.14 이하 수축 후 상한선 돌파)
        squeeze_breakout = (df['min_bandwidth_20d'] <= 0.14) & (df['close_price'] > df['bb_ub']) & (df['close_prev'] <= df['bb_ub_prev'])
        mb_breakdown = (df['close_prev'] >= df['bb_mb']) & (df['close_price'] < df['bb_mb'])

        df['signal_buy_s3a'] = squeeze_breakout
        df['signal_sell_s3a'] = mb_breakdown & (~squeeze_breakout)

        # 4. 수급 팩터 + 시그모이드 S자 AI 확신 확률 (prob_up) 계산
        pct_b = (df['close_price'] - df['bb_lb']) / (df['bb_ub'] - df['bb_lb'] + 1e-6)
        z_core = (50.0 - (pct_b * 100.0)) / 25.0
        z_investor = self.calc_investor_z_score(df)
        signal_bonus = np.where(df['signal_buy'], 1.1, 0.0)

        df['prob_up'] = self.calc_sigmoid_prob(z_core, pd.Series(z_investor, index=df.index), signal_bonus)
        return df
