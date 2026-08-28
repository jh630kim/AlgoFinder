"""
코스피 20일 이동평균선의 방향(상승/하락/횡보)을 판정하는 KospiRegimeAnalyzer 클래스 모듈.

투자제안 화면의 '📊 코스피 20일선' 배지에 쓰이며, 기준일 시점의 MA20 값과
5거래일 전 시점의 MA20 값을 비교해 20일선 자체가 상승 추세인지 하락 추세인지를 산출합니다.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.app.repositories.market_indices_repository import MarketIndicesRepository


class KospiRegimeAnalyzer:
    """코스피 종가 시계열에서 20일 이동평균선의 방향(장세)을 판정하는 서비스 클래스."""

    def __init__(self, session: Session) -> None:
        """
        KospiRegimeAnalyzer 초기화.

        :param session: SQLAlchemy 세션 객체
        """
        self.repo = MarketIndicesRepository(session)

    def analyze(
        self,
        target_date: str,
        ma_window: int = 20,
        lookback: int = 5,
        flat_threshold_pct: float = 0.3,
    ) -> Dict[str, Any]:
        """
        기준일 기준 코스피 20일 이동평균선의 방향을 판정해 반환합니다.

        :param target_date: 판정 기준일 (YYYYMMDD)
        :param ma_window: 이동평균 기간 (기본 20거래일)
        :param lookback: 비교 기준 과거 거래일 수 (기본 5거래일)
        :param flat_threshold_pct: 이 값(%) 이내 변화면 '횡보'로 판정 (기본 ±0.3%)
        :returns: available(bool), ma20, ma20_prev, diff, diff_pct,
                  regime('up'|'down'|'flat'), label, text, as_of, prev_date 를 담은 dict
        """
        need = ma_window + lookback
        series = self.repo.get_kospi_series(end_date=target_date, limit=need + 10)
        closes = [row["kospi_close"] for row in series]
        if len(closes) < need:
            return {"available": False, "text": "📊 코스피 20일선: -", "regime": ""}

        ma_now = sum(closes[-ma_window:]) / ma_window
        ma_prev = sum(closes[-(ma_window + lookback):-lookback]) / ma_window
        diff = ma_now - ma_prev
        diff_pct = (diff / ma_prev * 100.0) if ma_prev else 0.0

        regime, label = self._classify(diff_pct, flat_threshold_pct)
        return {
            "available": True,
            "ma20": round(ma_now, 1),
            "ma20_prev": round(ma_prev, 1),
            "diff": round(diff, 1),
            "diff_pct": round(diff_pct, 2),
            "regime": regime,
            "label": label,
            "text": self._format_text(ma_now, diff_pct, label),
            "as_of": series[-1]["date"],
            "prev_date": series[-(lookback + 1)]["date"],
        }

    @staticmethod
    def _classify(diff_pct: float, flat_threshold_pct: float) -> tuple:
        """MA20 변화율(%)을 상승/하락/횡보 국면과 표시 라벨로 변환합니다."""
        if diff_pct > flat_threshold_pct:
            return "up", "▲ 상승장"
        if diff_pct < -flat_threshold_pct:
            return "down", "▼ 하락장"
        return "flat", "➖ 횡보"

    @staticmethod
    def _format_text(ma_now: float, diff_pct: float, label: str) -> str:
        """배지에 그대로 노출할 한 줄 문자열을 생성합니다."""
        return f"📊 코스피 20일선: {ma_now:,.1f} (D-5 대비 {diff_pct:+.2f}% {label})"
