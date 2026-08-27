"""
백테스트 리더보드/차트/매매일지 렌더 payload 조립 서비스 모듈.

`/api/backtest-leaderboard` 응답(JSON dict)을 DB로부터 1회 조립하는 BacktestLeaderboardBuilder
클래스를 정의합니다. 라우트는 이 결과를 파일 캐시에 저장해 두고 매 요청마다 재사용합니다.
"""

import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from backend.app.models.market_indices_daily import MarketIndicesDaily
from backend.app.models.strategy_leaderboard import StrategyLeaderboard
from backend.app.models.strategy_daily_equity import StrategyDailyEquity
from backend.app.models.strategy_trade_logs import StrategyTradeLogs
from backend.app.repositories.strategy_leaderboard_repository import StrategyLeaderboardRepository
from backend.app.repositories.strategy_daily_equity_repository import StrategyDailyEquityRepository

logger = logging.getLogger(__name__)

PERIOD_LIMITS = {"6m": 125, "1y": 250, "3y": 750, "5y": 1250, "all": 5000}
INITIAL_CAPITAL = 10000000.0


class BacktestLeaderboardBuilder:
    """백테스트 리더보드 화면 payload를 DB에서 조립하는 서비스 클래스."""

    def __init__(self, session: Session) -> None:
        """BacktestLeaderboardBuilder 초기화.

        :param session: SQLAlchemy DB 세션 객체
        """
        self.session = session

    def build(
        self, period: str, custom_start: str, custom_end: str, has_period_param: bool
    ) -> Dict[str, Any]:
        """리더보드/차트/매매일지 전체 payload를 조립해 반환합니다.

        :param period: 요청 기간 키(6m/1y/3y/5y/all/custom)
        :param custom_start: custom 기간 시작일(YYYY-MM-DD, 없으면 "")
        :param custom_end: custom 기간 종료일(YYYY-MM-DD, 없으면 "")
        :param has_period_param: 요청에 period 파라미터가 명시됐는지 여부
        :return: status/period/leaderboard/trade_logs/chart_trade_events/chart_data 딕셔너리
        """
        period = self._infer_period(period, has_period_param)
        kospi_chart_data = self._build_kospi_chart(period, custom_start, custom_end)
        full_combos = self._build_combos()
        trade_logs_map, chart_trade_events = self._build_trade_logs(full_combos)
        self._assemble_assets(kospi_chart_data, full_combos)

        return {
            "status": "success",
            "period": period,
            "leaderboard": full_combos,
            "trade_logs": trade_logs_map,
            "chart_trade_events": chart_trade_events,
            "chart_data": kospi_chart_data,
        }

    def _infer_period(self, period: str, has_period_param: bool) -> str:
        """period 파라미터가 없으면 DB에 저장된 연산 일수로 기간 키를 역추론합니다."""
        if has_period_param or self.session.query(StrategyLeaderboard).count() == 0:
            return period
        days = self.session.query(StrategyDailyEquity.trade_date).distinct().count()
        if days <= 0:
            return period
        for key, limit in (("6m", 150), ("1y", 300), ("3y", 800), ("5y", 1500)):
            if days <= limit:
                return key
        return "all"

    def _build_kospi_chart(self, period: str, custom_start: str, custom_end: str) -> List[Dict[str, Any]]:
        """KOSPI 종가 및 20일 이동평균을 연산하고 요청 기간만큼 잘라 반환합니다."""
        records = self.session.query(MarketIndicesDaily).order_by(MarketIndicesDaily.date.asc()).all()
        valid = [r for r in records if r.kospi_close is not None]
        if not valid:
            return []
        closes = [r.kospi_close for r in valid]
        dates = [r.date for r in valid]
        ma20 = [None] * len(closes)
        for i in range(19, len(closes)):
            ma20[i] = round(sum(closes[i - 19:i + 1]) / 20.0, 2)

        if period == "custom" and custom_start and custom_end:
            s_fmt, e_fmt = custom_start.replace("-", ""), custom_end.replace("-", "")
            idx = [i for i, d in enumerate(dates) if s_fmt <= d <= e_fmt]
            sel = idx if idx else list(range(max(0, len(dates) - 750), len(dates)))
        else:
            limit = PERIOD_LIMITS.get(period, 750)
            sel = list(range(max(0, len(dates) - limit), len(dates)))

        chart = []
        for i in sel:
            d_str = dates[i]
            if len(d_str) == 8:
                d_str = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            chart.append({"date": d_str, "kospi_close": closes[i], "kospi_ma20": ma20[i]})
        return chart

    def _build_combos(self) -> List[Dict[str, Any]]:
        """전략 리더보드 엔트리를 누적 수익률 내림차순으로 조립합니다."""
        entries = StrategyLeaderboardRepository(self.session).get_all_ordered_by_return() or []
        combos = []
        for idx, e in enumerate(entries):
            strategy = e.combo_name.split(" ")[0] if " " in e.combo_name else e.combo_name
            combos.append({
                "rank": idx + 1, "combo_id": e.combo_id, "strategy": strategy,
                "name": e.combo_name, "eval_amount": int(e.final_capital),
                "return_rate": round(e.total_return_pct, 2), "win_rate": round(e.win_rate_pct, 2),
                "mdd": round(e.mdd_pct, 2), "trade_count": e.total_trades,
            })
        return combos

    def _build_trade_logs(
        self, full_combos: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, List], Dict[str, List]]:
        """전략별 매매일지 및 차트 매수/매도 마커 이벤트 맵을 조립합니다."""
        logs = self.session.query(StrategyTradeLogs).order_by(StrategyTradeLogs.trade_date.asc()).all()
        combo_to_strat = {c["combo_id"]: c["strategy"] for c in full_combos}
        trade_logs_map: Dict[str, List] = {}
        chart_trade_events: Dict[str, List] = {}

        for log in logs:
            key = combo_to_strat.get(log.combo_id)
            if not key:
                continue
            trade_logs_map.setdefault(key, [])
            chart_trade_events.setdefault(key, [])
            d_str = log.trade_date
            if len(d_str) == 8:
                d_str = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            trade_logs_map[key].append(self._format_trade_row(log, d_str))
            chart_trade_events[key].append({
                "date": d_str, "trade_type": log.trade_type, "slot_no": log.slot_no or 0,
                "name": log.name, "symbol": log.symbol,
            })
        return trade_logs_map, chart_trade_events

    def _format_trade_row(self, log: StrategyTradeLogs, d_str: str) -> Dict[str, Any]:
        """단일 체결 로그를 매매일지 테이블 행 형식으로 변환합니다."""
        sign = "+" if log.cum_return_pct >= 0 else ""
        pnl = "-"
        if log.trade_type == "SELL":
            k_sign = "+" if log.profit_krw > 0 else ""
            p_sign = "+" if log.profit_pct >= 0 else ""
            pnl = f"{k_sign}{int(log.profit_krw):,}원 ({p_sign}{log.profit_pct}%)"
        return {
            "date": d_str, "name": log.name, "code": log.symbol,
            "type": f"{'매수' if log.trade_type == 'BUY' else '매도'}{log.strategy_tag}",
            "days": f"{log.holding_days}일", "quantity": log.shares,
            "price": int(log.unit_price), "total": int(log.total_amount),
            "cum_asset": f"{int(log.equity_after_trade):,}원 ({sign}{log.cum_return_pct}%)",
            "equity_raw": int(log.equity_after_trade), "slot_no": log.slot_no or 0, "pnl": pnl,
        }

    def _assemble_assets(
        self, kospi_chart_data: List[Dict[str, Any]], full_combos: List[Dict[str, Any]]
    ) -> None:
        """차트 일자 격자에 전략별 일별 평가자산을 forward-fill 방식으로 채웁니다."""
        equity_repo = StrategyDailyEquityRepository(self.session)
        equity_maps = {
            c["combo_id"]: {r.trade_date: r.equity_amount for r in equity_repo.get_equity_by_combo(c["combo_id"])}
            for c in full_combos
        }
        last_equity = {c["combo_id"]: INITIAL_CAPITAL for c in full_combos}
        for row in kospi_chart_data:
            db_date = row["date"].replace("-", "")
            asset_map = {}
            for c in full_combos:
                cid = c["combo_id"]
                if db_date in equity_maps[cid]:
                    last_equity[cid] = equity_maps[cid][db_date]
                asset_map[c["strategy"]] = round(last_equity[cid], 0)
            row["strategy_assets"] = asset_map
