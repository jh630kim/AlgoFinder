"""
퀀트 시뮬레이션 및 백테스팅 엔진 서비스 모듈 (딕셔너리 고속 연산 최적화 버전).

D-1일 데이터 지표 기반 신호 포착 ➔ D-0일 종가(close_price) 체결 규격,
초기 300만 원 / 최대 3슬롯(총자산 1/3) 관리, prob_up 상위 정렬 매수, 가변 기간 및
투자 대상 군 다중 필터링을 지원하는 BacktestEngine 클래스를 정의합니다.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session

from backend.app.models.investor_trading_daily import InvestorTradingDaily
from backend.app.models.all_stock_master import AllStockMaster
from backend.app.repositories.strategy_leaderboard_repository import StrategyLeaderboardRepository
from backend.app.repositories.strategy_trade_logs_repository import StrategyTradeLogsRepository

from backend.app.services.strategies.s1_ma_cross import S1MACrossStrategy
from backend.app.services.strategies.s1a_ma_cross_volume import S1aMACrossVolumeStrategy
from backend.app.services.strategies.s1b_ma_cross_legacy import S1bMACrossLegacyStrategy
from backend.app.services.strategies.s1c_ma_cross_adaptive import S1cMACrossAdaptiveStrategy
from backend.app.services.strategies.s2_breakout import S2BreakoutStrategy
from backend.app.services.strategies.s3_bollinger import S3BollingerStrategy
from backend.app.services.strategies.s4_rsi_overbought import S4RSIStrategy
from backend.app.services.strategies.s5_candle_patterns import S5CandlePatternsStrategy

logger = logging.getLogger(__name__)

STRATEGY_MAP = {
    "S1": S1MACrossStrategy(),
    "S1a": S1aMACrossVolumeStrategy(),
    "S1b": S1bMACrossLegacyStrategy(),
    "S1c": S1cMACrossAdaptiveStrategy(),
    "S2": S2BreakoutStrategy(),
    "S3": S3BollingerStrategy(),
    "S4": S4RSIStrategy(),
    "S5": S5CandlePatternsStrategy(),
}

STRATEGY_COMBOS = {
    1: ("S1", ["S1"]), 2: ("S1a", ["S1a"]), 3: ("S1b", ["S1b"]), 4: ("S1c", ["S1c"]),
    5: ("S2", ["S2"]), 6: ("S3", ["S3"]), 7: ("S4", ["S4"]), 8: ("S5", ["S5"]),
    9: ("S1+S2", ["S1", "S2"]), 10: ("S1a+S2", ["S1a", "S2"]), 11: ("S1b+S2", ["S1b", "S2"]), 12: ("S1c+S2", ["S1c", "S2"]),
    13: ("S1+S3", ["S1", "S3"]), 14: ("S1a+S3", ["S1a", "S3"]), 15: ("S1b+S3", ["S1b", "S3"]), 16: ("S1c+S3", ["S1c", "S3"]),
    17: ("S2+S3", ["S2", "S3"]),
    18: ("S1+S2+S3", ["S1", "S2", "S3"]), 19: ("S1a+S2+S3", ["S1a", "S2", "S3"]),
    20: ("S1b+S2+S3", ["S1b", "S2", "S3"]), 21: ("S1c+S2+S3", ["S1c", "S2", "S3"])
}


class BacktestEngine:
    """
    21개 퀀트 전략 시뮬레이션 및 백테스팅 엔진 클래스.
    """

    def __init__(self, session: Session) -> None:
        """BacktestEngine 초기화."""
        self.session = session
        self.leaderboard_repo = StrategyLeaderboardRepository(session)
        self.trade_logs_repo = StrategyTradeLogsRepository(session)
        self._df_cache = None
        self._cached_sectors = None

    def load_market_dataframe(self, target_sectors: List[str]) -> pd.DataFrame:
        """지정된 투자 대상 군의 시계열 데이터를 캐싱하여 고속 로딩합니다."""
        sectors_key = str(sorted(target_sectors)) if target_sectors else "ALL"
        if self._df_cache is not None and self._cached_sectors == sectors_key:
            return self._df_cache

        query = self.session.query(
            InvestorTradingDaily.symbol, InvestorTradingDaily.date,
            InvestorTradingDaily.open_price, InvestorTradingDaily.high_price,
            InvestorTradingDaily.low_price, InvestorTradingDaily.close_price,
            InvestorTradingDaily.volume, InvestorTradingDaily.personal_net_buy,
            InvestorTradingDaily.foreigner_net_buy, InvestorTradingDaily.institution_net_buy,
            AllStockMaster.name, AllStockMaster.sector
        ).join(AllStockMaster, InvestorTradingDaily.symbol == AllStockMaster.code)

        if target_sectors and "ALL" not in [t.upper() for t in target_sectors]:
            query = query.filter(AllStockMaster.sector.in_(target_sectors))

        df = pd.read_sql(query.statement, self.session.bind)
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values(by=["symbol", "date"]).reset_index(drop=True)
        self._df_cache = df
        self._cached_sectors = sectors_key
        return df

    def run_backtest_for_combo(
        self, combo_id: int, initial_capital: float = 3000000.0, max_slots: int = 3,
        start_date: str = None, end_date: str = None, target_sectors: List[str] = None
    ) -> Dict[str, Any]:
        """특정 combo_id 전략 조합 백테스트를 실행하고 결과를 저장합니다."""
        if combo_id not in STRATEGY_COMBOS:
            raise ValueError(f"존재하지 않는 combo_id 입니다: {combo_id}")

        combo_name, strat_keys = STRATEGY_COMBOS[combo_id]
        if not target_sectors:
            target_sectors = ["KOSPI 200", "KOSDAQ 150", "ETF_USA"]

        df_raw = self.load_market_dataframe(target_sectors)
        if df_raw.empty:
            return self._empty_result(combo_id, combo_name, initial_capital)

        today_dt = datetime.now()
        if not end_date:
            end_date = today_dt.strftime("%Y%m%d")
        if not start_date:
            start_date = (today_dt - timedelta(days=365)).strftime("%Y%m%d")

        processed_dfs = [STRATEGY_MAP[k].calculate_indicators(df_raw) for k in strat_keys]
        metrics, logs = self._simulate_trading(
            combo_id, processed_dfs, initial_capital, max_slots, start_date, end_date
        )

        self.leaderboard_repo.upsert_leaderboard_entry({
            "combo_id": combo_id, "combo_name": combo_name,
            "final_capital": metrics["final_capital"], "total_return_pct": metrics["total_return_pct"],
            "win_rate_pct": metrics["win_rate_pct"], "mdd_pct": metrics["mdd_pct"],
            "total_trades": metrics["total_trades"]
        })
        self.trade_logs_repo.clear_logs_by_combo(combo_id)
        self.trade_logs_repo.bulk_insert_trade_logs(logs)

        return {"combo_id": combo_id, "combo_name": combo_name, "metrics": metrics, "log_count": len(logs)}

    def _simulate_trading(
        self, combo_id: int, dfs: List[pd.DataFrame], initial_capital: float,
        max_slots: int, start_date: str, end_date: str
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """D-1 신호 포착 ➔ D-0 종가 체결 시뮬레이션을 딕셔너리 고속 룩업으로 연산합니다."""
        dates = sorted(dfs[0]["date"].unique())
        sim_dates = [d for d in dates if start_date <= d <= end_date]
        if not sim_dates:
            return self._empty_metrics(initial_capital), []

        # 고속 룩업용 딕셔너리 빌드: (symbol, date) -> dict_row
        dict_maps = []
        for df in dfs:
            d_map = df.set_index(["symbol", "date"]).to_dict("index")
            dict_maps.append(d_map)

        all_symbols = sorted(dfs[0]["symbol"].unique())
        cash = initial_capital
        positions = {}  # symbol -> {shares, buy_price, buy_date, prob_up, name, holding_days}
        logs = []
        equity_curve = []
        closed_trades = []

        date_to_idx = {d: i for i, d in enumerate(dates)}

        for d in sim_dates:
            d_idx = date_to_idx.get(d, 0)
            if d_idx == 0:
                continue
            prev_d = dates[d_idx - 1]

            # 1. 기존 포지션 매도 판정 (D-1 신호 기준, D-0 종가 체결)
            symbols_to_sell = []
            for sym, pos in list(positions.items()):
                pos["holding_days"] += 1
                should_sell = False
                for d_map in dict_maps:
                    row_prev = d_map.get((sym, prev_d))
                    if row_prev and row_prev.get("signal_sell", False):
                        should_sell = True
                        break

                if should_sell:
                    row_curr = dict_maps[0].get((sym, d))
                    if row_curr:
                        sell_price = float(row_curr["close_price"])
                        revenue = pos["shares"] * sell_price
                        profit_krw = revenue - (pos["shares"] * pos["buy_price"])
                        profit_pct = (sell_price - pos["buy_price"]) / pos["buy_price"] * 100.0
                        cash += revenue
                        closed_trades.append(profit_pct)

                        curr_equity = cash + sum(p["shares"] * sell_price for p in positions.values() if p != pos)
                        cum_ret = (curr_equity - initial_capital) / initial_capital * 100.0

                        logs.append({
                            "combo_id": combo_id, "trade_date": d, "symbol": sym, "name": pos["name"],
                            "trade_type": "SELL", "holding_days": pos["holding_days"], "shares": pos["shares"],
                            "unit_price": sell_price, "total_amount": revenue, "equity_after_trade": curr_equity,
                            "cum_return_pct": round(cum_ret, 2), "profit_pct": round(profit_pct, 2),
                            "profit_krw": round(profit_krw, 0), "prob_up": pos["prob_up"], "strategy_tag": "SELL"
                        })
                        symbols_to_sell.append(sym)

            for sym in symbols_to_sell:
                del positions[sym]

            # 2. 신규 포지션 매수 판정 (D-1 신호 기준 prob_up 정렬, D-0 종가 체결)
            open_slots = max_slots - len(positions)
            if open_slots > 0:
                buy_candidates = []
                for sym in all_symbols:
                    if sym in positions:
                        continue
                    buy_signaled = False
                    prob_val = 50.0
                    name_val = sym
                    for d_map in dict_maps:
                        r_prev = d_map.get((sym, prev_d))
                        if r_prev and r_prev.get("signal_buy", False):
                            buy_signaled = True
                            prob_val = float(r_prev.get("prob_up", 50.0))
                            name_val = str(r_prev.get("name", sym))
                            break
                    if buy_signaled:
                        buy_candidates.append({"symbol": sym, "prob_up": prob_val, "name": name_val})

                if buy_candidates:
                    buy_candidates.sort(key=lambda x: x["prob_up"], reverse=True)
                    selected_buys = buy_candidates[:open_slots]

                    for b_item in selected_buys:
                        curr_total_equity = cash + sum(
                            p["shares"] * float(dict_maps[0].get((s, d), {}).get("close_price", p["buy_price"]))
                            for s, p in positions.items()
                        )
                        target_alloc = curr_total_equity / float(max_slots)
                        r_curr = dict_maps[0].get((b_item["symbol"], d))
                        if r_curr:
                            buy_price = float(r_curr["close_price"])
                            shares = int(target_alloc // buy_price) if buy_price > 0 else 0
                            if shares > 0 and cash >= (shares * buy_price):
                                cost = shares * buy_price
                                cash -= cost
                                positions[b_item["symbol"]] = {
                                    "shares": shares, "buy_price": buy_price, "buy_date": d,
                                    "prob_up": b_item["prob_up"], "name": b_item["name"], "holding_days": 0
                                }
                                curr_eq_after = cash + cost + sum(p["shares"] * p["buy_price"] for s, p in positions.items() if s != b_item["symbol"])
                                cum_ret_b = (curr_eq_after - initial_capital) / initial_capital * 100.0
                                logs.append({
                                    "combo_id": combo_id, "trade_date": d, "symbol": b_item["symbol"],
                                    "name": b_item["name"], "trade_type": "BUY", "holding_days": 0,
                                    "shares": shares, "unit_price": buy_price, "total_amount": cost,
                                    "equity_after_trade": curr_eq_after, "cum_return_pct": round(cum_ret_b, 2),
                                    "profit_pct": 0.0, "profit_krw": 0.0, "prob_up": b_item["prob_up"], "strategy_tag": "BUY"
                                })

            # 당일 총 평가 자산 기록
            day_equity = cash + sum(
                p["shares"] * float(dict_maps[0].get((s, d), {}).get("close_price", p["buy_price"]))
                for s, p in positions.items()
            )
            equity_curve.append(day_equity)

        final_cap = equity_curve[-1] if equity_curve else initial_capital
        tot_ret = (final_cap - initial_capital) / initial_capital * 100.0
        win_rate = (len([t for t in closed_trades if t > 0]) / len(closed_trades) * 100.0) if closed_trades else 0.0
        mdd = self._calc_mdd(equity_curve)

        metrics = {
            "final_capital": round(final_cap, 0), "total_return_pct": round(tot_ret, 2),
            "win_rate_pct": round(win_rate, 2), "mdd_pct": round(mdd, 2), "total_trades": len(logs)
        }
        return metrics, logs

    def _calc_mdd(self, equity_curve: List[float]) -> float:
        """평가 자산 곡선으로부터 최고점 대비 최대 낙폭(MDD %)을 산출합니다."""
        if not equity_curve:
            return 0.0
        peaks = pd.Series(equity_curve).cummax()
        drawdowns = (pd.Series(equity_curve) - peaks) / peaks * 100.0
        return float(abs(drawdowns.min())) if not drawdowns.empty else 0.0

    def _empty_metrics(self, initial_capital: float) -> Dict[str, Any]:
        """빈 결과 메트릭을 반환합니다."""
        return {"final_capital": initial_capital, "total_return_pct": 0.0, "win_rate_pct": 0.0, "mdd_pct": 0.0, "total_trades": 0}

    def _empty_result(self, combo_id: int, combo_name: str, initial_capital: float) -> Dict[str, Any]:
        """빈 백테스트 결과 딕셔너리를 반환합니다."""
        return {"combo_id": combo_id, "combo_name": combo_name, "metrics": self._empty_metrics(initial_capital), "log_count": 0}
