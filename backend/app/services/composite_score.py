"""
순수관행 합성 점수 서비스 모듈 (composite_score.py).

OHLCV(+지수)만으로 (종목, 날짜)별 횡단면 팩터 합성 점수·백분위·등수를 산출하는
CompositeScorer 클래스를 정의한다. 수급·재무는 쓰지 않는다.

절차([순수관행.md] §3-1·§3-2):
  1) 팩터 패밀리별 원값 계산(종목별 시계열)
  2) 날짜별 횡단면 윈저라이즈(1/99) → z-score → 섹터 중립화
  3) 패밀리 균등 가중합 → 합성 점수 → 날짜별 백분위(0~100)·등수(1=최상위)

12-1개월 모멘텀은 데이터 창이 짧을 때 결측이 커서 6-1개월(126-21거래일)로 사용한다.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 패밀리 가중치(균등 고정, 단기역추세만 낮게)
FAMILY_WEIGHTS = {"momentum": 1.0, "trend": 1.0, "lowvol": 1.0, "volume": 1.0, "reversal": 0.1}
PRICE_FLOOR = 1000.0          # 동전주 배제
MIN_TURNOVER = 3.0e8          # 20일 평균 거래대금 하한(3억)


class CompositeScorer:
    """OHLCV 기반 횡단면 합성 점수·등수를 산출하는 서비스 클래스."""

    def __init__(self, weights: dict = None) -> None:
        """
        :param weights: 패밀리 가중치 오버라이드(None이면 FAMILY_WEIGHTS)
        """
        self.weights = dict(weights or FAMILY_WEIGHTS)

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        시세 데이터프레임에 합성 점수 컬럼을 붙여 반환합니다.

        :param df: symbol, date, open_price, high_price, low_price, close_price, volume,
                   (선택) sector 컬럼을 가진 DataFrame
        :return: 입력 + [composite_score, composite_pct, composite_rank, cs_eligible] 컬럼
        """
        if df is None or df.empty:
            return df
        d = df.sort_values(["symbol", "date"]).reset_index(drop=True).copy()
        if "sector" not in d.columns:
            d["sector"] = "ALL"

        fac = self._raw_factors(d)                    # {family: Series}
        z_sum = None
        for fam, raw in fac.items():
            z = self._cross_sectional_z(d, raw)      # 날짜별 윈저·z
            z = self._sector_neutralize(d, z)        # 날짜별 섹터 평균 차감
            w = float(self.weights.get(fam, 0.0))
            z_sum = (w * z) if z_sum is None else (z_sum + w * z)

        d["composite_score"] = z_sum.fillna(0.0)
        d["cs_eligible"] = self._eligibility(d)
        # 부적격 종목은 랭킹에서 바닥으로
        d.loc[~d["cs_eligible"], "composite_score"] = -9.99e9
        d["composite_pct"] = d.groupby("date")["composite_score"].rank(pct=True) * 100.0
        d["composite_rank"] = d.groupby("date")["composite_score"].rank(
            ascending=False, method="first"
        ).astype("Int64")
        d.loc[~d["cs_eligible"], ["composite_pct", "composite_rank"]] = [np.nan, pd.NA]
        return d

    # ---- 내부 헬퍼 ---------------------------------------------------------

    def _raw_factors(self, d: pd.DataFrame) -> dict:
        """팩터 패밀리별 원값 Series를 계산합니다(높을수록 매력적 롱)."""
        g = d.groupby("symbol")
        c = d["close_price"]
        ret1 = g["close_price"].pct_change()
        sma60 = g["close_price"].transform(lambda x: x.rolling(60, min_periods=20).mean())
        sma120 = g["close_price"].transform(lambda x: x.rolling(120, min_periods=40).mean())
        # 모멘텀: 6-1개월 수익률 + 장기선 이격
        mom_6_1 = g["close_price"].transform(lambda x: x.shift(21) / x.shift(126) - 1.0)
        mom_gap = c / sma120 - 1.0
        momentum = mom_6_1.fillna(0.0) + mom_gap.fillna(0.0)
        # 추세 품질: 60일 상승마감일 비율
        trend = g["close_price"].transform(
            lambda x: (x.diff() > 0).rolling(60, min_periods=20).mean()
        )
        # 저변동성: 60일 수익률 표준편차의 음수
        lowvol = -ret1.groupby(d["symbol"]).transform(
            lambda x: x.rolling(60, min_periods=20).std()
        )
        # 거래량 확인: OBV 20일 변화량 / 20일 평균 거래량
        obv = (np.sign(g["close_price"].diff().fillna(0.0)) * d["volume"]).groupby(
            d["symbol"]
        ).cumsum()
        vol20 = g["volume"].transform(lambda x: x.rolling(20, min_periods=5).mean())
        volume = (obv - obv.groupby(d["symbol"]).shift(20)) / (vol20 + 1.0)
        # 단기 역추세: 최근 5일 수익률의 음수
        reversal = -g["close_price"].transform(lambda x: x.pct_change(5))
        return {
            "momentum": momentum, "trend": trend.fillna(0.0), "lowvol": lowvol.fillna(0.0),
            "volume": volume.fillna(0.0), "reversal": reversal.fillna(0.0),
        }

    @staticmethod
    def _cross_sectional_z(d: pd.DataFrame, raw: pd.Series) -> pd.Series:
        """날짜별로 1/99 윈저라이즈 후 z-score를 계산합니다."""
        s = pd.Series(raw, index=d.index).astype(float)
        by = s.groupby(d["date"])
        lo = by.transform(lambda x: x.quantile(0.01))
        hi = by.transform(lambda x: x.quantile(0.99))
        w = s.clip(lower=lo, upper=hi)
        mu = w.groupby(d["date"]).transform("mean")
        sd = w.groupby(d["date"]).transform("std").replace(0.0, np.nan)
        return ((w - mu) / sd).fillna(0.0)

    @staticmethod
    def _sector_neutralize(d: pd.DataFrame, z: pd.Series) -> pd.Series:
        """날짜×섹터 평균을 빼 업종 편중을 제거합니다."""
        key = [d["date"], d["sector"]]
        return z - z.groupby(key).transform("mean")

    @staticmethod
    def _eligibility(d: pd.DataFrame) -> pd.Series:
        """유동성·가격 하한 + 최근 거래정지 아님 적격 마스크."""
        g = d.groupby("symbol")
        turnover = (d["close_price"] * d["volume"]).groupby(d["symbol"]).transform(
            lambda x: x.rolling(20, min_periods=5).mean()
        )
        suspended = (d["volume"].fillna(0) == 0) & (d["high_price"] == d["low_price"])
        return (d["close_price"] >= PRICE_FLOOR) & (turnover >= MIN_TURNOVER) & (~suspended)
