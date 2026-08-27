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
from backend.app.repositories.strategy_daily_equity_repository import StrategyDailyEquityRepository

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
        self.daily_equity_repo = StrategyDailyEquityRepository(session)
        self._df_cache = None
        self._cached_sectors = None
        self._indicator_cache = {}   # strat_key -> 지표 연산 완료 DataFrame
        self._dict_map_cache = {}    # strat_key -> {(symbol, date): row_dict}

    def load_market_dataframe(
        self, target_sectors: List[str], start_date: str = None, end_date: str = None
    ) -> pd.DataFrame:
        """지정된 투자 대상 군의 시계열 데이터를 기간 제한 + 캐싱하여 고속 로딩합니다.

        :param target_sectors: 투자 대상 업종 군 리스트
        :param start_date: 시뮬레이션 시작일(YYYYMMDD). 지표 워밍업용 200일 버퍼를 앞에 두고 조회
        :param end_date: 시뮬레이션 종료일(YYYYMMDD)
        :return: 심볼·일자 정렬된 시계열 데이터프레임
        """
        sectors_key = str(sorted(target_sectors)) if target_sectors else "ALL"

        # 지표 워밍업 버퍼(200달력일 ≈ 135거래일 > 최장 지표창 sma60)를 시작일 앞에 확보
        warmup_start = None
        if start_date:
            warmup_start = (
                datetime.strptime(start_date, "%Y%m%d") - timedelta(days=200)
            ).strftime("%Y%m%d")
        cache_key = f"{sectors_key}|{warmup_start}|{end_date}"
        if self._df_cache is not None and self._cached_sectors == cache_key:
            return self._df_cache

        from backend.app.models.target_stocks import TargetStocks

        query = self.session.query(
            InvestorTradingDaily.symbol, InvestorTradingDaily.date,
            InvestorTradingDaily.open_price, InvestorTradingDaily.high_price,
            InvestorTradingDaily.low_price, InvestorTradingDaily.close_price,
            InvestorTradingDaily.volume, InvestorTradingDaily.personal_net_buy,
            InvestorTradingDaily.foreigner_net_buy, InvestorTradingDaily.institution_net_buy,
            AllStockMaster.name, AllStockMaster.sector
        ).join(AllStockMaster, InvestorTradingDaily.symbol == AllStockMaster.code) \
         .join(TargetStocks, InvestorTradingDaily.symbol == TargetStocks.symbol)

        if target_sectors and "ALL" not in [t.upper() for t in target_sectors]:
            query = query.filter(AllStockMaster.sector.in_(target_sectors))
        if warmup_start:
            query = query.filter(InvestorTradingDaily.date >= warmup_start)
        if end_date:
            query = query.filter(InvestorTradingDaily.date <= end_date)

        df = pd.read_sql(query.statement, self.session.bind)
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values(by=["symbol", "date"]).reset_index(drop=True)

        # 로딩 데이터 범위가 바뀌면 전략별 지표/딕셔너리 캐시를 무효화
        self._df_cache = df
        self._cached_sectors = cache_key
        self._indicator_cache = {}
        self._dict_map_cache = {}
        return df

    def _get_processed_df(self, strat_key: str, df_raw: pd.DataFrame) -> pd.DataFrame:
        """전략별 지표 연산 결과를 캐싱해 combo 간 중복 계산을 제거합니다.

        :param strat_key: 전략 키(S1 ~ S5 등)
        :param df_raw: 원천 시계열 데이터프레임
        :return: 지표·시그널이 반영된 데이터프레임
        """
        if strat_key not in self._indicator_cache:
            self._indicator_cache[strat_key] = STRATEGY_MAP[strat_key].calculate_indicators(df_raw)
        return self._indicator_cache[strat_key]

    def _get_dict_map(self, strat_key: str, processed_df: pd.DataFrame) -> Dict[Any, Any]:
        """전략별 (symbol, date) 고속 룩업 딕셔너리를 캐싱합니다.

        :param strat_key: 전략 키
        :param processed_df: 지표가 반영된 데이터프레임
        :return: {(symbol, date): row_dict} 형태의 룩업 맵
        """
        if strat_key not in self._dict_map_cache:
            self._dict_map_cache[strat_key] = processed_df.set_index(["symbol", "date"]).to_dict("index")
        return self._dict_map_cache[strat_key]

    def run_backtest_for_combo(
        self, combo_id: int, initial_capital: float = 3000000.0, max_slots: int = 3,
        start_date: str = None, end_date: str = None, target_sectors: List[str] = None
    ) -> Dict[str, Any]:
        """특정 combo_id 전략 조합 백테스트를 실행하고 결과를 저장합니다."""
        if combo_id not in STRATEGY_COMBOS:
            raise ValueError(f"존재하지 않는 combo_id 입니다: {combo_id}")

        combo_name, strat_keys = STRATEGY_COMBOS[combo_id]
        if not target_sectors:
            target_sectors = ["KOSPI 200", "KOSDAQ 150"]

        # 기간 기본값을 먼저 확정한 뒤 해당 구간(+워밍업 버퍼)만 DB에서 로딩
        today_dt = datetime.now()
        if not end_date:
            end_date = today_dt.strftime("%Y%m%d")
        if not start_date:
            start_date = (today_dt - timedelta(days=365)).strftime("%Y%m%d")

        df_raw = self.load_market_dataframe(target_sectors, start_date, end_date)
        if df_raw.empty:
            return self._empty_result(combo_id, combo_name, initial_capital)

        processed_dfs = [self._get_processed_df(k, df_raw) for k in strat_keys]
        metrics, logs, equity_logs = self._simulate_trading(
            combo_id, processed_dfs, strat_keys, initial_capital, max_slots, start_date, end_date
        )

        self.leaderboard_repo.upsert_leaderboard_entry({
            "combo_id": combo_id, "combo_name": combo_name,
            "final_capital": metrics["final_capital"], "total_return_pct": metrics["total_return_pct"],
            "win_rate_pct": metrics["win_rate_pct"], "mdd_pct": metrics["mdd_pct"],
            "total_trades": metrics["total_trades"]
        })
        self.trade_logs_repo.clear_logs_by_combo(combo_id)
        self.trade_logs_repo.bulk_insert_trade_logs(logs)
        
        self.daily_equity_repo.clear_equity_by_combo(combo_id)
        self.daily_equity_repo.bulk_insert_daily_equity(equity_logs)

        return {"combo_id": combo_id, "combo_name": combo_name, "metrics": metrics, "log_count": len(logs)}

    def _portfolio_equity(
        self, cash: float, positions: Dict[str, Any], price_map: Dict[Any, Any],
        d: str, exclude: set = None
    ) -> float:
        """현금 + 전 보유종목을 당일(d) 종가로 평가한 총자산을 산출합니다.

        :param cash: 현재 현금 잔고
        :param positions: 보유 포지션 딕셔너리 (symbol -> {shares, buy_price, ...})
        :param price_map: (symbol, date) -> row_dict 룩업 맵 (기준 전략)
        :param d: 평가 기준 일자(YYYYMMDD)
        :param exclude: 평가에서 제외할 심볼 집합(당일 이미 매도 확정분 등)
        :return: 당일 종가 기준 평가 총자산
        """
        skip = exclude or set()
        total = cash
        for sym, pos in positions.items():
            if sym in skip:
                continue
            row = price_map.get((sym, d))
            price = float(row["close_price"]) if row else pos["buy_price"]
            total += pos["shares"] * price
        return total

    def _simulate_trading(
        self, combo_id: int, dfs: List[pd.DataFrame], strat_keys: List[str],
        initial_capital: float, max_slots: int, start_date: str, end_date: str
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """D-1 신호 포착 ➔ D-0 종가 체결 시뮬레이션을 딕셔너리 고속 룩업으로 연산합니다."""
        dates = sorted(dfs[0]["date"].unique())
        sim_dates = [d for d in dates if start_date <= d <= end_date]
        if not sim_dates:
            return self._empty_metrics(initial_capital), [], []

        # 고속 룩업용 딕셔너리: 전략별 캐시 재사용으로 combo 간 중복 빌드 제거
        dict_maps = [self._get_dict_map(k, df) for k, df in zip(strat_keys, dfs)]

        all_symbols = sorted(dfs[0]["symbol"].unique())
        cash = initial_capital
        positions = {}  # symbol -> {shares, buy_price, buy_date, prob_up, name, holding_days, slot_no}
        logs = []
        equity_curve = []
        equity_logs = []
        closed_trades = []

        # 슬롯 추적: 포트폴리오 자리 번호(1~max_slots)를 종목 매수/매도 쌍에 할당
        available_slots = set(range(1, max_slots + 1))  # {1, 2, 3}
        symbol_to_slot = {}  # symbol -> slot_no

        date_to_idx = {d: i for i, d in enumerate(dates)}
        portfolio_snapshots = {}
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

                        # 체결 직후 자산: 현금 + 남은 보유종목을 당일 종가로 평가 (매도 확정분 제외)
                        curr_equity = self._portfolio_equity(
                            cash, positions, dict_maps[0], d, exclude=set(symbols_to_sell) | {sym}
                        )
                        cum_ret = (curr_equity - initial_capital) / initial_capital * 100.0

                        # 슬롯 번호 조회 후 반환
                        sold_slot = symbol_to_slot.pop(sym, 0)
                        available_slots.add(sold_slot)

                        logs.append({
                            "combo_id": combo_id, "trade_date": d, "symbol": sym, "name": pos["name"],
                            "trade_type": "SELL", "holding_days": pos["holding_days"], "shares": pos["shares"],
                            "unit_price": sell_price, "total_amount": revenue, "equity_after_trade": curr_equity,
                            "cum_return_pct": round(cum_ret, 2), "profit_pct": round(profit_pct, 2),
                            "profit_krw": round(profit_krw, 0), "prob_up": pos["prob_up"],
                            "strategy_tag": "SELL", "slot_no": sold_slot
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

                                # 슬롯 배정: 사용 가능한 슬롯 중 가장 작은 번호 부여
                                new_slot = min(available_slots) if available_slots else 0
                                available_slots.discard(new_slot)
                                symbol_to_slot[b_item["symbol"]] = new_slot

                                positions[b_item["symbol"]] = {
                                    "shares": shares, "buy_price": buy_price, "buy_date": d,
                                    "prob_up": b_item["prob_up"], "name": b_item["name"],
                                    "holding_days": 0, "slot_no": new_slot
                                }
                                # 체결 직후 자산: 현금 + 전 보유종목(신규 포함)을 당일 종가로 평가
                                curr_eq_after = self._portfolio_equity(cash, positions, dict_maps[0], d)
                                cum_ret_b = (curr_eq_after - initial_capital) / initial_capital * 100.0
                                logs.append({
                                    "combo_id": combo_id, "trade_date": d, "symbol": b_item["symbol"],
                                    "name": b_item["name"], "trade_type": "BUY", "holding_days": 0,
                                    "shares": shares, "unit_price": buy_price, "total_amount": cost,
                                    "equity_after_trade": curr_eq_after, "cum_return_pct": round(cum_ret_b, 2),
                                    "profit_pct": 0.0, "profit_krw": 0.0, "prob_up": b_item["prob_up"],
                                    "strategy_tag": "BUY", "slot_no": new_slot
                                })

            portfolio_snapshots[d] = {
                "cash": cash,
                "holdings": {sym: pos["shares"] for sym, pos in positions.items()}
            }

        # Phase 2: 일별 자산 계산 (market_indices_daily 기준)
        from backend.app.models.market_indices_daily import MarketIndicesDaily
        market_dates = [
            r.date for r in self.session.query(MarketIndicesDaily.date)
            .filter(MarketIndicesDaily.date >= start_date, MarketIndicesDaily.date <= end_date)
            .order_by(MarketIndicesDaily.date.asc()).all()
        ]
        
        current_cash = initial_capital
        current_holdings = {}
        last_close_prices = {}
        
        # 만약 market_dates가 비어있다면, sim_dates라도 사용
        calc_dates = market_dates if market_dates else sim_dates

        for md in calc_dates:
            if md in portfolio_snapshots:
                current_cash = portfolio_snapshots[md]["cash"]
                current_holdings = portfolio_snapshots[md]["holdings"]
            
            day_equity = current_cash
            for sym, shares in current_holdings.items():
                price = float(dict_maps[0].get((sym, md), {}).get("close_price", 0.0))
                if price > 0:
                    last_close_prices[sym] = price
                else:
                    price = last_close_prices.get(sym, 0.0)
                day_equity += shares * price
            
            equity_curve.append(day_equity)
            equity_logs.append({
                "combo_id": combo_id,
                "trade_date": md,
                "equity_amount": day_equity
            })
        final_cap = equity_curve[-1] if equity_curve else initial_capital
        tot_ret = (final_cap - initial_capital) / initial_capital * 100.0
        win_rate = (len([t for t in closed_trades if t > 0]) / len(closed_trades) * 100.0) if closed_trades else 0.0
        mdd = self._calc_mdd(equity_curve)

        metrics = {
            "final_capital": round(final_cap, 0), "total_return_pct": round(tot_ret, 2),
            "win_rate_pct": round(win_rate, 2), "mdd_pct": round(mdd, 2), "total_trades": len(logs)
        }
        return metrics, logs, equity_logs

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
