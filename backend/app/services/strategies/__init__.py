"""
퀀트 매매 전략 모듈 패키지.

S1 ~ S5 개별 퀀트 전략 클래스를 제공합니다.
"""

from backend.app.services.strategies.base_strategy import BaseStrategy
from backend.app.services.strategies.s1_ma_cross import S1MACrossStrategy
from backend.app.services.strategies.s1a_ma_cross_volume import S1aMACrossVolumeStrategy
from backend.app.services.strategies.s1b_ma_cross_legacy import S1bMACrossLegacyStrategy
from backend.app.services.strategies.s1c_ma_cross_adaptive import S1cMACrossAdaptiveStrategy
from backend.app.services.strategies.s2_breakout import S2BreakoutStrategy
from backend.app.services.strategies.s3_bollinger import S3BollingerStrategy
from backend.app.services.strategies.s4_rsi_overbought import S4RSIStrategy
from backend.app.services.strategies.s5_candle_patterns import S5CandlePatternsStrategy

__all__ = [
    "BaseStrategy",
    "S1MACrossStrategy",
    "S1aMACrossVolumeStrategy",
    "S1bMACrossLegacyStrategy",
    "S1cMACrossAdaptiveStrategy",
    "S2BreakoutStrategy",
    "S3BollingerStrategy",
    "S4RSIStrategy",
    "S5CandlePatternsStrategy",
]
