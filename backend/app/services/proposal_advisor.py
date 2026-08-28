"""
투자제안 화면 데이터 조립 서비스 모듈 (proposal_advisor.py).

기준일 종가(D-0) 기준으로 S1~S5(8전략) 매수 신호를 산출해 전략별 TOP N 추천을 만들고,
보유 종목에 대해 매도 신호(전략 매도신호 / -5% 손절 / +10% 익절)를 판정하는 ProposalAdvisor 클래스.
"""

import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from backend.app.models.all_stock_master import AllStockMaster
from backend.app.services.backtest_engine import BacktestEngine, STRATEGY_MAP

logger = logging.getLogger(__name__)

TARGET_SECTORS = ["KOSPI 200", "KOSDAQ 150"]
STOP_LOSS_PCT = -5.0
TAKE_PROFIT_PCT = 10.0

STRATEGY_LABELS = {
    "S1": "🔵 S1 골든크로스", "S1a": "🔵 S1a 거래량 필터형", "S1b": "🟣 S1b 원본 수식형",
    "S1c": "🟡 S1c 20일선 적응형", "S2": "🟢 S2 눌림목 돌파", "S3": "🟠 S3 볼린저 밴드",
    "S4": "🔴 S4 RSI 과매수", "S5": "🕯️ S5 캔들 패턴",
}
STRATEGY_BUY_REASON = {
    "S1": "5/20일 골든크로스 및 60일선 정배열 추세 포착",
    "S1a": "골든크로스 + 거래량 급증 동시 충족",
    "S1b": "골든크로스 및 승률 Z-Score 기준 매수 조건 충족",
    "S1c": "20일선 추세 적응형 매수 타점 포착",
    "S2": "과매도 눌림목 이후 상방 돌파 포착",
    "S3": "볼린저 밴드 하단 반등 또는 밴드 수축 후 돌파 포착",
    "S4": "RSI 과매도 구간 반등 포착",
    "S5": "거래량 동반 반전 캔들 패턴 포착",
}


class ProposalAdvisor:
    """투자제안 추천/매도신호/포트폴리오 평가 데이터를 조립하는 서비스 클래스."""

    def __init__(self, session: Session) -> None:
        """세션 및 내부 캐시를 초기화합니다.

        :param session: SQLAlchemy DB 세션
        """
        self.session = session
        self._engine = BacktestEngine(session)
        self._loaded_for = None
        self._df = None
        self._eff_date = None
        self._processed: Dict[str, Any] = {}
        self._market_map: Dict[str, str] = {}

    def load(self, target_date: str) -> None:
        """기준일 시세 데이터를 로딩·캐싱합니다(공유 캐시 등 외부에서 쓰는 공개 진입점)."""
        self._load(target_date)

    def _load(self, target_date: str) -> None:
        """기준일(YYYYMMDD)까지의 시세 데이터 및 평가 기준 거래일을 1회 로딩·캐싱합니다."""
        if self._loaded_for == target_date:
            return
        self._loaded_for = target_date
        self._processed = {}
        self._eff_date = None
        self._df = self._engine.load_market_dataframe(TARGET_SECTORS, target_date, target_date)
        if self._df is None or self._df.empty:
            return
        avail = sorted(d for d in self._df["date"].unique() if d <= target_date)
        self._eff_date = avail[-1] if avail else None
        codes = set(self._df["symbol"].unique())
        rows = self.session.query(AllStockMaster.code, AllStockMaster.market).filter(
            AllStockMaster.code.in_(codes)
        ).all()
        self._market_map = {c: m for c, m in rows}

    def _processed_df(self, key: str):
        """전략별 지표·시그널 연산 결과를 캐싱해 반환합니다."""
        if key not in self._processed:
            self._processed[key] = STRATEGY_MAP[key].calculate_indicators(self._df)
        return self._processed[key]

    def _sell_rows_for(self, key: str, held: set):
        """보유 종목의 기준일 매도 신호 행을 반환합니다(연산량 축소).

        추천 계산이 이미 전체 종목 지표를 캐싱했으면 그대로 재사용하고, 아니면
        보유 종목만으로 지표를 연산합니다. 지표는 종목별 롤링이라 대상 종목만
        추려도 개별 결과는 전체 연산과 동일합니다.

        :param key: 전략 키(S1~S5)
        :param held: 보유 종목코드 집합
        :return: signal_sell=True 인 기준일 행 DataFrame
        """
        pdf = self._processed.get(key)
        if pdf is None:
            subset = self._df[self._df["symbol"].isin(held)]
            pdf = STRATEGY_MAP[key].calculate_indicators(subset)
        return pdf[(pdf["date"] == self._eff_date) & (pdf["signal_sell"].fillna(False))]

    def get_recommendations(self, target_date: str, top_n: int = 3) -> Dict[str, Any]:
        """기준일 종가 기준 8전략 각각의 매수 신호 TOP N 추천 목록을 반환합니다.

        :param target_date: 추천 기준일 (YYYYMMDD)
        :param top_n: 전략별 상위 노출 개수
        :return: {target_date, eval_date, data:[{code,name,market,strategy,strategy_name,prob_up,close_price,reason}]}
        """
        self._load(target_date)
        if not self._eff_date:
            return {"target_date": target_date, "eval_date": None, "data": []}

        out = []
        for key in STRATEGY_MAP:
            pdf = self._processed_df(key)
            day = pdf[(pdf["date"] == self._eff_date) & (pdf["signal_buy"].fillna(False))]
            day = day.sort_values("prob_up", ascending=False).head(top_n)
            for _, r in day.iterrows():
                out.append({
                    "code": r["symbol"],
                    "name": str(r.get("name") or r["symbol"]),
                    "market": self._market_map.get(r["symbol"], ""),
                    "strategy": key,
                    "strategy_name": STRATEGY_LABELS.get(key, key),
                    "prob_up": round(float(r.get("prob_up", 50.0)), 1),
                    "close_price": int(round(float(r["close_price"]))),
                    "reason": STRATEGY_BUY_REASON.get(key, "매수 신호 포착"),
                })
        out.sort(key=lambda x: x["prob_up"], reverse=True)
        return {"target_date": target_date, "eval_date": self._eff_date, "data": out}

    def build_portfolio_view(self, positions: List[Dict[str, Any]], target_date: str) -> Dict[str, Any]:
        """보유 종목을 기준일 종가로 평가하고 매도 신호를 판정한 결과를 반환합니다.

        :param positions: [{stock_code, stock_name, buy_price, quantity, ...}] 형태 보유 잔고
        :param target_date: 평가 기준일 (YYYYMMDD)
        :return: {eval_date, stock_value, positions:[...평가필드 추가...], sell_signals:[...]}
        """
        self._load(target_date)
        close_map = {}
        if self._eff_date and self._df is not None and not self._df.empty:
            day = self._df[self._df["date"] == self._eff_date]
            close_map = dict(zip(day["symbol"], day["close_price"]))

        held = {p["stock_code"] for p in positions}
        strat_sells: Dict[str, List[str]] = {}
        if self._eff_date and held:
            for key in STRATEGY_MAP:
                d = self._sell_rows_for(key, held)
                for sym in d["symbol"]:
                    if sym in held:
                        strat_sells.setdefault(sym, []).append(STRATEGY_LABELS.get(key, key))

        enriched, signals, stock_value = [], [], 0.0
        for p in positions:
            code = p["stock_code"]
            buy = float(p["buy_price"])
            qty = int(p["quantity"])
            cur = float(close_map.get(code, 0.0)) or buy
            eval_amt = cur * qty
            stock_value += eval_amt
            pnl_pct = ((cur - buy) / buy * 100.0) if buy else 0.0
            enriched.append({
                **p, "current_price": int(round(cur)), "eval_amount": int(round(eval_amt)),
                "profit_pct": round(pnl_pct, 2), "profit_krw": int(round((cur - buy) * qty)),
            })

            badges = list(strat_sells.get(code, []))
            reasons = [f"전략 매도 신호: {', '.join(badges)}"] if badges else []
            if pnl_pct <= STOP_LOSS_PCT:
                badges.append("🔻 손절선 -5%")
                reasons.append(f"매수가 대비 {pnl_pct:.2f}% 하락 (손절 관리)")
            elif pnl_pct >= TAKE_PROFIT_PCT:
                badges.append("🎯 익절선 +10%")
                reasons.append(f"매수가 대비 +{pnl_pct:.2f}% 상승 (수익 확정)")
            if badges:
                signals.append({
                    "code": code, "name": p.get("stock_name", code), "quantity": qty,
                    "buy_price": int(round(buy)), "current_price": int(round(cur)),
                    "badges": badges, "reason": " / ".join(reasons),
                })

        return {
            "eval_date": self._eff_date,
            "stock_value": int(round(stock_value)),
            "positions": enriched,
            "sell_signals": signals,
        }
