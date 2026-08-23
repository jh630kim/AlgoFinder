"""
퀀트 전략 공통 추상 클래스 및 지표 계산 도구함 모듈.

모든 S1 ~ S5 전략 클래스가 상속하는 BaseStrategy 및 재사용 가능한 지표 헬퍼 메서드,
주체별 수급 Z-Score 팩터 및 시그모이드 S자 확신 확률(prob_up) 변환 엔진을 정의합니다.
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    """
    퀀트 매매 전략 공통 BaseStrategy 추상 클래스.
    """

    def calc_sma(self, df: pd.DataFrame, window: int) -> pd.Series:
        """
        종가(close_price) 단순이동평균(SMA) 롤링 연산 헬퍼.

        :param df: 주가 데이터프레임
        :param window: 이동평균 기간
        :return: 종목별 이동평균 Series
        """
        return df.groupby('symbol')['close_price'].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )

    def calc_volume_sma(self, df: pd.DataFrame, window: int = 5) -> pd.Series:
        """
        거래량(volume) 단순이동평균 롤링 연산 헬퍼.

        :param df: 주가 데이터프레임
        :param window: 이동평균 기간
        :return: 종목별 거래량 이동평균 Series
        """
        return df.groupby('symbol')['volume'].transform(
            lambda x: x.rolling(window, min_periods=1).mean()
        )

    def calc_rsi(self, df: pd.DataFrame, window: int = 14, signal_window: int = 9) -> tuple:
        """
        14일 RSI 및 9일 Signal EMA, 5일 최저/최고 RSI 연산 헬퍼.

        :param df: 주가 데이터프레임
        :param window: RSI 기간 (기본 14일)
        :param signal_window: Signal EMA 기간 (기본 9일)
        :return: (rsi, rsi_signal, rsi_min5, rsi_max5) 튜플
        """
        delta = df.groupby('symbol')['close_price'].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.groupby(df['symbol']).transform(
            lambda x: x.rolling(window, min_periods=window).mean()
        )
        avg_loss = loss.groupby(df['symbol']).transform(
            lambda x: x.rolling(window, min_periods=window).mean()
        )

        rs = avg_gain / (avg_loss + 1e-6)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        rsi_signal = rsi.groupby(df['symbol']).transform(
            lambda x: x.ewm(span=signal_window, adjust=False).mean()
        )
        rsi_min5 = rsi.groupby(df['symbol']).transform(
            lambda x: x.rolling(5, min_periods=1).min()
        )
        rsi_max5 = rsi.groupby(df['symbol']).transform(
            lambda x: x.rolling(5, min_periods=1).max()
        )

        return rsi, rsi_signal, rsi_min5, rsi_max5

    def calc_bollinger(self, df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> tuple:
        """
        볼린저 밴드(MB, UB, LB) 및 밴드폭(Bandwidth), 20일 최저 밴드폭 연산 헬퍼.

        :param df: 주가 데이터프레임
        :param window: 밴드 중심선 기간 (기본 20일)
        :param num_std: 표준편차 승수 (기본 2.0)
        :return: (bb_mb, bb_ub, bb_lb, bb_bandwidth, min_bw20) 튜플
        """
        mb = self.calc_sma(df, window)
        std = df.groupby('symbol')['close_price'].transform(
            lambda x: x.rolling(window, min_periods=1).std(ddof=0)
        )
        ub = mb + (num_std * std)
        lb = mb - (num_std * std)
        bandwidth = (ub - lb) / (mb + 1e-6)
        min_bw20 = bandwidth.groupby(df['symbol']).transform(
            lambda x: x.rolling(window, min_periods=1).min()
        )
        return mb, ub, lb, bandwidth, min_bw20

    def calc_investor_z_score(self, df: pd.DataFrame) -> pd.Series:
        """
        주체별 수급 모멘텀 Z-Score 연산 헬퍼.
        기관+외국인 3일 연속 동시 순매수 포착 시 +1.5, 대량 동시 매도시 -1.5 반환.

        :param df: 주가 및 수급 데이터프레임
        :return: 수급 Z-Score Series
        """
        inst = df['institution_net_buy'].fillna(0.0) if 'institution_net_buy' in df.columns else pd.Series(0.0, index=df.index)
        foreign = df['foreigner_net_buy'].fillna(0.0) if 'foreigner_net_buy' in df.columns else pd.Series(0.0, index=df.index)

        inst_prev = inst.groupby(df['symbol']).shift(1).fillna(0.0)
        foreign_prev = foreign.groupby(df['symbol']).shift(1).fillna(0.0)

        dual_buy = (inst > 0) & (foreign > 0) & (inst_prev > 0) & (foreign_prev > 0)
        dual_sell = (inst < 0) & (foreign < 0) & (inst_prev < 0) & (foreign_prev < 0)

        z_inv = np.where(dual_buy, 1.5, np.where(dual_sell, -1.5, 0.0))
        return pd.Series(z_inv, index=df.index)

    def calc_sigmoid_prob(
        self, z_core: pd.Series, z_investor: pd.Series, signal_bonus: float = 0.0
    ) -> pd.Series:
        """
        시그모이드(Sigmoid) S자 확신 확률(10.0% ~ 90.0%) 변환 연산 엔진.

        :param z_core: 핵심 기술적 지표 Z-Score
        :param z_investor: 수급 모멘텀 Z-Score
        :param signal_bonus: 매수 신호 포착 가산점
        :return: prob_up (10.0% ~ 90.0% 정규화 Series)
        """
        z_total = (0.6 * z_core.fillna(0.0)) + (0.4 * z_investor.fillna(0.0)) + signal_bonus
        prob = 10.0 + (80.0 / (1.0 + np.exp(-0.8 * z_total)))
        prob = np.nan_to_num(prob, nan=50.0)
        return np.round(np.clip(prob, 10.0, 90.0), 1)

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        각 개별 전략 클래스에서 필요한 핀포인트 헬퍼만 호출하여 지표 및 시그널 구현.

        :param df: 원천 주가 및 수급 데이터프레임
        :return: indicator, signal_buy, signal_sell, prob_up 이 반영된 데이터프레임
        """
        pass
