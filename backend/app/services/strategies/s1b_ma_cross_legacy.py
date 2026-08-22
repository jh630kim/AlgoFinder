"""
S1b: 레거시 확률 수식 연동 전략 모듈.

S1 이동평균선 골든크로스 신호 발생 시 상승 확신 확률(prob_up)이
55% 이상인 고확률 조건에서만 제한적으로 매수합니다.
"""

import pandas as pd
from backend.app.services.strategies.s1_ma_cross import S1MACrossStrategy


class S1bMACrossLegacyStrategy(S1MACrossStrategy):
    """
    S1b_MA_Cross_Legacy 퀀트 매매 전략 클래스.
    """

    def __init__(self, short_window: int = 5, long_window: int = 20, min_prob: float = 55.0) -> None:
        """
        S1bMACrossLegacyStrategy 초기화.

        :param short_window: 단기 이평 기간 (기본 5일)
        :param long_window: 장기 이평 기간 (기본 20일)
        :param min_prob: 최소 요구 상승 확률 (기본 55.0%)
        """
        super().__init__(short_window=short_window, long_window=long_window)
        self.min_prob = min_prob

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        S1b 전략 전용 확률 필터 이평선 계산 및 매수/매도 시그널 생성.

        :param df: 주가 데이터프레임
        :return: 시그널 및 prob_up이 추가된 데이터프레임
        """
        # 1. S1 이평선 지표 및 prob_up 렌더링
        df = super().calculate_indicators(df)

        # 2. 🟢 매수 신호: S1 매수 신호 AND 상승 확신 확률 55% 이상
        df['signal_buy'] = df['signal_buy'] & (df['prob_up'] >= self.min_prob)

        # 3. 🔴 매도 신호: S1 매도 신호 유지
        return df
