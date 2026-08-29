"""
순수관행 백테스트 엔트리 엔진 모듈 (purerule_engine.py).

[순수관행.md] §3~§8 을 따르는 별도 시뮬레이션 경로. S1~S5 신호를 쓰지 않고
횡단면 합성 점수(CompositeScorer)만으로 상위 N종을 굴린다.

v1 규칙(자율 결정):
  - 슬롯 = 균등 비중(변동성 타깃·±5%p 밴드·비중조정 행은 v2)
  - 주 1회 리밸런싱: 각 주의 마지막 거래일(≈금) 종가 체결, 신호는 직전 거래일 랭킹
  - 매일 예외 청산: 하드 스톱(진입가 − 2.5·ATR14) / 랭킹 이탈(상위 2N 밖) / 최대 보유일(30)
  - 빈 슬롯은 그날(D-0) 종가로 다음 순위 후보 즉시 편입. 거래비용 무시.
  - 매매일지는 기존 strategy_trade_logs 스키마 재사용. prob_up 필드 = 합성 백분위.
"""

import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.services.backtest_engine import BacktestEngine
from backend.app.services.composite_score import CompositeScorer
from backend.app.repositories.strategy_leaderboard_repository import StrategyLeaderboardRepository
from backend.app.repositories.strategy_trade_logs_repository import StrategyTradeLogsRepository
from backend.app.repositories.strategy_daily_equity_repository import StrategyDailyEquityRepository

logger = logging.getLogger(__name__)

COMBO_ID = 22
COMBO_NAME = "순수관행"
ATR_MULT = 2.5
MAX_HOLD_DAYS = 30


class PureRuleEngine:
    """횡단면 합성 점수 기반 순수관행 백테스트 엔트리 엔진 클래스."""

    def __init__(self, session: Session) -> None:
        """:param session: SQLAlchemy 세션"""
        self.session = session
        self._bt = BacktestEngine(session)
        self.lb_repo = StrategyLeaderboardRepository(session)
        self.tl_repo = StrategyTradeLogsRepository(session)
        self.eq_repo = StrategyDailyEquityRepository(session)

    def run_backtest(self, initial_capital: float = 10000000.0, max_slots: int = 5,
                     start_date: str = None, end_date: str = None,
                     target_sectors=None) -> dict:
        """순수관행 시뮬레이션을 실행하고 리더보드/매매일지/일별자산을 저장합니다."""
        target_sectors = target_sectors or ["KOSPI 200", "KOSDAQ 150"]
        today = datetime.now().strftime("%Y%m%d")
        end_date = end_date or today
        start_date = start_date or (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        df = self._bt.load_market_dataframe(target_sectors, start_date, end_date)
        if df is None or df.empty:
            return {"combo_id": COMBO_ID, "combo_name": COMBO_NAME, "metrics": {}, "log_count": 0}

        scored = CompositeScorer().score(df)
        px = df.set_index(["symbol", "date"])[["close_price", "high_price", "low_price"]].to_dict("index")
        rank = {(r.symbol, r.date): (r.composite_rank, r.composite_pct)
                for r in scored.itertuples(index=False)}
        atr = self._atr_map(df)

        metrics, logs, eq = self._simulate(
            scored, px, rank, atr, initial_capital, max_slots, start_date, end_date
        )
        self.lb_repo.upsert_leaderboard_entry({"combo_id": COMBO_ID, "combo_name": COMBO_NAME, **metrics})
        self.tl_repo.clear_logs_by_combo(COMBO_ID)
        self.tl_repo.bulk_insert_trade_logs(logs)
        self.eq_repo.clear_equity_by_combo(COMBO_ID)
        self.eq_repo.bulk_insert_daily_equity(eq)
        return {"combo_id": COMBO_ID, "combo_name": COMBO_NAME, "metrics": metrics, "log_count": len(logs)}

    @staticmethod
    def _atr_map(df: pd.DataFrame) -> dict:
        """(symbol, date) -> ATR(14) 룩업 맵."""
        g = df.groupby("symbol")
        pc = g["close_price"].shift(1)
        tr = pd.concat([
            df["high_price"] - df["low_price"],
            (df["high_price"] - pc).abs(),
            (df["low_price"] - pc).abs(),
        ], axis=1).max(axis=1)
        atr = tr.groupby(df["symbol"]).transform(lambda x: x.rolling(14, min_periods=5).mean())
        return {(s, d): float(v) for s, d, v in zip(df["symbol"], df["date"], atr) if pd.notna(v)}

    def _simulate(self, scored, px, rank, atr, cap0, n_slots, start_date, end_date):
        """일자 루프 시뮬레이션. (metrics, logs, equity_logs) 반환."""
        dates = sorted(scored["date"].unique())
        sim = [d for d in dates if start_date <= d <= end_date]
        top_by_date = self._top_by_date(scored, n_slots)
        cash, pos, logs, curve, eqlogs, closed = cap0, {}, [], [], [], []
        for i, d in enumerate(sim):
            di = dates.index(d)
            if di == 0:
                continue
            pd_ = dates[di - 1]
            is_rebal = (i + 1 == len(sim)) or (
                datetime.strptime(d, "%Y%m%d").isocalendar()[1]
                != datetime.strptime(sim[i + 1], "%Y%m%d").isocalendar()[1]
            ) if i + 1 < len(sim) else True
            # --- 청산 (매일) ---
            for sym in list(pos):
                p = pos[sym]
                p["hold"] += 1
                row = px.get((sym, d))
                if not row:
                    continue
                c = float(row["close_price"])
                reason = self._exit_reason(sym, pd_, c, p, rank, atr, n_slots, is_rebal, top_by_date)
                if reason:
                    cash += p["sh"] * c
                    closed.append((c - p["buy"]) / p["buy"] * 100.0)
                    logs.append(self._log(d, sym, p, "SELL", c, cap0, cash, pos, px, reason))
                    del pos[sym]
            # --- 매수: 리밸런싱일 또는 빈 슬롯 즉시 편입 ---
            want = top_by_date.get(pd_, [])
            for sym in want:
                if len(pos) >= n_slots:
                    break
                if sym in pos:
                    continue
                row = px.get((sym, d))
                if not row:
                    continue
                c = float(row["close_price"])
                alloc = (cash + sum(q["sh"] * float(px.get((s, d), {}).get("close_price", q["buy"]))
                                    for s, q in pos.items())) / n_slots
                sh = int(alloc // c) if c > 0 else 0
                if sh <= 0 or cash < sh * c:
                    continue
                cash -= sh * c
                _, cpct = rank.get((sym, pd_), (None, 50.0))
                pos[sym] = {"sh": sh, "buy": c, "hold": 0, "pct": float(cpct or 50.0),
                            "name": self._name(scored, sym)}
                logs.append(self._log(d, sym, pos[sym], "BUY", c, cap0, cash, pos, px, "랭킹편입"))
            eqv = cash + sum(q["sh"] * float(px.get((s, d), {}).get("close_price", q["buy"]))
                             for s, q in pos.items())
            curve.append(eqv)
            eqlogs.append({"combo_id": COMBO_ID, "trade_date": d, "equity_amount": eqv})
        return self._metrics(curve, closed, cap0, len(logs)), logs, eqlogs

    @staticmethod
    def _top_by_date(scored: pd.DataFrame, n_slots: int) -> dict:
        """날짜별 상위 2N 적격 종목코드 리스트(합성 랭킹 오름차순)."""
        elig = scored[scored["cs_eligible"]].dropna(subset=["composite_rank"])
        out = {}
        for d, grp in elig.groupby("date"):
            out[d] = list(grp.nsmallest(2 * n_slots, "composite_rank")["symbol"])
        return out

    @staticmethod
    def _exit_reason(sym, sig_d, c, p, rank, atr, n_slots, is_rebal, top_by_date):
        """청산 사유 판정: 하드스톱 → 랭킹이탈 → 최대보유일 → (리밸런싱일) 정기교체."""
        a = atr.get((sym, sig_d))
        if a and c <= p["buy"] - ATR_MULT * a:
            return "하드스톱"
        rk, _ = rank.get((sym, sig_d), (None, None))
        if rk is not None and rk > 2 * n_slots:
            return "랭킹이탈"
        if p["hold"] >= MAX_HOLD_DAYS:
            return "최대보유일"
        if is_rebal and sym not in set(top_by_date.get(sig_d, [])[:n_slots]):
            return "정기교체"
        return None

    @staticmethod
    def _name(scored: pd.DataFrame, sym: str) -> str:
        """종목명 조회(없으면 코드)."""
        if "name" in scored.columns:
            m = scored.loc[scored["symbol"] == sym, "name"]
            if len(m):
                return str(m.iloc[0])
        return sym

    @staticmethod
    def _log(d, sym, p, ttype, price, cap0, cash, pos, px, tag):
        """strategy_trade_logs 행 dict 조립."""
        eqv = cash + sum(q["sh"] * float(px.get((s, d), {}).get("close_price", q["buy"]))
                         for s, q in pos.items())
        profit_pct = (price - p["buy"]) / p["buy"] * 100.0 if ttype == "SELL" else 0.0
        profit_krw = (price - p["buy"]) * p["sh"] if ttype == "SELL" else 0.0
        return {
            "combo_id": COMBO_ID, "trade_date": d, "symbol": sym, "name": p["name"],
            "trade_type": ttype, "holding_days": p["hold"], "shares": p["sh"],
            "unit_price": price, "total_amount": p["sh"] * price, "equity_after_trade": eqv,
            "cum_return_pct": round((eqv - cap0) / cap0 * 100.0, 2),
            "profit_pct": round(profit_pct, 2), "profit_krw": round(profit_krw, 0),
            "prob_up": round(p["pct"], 1), "strategy_tag": tag, "slot_no": 0,
        }

    @staticmethod
    def _metrics(curve, closed, cap0, n_logs):
        """총수익·승률·MDD 지표 dict."""
        final = curve[-1] if curve else cap0
        wr = (len([t for t in closed if t > 0]) / len(closed) * 100.0) if closed else 0.0
        if curve:
            s = pd.Series(curve)
            mdd = float(abs(((s - s.cummax()) / s.cummax() * 100.0).min()))
        else:
            mdd = 0.0
        return {
            "final_capital": round(final, 0), "total_return_pct": round((final - cap0) / cap0 * 100.0, 2),
            "win_rate_pct": round(wr, 2), "mdd_pct": round(mdd, 2), "total_trades": n_logs,
        }
