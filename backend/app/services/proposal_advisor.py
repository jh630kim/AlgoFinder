"""
투자제안 화면 데이터 조립 서비스 모듈 (proposal_advisor.py).

기준일 기준으로 S1~S5(6전략) 매수 신호를 산출해 전략별 TOP N 추천을 만들고,
보유 종목에 대해 매도 신호(전략 매도신호 / -5% 손절 / +10% 익절)를 판정하는 ProposalAdvisor 클래스.

판단 기준일 모드(mode):
- "advice"(기본, 투자제안): 신호 판단일 = 체결·평가일 = 기준일(D-0).
- "sim"(모의투자): 신호 판단일 = 기준일 직전 거래일(D-1), 추천가·평가액은 기준일(D-0) 종가.

성능(A+C): 기준일마다 재로딩·재계산하지 않고, 기준일 앞뒤로 넓은 창(워밍업 ~ 기준일+FORWARD)을
1회 로드·1회 지표 계산해 캐싱한다. 기준일이 창 안이면 필터만 하므로 '다음날 조회' 반복이 즉시 처리된다.
워밍업 버퍼는 최장 지표(sma60 ≈ 60거래일)를 큰 마진으로 덮는 135달력일로 축소했다.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from backend.app.models.all_stock_master import AllStockMaster
from backend.app.services.backtest_engine import (
    BacktestEngine, STRATEGY_MAP, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
)

logger = logging.getLogger(__name__)

TARGET_SECTORS = ["KOSPI 200", "KOSDAQ 150"]
# STOP_LOSS_PCT / TAKE_PROFIT_PCT 는 backtest_engine 에서 import (백테스트와 동일 값 공유)

# 창 크기(달력일): 앞쪽은 지표 워밍업, 뒤쪽은 '다음날 조회' 반복을 재로딩 없이 흡수
WARMUP_CAL_DAYS = 135
FORWARD_CAL_DAYS = 180
# 창 재사용 판정 시 워밍업 요구를 이만큼 완화(거래일 경계로 하루이틀 모자란 재적재 방지).
# 135-25=110달력일 ≈ 75거래일 > 최장 지표 sma60 이므로 신호행 지표는 동일.
COVER_SLACK_CAL_DAYS = 25

STRATEGY_LABELS = {
    "S1": "🔵 S1 골든크로스", "S1a": "🔵 S1a 거래량 필터형", "S2": "🟢 S2 눌림목 돌파",
    "S3": "🟠 S3 볼린저 밴드", "S4": "🔴 S4 RSI 과매수", "S5": "🕯️ S5 캔들 패턴",
}
STRATEGY_BUY_REASON = {
    "S1": "5/20일 골든크로스 및 60일선 정배열 추세 포착",
    "S1a": "골든크로스 + 거래량 급증 동시 충족",
    "S2": "과매도 눌림목 이후 상방 돌파 포착",
    "S3": "볼린저 밴드 하단 반등 또는 밴드 수축 후 돌파 포착",
    "S4": "RSI 과매도 구간 반등 포착",
    "S5": "거래량 동반 반전 캔들 패턴 포착",
}


class ProposalAdvisor:
    """투자제안 추천/매도신호/포트폴리오 평가 데이터를 조립하는 서비스 클래스."""

    def __init__(self, session: Session, mode: str = "advice") -> None:
        """세션 및 내부 캐시를 초기화합니다.

        :param session: SQLAlchemy DB 세션
        :param mode: "advice"(투자제안, 신호일=기준일) 또는 "sim"(모의투자, 신호일=기준일 직전 거래일)
        """
        self.session = session
        self.mode = mode
        # 신호 판단일 오프셋: advice=0(기준일), sim=-1(직전 거래일)
        self._signal_offset = -1 if mode == "sim" else 0
        self._engine = BacktestEngine(session)
        self._df = None
        self._all_dates: List[str] = []      # 로드된 창의 거래일 목록(오름차순)
        self._win_lo = None                  # 창 내 최초 거래일
        self._win_hi = None                  # 창 내 최종 거래일
        self._resolved_for = None            # _resolve_dates 를 마지막으로 수행한 기준일
        self._eff_date = None
        self._signal_date = None
        self._eff_close_map: Dict[str, float] = {}
        self._processed: Dict[str, Any] = {}
        self._cs_cache = None  # 합성 점수 캐시
        self._market_map: Dict[str, str] = {}

    def load(self, target_date: str) -> None:
        """기준일 시세 데이터를 로딩·캐싱합니다(공유 캐시 등 외부에서 쓰는 공개 진입점)."""
        self._load(target_date)

    def _covers(self, target_date: str) -> bool:
        """이미 로드된 창이 기준일을 충분한 워밍업과 함께 포함하는지 판정합니다."""
        if self._win_lo is None or self._win_hi is None:
            return False
        need_lo = (datetime.strptime(target_date, "%Y%m%d")
                   - timedelta(days=WARMUP_CAL_DAYS - COVER_SLACK_CAL_DAYS)).strftime("%Y%m%d")
        return self._win_lo <= need_lo and target_date <= self._win_hi

    def _load(self, target_date: str) -> None:
        """기준일을 포함하는 넓은 시세 창을 1회 로드하고, 필요 시에만 재적재합니다."""
        if self._df is not None and not self._df.empty and self._covers(target_date):
            self._resolve_dates(target_date)
            return

        td = datetime.strptime(target_date, "%Y%m%d")
        win_start = (td - timedelta(days=WARMUP_CAL_DAYS)).strftime("%Y%m%d")
        win_end = (td + timedelta(days=FORWARD_CAL_DAYS)).strftime("%Y%m%d")

        self._processed = {}
        self._cs_cache = None
        self._resolved_for = None
        self._eff_date = None
        self._signal_date = None
        self._eff_close_map = {}
        self._win_lo = self._win_hi = None
        # warmup_days=0: 워밍업을 win_start 에 이미 반영했으므로 엔진의 추가 버퍼는 끈다
        self._df = self._engine.load_market_dataframe(
            TARGET_SECTORS, win_start, win_end, warmup_days=0
        )
        if self._df is None or self._df.empty:
            self._all_dates = []
            return

        self._all_dates = sorted(self._df["date"].unique())
        self._win_lo, self._win_hi = self._all_dates[0], self._all_dates[-1]
        codes = set(self._df["symbol"].unique())
        rows = self.session.query(AllStockMaster.code, AllStockMaster.market).filter(
            AllStockMaster.code.in_(codes)
        ).all()
        self._market_map = {c: m for c, m in rows}
        self._resolve_dates(target_date)

    def _resolve_dates(self, target_date: str) -> None:
        """로드된 창에서 기준일에 대응하는 평가일(D-0)·신호일(D-1/D-0)·종가맵을 계산합니다."""
        if self._resolved_for == target_date:
            return
        self._resolved_for = target_date
        avail = [d for d in self._all_dates if d <= target_date]
        self._eff_date = avail[-1] if avail else None
        sig_idx = len(avail) - 1 + self._signal_offset
        self._signal_date = avail[sig_idx] if 0 <= sig_idx < len(avail) else None
        self._eff_close_map = {}
        if self._eff_date is not None:
            d0 = self._df[self._df["date"] == self._eff_date]
            self._eff_close_map = dict(zip(d0["symbol"], d0["close_price"]))

    def _processed_df(self, key: str):
        """전략별 지표·시그널 연산 결과를 창 단위로 1회 캐싱해 반환합니다."""
        if key not in self._processed:
            self._processed[key] = STRATEGY_MAP[key].calculate_indicators(self._df)
        return self._processed[key]

    def _composite_map(self) -> Dict[str, Any]:
        """로드된 창에 대해 순수관행 합성 점수를 1회 계산해 (symbol,date)->(pct,rank) 로 반환."""
        if getattr(self, "_cs_cache", None) is None:
            import pandas as pd
            from backend.app.services.composite_score import CompositeScorer
            scored = CompositeScorer().score(self._df)
            m = {}
            for r in scored.itertuples(index=False):
                pct = None if pd.isna(r.composite_pct) else round(float(r.composite_pct), 1)
                rk = None if pd.isna(r.composite_rank) else int(r.composite_rank)
                m[(r.symbol, r.date)] = (pct, rk)
            self._cs_cache = m
        return self._cs_cache

    def get_composite_top(self, target_date: str, n: int = 10) -> Dict[str, Any]:
        """신호 판단일 시점, 합성 점수 상위 n종을 반환합니다(신호 유무 무관).

        :param target_date: 기준일 (YYYYMMDD)
        :param n: 상위 노출 개수
        :return: {eval_date, signal_date, data:[{rank,code,name,market,composite_pct,close_price}]}
        """
        self._load(target_date)
        if not self._eff_date or not self._signal_date:
            return {"eval_date": self._eff_date, "signal_date": self._signal_date, "data": []}
        cmap = self._composite_map()
        name_map = dict(zip(self._df["symbol"], self._df["name"]))
        rows = [
            (rk, sym, pct) for (sym, d), (pct, rk) in cmap.items()
            if d == self._signal_date and rk is not None
        ]
        rows.sort(key=lambda x: x[0])
        out = []
        for rk, sym, pct in rows[:n]:
            px = float(self._eff_close_map.get(sym, 0.0))
            out.append({
                "rank": rk, "code": sym, "name": str(name_map.get(sym) or sym),
                "market": self._market_map.get(sym, ""),
                "composite_pct": pct, "close_price": int(round(px)),
            })
        return {"eval_date": self._eff_date, "signal_date": self._signal_date, "data": out}

    def _sell_rows_for(self, key: str, held: set):
        """보유 종목의 신호일 매도 신호 행을 반환합니다(연산량 축소).

        추천 계산이 이미 전체 종목 지표를 캐싱했으면 그대로 재사용하고, 아니면
        보유 종목만으로 지표를 연산합니다. 지표는 종목별 롤링이라 대상 종목만
        추려도 개별 결과는 전체 연산과 동일합니다.

        :param key: 전략 키(S1~S5)
        :param held: 보유 종목코드 집합
        :return: signal_sell=True 인 신호일 행 DataFrame
        """
        pdf = self._processed.get(key)
        if pdf is None:
            subset = self._df[self._df["symbol"].isin(held)]
            pdf = STRATEGY_MAP[key].calculate_indicators(subset)
        return pdf[(pdf["date"] == self._signal_date) & (pdf["signal_sell"].fillna(False))]

    def get_recommendations(self, target_date: str, top_n: int = 3) -> Dict[str, Any]:
        """기준일 종가 기준 6전략 각각의 매수 신호 TOP N 추천 목록을 반환합니다.

        :param target_date: 추천 기준일 (YYYYMMDD)
        :param top_n: 전략별 상위 노출 개수
        :return: {target_date, eval_date, signal_date, data:[{code,name,market,strategy,strategy_name,prob_up,close_price,reason}]}
        """
        self._load(target_date)
        if not self._eff_date or not self._signal_date:
            return {"target_date": target_date, "eval_date": self._eff_date,
                    "signal_date": self._signal_date, "data": []}

        cmap = self._composite_map()
        out = []
        for key in STRATEGY_MAP:
            pdf = self._processed_df(key)
            # 매수 신호는 판단 기준일(sim이면 D-1)에서 포착
            day = pdf[(pdf["date"] == self._signal_date) & (pdf["signal_buy"].fillna(False))]
            for _, r in day.iterrows():
                sym = r["symbol"]
                # 추천가는 체결·평가 기준일(D-0) 종가. advice 모드는 신호행과 동일 값
                px = float(self._eff_close_map.get(sym, r["close_price"]))
                cs_pct, cs_rank = cmap.get((sym, self._signal_date), (None, None))
                out.append({
                    "code": sym,
                    "name": str(r.get("name") or sym),
                    "market": self._market_map.get(sym, ""),
                    "strategy": key,
                    "strategy_name": STRATEGY_LABELS.get(key, key),
                    # prob_up 필드는 합성 백분위로 대체(없으면 기존 prob_up)
                    "prob_up": cs_pct if cs_pct is not None else round(float(r.get("prob_up", 50.0)), 1),
                    "composite_pct": cs_pct,
                    "composite_rank": cs_rank,
                    "close_price": int(round(px)),
                    "reason": STRATEGY_BUY_REASON.get(key, "매수 신호 포착"),
                })
        # 합성 점수(백분위) 내림차순 정렬 → 전략별 top_n 제한
        out.sort(key=lambda x: (x["prob_up"] if x["prob_up"] is not None else -1), reverse=True)
        seen: Dict[str, int] = {}
        limited = []
        for row in out:
            k = row["strategy"]
            if seen.get(k, 0) >= top_n:
                continue
            seen[k] = seen.get(k, 0) + 1
            limited.append(row)
        return {"target_date": target_date, "eval_date": self._eff_date,
                "signal_date": self._signal_date, "data": limited}

    def build_portfolio_view(self, positions: List[Dict[str, Any]], target_date: str) -> Dict[str, Any]:
        """보유 종목을 기준일 종가로 평가하고 매도 신호를 판정한 결과를 반환합니다.

        :param positions: [{stock_code, stock_name, buy_price, quantity, ...}] 형태 보유 잔고
        :param target_date: 평가 기준일 (YYYYMMDD)
        :return: {eval_date, signal_date, stock_value, positions:[...평가필드 추가...], sell_signals:[...]}
        """
        self._load(target_date)
        close_map = {}
        if self._eff_date and self._df is not None and not self._df.empty:
            day = self._df[self._df["date"] == self._eff_date]
            close_map = dict(zip(day["symbol"], day["close_price"]))

        held = {p["stock_code"] for p in positions}
        cmap = self._composite_map() if (self._df is not None and not self._df.empty) else {}
        strat_sells: Dict[str, List[str]] = {}
        if self._eff_date and self._signal_date and held:
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
            h_pct, h_rank = cmap.get((code, self._eff_date), (None, None))
            enriched.append({
                **p, "current_price": int(round(cur)), "eval_amount": int(round(eval_amt)),
                "profit_pct": round(pnl_pct, 2), "profit_krw": int(round((cur - buy) * qty)),
                "composite_pct": h_pct, "composite_rank": h_rank,
                "entry_strategy": p.get("entry_strategy"),
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
                cs_pct, cs_rank = cmap.get((code, self._eff_date), (None, None))
                signals.append({
                    "code": code, "name": p.get("stock_name", code), "quantity": qty,
                    "buy_price": int(round(buy)), "current_price": int(round(cur)),
                    "badges": badges, "reason": " / ".join(reasons),
                    "entry_strategy": p.get("entry_strategy"),
                    "composite_pct": cs_pct, "composite_rank": cs_rank,
                })

        return {
            "eval_date": self._eff_date,
            "signal_date": self._signal_date,
            "stock_value": int(round(stock_value)),
            "positions": enriched,
            "sell_signals": signals,
        }
